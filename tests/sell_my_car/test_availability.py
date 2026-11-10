from datetime import date, time

import pytest

from apps.sell_my_car.models import SellMyCarEnquiry

from .helpers import AVAILABILITY_URL


@pytest.mark.django_db
class TestAvailability:
    def test_returns_booked_times_in_order(self, api_client, make_enquiry):
        make_enquiry(appointment_time=time(14, 30))
        make_enquiry(appointment_time=time(10, 0))
        response = api_client.get(AVAILABILITY_URL, {"date": "2026-11-03"})
        assert response.status_code == 200
        assert response.json() == {"date": "2026-11-03", "booked_times": ["10:00", "14:30"]}

    def test_no_bookings_is_an_empty_list(self, api_client):
        response = api_client.get(AVAILABILITY_URL, {"date": "2026-11-03"})
        assert response.json() == {"date": "2026-11-03", "booked_times": []}

    def test_only_covers_the_requested_date(self, api_client, make_enquiry):
        make_enquiry(appointment_date=date(2026, 11, 4))
        response = api_client.get(AVAILABILITY_URL, {"date": "2026-11-03"})
        assert response.json()["booked_times"] == []

    def test_leaves_out_cancelled_enquiries(self, api_client, make_enquiry):
        make_enquiry(appointment_time=time(10, 0), status=SellMyCarEnquiry.Status.CANCELLED)
        make_enquiry(appointment_time=time(11, 0))
        response = api_client.get(AVAILABILITY_URL, {"date": "2026-11-03"})
        assert response.json()["booked_times"] == ["11:00"]

    @pytest.mark.parametrize("status", ["new", "in_progress", "completed"])
    def test_other_statuses_keep_the_slot_booked(self, api_client, make_enquiry, status):
        make_enquiry(status=status)
        response = api_client.get(AVAILABILITY_URL, {"date": "2026-11-03"})
        assert response.json()["booked_times"] == ["12:00"]

    @pytest.mark.parametrize("params", [{}, {"date": ""}, {"date": "03/11/2026"}, {"date": "2026-13-40"}, {"date": "soon"}])
    def test_missing_or_malformed_date_is_400(self, api_client, params):
        response = api_client.get(AVAILABILITY_URL, params)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)
