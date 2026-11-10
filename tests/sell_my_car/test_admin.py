from datetime import time

import pytest
from django.core.files.storage import default_storage
from django.urls import reverse

from apps.sell_my_car.models import SellMyCarEnquiry, SellMyCarImage

from .helpers import image_file

LIST_URL = reverse("admin:sell_my_car_sellmycarenquiry_changelist")
CANCELLED = SellMyCarEnquiry.Status.CANCELLED


def change_url(enquiry):
    return reverse("admin:sell_my_car_sellmycarenquiry_change", args=[enquiry.pk])


def list_edit_data(enquiry, status):
    return {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "1",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "form-0-id": str(enquiry.pk),
        "form-0-status": status,
        "_save": "Save",
    }


def detail_edit_data(status):
    return {
        "status": status,
        "images-TOTAL_FORMS": "0",
        "images-INITIAL_FORMS": "0",
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "0",
    }


@pytest.fixture(autouse=True)
def plain_static_files(settings):
    """The production storage needs collectstatic, which tests don't run."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.mark.django_db
class TestEnquiryAdmin:
    def test_list_shows_the_columns(self, admin_client, make_enquiry):
        make_enquiry(make="CITROEN", model="C3")
        response = admin_client.get(LIST_URL)
        assert response.status_code == 200
        content = response.content.decode()
        for value in ("ZZ99ZZZ", "CITROEN C3", "Existing Customer", "+447701910159", "03/11/2026 12:00"):
            assert value in content

    @pytest.mark.parametrize("term, matches", [("ZZ99", 1), ("Existing", 1), ("existing@", 1), ("+4477", 1), ("nobody", 0)])
    def test_search(self, admin_client, make_enquiry, term, matches):
        make_enquiry()
        response = admin_client.get(LIST_URL, {"q": term})
        assert response.context["cl"].result_count == matches

    def test_status_filter(self, admin_client, make_enquiry):
        make_enquiry()
        response = admin_client.get(LIST_URL, {"status__exact": "completed"})
        assert response.context["cl"].result_count == 0

    def test_status_is_editable_from_the_list(self, admin_client, make_enquiry):
        enquiry = make_enquiry()
        response = admin_client.post(LIST_URL, list_edit_data(enquiry, "completed"))
        assert response.status_code == 302
        enquiry.refresh_from_db()
        assert enquiry.status == "completed"

    def test_only_status_is_editable_on_the_detail_page(self, admin_client, make_enquiry):
        enquiry = make_enquiry()
        response = admin_client.get(change_url(enquiry))
        assert response.status_code == 200
        assert list(response.context["adminform"].form.fields) == ["status"]

    def test_customer_fields_cannot_be_posted(self, admin_client, make_enquiry):
        enquiry = make_enquiry()
        data = {**detail_edit_data("in_progress"), "name": "Changed", "reg": "HACKED"}
        admin_client.post(change_url(enquiry), data)
        enquiry.refresh_from_db()
        assert enquiry.status == "in_progress"
        assert enquiry.name == "Existing Customer"
        assert enquiry.reg == "ZZ99ZZZ"

    def test_enquiries_cannot_be_added_by_hand(self, admin_client):
        assert admin_client.get(reverse("admin:sell_my_car_sellmycarenquiry_add")).status_code == 403

    def test_detail_page_shows_photo_thumbnails(self, admin_client, make_enquiry):
        enquiry = make_enquiry()
        image = SellMyCarImage.objects.create(enquiry=enquiry, image=image_file())
        content = admin_client.get(change_url(enquiry)).content.decode()
        assert f'<img src="{image.image.url}"' in content


@pytest.mark.django_db
class TestReactivatingACancelledEnquiry:
    def clash(self, make_enquiry):
        cancelled = make_enquiry(status=CANCELLED)
        make_enquiry(reg="AA11AAA")
        return cancelled

    def test_from_the_list_shows_an_error_instead_of_crashing(self, admin_client, make_enquiry):
        cancelled = self.clash(make_enquiry)
        response = admin_client.post(LIST_URL, list_edit_data(cancelled, "new"))
        assert response.status_code == 200
        assert b"Another enquiry has since booked" in response.content
        cancelled.refresh_from_db()
        assert cancelled.status == CANCELLED

    def test_from_the_detail_page_shows_an_error_instead_of_crashing(self, admin_client, make_enquiry):
        cancelled = self.clash(make_enquiry)
        response = admin_client.post(change_url(cancelled), detail_edit_data("new"))
        assert response.status_code == 200
        assert b"Another enquiry has since booked" in response.content
        cancelled.refresh_from_db()
        assert cancelled.status == CANCELLED

    def test_is_allowed_when_the_slot_is_still_free(self, admin_client, make_enquiry):
        cancelled = make_enquiry(status=CANCELLED, appointment_time=time(15, 0))
        admin_client.post(LIST_URL, list_edit_data(cancelled, "new"))
        cancelled.refresh_from_db()
        assert cancelled.status == "new"

    def test_an_active_enquiry_can_keep_its_own_slot(self, admin_client, make_enquiry):
        enquiry = make_enquiry()
        admin_client.post(LIST_URL, list_edit_data(enquiry, "in_progress"))
        enquiry.refresh_from_db()
        assert enquiry.status == "in_progress"


@pytest.mark.django_db
class TestDeletingPhotos:
    def test_deleting_an_enquiry_deletes_its_files(self, make_enquiry, django_capture_on_commit_callbacks):
        enquiry = make_enquiry()
        names = [
            SellMyCarImage.objects.create(enquiry=enquiry, image=image_file()).image.name
            for _ in range(2)
        ]
        assert all(default_storage.exists(name) for name in names)
        with django_capture_on_commit_callbacks(execute=True):
            enquiry.delete()
        assert not any(default_storage.exists(name) for name in names)
        assert SellMyCarImage.objects.count() == 0

    def test_admin_bulk_delete_deletes_the_files(self, admin_client, make_enquiry, django_capture_on_commit_callbacks):
        enquiry = make_enquiry()
        name = SellMyCarImage.objects.create(enquiry=enquiry, image=image_file()).image.name
        data = {"action": "delete_selected", "_selected_action": [str(enquiry.pk)], "post": "yes"}
        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(LIST_URL, data)
        assert response.status_code == 302
        assert not SellMyCarEnquiry.objects.exists()
        assert not default_storage.exists(name)

    def test_file_stays_until_the_delete_commits(self, make_enquiry, django_capture_on_commit_callbacks):
        enquiry = make_enquiry()
        name = SellMyCarImage.objects.create(enquiry=enquiry, image=image_file()).image.name
        with django_capture_on_commit_callbacks(execute=False):
            enquiry.delete()
        assert default_storage.exists(name)
