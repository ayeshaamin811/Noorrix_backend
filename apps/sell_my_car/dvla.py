"""Client for the DVLA Vehicle Enquiry Service. Only this module talks to DVLA."""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

VEHICLE_URL = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
TIMEOUT_SECONDS = 8
VEHICLE_CACHE_SECONDS = 24 * 60 * 60


class VehicleLookupError(Exception):
    pass


class InvalidRegistration(VehicleLookupError):
    pass


class LookupUnavailable(VehicleLookupError):
    pass


def lookup_vehicle(reg):
    """Return the vehicle's details, or {} if DVLA doesn't know the vehicle.

    The keys are make, model, year, colour and fuel_type. DVLA doesn't
    provide the model, so it is always None. It stays in the result because
    the frontend reads it.

    Raises InvalidRegistration or LookupUnavailable. Only a real match is
    cached, so a failure or an unknown vehicle is looked up again.
    """
    if not settings.DVLA_API_KEY:
        raise LookupUnavailable("DVLA_API_KEY is not configured")

    cache_key = f"sell_my_car:dvla_vehicle:{reg}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.post(
            VEHICLE_URL,
            json={"registrationNumber": reg},
            headers={"x-api-key": settings.DVLA_API_KEY},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("DVLA vehicle request failed: %s", type(exc).__name__)
        raise LookupUnavailable("request failed") from None

    try:
        body = response.json()
    except ValueError:
        body = None

    if response.status_code == 404:
        return {}
    # DVLA's own 400 has an `errors` list. A 400 from its gateway has
    # `message` instead and means our request was wrong, not the reg.
    if response.status_code == 400 and isinstance(body, dict) and body.get("errors"):
        raise InvalidRegistration(reg)
    if response.status_code != 200 or not isinstance(body, dict):
        logger.warning("DVLA lookup failed: status=%s", response.status_code)
        raise LookupUnavailable(f"status {response.status_code}")

    if not body.get("make"):
        return {}

    vehicle = {
        "make": body["make"],
        "model": None,
        "year": body.get("yearOfManufacture") or None,
        "colour": body.get("colour") or None,
        "fuel_type": body.get("fuelType") or None,
    }
    cache.set(cache_key, vehicle, VEHICLE_CACHE_SECONDS)
    return vehicle
