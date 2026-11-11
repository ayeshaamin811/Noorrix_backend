from unittest.mock import patch

import pytest

from apps.sell_my_car.models import SellMyCarEnquiry, SellMyCarImage

from .helpers import DVLA_VEHICLE, dvla_response, email_to, image_file, submit

OWNER = "owner@noorrix.test"
CUSTOMER = "alex@example.com"


@pytest.mark.django_db
class TestOwnerEmail:
    def test_has_reply_to_and_every_detail(self, api_client, dvla_ready, resend_send):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        submit(api_client)
        email = email_to(resend_send, OWNER)
        assert email["from"] == "Noorrix Motors <noreply@noorrix.test>"
        assert email["reply_to"] == [CUSTOMER]
        assert email["subject"] == "[Sell My Car] AB12CDE CITROEN"
        for value in (
            "AB12CDE", "CITROEN", "10,220 miles", "Alex Smith",
            CUSTOMER, "+447701910159", "1 High Street, Bedford MK40 1AA", "Full service history.",
            "Tuesday 3 November 2026 at 12:00 (UK time)",
        ):
            assert value in email["html"]
        for removed in (">Year<", ">Colour<", ">Fuel<", "2009", "SILVER", "DIESEL"):
            assert removed not in email["html"]

    def test_model_shows_not_available(self, api_client, dvla_ready, resend_send):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        submit(api_client)
        assert ">Model</td>" in email_to(resend_send, OWNER)["html"]
        assert email_to(resend_send, OWNER)["html"].count("Not available") == 1

    def test_photos_are_thumbnails_linking_to_full_images(self, api_client, resend_send):
        submit(api_client, images=[image_file(), image_file()])
        email = email_to(resend_send, OWNER)
        for image in SellMyCarImage.objects.all():
            url = f"http://testserver{image.image.url}"
            assert f'<a href="{url}"' in email["html"]
            assert f'<img src="{url}"' in email["html"]
        assert "attachments" not in email

    def test_is_skipped_with_a_warning_when_admin_email_is_empty(self, api_client, resend_send, settings):
        settings.ADMIN_EMAIL = ""
        with patch("apps.sell_my_car.emails.logger") as logger:
            assert submit(api_client).status_code == 201
        logger.warning.assert_called_once()
        assert [call.args[0]["to"] for call in resend_send.call_args_list] == [[CUSTOMER]]


@pytest.mark.django_db
class TestCustomerEmail:
    def test_content_when_the_car_is_known(self, api_client, dvla_ready, resend_send):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        submit(api_client)
        email = email_to(resend_send, CUSTOMER)
        for value in ("AB12CDE", "CITROEN", "10,220 miles", "Tuesday 3 November 2026 at 12:00 (UK time)"):
            assert value in email["html"]
        assert "review" in email["html"]
        assert "offer" in email["html"]
        assert "reply_to" not in email

    def test_leaves_out_the_car_when_unknown(self, api_client, resend_send):
        submit(api_client)
        assert ">Car<" not in email_to(resend_send, CUSTOMER)["html"]

    def test_does_not_mention_a_price(self, api_client, resend_send):
        submit(api_client)
        html = email_to(resend_send, CUSTOMER)["html"].lower()
        assert "£" not in html
        assert "price" not in html
        assert "valuation" not in html


@pytest.mark.django_db
class TestEmailSafety:
    MARKUP = '<script>alert("x")</script>'

    def test_customer_values_are_escaped_in_both_emails(self, api_client, resend_send):
        submit(api_client, name=self.MARKUP, address=self.MARKUP, message=self.MARKUP)
        owner_html = email_to(resend_send, OWNER)["html"]
        customer_html = email_to(resend_send, CUSTOMER)["html"]
        assert "<script" not in owner_html
        assert "<script" not in customer_html
        assert "&lt;script&gt;" in owner_html
        assert "&lt;script&gt;" in customer_html

    def test_dvla_values_are_escaped(self, api_client, dvla_ready, resend_send):
        dvla_ready.return_value = dvla_response(200, {"make": "<b>FORD</b>"})
        submit(api_client)
        assert "<b>FORD" not in email_to(resend_send, OWNER)["html"]
        assert "<b>FORD" not in email_to(resend_send, CUSTOMER)["html"]

    def test_format_braces_in_customer_values_are_harmless(self, api_client, resend_send):
        assert submit(api_client, name="{title} {0}", message="{rows}").status_code == 201
        assert "{title} {0}" in email_to(resend_send, CUSTOMER)["html"]


@pytest.mark.django_db
class TestDelivery:
    def test_runs_in_a_daemon_thread(self, api_client, email_thread):
        submit(api_client)
        email_thread.assert_called_once()
        assert email_thread.call_args.kwargs["daemon"] is True

    def test_failed_email_does_not_fail_the_request(self, api_client, resend_send):
        resend_send.side_effect = RuntimeError("resend down")
        assert submit(api_client).status_code == 201
        assert SellMyCarEnquiry.objects.count() == 1

    def test_owner_failure_does_not_stop_the_customer_email(self, api_client, resend_send):
        resend_send.side_effect = [RuntimeError("resend down"), {"id": "1"}]
        submit(api_client)
        assert [call.args[0]["to"] for call in resend_send.call_args_list] == [[OWNER], [CUSTOMER]]
