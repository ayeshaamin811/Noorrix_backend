"""DVSA and DVLA together: DVSA's details first, DVLA's when DVSA misses."""

import pytest
import requests

from apps.sell_my_car.models import SellMyCarEnquiry

from .helpers import (
    DVLA_VEHICLE,
    LOOKUP_URL,
    VEHICLE_WITH_MOT_TESTS,
    dvla_error,
    dvla_response,
    dvsa_error,
    dvsa_response,
    email_to,
    submit,
)

OWNER = "owner@noorrix.test"

FROM_DVSA = {"make": "CITROEN", "model": "C3", "year": 2009, "colour": "SILVER", "fuel_type": "DIESEL"}
FROM_DVLA = {**FROM_DVSA, "model": None}


def lookup(client, reg="AB12CDE"):
    return client.get(LOOKUP_URL, {"reg": reg, "mileage": "10220"})


class TestLookupWithBothApis:
    def test_dvsa_gives_make_and_model_and_dvla_is_not_called(self, api_client, dvla_ready, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == FROM_DVSA
        dvla_ready.assert_not_called()

    def test_dvsa_alone_is_enough(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        assert lookup(api_client).json() == FROM_DVSA

    @pytest.mark.parametrize(
        "dvsa_reply",
        [
            pytest.param(dvsa_error("MOTH-NF-01", 404), id="not-found"),
            pytest.param(dvsa_error("MOTH-IV-03", 400), id="invalid-reg"),
            pytest.param(dvsa_error("MOTH-RL-01", 429), id="rate-limited"),
            pytest.param(dvsa_response(500, {"message": "boom"}), id="server-error"),
            pytest.param(dvsa_response(200, {"registration": "AB12CDE"}), id="no-make-or-model"),
        ],
    )
    def test_dvsa_miss_falls_back_to_the_dvla_make(self, api_client, dvla_ready, dvsa_ready, dvsa_reply):
        dvsa_ready.get.return_value = dvsa_reply
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == FROM_DVLA

    def test_dvsa_down_falls_back_to_the_dvla_make(self, api_client, dvla_ready, dvsa_ready):
        dvsa_ready.get.side_effect = requests.Timeout()
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        assert lookup(api_client).json() == FROM_DVLA

    def test_rejected_dvsa_secret_falls_back_to_the_dvla_make(self, api_client, dvla_ready, dvsa_ready):
        dvsa_ready.post.return_value = dvsa_response(401, {"error": "invalid_client"})
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        assert lookup(api_client).json() == FROM_DVLA

    def test_neither_knowing_the_car_is_an_empty_object(self, api_client, dvla_ready, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_error("MOTH-NF-01", 404)
        dvla_ready.return_value = dvla_error(404, "Vehicle Not Found")
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {}

    def test_dvla_rejecting_the_reg_is_404(self, api_client, dvla_ready, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_error("MOTH-IV-03", 400)
        dvla_ready.return_value = dvla_error(400, "Bad Request")
        assert lookup(api_client).status_code == 404

    def test_dvsa_is_not_called_until_it_is_set_up(self, api_client, dvla_ready, dvsa_http):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        assert lookup(api_client).json() == FROM_DVLA
        dvsa_http.post.assert_not_called()
        dvsa_http.get.assert_not_called()


@pytest.mark.django_db
class TestSubmitWithBothApis:
    def test_saves_make_and_model_from_dvsa(self, api_client, dvla_ready, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        assert submit(api_client).status_code == 201
        enquiry = SellMyCarEnquiry.objects.get()
        assert (enquiry.make, enquiry.model) == ("CITROEN", "C3")

    def test_owner_email_shows_the_model(self, api_client, dvla_ready, dvsa_ready, resend_send):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        submit(api_client)
        email = email_to(resend_send, OWNER)
        assert email["subject"] == "[Sell My Car] AB12CDE CITROEN C3"
        assert "Not available" not in email["html"]
