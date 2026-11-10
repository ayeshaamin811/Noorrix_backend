from rest_framework import serializers

from .models import COST_FIELDS, ExpenseCar


class ExpenseCarSerializer(serializers.ModelSerializer):
    """The full car JSON returned by the list, POST and PUT responses."""

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

    class Meta(ExpenseCarSerializer.Meta):
        read_only_fields = ['name']


class ExpenseSummarySerializer(serializers.Serializer):
    cars_in_stock = serializers.IntegerField()
    cars_sold = serializers.IntegerField()
    money_tied_up = serializers.DecimalField(max_digits=None, decimal_places=2)
    profit_from_sold = serializers.DecimalField(max_digits=None, decimal_places=2)
