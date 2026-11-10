import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import ANY, patch

import pytest
import requests
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.sell_my_car.models import SellMyCarEnquiry, SellMyCarImage

from .helpers import (
    SUBMIT_URL,
    VEHICLE_WITH_MOT_TESTS,
    dvsa_error,
    dvsa_response,
    image_file,
    submit,
)

MB = 1024 * 1024
PHONE_ERROR = "Please enter a valid UK phone number."


def stored_files(settings):
    return [path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()]


def assert_field_error(response, field):
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert list(body["errors"]) == [field]
    assert all(isinstance(message, str) for message in body["errors"][field])
    return body["errors"][field]


@pytest.mark.django_db
class TestSuccess:
    def test_without_images(self, api_client):
        response = submit(api_client)
        assert response.status_code == 201
        enquiry = SellMyCarEnquiry.objects.get()
        assert response.json() == {"success": True, "id": enquiry.id, "message": ANY}
        assert enquiry.reg == "AB12CDE"
        assert enquiry.mileage == 10220
        assert enquiry.name == "Alex Smith"
        assert enquiry.email == "alex@example.com"
        assert enquiry.phone == "+447701910159"
        assert enquiry.address == "1 High Street, Bedford MK40 1AA"
        assert enquiry.message == "Full service history."
        assert enquiry.appointment_date == date(2026, 11, 3)
        assert enquiry.appointment_time == time(12, 0)
        assert enquiry.status == SellMyCarEnquiry.Status.NEW
        assert enquiry.images.count() == 0

    def test_message_is_optional(self, api_client):
        assert submit(api_client, message=None).status_code == 201
        assert SellMyCarEnquiry.objects.get().message == ""

    def test_name_and_address_are_trimmed(self, api_client):
        assert submit(api_client, name="  Alex  ", address="  1 High St  ").status_code == 201
        enquiry = SellMyCarEnquiry.objects.get()
        assert enquiry.name == "Alex"
        assert enquiry.address == "1 High St"

    def test_with_images(self, api_client, settings):
        response = submit(api_client, images=[image_file(), image_file("two.png", "PNG", "image/png")])
        assert response.status_code == 201
        enquiry = SellMyCarEnquiry.objects.get()
        assert enquiry.images.count() == 2
        assert len(stored_files(settings)) == 2

    def test_ten_images_are_allowed(self, api_client):
        assert submit(api_client, images=[image_file() for _ in range(10)]).status_code == 201
        assert SellMyCarImage.objects.count() == 10

    @pytest.mark.parametrize(
        "image_format, extension",
        [("PNG", ".png"), ("JPEG", ".jpg"), ("GIF", ".gif"), ("WEBP", ".webp")],
    )
    def test_each_allowed_format(self, api_client, image_format, extension):
        response = submit(api_client, images=[image_file("photo", image_format, "application/octet-stream")])
        assert response.status_code == 201
        assert SellMyCarImage.objects.get().image.name.endswith(extension)

    def test_file_name_is_random_and_ignores_the_browser_name(self, api_client):
        response = submit(api_client, images=[image_file("../../evil.php", "PNG", "text/x-php")])
        assert response.status_code == 201
        name = SellMyCarImage.objects.get().image.name
        assert re.fullmatch(r"sell_my_car/[0-9a-f]{32}\.png", name)

    def test_saved_file_is_the_complete_image(self, api_client):
        upload = image_file()
        original = upload.read()
        upload.seek(0)
        submit(api_client, images=[upload])
        with SellMyCarImage.objects.get().image.open("rb") as stored:
            assert stored.read() == original

    def test_file_of_exactly_10mb_is_allowed(self, api_client):
        assert submit(api_client, images=[image_file(pad_to=10 * MB)]).status_code == 201


