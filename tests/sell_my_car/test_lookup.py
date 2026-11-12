from unittest.mock import patch

import pytest
import requests

from apps.sell_my_car import dvla

from .helpers import DVLA_VEHICLE, LOOKUP_URL, dvla_error, dvla_response, gateway_error


def lookup(client, reg="AB12CDE", mileage="10220", **extra):
    return client.get(LOOKUP_URL, {"reg": reg, "mileage": mileage}, **extra)


class TestVehicleMapping:
    def test_returns_make_year_colour_fuel_and_a_null_model(self, api_client, dvla_ready):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {
            "make": "CITROEN",
            "model": None,
            "year": 2009,
            "colour": "SILVER",
            "fuel_type": "DIESEL",
        }

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"make": "FORD"}, id="left-out"),
            pytest.param({"make": "FORD", "yearOfManufacture": None, "colour": None, "fuelType": None}, id="null"),
            pytest.param({"make": "FORD", "colour": "", "fuelType": ""}, id="blank"),
        ],
    )
    def test_missing_details_are_null(self, api_client, dvla_ready, body):
        dvla_ready.return_value = dvla_response(200, body)
        assert lookup(api_client).json() == {
            "make": "FORD",
            "model": None,
            "year": None,
            "colour": None,
            "fuel_type": None,
        }

    @pytest.mark.parametrize("body", [{"registrationNumber": "AB12CDE"}, {"make": ""}, {"make": None}])
    def test_vehicle_without_a_make_is_an_empty_object(self, api_client, dvla_ready, body):
        dvla_ready.return_value = dvla_response(200, body)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {}


class TestDvlaRequest:
    def test_url_body_headers_and_timeout(self, api_client, dvla_ready):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        lookup(api_client)
        args, kwargs = dvla_ready.call_args
        assert args == ("https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles",)
        assert kwargs["json"] == {"registrationNumber": "AB12CDE"}
        assert kwargs["headers"] == {"x-api-key": "the-api-key"}
        assert kwargs["timeout"] == 8


class TestDvlaErrors:
    def test_vehicle_not_found_returns_empty_object(self, api_client, dvla_ready):
        dvla_ready.return_value = dvla_error(404, "Vehicle Not Found", "Record for vehicle not found")
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {}

    def test_invalid_registration_returns_json_404(self, api_client, dvla_ready):
        dvla_ready.return_value = dvla_error(
            400, "Bad Request", "Invalid format for field - vehicle registration number"
        )
        response = lookup(api_client)
        assert response.status_code == 404
        assert response.json() == {"error": "We couldn't find a vehicle with that registration."}

    @pytest.mark.parametrize(
        "vehicle_response",
        [
            pytest.param(gateway_error(400, "Missing required request parameters: []"), id="400-from-gateway"),
            pytest.param(gateway_error(403, "Access denied"), id="403-bad-key"),
            pytest.param(gateway_error(429, "Too Many Requests"), id="429-rate-limited"),
            pytest.param(dvla_error(500, "Internal Server Error"), id="500"),
            pytest.param(gateway_error(502, "Internal server error"), id="502"),
            pytest.param(dvla_error(503, "Service Unavailable"), id="503"),
            pytest.param(dvla_response(200, ["not", "an", "object"]), id="200-not-an-object"),
        ],
    )
    def test_anything_else_is_503(self, api_client, dvla_ready, vehicle_response):
        dvla_ready.return_value = vehicle_response
        response = lookup(api_client)
        assert response.status_code == 503
        assert response.json() == {"error": "Vehicle lookup is temporarily unavailable."}

    def test_non_json_response_is_503(self, api_client, dvla_ready):
        broken = dvla_response(504)
        broken.json.side_effect = ValueError("not json")
        dvla_ready.return_value = broken
        assert lookup(api_client).status_code == 503

    @pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
    def test_timeout_or_connection_error_is_503(self, api_client, dvla_ready, error):
        dvla_ready.side_effect = error
        response = lookup(api_client)
        assert response.status_code == 503
        assert "error" in response.json()

    def test_logs_the_status_but_never_the_key(self, api_client, dvla_ready):
        dvla_ready.return_value = gateway_error(403, "Access denied")
        with patch("apps.sell_my_car.dvla.logger") as logger:
            lookup(api_client)
        logged = str(logger.mock_calls)
        assert "403" in logged
        assert "the-api-key" not in logged


class TestMissingKey:
    def test_missing_key_is_503_without_calling_dvla(self, api_client, dvla_post):
        response = lookup(api_client)
        assert response.status_code == 503
        assert "error" in response.json()
        dvla_post.assert_not_called()


class TestVehicleCaching:
    def test_successful_lookup_is_cached_for_24_hours(self, api_client, dvla_ready):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        first = lookup(api_client).json()
        second = lookup(api_client).json()
        assert first == second
        assert dvla_ready.call_count == 1
        assert dvla.VEHICLE_CACHE_SECONDS == 86400

    def test_cache_is_per_registration(self, api_client, dvla_ready):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        lookup(api_client, reg="AB12CDE")
        lookup(api_client, reg="CD34EFG")
        assert dvla_ready.call_count == 2

    def test_failure_is_not_cached(self, api_client, dvla_ready):
        dvla_ready.side_effect = [requests.Timeout(), dvla_response(200, DVLA_VEHICLE)]
        assert lookup(api_client).status_code == 503
        assert lookup(api_client).status_code == 200

    def test_not_found_is_not_cached(self, api_client, dvla_ready):
        dvla_ready.side_effect = [
            dvla_error(404, "Vehicle Not Found"),
            dvla_response(200, DVLA_VEHICLE),
        ]
        assert lookup(api_client).json() == {}
        assert lookup(api_client).json()["make"] == "CITROEN"


class TestMalformedInput:
    @pytest.mark.parametrize("reg", ["", "A", "AB12CDEF", "ab12cde", "AB12 CDE", "AB-12", "AB12CDÉ"])
    def test_bad_registration_is_400(self, api_client, dvla_ready, reg):
        response = lookup(api_client, reg=reg)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)
        dvla_ready.assert_not_called()

    @pytest.mark.parametrize("mileage", ["", "0", "-1", "10000000", "abc", "10.5"])
    def test_bad_mileage_is_400(self, api_client, dvla_ready, mileage):
        response = lookup(api_client, mileage=mileage)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)
        dvla_ready.assert_not_called()

    def test_missing_params_are_400(self, api_client):
        response = api_client.get(LOOKUP_URL)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)

    @pytest.mark.parametrize("mileage", ["1", "9999999"])
    def test_mileage_limits_are_allowed(self, api_client, dvla_ready, mileage):
        dvla_ready.return_value = dvla_response(200, DVLA_VEHICLE)
        assert lookup(api_client, mileage=mileage).status_code == 200


class TestLookupRateLimit:
    def test_31st_request_in_an_hour_is_429(self, api_client):
        for _ in range(30):
            assert lookup(api_client).status_code == 503
        response = lookup(api_client)
        assert response.status_code == 429
        assert response.json() == {"error": "Too many requests. Please try again later."}

    def test_limit_is_per_ip(self, api_client):
        for _ in range(30):
            lookup(api_client, REMOTE_ADDR="10.0.0.1")
        assert lookup(api_client, REMOTE_ADDR="10.0.0.1").status_code == 429
        assert lookup(api_client, REMOTE_ADDR="10.0.0.2").status_code == 503
