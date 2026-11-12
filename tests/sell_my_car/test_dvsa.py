"""The DVSA client on its own. How it combines with DVLA is in test_vehicle_lookup.py."""

from unittest.mock import patch

import pytest
import requests

from apps.sell_my_car import dvsa

from .helpers import NEWLY_REGISTERED_VEHICLE, VEHICLE_WITH_MOT_TESTS, dvsa_error, dvsa_response

REG = "AB12CDE"


class TestVehicleMapping:
    def test_vehicle_with_mot_tests(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        assert dvsa.lookup_vehicle(REG) == {
            "make": "CITROEN",
            "model": "C3",
            "year": 2009,
            "colour": "SILVER",
            "fuel_type": "DIESEL",
        }

    def test_newly_registered_vehicle(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, NEWLY_REGISTERED_VEHICLE)
        assert dvsa.lookup_vehicle(REG) == {
            "make": "TESLA",
            "model": "MODEL 3",
            "year": 2025,
            "colour": "WHITE",
            "fuel_type": "ELECTRIC",
        }

    def test_missing_fields_are_none(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, {"make": "FORD", "primaryColour": ""})
        assert dvsa.lookup_vehicle(REG) == {
            "make": "FORD",
            "model": None,
            "year": None,
            "colour": None,
            "fuel_type": None,
        }

    @pytest.mark.parametrize(
        "dates, year",
        [
            pytest.param({"manufactureDate": "2009-11-30", "registrationDate": "2010-02-15"}, 2009, id="manufacture-date"),
            pytest.param({"manufactureDate": "2009.11.30"}, 2009, id="dotted-date"),
            pytest.param({"manufactureYear": "2025"}, 2025, id="manufacture-year"),
            pytest.param({"registrationDate": "2010-02-15"}, 2010, id="registration-date"),
            pytest.param({"firstUsedDate": "2010-03-01"}, 2010, id="first-used-date"),
            pytest.param({"manufactureDate": "unknown", "registrationDate": "2010-02-15"}, 2010, id="bad-then-good"),
            pytest.param({"manufactureDate": "n/a"}, None, id="no-usable-date"),
        ],
    )
    def test_year(self, dvsa_ready, dates, year):
        dvsa_ready.get.return_value = dvsa_response(200, {"make": "FORD", **dates})
        assert dvsa.lookup_vehicle(REG)["year"] == year


class TestDvsaRequest:
    def test_token_request_is_form_encoded_with_credentials(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        dvsa.lookup_vehicle(REG)
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

    def test_vehicle_request_url_headers_and_timeout(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        dvsa.lookup_vehicle(REG)
        args, kwargs = dvsa_ready.get.call_args
        assert args == ("https://history.mot.api.gov.uk/v1/trade/vehicles/registration/AB12CDE",)
        assert kwargs["headers"] == {
            "Authorization": "Bearer the-token",
            "X-API-Key": "the-dvsa-api-key",
        }
        assert kwargs["timeout"] == 8


class TestDvsaErrors:
    @pytest.mark.parametrize("status", [200, 400, 404])
    def test_vehicle_not_found_is_an_empty_dict(self, dvsa_ready, status):
        dvsa_ready.get.return_value = dvsa_error("MOTH-NF-01", status)
        assert dvsa.lookup_vehicle(REG) == {}

    @pytest.mark.parametrize("status", [200, 400, 404])
    def test_invalid_registration_raises(self, dvsa_ready, status):
        dvsa_ready.get.return_value = dvsa_error("MOTH-IV-03", status)
        with pytest.raises(dvsa.InvalidRegistration):
            dvsa.lookup_vehicle(REG)

    def test_expired_token_gets_a_new_token_and_retries_once(self, dvsa_ready):
        dvsa_ready.post.side_effect = [
            dvsa_response(body={"access_token": "old-token", "expires_in": 3600}),
            dvsa_response(body={"access_token": "new-token", "expires_in": 3600}),
        ]
        dvsa_ready.get.side_effect = [
            dvsa_error("MOTH-FB-02", 401),
            dvsa_response(200, VEHICLE_WITH_MOT_TESTS),
        ]
        assert dvsa.lookup_vehicle(REG)["make"] == "CITROEN"
        assert dvsa_ready.post.call_count == 2
        tokens = [call.kwargs["headers"]["Authorization"] for call in dvsa_ready.get.call_args_list]
        assert tokens == ["Bearer old-token", "Bearer new-token"]

    def test_token_expired_twice_is_unavailable_after_one_retry(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_error("MOTH-FB-02", 401)
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)
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
    def test_anything_else_is_unavailable(self, dvsa_ready, vehicle_response):
        dvsa_ready.get.return_value = vehicle_response
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)

    def test_non_json_response_is_unavailable(self, dvsa_ready):
        broken = dvsa_response(502)
        broken.json.side_effect = ValueError("not json")
        dvsa_ready.get.return_value = broken
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)

    @pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
    def test_timeout_or_connection_error_is_unavailable(self, dvsa_ready, error):
        dvsa_ready.get.side_effect = error
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)

    def test_logs_error_code_and_request_id_but_no_secrets(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_error("MOTH-RL-01", 429)
        with patch("apps.sell_my_car.dvsa.logger") as logger, pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)
        logged = str(logger.mock_calls)
        assert "MOTH-RL-01" in logged
        assert "req-123" in logged
        for secret in ("the-client-secret", "the-client-id", "the-dvsa-api-key", "the-token"):
            assert secret not in logged


