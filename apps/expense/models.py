from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

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
        built_in = sum((getattr(self, field) or Decimal('0') for field in COST_FIELDS), Decimal('0'))
        return built_in + self._extra_column_costs()

    def _extra_column_costs(self):
        if self.pk is None:  # A reverse relation can't be read before the first save.
            return Decimal('0')
        return sum(
            (value.amount or Decimal('0') for value in self.column_values.all() if value.column.is_cost),
            Decimal('0'),
        )

    @property
    def profit(self):
        """None when there is no sale price, so a blank price never reads as a loss."""
        if self.sale_price is None:
            return None
        return self.sale_price - self.total_cost


class ExpenseColumn(models.Model):
    """A column staff added to the cars table themselves."""

    KIND_COST = 'cost'
    KIND_INFO = 'info'
    KIND_CHOICES = [
        (KIND_COST, 'Cost'),
        (KIND_INFO, 'Info'),
    ]

    name = models.CharField(max_length=30)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(Lower('name'), name='unique_expense_column_name_ignoring_case'),
        ]

    def __str__(self):
        return self.name

    @property
    def is_cost(self):
        return self.kind == self.KIND_COST


class ExpenseColumnValue(models.Model):
    """One car's value in one extra column. A blank value has no row."""

    car = models.ForeignKey(ExpenseCar, on_delete=models.CASCADE, related_name='column_values')
    column = models.ForeignKey(ExpenseColumn, on_delete=models.CASCADE, related_name='values')
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    text = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['car', 'column'], name='unique_expense_value_per_car_and_column'),
        ]

    def __str__(self):
        return f'{self.column}: {self.api_value}'

    @property
    def api_value(self):
        return f'{self.amount:.2f}' if self.column.is_cost else self.text