@pytest.mark.django_db
class TestDvsaDuringSubmit:
    def test_saves_vehicle_details(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        assert submit(api_client).status_code == 201
        enquiry = SellMyCarEnquiry.objects.get()
        assert enquiry.make == "CITROEN"
        assert enquiry.model == "C3"
        assert enquiry.year == 2009
        assert enquiry.colour == "SILVER"
        assert enquiry.fuel_type == "DIESEL"

    def assert_saved_blank(self):
        enquiry = SellMyCarEnquiry.objects.get()
        assert (enquiry.make, enquiry.model, enquiry.colour, enquiry.fuel_type) == ("", "", "", "")
        assert enquiry.year is None

    def test_missing_credentials_still_saves(self, api_client, dvsa_http):
        assert submit(api_client).status_code == 201
        self.assert_saved_blank()
        dvsa_http.get.assert_not_called()

    def test_dvsa_down_still_saves(self, api_client, dvsa_ready):
        dvsa_ready.get.side_effect = requests.ConnectionError()
        assert submit(api_client).status_code == 201
        self.assert_saved_blank()

    @pytest.mark.parametrize("code", ["MOTH-NF-01", "MOTH-IV-03", "MOTH-RL-01"])
    def test_dvsa_error_codes_still_save(self, api_client, dvsa_ready, code):
        dvsa_ready.get.return_value = dvsa_error(code)
        assert submit(api_client).status_code == 201
        self.assert_saved_blank()

    def test_unexpected_lookup_crash_still_saves(self, api_client):
        with patch("apps.sell_my_car.views.dvsa.lookup_vehicle", side_effect=RuntimeError("boom")):
            assert submit(api_client).status_code == 201
        self.assert_saved_blank()

    def test_oversized_dvsa_values_cannot_block_the_customer(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, {"make": "X" * 500, "primaryColour": "Y" * 500})
        assert submit(api_client).status_code == 201
        enquiry = SellMyCarEnquiry.objects.get()
        assert len(enquiry.make) == 100
        assert len(enquiry.colour) == 50

    def test_uses_the_lookup_cache(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        api_client.get("/api/sell-my-car/lookup/", {"reg": "AB12CDE", "mileage": "10220"})
        submit(api_client)
        assert dvsa_ready.get.call_count == 1


@pytest.mark.django_db
class TestPhoneRule:
    @pytest.mark.parametrize(
        "phone",
        [
            "+447701910159",  # UK mobile
            "+447624123456",  # Isle of Man mobile
            "+441234567890",  # 01 geographic, 10 digits
            "+44123456789",  # 01 geographic, 9 digits
            "+442079460958",  # 020 London
        ],
    )
    def test_uk_numbers_are_accepted(self, api_client, phone):
        assert submit(api_client, phone=phone).status_code == 201

    @pytest.mark.parametrize(
        "phone",
        [
            pytest.param("+923321234567", id="pakistan"),
            pytest.param("+14155552671", id="usa"),
            pytest.param("+443321234567", id="uk-03-same-shape-as-pakistani-mobile"),
            pytest.param("+448001234567", id="uk-08"),
            pytest.param("07701910159", id="no-country-code"),
            pytest.param("+44770191015", id="too-short"),
            pytest.param("+4477019101590", id="too-long"),
            pytest.param("+447601234567", id="pager-range"),
            pytest.param("+44770191015٩", id="non-ascii-digit"),
            pytest.param("not a number", id="text"),
            pytest.param("", id="blank"),
            pytest.param(None, id="missing"),
        ],
    )
    def test_other_numbers_get_the_exact_message(self, api_client, phone):
        assert assert_field_error(submit(api_client, phone=phone), "phone") == [PHONE_ERROR]
        assert not SellMyCarEnquiry.objects.exists()


@pytest.mark.django_db
class TestSlotRules:
    @pytest.mark.parametrize(
        "appointment_date, appointment_time",
        [
            ("2026-11-02", "11:30"),  # later today
            ("2026-11-08", "12:00"),  # today + 6
            ("2026-11-03", "09:00"),  # first slot
            ("2026-11-03", "17:30"),  # last slot
        ],
    )
    def test_valid_slots(self, api_client, appointment_date, appointment_time):
        response = submit(api_client, appointment_date=appointment_date, appointment_time=appointment_time)
        assert response.status_code == 201

    @pytest.mark.parametrize(
        "appointment_date",
        ["2026-11-01", "2026-11-09", "03/11/2026", "soon", "", None],
    )
    def test_invalid_dates(self, api_client, appointment_date):
        assert_field_error(submit(api_client, appointment_date=appointment_date), "appointment_date")

    @pytest.mark.parametrize(
        "appointment_time",
        ["08:30", "18:00", "12:15", "12:00:00", "noon", "", None],
    )
    def test_invalid_times(self, api_client, appointment_time):
        assert_field_error(submit(api_client, appointment_time=appointment_time), "appointment_time")

    @pytest.mark.parametrize("appointment_time", ["09:00", "11:00"])
    def test_slot_already_started_today(self, api_client, appointment_time):
        response = submit(api_client, appointment_date="2026-11-02", appointment_time=appointment_time)
        assert_field_error(response, "appointment_time")

    def test_slot_starting_exactly_now_has_started(self, api_client, frozen_time):
        frozen_time.return_value = datetime(2026, 11, 2, 11, 30, tzinfo=timezone.utc)
        response = submit(api_client, appointment_date="2026-11-02", appointment_time="11:30")
        assert_field_error(response, "appointment_time")

    def test_started_check_uses_uk_summer_time(self, api_client, frozen_time):
        # 08:30 UTC is 09:30 in the UK during British Summer Time.
        frozen_time.return_value = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc)
        response = submit(api_client, appointment_date="2026-07-01", appointment_time="09:30")
        assert_field_error(response, "appointment_time")
        assert submit(api_client, appointment_date="2026-07-01", appointment_time="10:00").status_code == 201

    def test_today_uses_the_uk_date(self, api_client, frozen_time):
        # 23:30 UTC on 1 July is already 2 July in the UK.
        frozen_time.return_value = datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)
        response = submit(api_client, appointment_date="2026-07-01", appointment_time="12:00")
        assert_field_error(response, "appointment_date")
        assert submit(api_client, appointment_date="2026-07-08", appointment_time="12:00").status_code == 201


