import os
import uuid

from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver


class SellMyCarEnquiry(models.Model):
    """A customer offering their car, with a chosen inspection slot.

    The partial unique constraint is the source of truth against double
    booking. The view turns a collision into a 409, and cancelling an enquiry
    frees its slot.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    reg = models.CharField(max_length=7)
    mileage = models.PositiveIntegerField()

    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=300)
    message = models.TextField(blank=True)

    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Sell my car enquiry"
        verbose_name_plural = "Sell my car enquiries"
        constraints = [
            models.UniqueConstraint(
                fields=["appointment_date", "appointment_time"],
                condition=~Q(status="cancelled"),
                name="unique_active_sell_my_car_slot",
            )
        ]

    def __str__(self):
        return f"{self.reg} — {self.name} ({self.appointment_date} {self.appointment_time:%H:%M})"

    @property
    def car_label(self):
        return " ".join(part for part in (self.make, self.model) if part)


def enquiry_image_path(instance, filename):
    """Media URLs are public, so the stored name must not be guessable."""
    extension = os.path.splitext(filename)[1].lower()
    return f"sell_my_car/{uuid.uuid4().hex}{extension}"


class SellMyCarImage(models.Model):
    enquiry = models.ForeignKey(SellMyCarEnquiry, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=enquiry_image_path)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Photo {self.pk} for enquiry {self.enquiry_id}"


@receiver(post_delete, sender=SellMyCarImage)
def delete_image_file(sender, instance, **kwargs):
    """Remove the customer's photo from storage, which Django doesn't do itself.

    Waits for the commit so a rolled-back delete keeps its file.
    """
    if instance.image:
        storage, name = instance.image.storage, instance.image.name
        transaction.on_commit(lambda: storage.delete(name), robust=True)
