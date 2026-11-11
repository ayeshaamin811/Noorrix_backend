"""The vehicle lookup the views use.

DVSA gives the make and model but only once its credentials are set. DVLA
gives the make only. DVSA is asked first when it is set up, and DVLA covers
any car DVSA doesn't return.
"""

from . import dvla, dvsa
from .dvla import InvalidRegistration, LookupUnavailable, VehicleLookupError

__all__ = ["InvalidRegistration", "LookupUnavailable", "VehicleLookupError", "lookup_vehicle"]


def lookup_vehicle(reg):
    """Return {"make", "model"}, or {} if the vehicle isn't known.

    Only DVLA's errors reach the caller. Any DVSA failure falls back to DVLA,
    which holds every UK registration.
    """
    if dvsa.is_configured():
        try:
            vehicle = dvsa.lookup_vehicle(reg)
        except dvsa.DvsaError:
            vehicle = {}
        if vehicle.get("make") or vehicle.get("model"):
            return vehicle
    return dvla.lookup_vehicle(reg)