@pytest.mark.django_db
class TestSlotClash:
    def test_taken_slot_is_409(self, api_client, make_enquiry):
        make_enquiry()
        response = submit(api_client)
        assert response.status_code == 409
        assert response.json() == {"error": "This time slot has just been booked. Please pick another."}
        assert SellMyCarEnquiry.objects.count() == 1

    def test_clash_writes_no_files_and_sends_no_email(self, api_client, make_enquiry, settings, resend_send):
        make_enquiry()
        response = submit(api_client, images=[image_file(), image_file()])
        assert response.status_code == 409
        assert stored_files(settings) == []
        assert SellMyCarImage.objects.count() == 0
        resend_send.assert_not_called()

    @pytest.mark.parametrize("status", ["new", "in_progress", "completed"])
    def test_active_statuses_hold_the_slot(self, api_client, make_enquiry, status):
        make_enquiry(status=status)
        assert submit(api_client).status_code == 409

    def test_cancelled_slot_can_be_booked_again(self, api_client, make_enquiry):
        make_enquiry(status=SellMyCarEnquiry.Status.CANCELLED)
        assert submit(api_client).status_code == 201
        assert SellMyCarEnquiry.objects.count() == 2

    def test_same_time_on_another_day_is_free(self, api_client, make_enquiry):
        make_enquiry(appointment_date=date(2026, 11, 4))
        assert submit(api_client).status_code == 201

    def test_failed_image_save_leaves_nothing_behind(self, api_client, settings):
        real_create = SellMyCarImage.objects.create
        calls = []

        def fail_on_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise OSError("storage down")
            return real_create(**kwargs)

        api_client.raise_request_exception = False
        with patch.object(SellMyCarImage.objects, "create", side_effect=fail_on_second):
            response = submit(api_client, images=[image_file(), image_file()])
        assert response.status_code == 500
        assert not SellMyCarEnquiry.objects.exists()
        assert stored_files(settings) == []


