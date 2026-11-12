"""Client for the DVSA MOT History API. Only this module talks to DVSA."""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

VEHICLE_URL = "https://history.mot.api.gov.uk/v1/trade/vehicles/registration/{reg}"
TIMEOUT_SECONDS = 8
TOKEN_CACHE_KEY = "sell_my_car:dvsa_token"
TOKEN_EXPIRY_MARGIN_SECONDS = 60
VEHICLE_CACHE_SECONDS = 24 * 60 * 60

VEHICLE_NOT_FOUND = "MOTH-NF-01"
INVALID_REGISTRATION = "MOTH-IV-03"
TOKEN_EXPIRED = "MOTH-FB-02"


class DvsaError(Exception):
    pass


class InvalidRegistration(DvsaError):
    pass


class LookupUnavailable(DvsaError):
    pass


def is_configured():
    return all(
        [
            settings.DVSA_TOKEN_URL,
            settings.DVSA_CLIENT_ID,
            settings.DVSA_CLIENT_SECRET,
            settings.DVSA_SCOPE,
            settings.DVSA_API_KEY,
        ]
    )


def lookup_vehicle(reg):
    """Return the vehicle's details, or {} if DVSA doesn't know the vehicle.

    The keys are make, model, year, colour and fuel_type.

    Raises InvalidRegistration or LookupUnavailable. Only a real match is
    cached, so a failure or a not-yet-listed vehicle is looked up again.
    """
    if not is_configured():
        raise LookupUnavailable("DVSA credentials are not configured")

    cache_key = f"sell_my_car:dvsa_vehicle:{reg}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    body, error_code = _fetch_vehicle(reg)
    if error_code == TOKEN_EXPIRED:
        cache.delete(TOKEN_CACHE_KEY)
        body, error_code = _fetch_vehicle(reg)

    if error_code == VEHICLE_NOT_FOUND:
        return {}
    if error_code == INVALID_REGISTRATION:
        raise InvalidRegistration(reg)
    if error_code:
        raise LookupUnavailable(error_code)

    vehicle = _map_vehicle(body)
    cache.set(cache_key, vehicle, VEHICLE_CACHE_SECONDS)
    return vehicle


def _fetch_vehicle(reg):
    """Return (body, error_code). Decides on errorCode, not the HTTP status."""
    token = _get_token()
    try:
        response = requests.get(
            VEHICLE_URL.format(reg=reg),
            headers={"Authorization": f"Bearer {token}", "X-API-Key": settings.DVSA_API_KEY},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("DVSA vehicle request failed: %s", type(exc).__name__)
        raise LookupUnavailable("request failed") from None

    try:
        body = response.json()
    except ValueError:
        body = None

    if not isinstance(body, dict):
        logger.warning("DVSA returned an unreadable response: status=%s", response.status_code)
        raise LookupUnavailable("unreadable response")

    error_code = body.get("errorCode")
    if error_code:
        logger.warning(
            "DVSA lookup failed: errorCode=%s requestId=%s", error_code, body.get("requestId")
        )
        return body, error_code

    if response.status_code != 200:
        logger.warning(
            "DVSA lookup failed: status=%s requestId=%s", response.status_code, body.get("requestId")
        )
        raise LookupUnavailable(f"status {response.status_code}")

    return body, None


def _get_token():
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token

    try:
        response = requests.post(
            settings.DVSA_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.DVSA_CLIENT_ID,
                "client_secret": settings.DVSA_CLIENT_SECRET,
                "scope": settings.DVSA_SCOPE,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("DVSA token request failed: %s", type(exc).__name__)
        raise LookupUnavailable("token request failed") from None

    try:
        body = response.json()
        token = body["access_token"]
    except (ValueError, KeyError, TypeError):
        logger.warning("DVSA token request failed: status=%s", response.status_code)
        raise LookupUnavailable("no access token") from None

    try:
        cache_seconds = int(body["expires_in"]) - TOKEN_EXPIRY_MARGIN_SECONDS
    except (KeyError, TypeError, ValueError):
        cache_seconds = 0
    if cache_seconds > 0:
        cache.set(TOKEN_CACHE_KEY, token, cache_seconds)

    return token


def _map_vehicle(body):
    return {
        "make": body.get("make"),
        "model": body.get("model"),
        "year": _year(body),
        "colour": body.get("primaryColour") or None,
        "fuel_type": body.get("fuelType") or None,
    }


def _year(body):
    """The year of manufacture, or of first registration if that is all DVSA has.

    A vehicle with MOT tests has full dates, such as 2009-11-30. A newly
    registered one has manufactureYear only.
    """
    for field in ("manufactureDate", "manufactureYear", "registrationDate", "firstUsedDate"):
        year = str(body.get(field) or "")[:4]
        if len(year) == 4 and year.isdigit():
            return int(year)
    return None
