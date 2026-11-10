from decimal import Decimal

from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import COST_FIELDS, ExpenseCar, ExpenseColumn, ExpenseColumnValue

BUILT_IN_COLUMN_NAMES = frozenset(
    name.casefold()
    for name in (
        'Car',
        'Status',
        'Car Name',
        'Date Added',
        'Purchase',
        'Delivery',
        'MOT',
        'Wash',
        'Denting/Painting',
        'Oil Change/Coolant/Repairs',
        'Fuel',
        'Timing Chain',
        'Electrical Work',
        'Brakes',
        'Exhaust',
        'Clutch and Gearbox',
        'Other',
        'Total Cost',
        'Tyre Tread Depth (mm)',
        'Sale Price',
        'Profit',
        'Date Sold',
        'Notes',
    )
)
COLUMN_NAME_TAKEN = 'A column with this name already exists.'
COST_VALUE_ERROR = 'Enter a number of 0 or more.'

COST_VALUE_FIELD = serializers.DecimalField(
    max_digits=10,
    decimal_places=2,
    min_value=Decimal('0'),
    error_messages={
        'invalid': COST_VALUE_ERROR,
        'min_value': COST_VALUE_ERROR,
        'max_string_length': COST_VALUE_ERROR,
        'max_digits': 'Enter a number with at most 10 digits.',
        'max_whole_digits': 'Enter a number with at most 10 digits.',
        'max_decimal_places': 'Enter a number with up to 2 decimal places.',
    },
)
INFO_VALUE_FIELD = serializers.CharField(
    max_length=255,
    error_messages={
        'invalid': 'Enter text of up to 255 characters.',
        'max_length': 'Enter text of up to 255 characters.',
    },
)


@extend_schema_field(
    {'type': 'object', 'additionalProperties': {'type': 'string', 'nullable': True}}
)
class CustomValuesField(serializers.Field):
    """A car's extra column values, keyed by column id as a string."""

    default_error_messages = {'not_an_object': 'Expected an object of column values.'}

    def to_representation(self, car):
        return {str(value.column_id): value.api_value for value in car.column_values.all()}

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            self.fail('not_an_object')

        columns = {str(column.pk): column for column in ExpenseColumn.objects.all()}
        cleaned = {}
        errors = {}
        for column_id, raw_value in data.items():
            column = columns.get(column_id)
            if column is None:  # Another user may have just deleted it.
                continue
            try:
                cleaned[column] = self.clean_value(column, raw_value)
            except serializers.ValidationError as exc:
                errors[column_id] = exc.detail

        if errors:
            raise serializers.ValidationError(errors)
        return {'custom_values': cleaned}

    @staticmethod
    def clean_value(column, raw_value):
        """Return the value to store, or None to remove it."""
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            return None
        field = COST_VALUE_FIELD if column.is_cost else INFO_VALUE_FIELD
        return field.run_validation(raw_value)


def save_custom_values(car, custom_values):
    # The lock stops a column being deleted before its value is written.
    live_column_ids = set(
        ExpenseColumn.objects.select_for_update()
        .filter(pk__in=[column.pk for column in custom_values])
        .values_list('pk', flat=True)
    )
    for column, value in custom_values.items():
        if column.pk not in live_column_ids:
            continue
        if value is None:
            ExpenseColumnValue.objects.filter(car=car, column=column).delete()
        else:
            defaults = {'amount': value, 'text': ''} if column.is_cost else {'amount': None, 'text': value}
            ExpenseColumnValue.objects.update_or_create(car=car, column=column, defaults=defaults)


class ExpenseCarSerializer(serializers.ModelSerializer):
    """The full car JSON returned by the list, POST and PUT responses."""

    custom_values = CustomValuesField(source='*', read_only=True)

    class Meta:
        model = ExpenseCar
        fields = [
            'id',
            'name',
            'status',
            'date_added',
            'date_sold',
            *COST_FIELDS,
            'tyre_tread_depth',
            'sale_price',
            'notes',
            'custom_values',
        ]


class ExpenseCarCreateSerializer(ExpenseCarSerializer):
    """POST accepts only the Add Car fields. New cars always start as available."""

    class Meta(ExpenseCarSerializer.Meta):
        read_only_fields = [
            field for field in ExpenseCarSerializer.Meta.fields
            if field not in ('name', 'date_added', 'purchase')
        ]


class ExpenseCarUpdateSerializer(ExpenseCarSerializer):
    """PUT never sends name, and cars cannot be renamed, so name is read-only."""

    custom_values = CustomValuesField(source='*', required=False)

    class Meta(ExpenseCarSerializer.Meta):
        read_only_fields = ['name']

    def update(self, instance, validated_data):
        custom_values = validated_data.pop('custom_values', None)
        with transaction.atomic():
            car = super().update(instance, validated_data)
            if custom_values:
                save_custom_values(car, custom_values)
        return car


class ExpenseColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseColumn
        fields = ['id', 'name', 'kind']

    def validate_name(self, value):
        if value.casefold() in BUILT_IN_COLUMN_NAMES:
            raise serializers.ValidationError('This name is used by a built-in column.')
        if ExpenseColumn.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(COLUMN_NAME_TAKEN)
        return value

    def create(self, validated_data):
        # The database constraint catches two people adding the same name at once.
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'name': [COLUMN_NAME_TAKEN]}) from None


class ExpenseSummarySerializer(serializers.Serializer):
    cars_in_stock = serializers.IntegerField()
    cars_sold = serializers.IntegerField()
    money_tied_up = serializers.DecimalField(max_digits=None, decimal_places=2)
    profit_from_sold = serializers.DecimalField(max_digits=None, decimal_places=2)
