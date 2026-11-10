from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

# The fields that make up Total Cost. tyre_tread_depth and sale_price are
# deliberately not here.
COST_FIELDS = (
    'purchase',
    'delivery',
    'mot',
    'wash',
    'denting_painting',
    'oil_coolant_repairs',
    'fuel',
    'timing_chain',
    'electrical_work',
    'brakes',
    'exhaust',
    'clutch_gearbox',
    'other',
)


def money_field():
    return models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )


class ExpenseCar(models.Model):
    STATUS_AVAILABLE = 'available'
    STATUS_SOLD = 'sold'
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_SOLD, 'Sold'),
    ]

    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    date_added = models.DateField(null=True, blank=True)
    date_sold = models.DateField(null=True, blank=True)

    purchase = money_field()
    delivery = money_field()
    mot = money_field()
    wash = money_field()
    denting_painting = money_field()
    oil_coolant_repairs = money_field()
    fuel = money_field()
    timing_chain = money_field()
    electrical_work = money_field()
    brakes = money_field()
    exhaust = money_field()
    clutch_gearbox = money_field()
    other = money_field()

    sale_price = money_field()
    tyre_tread_depth = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # id breaks ties, because two rows can share a created_at timestamp.
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.name

    @property
    def total_cost(self):
        return sum((getattr(self, field) or Decimal('0') for field in COST_FIELDS), Decimal('0'))

    @property
    def profit(self):
        """None when there is no sale price, so a blank price never reads as a loss."""
        if self.sale_price is None:
            return None
        return self.sale_price - self.total_cost