class TestMissingCredentials:
    @pytest.mark.parametrize(
        "setting",
        ["DVSA_TOKEN_URL", "DVSA_CLIENT_ID", "DVSA_CLIENT_SECRET", "DVSA_SCOPE", "DVSA_API_KEY"],
    )
    def test_any_missing_value_is_unavailable_without_calling_dvsa(self, dvsa_ready, settings, setting):
        setattr(settings, setting, "")
        assert not dvsa.is_configured()
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)
        dvsa_ready.post.assert_not_called()
        dvsa_ready.get.assert_not_called()


class TestTokenCaching:
    def test_token_is_reused_between_lookups(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        dvsa.lookup_vehicle("AB12CDE")
        dvsa.lookup_vehicle("CD34EFG")
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
    def test_short_lived_or_undated_token_is_not_cached(self, dvsa_ready, token_body):
        dvsa_ready.post.return_value = dvsa_response(body=token_body)
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        dvsa.lookup_vehicle("AB12CDE")
        dvsa.lookup_vehicle("CD34EFG")
        assert dvsa_ready.post.call_count == 2

    def test_token_rejected_is_unavailable(self, dvsa_ready):
        dvsa_ready.post.return_value = dvsa_response(401, {"error": "invalid_client"})
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)
        dvsa_ready.get.assert_not_called()

    def test_token_timeout_is_unavailable(self, dvsa_ready):
        dvsa_ready.post.side_effect = requests.Timeout()
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)


class TestVehicleCaching:
    def test_successful_lookup_is_cached_for_24_hours(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        assert dvsa.lookup_vehicle(REG) == dvsa.lookup_vehicle(REG)
        assert dvsa_ready.get.call_count == 1
        assert dvsa.VEHICLE_CACHE_SECONDS == 86400

    def test_cache_is_per_registration(self, dvsa_ready):
        dvsa_ready.get.return_value = dvsa_response(200, VEHICLE_WITH_MOT_TESTS)
        dvsa.lookup_vehicle("AB12CDE")
        dvsa.lookup_vehicle("CD34EFG")
        assert dvsa_ready.get.call_count == 2

    def test_failure_is_not_cached(self, dvsa_ready):
        dvsa_ready.get.side_effect = [requests.Timeout(), dvsa_response(200, VEHICLE_WITH_MOT_TESTS)]
        with pytest.raises(dvsa.LookupUnavailable):
            dvsa.lookup_vehicle(REG)
        assert dvsa.lookup_vehicle(REG)["make"] == "CITROEN"

    def test_not_found_is_not_cached(self, dvsa_ready):
        dvsa_ready.get.side_effect = [dvsa_error("MOTH-NF-01"), dvsa_response(200, VEHICLE_WITH_MOT_TESTS)]
        assert dvsa.lookup_vehicle(REG) == {}
        assert dvsa.lookup_vehicle(REG)["make"] == "CITROEN"
