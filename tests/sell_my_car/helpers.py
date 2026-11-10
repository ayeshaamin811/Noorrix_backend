import io
from datetime import date, datetime, timezone
from unittest.mock import Mock

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

SUBMIT_URL = "/api/sell-my-car/"
LOOKUP_URL = "/api/sell-my-car/lookup/"
AVAILABILITY_URL = "/api/sell-my-car/availability/"

# Monday 2 November 2026, 11:10 in the UK (GMT).
NOW = datetime(2026, 11, 2, 11, 10, tzinfo=timezone.utc)
TODAY = date(2026, 11, 2)

# The two shapes DVSA returns.
VEHICLE_WITH_MOT_TESTS = {
    "registration": "AB12CDE",
    "make": "CITROEN",
    "model": "C3",
    "firstUsedDate": "2010.03.01",
    "fuelType": "DIESEL",
    "primaryColour": "SILVER",
    "registrationDate": "2010.02.15",
    "manufactureDate": "2009.11.30",
    "engineSize": "1398",
    "hasOutstandingRecall": "No",
    "motTests": [{"testResult": "PASSED", "odometerValue": "10220"}],
}
NEWLY_REGISTERED_VEHICLE = {
    "registration": "AB25XYZ",
    "make": "TESLA",
    "model": "MODEL 3",
    "manufactureYear": "2025",
    "fuelType": "ELECTRIC",
    "primaryColour": "WHITE",
    "motTestDueDate": "2028-01-31",
    "dvlaId": "1234567",
}


def dvsa_response(status=200, body=None):
    response = Mock(status_code=status)
    response.json.return_value = body
    return response


def dvsa_error(code, status=400):
    return dvsa_response(status, {"errorCode": code, "errorMessage": "Nope", "requestId": "req-123"})


def image_file(name="car.jpg", image_format="JPEG", content_type="image/jpeg", pad_to=None):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, image_format)
    content = buffer.getvalue()
    if pad_to:
        content += b"\0" * (pad_to - len(content))
    return SimpleUploadedFile(name, content, content_type=content_type)


def payload(**overrides):
    """A valid submission. Passing None for a field leaves it out."""
    data = {
        "reg": "AB12CDE",
        "mileage": "10220",
        "name": "Alex Smith",
        "email": "alex@example.com",
        "phone": "+447701910159",
        "address": "1 High Street, Bedford MK40 1AA",
        "message": "Full service history.",
        "appointment_date": "2026-11-03",
        "appointment_time": "12:00",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def submit(client, **overrides):
    return client.post(SUBMIT_URL, payload(**overrides), format="multipart")
