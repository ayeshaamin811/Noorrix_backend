"""Car admin: colour accepts any typed value, and colour and engine cc are optional."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.cars.admin import CarAdminForm
from apps.cars.models import Car

from .test_car_list import make_car

ADD_URL = reverse("admin:cars_car_add")


@pytest.fixture(autouse=True)
def plain_static_files(settings):
    """The production storage needs collectstatic, which tests don't run."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def image_upload():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "JPEG")
    return SimpleUploadedFile("car.jpg", buffer.getvalue(), content_type="image/jpeg")


def form_data(**overrides):
    data = {
        "title": "2015 Infiniti Q70", "subtitle": "2.2d Sport", "status": "available",
        "make": "Infiniti", "model": "Q70 Sport", "body_type": "Saloon", "fuel": "Diesel",
        "transmission": "Automatic", "colour": "Black", "year": "2015", "engine_cc": "2143",
        "doors": "5", "seats": "4", "mileage": "83686", "price": "9995",
        "history_check": "All passed", "deposit_amount": "200.00",
    }
    data.update(overrides)
    return data


def car_form(**overrides):
    return CarAdminForm(data=form_data(**overrides), files={"image": image_upload()})


@pytest.mark.django_db
class TestColour:
    def test_any_colour_can_be_typed(self):
        form = car_form(colour="Bronze")
        assert form.is_valid(), form.errors
        assert form.cleaned_data["colour"] == "Bronze"

    @pytest.mark.parametrize("typed", ["Black", "black", "  BLACK  "])
    def test_a_standard_colour_keeps_its_spelling(self, typed):
        form = car_form(colour=typed)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["colour"] == "Black"

    def test_a_colour_from_an_earlier_car_keeps_its_spelling(self):
        make_car(colour="Midnight Blue")
        form = car_form(colour="midnight   blue")
        assert form.is_valid(), form.errors
        assert form.cleaned_data["colour"] == "Midnight Blue"

    def test_colour_can_be_left_blank(self):
        form = car_form(colour="")
        assert form.is_valid(), form.errors
        assert form.cleaned_data["colour"] == ""

    def test_colour_over_20_characters_is_rejected(self):
        form = car_form(colour="A" * 21)
        assert not form.is_valid()
        assert "colour" in form.errors

    def test_add_page_suggests_standard_and_earlier_colours(self, admin_client):
        make_car(colour="Bronze")
        html = admin_client.get(ADD_URL).content.decode()
        assert 'list="id_colour_suggestions"' in html
        assert '<datalist id="id_colour_suggestions">' in html
        for colour in ("Black", "Silver", "Orange", "Bronze"):
            assert f'<option value="{colour}">' in html


@pytest.mark.django_db
class TestEngineCc:
    def test_engine_cc_can_be_left_blank(self):
        form = car_form(engine_cc="")
        assert form.is_valid(), form.errors
        assert form.cleaned_data["engine_cc"] is None

    def test_engine_cc_still_has_to_be_a_whole_number(self):
        form = car_form(engine_cc="2.2")
        assert not form.is_valid()
        assert "engine_cc" in form.errors


@pytest.mark.django_db
class TestSavingThroughAdmin:
    def test_car_with_a_typed_colour_and_no_engine_cc_is_saved(self, admin_client, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        data = {**form_data(colour="Bronze", engine_cc=""), "image": image_upload()}
        response = admin_client.post(ADD_URL, data)
        assert response.status_code == 302
        car = Car.objects.get()
        assert (car.colour, car.engine_cc) == ("Bronze", None)

    def test_car_with_no_colour_is_saved(self, admin_client, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        data = {**form_data(colour=""), "image": image_upload()}
        assert admin_client.post(ADD_URL, data).status_code == 302
        assert Car.objects.get().colour == ""


@pytest.mark.django_db
class TestApi:
    def test_list_returns_blank_colour_and_null_engine_cc(self, api_client):
        make_car(colour="", engine_cc=None)
        car = api_client.get(reverse("car-list")).data[0]
        assert (car["colour"], car["engine_cc"]) == ("", None)

    def test_filters_list_typed_colours_and_skip_blank_ones(self, api_client):
        make_car(colour="Bronze")
        make_car(colour="")
        make_car(colour="Black")
        assert api_client.get("/api/filters/").data["colours"] == ["Black", "Bronze"]

    def test_typed_colour_can_be_filtered(self, api_client):
        bronze = make_car(colour="Bronze")
        make_car(colour="Black")
        results = api_client.get(reverse("car-list"), {"colour": "Bronze"}).data
        assert [car["id"] for car in results] == [bronze.id]