@pytest.mark.django_db
class TestFieldValidation:
    @pytest.mark.parametrize(
        "field, value",
        [
            ("reg", "ab12cde"),
            ("reg", "AB12 CDE"),
            ("reg", "AB12CDEF"),
            ("reg", "A"),
            ("reg", None),
            ("mileage", "0"),
            ("mileage", "10000000"),
            ("mileage", "12.5"),
            ("mileage", "lots"),
            ("mileage", None),
            ("name", "A"),
            ("name", "   A   "),
            ("name", "x" * 151),
            ("name", None),
            ("email", "not-an-email"),
            ("email", None),
            ("address", "abcd"),
            ("address", "x" * 301),
            ("address", None),
            ("message", "x" * 2001),
        ],
    )
    def test_invalid_field_uses_its_exact_key(self, api_client, field, value):
        assert_field_error(submit(api_client, **{field: value}), field)
        assert not SellMyCarEnquiry.objects.exists()

    @pytest.mark.parametrize(
        "field, value",
        [("name", "Al"), ("name", "x" * 150), ("address", "1 Hi."), ("address", "x" * 300), ("message", "x" * 2000)],
    )
    def test_length_limits_are_allowed(self, api_client, field, value):
        assert submit(api_client, **{field: value}).status_code == 201

    def test_every_error_is_a_flat_list_of_strings(self, api_client):
        response = api_client.post(SUBMIT_URL, {"images": ["not-a-file"]}, format="multipart")
        assert response.status_code == 400
        errors = response.json()["errors"]
        assert {"reg", "mileage", "name", "email", "phone", "address", "appointment_date", "appointment_time", "images"} == set(errors)
        for messages in errors.values():
            assert isinstance(messages, list)
            assert all(isinstance(message, str) for message in messages)


@pytest.mark.django_db
class TestImageValidation:
    def assert_images_error(self, response, message):
        assert response.status_code == 400
        assert response.json() == {"success": False, "errors": {"images": [message]}}
        assert not SellMyCarEnquiry.objects.exists()

    BAD_FORMAT = "Photos must be PNG, JPEG, GIF or WEBP images."

    def test_non_image_with_an_image_name_and_type(self, api_client):
        fake = SimpleUploadedFile("car.jpg", b"this is not an image", content_type="image/jpeg")
        self.assert_images_error(submit(api_client, images=[fake]), self.BAD_FORMAT)

    def test_empty_file(self, api_client):
        empty = SimpleUploadedFile("car.jpg", b"", content_type="image/jpeg")
        response = submit(api_client, images=[empty])
        assert response.status_code == 400
        assert list(response.json()["errors"]) == ["images"]
        assert isinstance(response.json()["errors"]["images"][0], str)

    def test_real_image_in_a_format_that_is_not_allowed(self, api_client):
        bmp = image_file("car.jpg", "BMP", "image/jpeg")
        self.assert_images_error(submit(api_client, images=[bmp]), self.BAD_FORMAT)

    def test_svg_is_rejected(self, api_client):
        svg = SimpleUploadedFile(
            "car.png",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type="image/png",
        )
        self.assert_images_error(submit(api_client, images=[svg]), self.BAD_FORMAT)

    def test_text_value_instead_of_a_file(self, api_client):
        self.assert_images_error(submit(api_client, images=["not-a-file"]), self.BAD_FORMAT)

    def test_one_bad_file_among_good_ones_is_still_flat(self, api_client):
        fake = SimpleUploadedFile("car.jpg", b"nope", content_type="image/jpeg")
        response = submit(api_client, images=[image_file(), fake, image_file()])
        self.assert_images_error(response, self.BAD_FORMAT)

    def test_eleven_files(self, api_client):
        response = submit(api_client, images=[image_file() for _ in range(11)])
        self.assert_images_error(response, "You can upload up to 10 photos.")

    def test_file_over_10mb(self, api_client):
        response = submit(api_client, images=[image_file(pad_to=10 * MB + 1)])
        self.assert_images_error(response, "Each photo must be 10MB or smaller.")


@pytest.mark.django_db
class TestSubmitRateLimit:
    def test_11th_request_in_an_hour_is_429_with_an_error_body(self, api_client):
        for _ in range(10):
            assert api_client.post(SUBMIT_URL, {}, format="multipart").status_code == 400
        response = api_client.post(SUBMIT_URL, {}, format="multipart")
        assert response.status_code == 429
        assert response.json() == {"error": "Too many requests. Please try again later."}
        assert "Retry-After" in response

    def test_limit_is_per_ip(self, api_client):
        for _ in range(10):
            api_client.post(SUBMIT_URL, {}, format="multipart", REMOTE_ADDR="10.0.0.1")
        blocked = api_client.post(SUBMIT_URL, {}, format="multipart", REMOTE_ADDR="10.0.0.1")
        other = api_client.post(SUBMIT_URL, {}, format="multipart", REMOTE_ADDR="10.0.0.2")
        assert blocked.status_code == 429
        assert other.status_code == 400
