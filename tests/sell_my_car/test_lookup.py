from unittest.mock import patch

import pytest
import requests

from apps.sell_my_car import dvsa

from .helpers import (
    LOOKUP_URL,
    NEWLY_REGISTERED_VEHICLE,
    VEHICLE_WITH_MOT_TESTS,
    dvsa_error,
    dvsa_response,
)


def lookup(client, reg="AB12CDE", mileage="10220", **extra):
    return client.get(LOOKUP_URL, {"reg": reg, "mileage": mileage}, **extra)


class TestVehicleMapping:
    def test_vehicle_with_mot_tests(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {
            "make": "CITROEN",
            "model": "C3",
            "year": 2009,
            "colour": "SILVER",
            "fuel_type": "DIESEL",
        }

    def test_newly_registered_vehicle(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, NEWLY_REGISTERED_VEHICLE)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {
            "make": "TESLA",
            "model": "MODEL 3",
            "year": 2025,
            "colour": "WHITE",
            "fuel_type": "ELECTRIC",
        }

    @pytest.mark.parametrize(
        "fields, year",
        [
            ({"manufactureYear": 2012, "manufactureDate": "2009.11.30"}, 2012),
            ({"manufactureDate": "2011-04-01"}, 2011),
            ({"registrationDate": "2010.02.15", "firstUsedDate": "2009.01.01"}, 2010),
            ({"firstUsedDate": "2008.06.20"}, 2008),
            ({"manufactureYear": None, "manufactureDate": "", "firstUsedDate": "2007.01.01"}, 2007),
            ({}, None),
            ({"manufactureYear": "unknown"}, None),
        ],
    )
    def test_year_fallback_order(self, api_client, dvsa_ready, fields, year):
        dvsa_ready.get.return_value = dvsa_response(200, {"make": "FORD", **fields})
        assert lookup(api_client).json()["year"] == year

    def test_missing_fields_are_null(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, {"make": "FORD"})
        assert lookup(api_client).json() == {
            "make": "FORD",
            "model": None,
            "year": None,
            "colour": None,
            "fuel_type": None,
        }


class TestDvsaRequest:
    def test_token_request_is_form_encoded_with_credentials(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        lookup(api_client)
        args, kwargs = dvsa_ready.post.call_args
        assert args == ("https://login.example/tenant-id/oauth2/v2.0/token",)
        assert kwargs["data"] == {
            "grant_type": "client_credentials",
            "client_id": "the-client-id",
            "client_secret": "the-client-secret",
            "scope": "https://tapi.dvsa.gov.uk/.default",
        }
        assert "json" not in kwargs
        assert kwargs["timeout"] == 8

    def test_vehicle_request_url_headers_and_timeout(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        lookup(api_client)
        args, kwargs = dvsa_ready.get.call_args
        assert args == ("https://history.mot.api.gov.uk/v1/trade/vehicles/registration/AB12CDE",)
        assert kwargs["headers"] == {
            "Authorization": "Bearer the-token",
            "X-API-Key": "the-api-key",
        }
        assert kwargs["timeout"] == 8


class TestDvsaErrors:
    @pytest.mark.parametrize("status", [200, 400, 404])
    def test_vehicle_not_found_returns_empty_object(self, api_client, dvsa_ready, status):
        dvsa_ready.get.return_value = dvsa_error("MOTH-NF-01", status)
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json() == {}

    @pytest.mark.parametrize("status", [200, 400, 404])
    def test_invalid_registration_returns_json_404(self, api_client, dvsa_ready, status):
        dvsa_ready.get.return_value = dvsa_error("MOTH-IV-03", status)
        response = lookup(api_client)
        assert response.status_code == 404
        assert response.json() == {"error": "We couldn't find a vehicle with that registration."}

    def test_expired_token_gets_a_new_token_and_retries_once(self, api_client, dvsa_ready):
        dvsa_ready.post.side_effect = [
            dvsa_response(body={"access_token": "old-token", "expires_in": 3600}),
            dvsa_response(body={"access_token": "new-token", "expires_in": 3600}),
        ]
        dvsa_ready.get.side_effect = [
            dvsa_error("MOTH-FB-02", 401),
            dvsa_response(200, VEHICLE_WITH_MOT_TESTS),
        ]
        response = lookup(api_client)
        assert response.status_code == 200
        assert response.json()["make"] == "CITROEN"
        assert dvsa_ready.post.call_count == 2
        tokens = [call.kwargs["headers"]["Authorization"] for call in dvsa_ready.get.call_args_list]
        assert tokens == ["Bearer old-token", "Bearer new-token"]

    def test_token_expired_twice_is_503_after_one_retry(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_error("MOTH-FB-02", 401)
        response = lookup(api_client)
        assert response.status_code == 503
        assert "error" in response.json()
        assert dvsa_ready.get.call_count == 2

    @pytest.mark.parametrize(
        "vehicle_response",
        [
            pytest.param(dvsa_error("MOTH-RL-01", 429), id="other-error-code"),
            pytest.param(dvsa_error("MOTH-UNKNOWN", 200), id="error-code-on-200"),
            pytest.param(dvsa_response(500, {"message": "boom"}), id="500-without-code"),
            pytest.param(dvsa_response(200, ["not", "an", "object"]), id="200-not-an-object"),
        ],
    )
    def test_anything_else_is_503(self, api_client, dvsa_ready, vehicle_response):
        dvsa_ready.get.return_value = vehicle_response
        response = lookup(api_client)
        assert response.status_code == 503
        assert "error" in response.json()

    def test_non_json_response_is_503(self, api_client, dvsa_ready):
        broken = dvsa_response(502)
        broken.json.side_effect = ValueError("not json")
        dvsa_ready.get.return_value = broken
        assert lookup(api_client).status_code == 503

    @pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
    def test_timeout_or_connection_error_is_503(self, api_client, dvsa_ready, error):
        dvsa_ready.get.side_effect = error
        response = lookup(api_client)
        assert response.status_code == 503
        assert "error" in response.json()

    def test_logs_error_code_and_request_id_but_no_secrets(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_error("MOTH-RL-01", 429)
        with patch("apps.sell_my_car.dvsa.logger") as logger:
            lookup(api_client)
        logged = str(logger.mock_calls)
        assert "MOTH-RL-01" in logged
        assert "req-123" in logged
        for secret in ("the-client-secret", "the-client-id", "the-api-key", "the-token"):
            assert secret not in logged


class TestMissingCredentials:
    @pytest.mark.parametrize(
        "setting",
        ["DVSA_TOKEN_URL", "DVSA_CLIENT_ID", "DVSA_CLIENT_SECRET", "DVSA_SCOPE", "DVSA_API_KEY"],
    )
    def test_any_missing_value_is_503_without_calling_dvsa(self, api_client, dvsa_ready, settings, setting):
        setattr(settings, setting, "")
        response = lookup(api_client)
        assert response.status_code == 503
        assert "error" in response.json()
        dvsa_ready.post.assert_not_called()
        dvsa_ready.get.assert_not_called()


class TestTokenCaching:
    def test_token_is_reused_between_lookups(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        lookup(api_client, reg="AB12CDE")
        lookup(api_client, reg="CD34EFG")
        assert dvsa_ready.post.call_count == 1
        assert dvsa_ready.get.call_count == 2

    @pytest.mark.parametrize("expires_in, cached_for", [(3600, 3540), ("1800", 1740)])
    def test_token_expires_one_minute_early(self, dvsa_ready, expires_in, cached_for):
        dvsa_ready.post.return_value = dvsa_response(body={"access_token": "t", "expires_in": expires_in})
        with patch("apps.sell_my_car.dvsa.cache") as mock_cache:
            mock_cache.get.return_value = None
            assert dvsa._get_token() == "t"
        mock_cache.set.assert_called_once_with(dvsa.TOKEN_CACHE_KEY, "t", cached_for)

    @pytest.mark.parametrize("token_body", [{"access_token": "t", "expires_in": 30}, {"access_token": "t"}])
    def test_short_lived_or_undated_token_is_not_cached(self, api_client, dvsa_ready, token_body):
        dvsa_ready.post.return_value = dvsa_response(body=token_body)
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        lookup(api_client, reg="AB12CDE")
        lookup(api_client, reg="CD34EFG")
        assert dvsa_ready.post.call_count == 2

    def test_token_rejected_is_503(self, api_client, dvsa_ready):
        dvsa_ready.post.return_value = dvsa_response(401, {"error": "invalid_client"})
        assert lookup(api_client).status_code == 503
        dvsa_ready.get.assert_not_called()

    def test_token_timeout_is_503(self, api_client, dvsa_ready):
        dvsa_ready.post.side_effect = requests.Timeout()
        assert lookup(api_client).status_code == 503


class TestVehicleCaching:
    def test_successful_lookup_is_cached_for_24_hours(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        first = lookup(api_client).json()
        second = lookup(api_client).json()
        assert first == second
        assert dvsa_ready.get.call_count == 1
        assert dvsa.VEHICLE_CACHE_SECONDS == 86400

    def test_cache_is_per_registration(self, api_client, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        lookup(api_client, reg="AB12CDE")
        lookup(api_client, reg="CD34EFG")
        assert dvsa_ready.get.call_count == 2

    def test_failure_is_not_cached(self, api_client, dvsa_ready):
        dvsa_ready.get.side_effect = [requests.Timeout(), dvsa_response(200, VEHICLE_WITH_MOT_TESTS)]
        assert lookup(api_client).status_code == 503
        assert lookup(api_client).status_code == 200

    def test_not_found_is_not_cached(self, api_client, dvsa_ready):
        dvsa_ready.get.side_effect = [dvsa_error("MOTH-NF-01"), dvsa_response(200, VEHICLE_WITH_MOT_TESTS)]
        assert lookup(api_client).json() == {}
        assert lookup(api_client).json()["make"] == "CITROEN"


class TestMalformedInput:
    @pytest.mark.parametrize("reg", ["", "A", "AB12CDEF", "ab12cde", "AB12 CDE", "AB-12", "AB12CDÉ"])
    def test_bad_registration_is_400(self, api_client, dvsa_ready, reg):
        response = lookup(api_client, reg=reg)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)
        dvsa_ready.get.assert_not_called()

    @pytest.mark.parametrize("mileage", ["", "0", "-1", "10000000", "abc", "10.5"])
    def test_bad_mileage_is_400(self, api_client, dvsa_ready, mileage):
        response = lookup(api_client, mileage=mileage)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)
        dvsa_ready.get.assert_not_called()

    def test_missing_params_are_400(self, api_client):
        response = api_client.get(LOOKUP_URL)
        assert response.status_code == 400
        assert isinstance(response.json()["error"], str)

    @pytest.mark.parametrize("mileage", ["1", "9999999"])
    def test_mileage_limits_are_allowed(self, api_client, dvsa_ready, mileage):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
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
