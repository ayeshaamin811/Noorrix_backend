import csv
from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import COST_FIELDS, ExpenseCar
from .permissions import CanUseExpenses
from .serializers import (
    ExpenseCarCreateSerializer,
    ExpenseCarSerializer,
    ExpenseCarUpdateSerializer,
    ExpenseSummarySerializer,
)

CSV_FILENAME = 'noorrix-car-expenses.csv'
CSV_HEADER = [
    'Car',
    'Status',
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
]
FORMULA_PREFIXES = ('=', '+', '-', '@')

CAR_FILTER_PARAMETERS = [
    OpenApiParameter(
        'status',
        OpenApiTypes.STR,
        enum=[ExpenseCar.STATUS_AVAILABLE, ExpenseCar.STATUS_SOLD],
        description='Leave out for all cars.',
    ),
    OpenApiParameter(
        'search',
        OpenApiTypes.STR,
        description='Case-insensitive match on name or notes.',
    ),
]


def filter_cars(queryset, params):
    status = params.get('status', '').strip().lower()
    if status:
        queryset = queryset.filter(status=status)

    search = params.get('search', '').strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(notes__icontains=search))

    return queryset


def csv_number(value):
    return '' if value is None else f'{value:.2f}'


def csv_date(value):
    return value.strftime('%d/%m/%Y') if value else ''


def csv_text(value):
    """Stop spreadsheets from running a name or note as a formula."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def csv_row(car):
    return [
        csv_text(car.name),
        car.get_status_display(),
        csv_date(car.date_added),
        *(csv_number(getattr(car, field)) for field in COST_FIELDS),
        csv_number(car.total_cost),
        csv_number(car.tyre_tread_depth),
        csv_number(car.sale_price),
        csv_number(car.profit),
        csv_date(car.date_sold),
        csv_text(car.notes),
    ]


@extend_schema_view(
    get=extend_schema(
        tags=['Expenses'],
        summary='List tracker cars, newest first',
        parameters=CAR_FILTER_PARAMETERS,
        responses=ExpenseCarSerializer(many=True),
    ),
    post=extend_schema(
        tags=['Expenses'],
        summary='Add a tracker car',
        request=ExpenseCarCreateSerializer,
        responses={201: ExpenseCarSerializer},
    ),
)
class ExpenseCarListCreateView(generics.ListCreateAPIView):
    permission_classes = [CanUseExpenses]
    pagination_class = None

    def get_queryset(self):
        return filter_cars(ExpenseCar.objects.all(), self.request.query_params)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ExpenseCarCreateSerializer
        return ExpenseCarSerializer


@extend_schema_view(
    put=extend_schema(
        tags=['Expenses'],
        summary='Save a tracker car',
        request=ExpenseCarUpdateSerializer,
        responses=ExpenseCarSerializer,
    ),
)
class ExpenseCarUpdateView(generics.UpdateAPIView):
    permission_classes = [CanUseExpenses]
    queryset = ExpenseCar.objects.all()
    serializer_class = ExpenseCarUpdateSerializer
    http_method_names = ['put', 'options']


@extend_schema(
    tags=['Expenses'],
    summary='The four summary cards, always covering every car',
    responses=ExpenseSummarySerializer,
)
class ExpenseSummaryView(APIView):
    permission_classes = [CanUseExpenses]

    def get(self, request):
        cars = list(ExpenseCar.objects.all())
        in_stock = [car for car in cars if car.status == ExpenseCar.STATUS_AVAILABLE]
        sold = [car for car in cars if car.status == ExpenseCar.STATUS_SOLD]

        summary = {
            'cars_in_stock': len(in_stock),
            'cars_sold': len(sold),
            'money_tied_up': sum((car.total_cost for car in in_stock), Decimal('0')),
            'profit_from_sold': sum(
                (car.profit for car in sold if car.profit is not None),
                Decimal('0'),
            ),
        }
        return Response(ExpenseSummarySerializer(summary).data)


@extend_schema(
    tags=['Expenses'],
    summary='Download the tracker cars as CSV',
    parameters=CAR_FILTER_PARAMETERS,
    responses={(200, 'text/csv'): OpenApiTypes.BINARY},
)
class ExpenseExportView(APIView):
    permission_classes = [CanUseExpenses]

    def perform_content_negotiation(self, request, force=False):
        # Without force, a client sending Accept: text/csv gets a 406, because
        # only the JSON renderers are registered.
        return super().perform_content_negotiation(request, force=True)

    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{CSV_FILENAME}"'
        # The byte order mark makes Excel read the file as UTF-8.
        response.write('﻿')

        writer = csv.writer(response)
        writer.writerow(CSV_HEADER)
        for car in filter_cars(ExpenseCar.objects.all(), request.query_params):
            writer.writerow(csv_row(car))
        return response
