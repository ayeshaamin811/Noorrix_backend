import logging
import threading
from datetime import datetime

from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import Throttled
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import dvsa
from .emails import send_enquiry_emails
from .models import SellMyCarEnquiry, SellMyCarImage
from .serializers import SellMyCarSubmitSerializer, VehicleQuerySerializer
from .throttles import SellMyCarLookupThrottle, SellMyCarSubmitThrottle

logger = logging.getLogger(__name__)

SLOT_TAKEN_ERROR = "This time slot has just been booked. Please pick another."
THROTTLED_ERROR = "Too many requests. Please try again later."

ERROR_RESPONSE = inline_serializer(name="SellMyCarError", fields={"error": serializers.CharField()})


class ThrottleErrorMixin:
    """The frontend reads `error`, not DRF's default `detail`, on a 429."""

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(exc, Throttled):
            response.data = {"error": THROTTLED_ERROR}
        return response


@extend_schema(
    tags=["Sell My Car"],
    summary="Look up a vehicle by registration",
    parameters=[VehicleQuerySerializer],
    responses={
        200: inline_serializer(
            name="SellMyCarVehicle",
            fields={
                "make": serializers.CharField(allow_null=True, required=False),
                "model": serializers.CharField(allow_null=True, required=False),
            },
        ),
        400: ERROR_RESPONSE,
        404: ERROR_RESPONSE,
        429: ERROR_RESPONSE,
        503: ERROR_RESPONSE,
    },
)
class SellMyCarLookupView(ThrottleErrorMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SellMyCarLookupThrottle]

    def get(self, request):
        serializer = VehicleQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            first_messages = next(iter(serializer.errors.values()))
            return Response({"error": first_messages[0]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            vehicle = dvsa.lookup_vehicle(serializer.validated_data["reg"])
        except dvsa.InvalidRegistration:
            return Response(
                {"error": "We couldn't find a vehicle with that registration."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except dvsa.LookupUnavailable:
            return Response(
                {"error": "Vehicle lookup is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(vehicle)


@extend_schema(
    tags=["Sell My Car"],
    summary="Booked inspection slots for a date",
    responses={
        200: inline_serializer(
            name="SellMyCarAvailability",
            fields={
                "date": serializers.DateField(),
                "booked_times": serializers.ListField(child=serializers.CharField()),
            },
        ),
        400: ERROR_RESPONSE,
    },
)
class SellMyCarAvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date query param is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "date must be in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST
            )

        booked_times = [
            slot.strftime("%H:%M")
            for slot in SellMyCarEnquiry.objects.filter(appointment_date=date_obj)
            .exclude(status=SellMyCarEnquiry.Status.CANCELLED)
            .order_by("appointment_time")
            .values_list("appointment_time", flat=True)
        ]
        return Response({"date": date_str, "booked_times": booked_times})


def vehicle_details_for_enquiry(reg):
    """The enquiry's vehicle columns. A customer must never be blocked by DVSA."""
    try:
        vehicle = dvsa.lookup_vehicle(reg)
    except dvsa.DvsaError:
        return {}
    except Exception:
        logger.exception("Unexpected error in the DVSA lookup, saving enquiry without vehicle details")
        return {}

    return {
        field: str(vehicle.get(field) or "")[: SellMyCarEnquiry._meta.get_field(field).max_length]
        for field in ("make", "model")
    }


def save_images(enquiry, uploads):
    saved = []
    try:
        for upload in uploads:
            saved.append(SellMyCarImage.objects.create(enquiry=enquiry, image=upload))
    except Exception:
        # The rollback undoes the rows but not files already in storage.
        for image in saved:
            image.image.delete(save=False)
        raise
    return saved


@extend_schema(
    tags=["Sell My Car"],
    summary="Submit a car and book an inspection slot",
    request=SellMyCarSubmitSerializer,
    responses={
        201: inline_serializer(
            name="SellMyCarSubmitSuccess",
            fields={
                "success": serializers.BooleanField(),
                "id": serializers.IntegerField(),
                "message": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="SellMyCarSubmitError",
            fields={"success": serializers.BooleanField(), "errors": serializers.DictField()},
        ),
        409: ERROR_RESPONSE,
        429: ERROR_RESPONSE,
    },
)
class SellMyCarSubmitView(ThrottleErrorMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SellMyCarSubmitThrottle]
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = SellMyCarSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fields = dict(serializer.validated_data)
        uploads = fields.pop("images", [])
        vehicle = vehicle_details_for_enquiry(fields["reg"])

        # The enquiry goes first so that a slot clash writes no files.
        try:
            with transaction.atomic():
                enquiry = SellMyCarEnquiry.objects.create(**fields, **vehicle)
                images = save_images(enquiry, uploads)
        except IntegrityError:
            return Response({"error": SLOT_TAKEN_ERROR}, status=status.HTTP_409_CONFLICT)

        image_urls = [request.build_absolute_uri(image.image.url) for image in images]
        threading.Thread(target=send_enquiry_emails, args=(enquiry, image_urls), daemon=True).start()

        return Response(
            {
                "success": True,
                "id": enquiry.id,
                "message": "Thanks! Our team will review your details and email you an offer.",
            },
            status=status.HTTP_201_CREATED,
        )
