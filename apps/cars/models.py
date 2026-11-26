from django.conf import settings
from django.db import models


class BodyType(models.TextChoices):
    SUV         = "SUV", "SUV"
    HATCHBACK   = "Hatchback", "Hatchback"
    SALOON      = "Saloon", "Saloon"
    ESTATE      = "Estate", "Estate"
    COUPE       = "Coupe", "Coupe"
    CONVERTIBLE = "Convertible", "Convertible"
    MPV         = "MPV", "MPV"
    VAN         = "Van", "Van"


class FuelType(models.TextChoices):
    PETROL      = "Petrol", "Petrol"
    DIESEL      = "Diesel", "Diesel"
    HYBRID      = "Hybrid", "Hybrid"
    ELECTRIC    = "Electric", "Electric"
    MILD_HYBRID = "Mild Hybrid", "Mild Hybrid"


class Transmission(models.TextChoices):
    AUTOMATIC      = "Automatic", "Automatic"
    MANUAL         = "Manual", "Manual"
    CVT            = "CVT", "CVT"
    SEMI_AUTOMATIC = "Semi-Automatic", "Semi-Automatic"


class Colour(models.TextChoices):
    """The colours admin suggests. Car.colour accepts any other colour too."""

    BLACK  = "Black", "Black"
    WHITE  = "White", "White"
    SILVER = "Silver", "Silver"
    GREY   = "Grey", "Grey"
    BLUE   = "Blue", "Blue"
    RED    = "Red", "Red"
    GREEN  = "Green", "Green"
    ORANGE = "Orange", "Orange"


class CarStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    RESERVED  = "reserved", "Reserved"
    SOLD      = "sold", "Sold"


class FeatureCategory(models.TextChoices):
    EXTERIOR = "Exterior", "Exterior"
    INTERIOR = "Interior", "Interior"
    PERFORMANCE = "Performance", "Performance"
    SIZE_AND_DIMENSIONS = "Size and dimensions", "Size and dimensions"
    AUDIO_AND_COMMUNICATIONS = "Audio and Communications", "Audio and Communications"


class Car(models.Model):
    """A single vehicle in stock — the single source of truth for list, detail,
    brand, similar and checkout. The numeric ``id`` is the stable key the
    front-end uses everywhere (``/cars/:id`` and ``/checkout?car=:id``)."""

    # ── Identity ───────────────────────────────────────────────
    title    = models.CharField(max_length=255, help_text='e.g. "BMW 3 Series"')
    subtitle = models.CharField(
        max_length=255,
        help_text='Trim/spec line, e.g. "2.0 320d M Sport Saloon Auto Euro 6 4dr"',
    )
    reg = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Registration number, e.g. "AB15 CDE"',
    )

    # ── Classification (drives the filters) ────────────────────
    make         = models.CharField(max_length=100, help_text='Brand, e.g. "BMW"')
    model        = models.CharField(max_length=100, help_text='Model, e.g. "3 Series"')
    body_type    = models.CharField(max_length=20, choices=BodyType.choices)
    fuel         = models.CharField(max_length=20, choices=FuelType.choices)
    transmission = models.CharField(max_length=20, choices=Transmission.choices)
    colour       = models.CharField(
        max_length=20, blank=True, default="",
        help_text='Pick one from the list or type any colour, e.g. "Bronze"',
    )

    # ── Specs (numbers — front-end formats for display) ────────
    year          = models.PositiveIntegerField(help_text="Registration year, e.g. 2019")
    engine_cc     = models.PositiveIntegerField(null=True, blank=True, help_text="Engine size in CC, e.g. 1995")
    engine        = models.CharField(max_length=20, blank=True, help_text='Display engine, e.g. "2.0L"')
    doors         = models.PositiveSmallIntegerField(default=5)
    seats         = models.PositiveSmallIntegerField(default=5)
    mileage       = models.PositiveIntegerField(help_text="Mileage as a number, e.g. 42300")
    price         = models.PositiveIntegerField(help_text="Total price in £ (whole pounds), e.g. 14495")
    monthly       = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Monthly payment in £, e.g. 245.00",
    )
    mot_date      = models.DateField(null=True, blank=True, help_text="MOT expiry date")
    history_check = models.CharField(max_length=120, blank=True, default="All passed")
    deposit_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default="200.00",
        help_text="Refundable reservation deposit charged at checkout, in £.",
    )

    # ── Media ──────────────────────────────────────────────────
    image = models.ImageField(
        upload_to="cars/", help_text="Main/card thumbnail. Gallery images are added below."
    )

    # ── Detail copy ────────────────────────────────────────────
    description = models.TextField(blank=True, help_text="Marketing description shown on the detail page")
    video_url   = models.URLField(blank=True, help_text="Video walkthrough URL (YouTube etc.)")

    # ── Location (blank → front-end uses the global default) ───
    location_name    = models.CharField(max_length=255, blank=True)
    location_address = models.TextField(blank=True)

    # ── Lifecycle ──────────────────────────────────────────────
    status     = models.CharField(
        max_length=20, choices=CarStatus.choices, default=CarStatus.AVAILABLE,
        help_text="Only 'available' cars appear in stock listings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        # One per filter/sort field used by GET /api/cars/.
        indexes = [
            models.Index(fields=[field], name=f"car_{field}_idx")
            for field in (
                "make", "model", "body_type", "fuel", "transmission", "colour",
                "status", "price", "mileage", "year", "created_at",
            )
        ]

    def __str__(self):
        return f"{self.title} — {self.subtitle} (#{self.pk})"


class CarImage(models.Model):
    """A gallery image for a car (the detail-page slider)."""

    car        = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="gallery")
    image      = models.ImageField(upload_to="cars/")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Image #{self.pk} for {self.car_id}"


class CarFeature(models.Model):
    """A single feature/highlight for a car (e.g. 'Bluetooth'), grouped by
    category so the front-end doesn't have to guess from the text."""

    car      = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="features")
    category = models.CharField(max_length=40, choices=FeatureCategory.choices, default=FeatureCategory.INTERIOR)
    text     = models.CharField(max_length=200)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"[{self.category}] {self.text}"


class Favourite(models.Model):
    """A car a user has saved/favourited, tied to their account."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favourites"
    )
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="favourited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "car"], name="unique_user_car_favourite")
        ]

    def __str__(self):
        return f"{self.user_id} → {self.car_id}"
