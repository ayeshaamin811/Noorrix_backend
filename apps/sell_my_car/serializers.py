import re
from datetime import time, timedelta

from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from PIL import Image
from rest_framework import serializers

REG_PATTERN = re.compile(r"^[A-Z0-9]{2,7}$")
# re.ASCII limits \d to 0-9, as Python otherwise accepts any Unicode digit.
PHONE_PATTERN = re.compile(r"^\+44(?:7[1-57-9]\d{8}|7624\d{6}|1\d{8,9}|2[03489]\d{8})$", re.ASCII)

REG_ERROR = "Please enter a valid registration."
PHONE_ERROR = "Please enter a valid UK phone number."
DATE_ERROR = "Please pick a valid inspection date."
TIME_ERROR = "Please pick a valid inspection time."

FIRST_SLOT = time(9, 0)
LAST_SLOT = time(17, 30)
BOOKING_WINDOW_DAYS = 6

MAX_IMAGES = 10
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}


def one_message(message):
    """Use the same customer-facing text for every way a field can fail."""
    keys = (
        "required", "null", "blank", "invalid", "datetime",
        "min_length", "max_length", "min_value", "max_value", "max_string_length",
    )
    return {key: message for key in keys}


def detect_image_extension(upload):
    """Return the extension for the file's real format, or None if it isn't allowed.

    Reads the file's own bytes, so the browser's content type and file name
    play no part.
    """
    try:
        with Image.open(upload, formats=tuple(IMAGE_EXTENSIONS)) as image:
            extension = IMAGE_EXTENSIONS[image.format]
            image.verify()
        return extension
    except Exception:  # Pillow raises many types for a corrupt or hostile file.
        return None
    finally:
        upload.seek(0)


@extend_schema_field({"type": "array", "items": {"type": "string", "format": "binary"}})
class ImageUploadsField(serializers.Field):
    """The repeated `images` key.

    A ListField would nest errors by index, which the frontend can't display,
    so this raises one flat message for the whole field.
    """

    default_error_messages = {
        "too_many": f"You can upload up to {MAX_IMAGES} photos.",
        "too_large": "Each photo must be 10MB or smaller.",
        "bad_format": "Photos must be PNG, JPEG, GIF or WEBP images.",
    }

    def get_value(self, dictionary):
        return dictionary.getlist(self.field_name)

    def to_internal_value(self, files):
        if len(files) > MAX_IMAGES:
            self.fail("too_many")

        for upload in files:
            if not isinstance(upload, UploadedFile):
                self.fail("bad_format")
            if upload.size > MAX_IMAGE_BYTES:
                self.fail("too_large")
            extension = detect_image_extension(upload)
            if extension is None:
                self.fail("bad_format")
            upload.name = f"photo{extension}"

        return files

    def to_representation(self, value):
        return [upload.name for upload in value]


class VehicleQuerySerializer(serializers.Serializer):
    reg = serializers.CharField(error_messages=one_message(REG_ERROR))
    mileage = serializers.IntegerField(
        min_value=1,
        max_value=9_999_999,
        error_messages=one_message("Please enter your mileage as a whole number from 1 to 9,999,999."),
    )

    def validate_reg(self, value):
        if not REG_PATTERN.fullmatch(value):
            raise serializers.ValidationError(REG_ERROR)
        return value


class SellMyCarSubmitSerializer(VehicleQuerySerializer):
    name = serializers.CharField(
        min_length=2,
        max_length=150,
        error_messages=one_message("Please enter your name (2 to 150 characters)."),
    )
    email = serializers.EmailField(
        max_length=254,
        error_messages=one_message("Please enter a valid email address."),
    )
    phone = serializers.CharField(error_messages=one_message(PHONE_ERROR))
    address = serializers.CharField(
        min_length=5,
        max_length=300,
        error_messages=one_message("Please enter your address (5 to 300 characters)."),
    )
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        error_messages=one_message("Your message must be 2,000 characters or fewer."),
    )
    appointment_date = serializers.DateField(
        input_formats=["%Y-%m-%d"],
        error_messages=one_message(DATE_ERROR),
    )
    appointment_time = serializers.TimeField(
        input_formats=["%H:%M"],
        error_messages=one_message(TIME_ERROR),
    )
    images = ImageUploadsField(required=False)

    def validate_phone(self, value):
        if not PHONE_PATTERN.fullmatch(value):
            raise serializers.ValidationError(PHONE_ERROR)
        return value

    def validate_appointment_date(self, value):
        today = timezone.localdate()
        if not today <= value <= today + timedelta(days=BOOKING_WINDOW_DAYS):
            raise serializers.ValidationError(
                "Please pick an inspection date from today to 6 days from now."
            )
        return value

    def validate_appointment_time(self, value):
        if value.minute not in (0, 30) or not FIRST_SLOT <= value <= LAST_SLOT:
            raise serializers.ValidationError(
                "Please pick a 30-minute inspection slot between 09:00 and 18:00."
            )
        return value

    def validate(self, attrs):
        now = timezone.localtime()
        if attrs["appointment_date"] == now.date() and attrs["appointment_time"] <= now.time():
            raise serializers.ValidationError(
                {"appointment_time": ["That inspection slot has already started. Please pick another."]}
            )
        return attrs
