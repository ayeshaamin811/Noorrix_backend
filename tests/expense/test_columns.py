import csv
import io
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.expense.models import ExpenseCar, ExpenseColumn, ExpenseColumnValue

COLUMNS_URL = '/api/expenses/columns/'
CARS_URL = '/api/expenses/cars/'
SUMMARY_URL = '/api/expenses/summary/'
EXPORT_URL = '/api/expenses/export/'
BUILT_IN_NAMES = [
    'Car', 'Status', 'Car Name', 'Date Added', 'Purchase', 'Delivery', 'MOT', 'Wash',
    'Denting/Painting', 'Oil Change/Coolant/Repairs', 'Fuel', 'Timing Chain', 'Electrical Work',
    'Brakes', 'Exhaust', 'Clutch and Gearbox', 'Other', 'Total Cost', 'Tyre Tread Depth (mm)',
    'Sale Price', 'Profit', 'Date Sold', 'Notes',
]
BASE_HEADER_COSTS = [
    'Car', 'Status', 'Date Added', 'Purchase', 'Delivery', 'MOT', 'Wash', 'Denting/Painting',
    'Oil Change/Coolant/Repairs', 'Fuel', 'Timing Chain', 'Electrical Work', 'Brakes', 'Exhaust',
    'Clutch and Gearbox', 'Other',
]
BASE_HEADER_TOTALS = ['Total Cost', 'Tyre Tread Depth (mm)', 'Sale Price', 'Profit', 'Date Sold', 'Notes']


@pytest.fixture
def make_column(db):
    def _make_column(name='Insurance', kind='cost'):
        return ExpenseColumn.objects.create(name=name, kind=kind)

    return _make_column


@pytest.fixture
def set_value(db):
    def _set_value(car, column, value):
        field = 'amount' if column.is_cost else 'text'
        return ExpenseColumnValue.objects.create(car=car, column=column, **{field: value})

    return _set_value


def car_url(car):
    return f'{CARS_URL}{car.id}/'


def column_url(column_id):
    return f'{COLUMNS_URL}{column_id}/'


def put_values(client, car, values):
    return client.put(car_url(car), {'custom_values': values}, format='json')


def read_rows(response):
    return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'), newline='')))


def stored(car, column):
    return ExpenseColumnValue.objects.filter(car=car, column=column).first()


@pytest.mark.django_db
class TestColumnAccess:
    def request(self, client, method, column):
        if method == 'get':
            return client.get(COLUMNS_URL)
        if method == 'post':
            return client.post(COLUMNS_URL, {'name': 'Tax', 'kind': 'info'}, format='json')
        return client.delete(column_url(column.id))

    @pytest.mark.parametrize('method', ['get', 'post', 'delete'])
    def test_no_token_is_401(self, api_client, make_column, method):
        assert self.request(api_client, method, make_column()).status_code == 401

    @pytest.mark.parametrize('method', ['get', 'post', 'delete'])
    def test_bad_token_is_401(self, api_client, make_column, method):
        api_client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')
        assert self.request(api_client, method, make_column()).status_code == 401

    @pytest.mark.parametrize('method', ['get', 'post', 'delete'])
    def test_customer_is_403_and_changes_nothing(self, auth_client, make_column, method):
        column = make_column()
        response = self.request(auth_client, method, column)
        assert response.status_code == 403
        assert list(ExpenseColumn.objects.values_list('id', flat=True)) == [column.id]

    @pytest.mark.parametrize('method, success', [('get', 200), ('post', 201), ('delete', 204)])
    def test_staff_succeeds(self, staff_client, make_column, method, success):
        assert self.request(staff_client, method, make_column()).status_code == success


def test_models_are_not_registered_in_admin():
    assert not admin.site.is_registered(ExpenseColumn)
    assert not admin.site.is_registered(ExpenseColumnValue)


@pytest.mark.django_db
class TestListColumns:
    def test_is_a_plain_array_oldest_first(self, staff_client, make_column):
        first = make_column('Insurance', 'cost')
        second = make_column('Colour', 'info')
        assert staff_client.get(COLUMNS_URL).json() == [
            {'id': first.id, 'name': 'Insurance', 'kind': 'cost'},
            {'id': second.id, 'name': 'Colour', 'kind': 'info'},
        ]

    def test_empty_is_an_empty_array(self, staff_client):
        assert staff_client.get(COLUMNS_URL).json() == []


@pytest.mark.django_db
class TestCreateColumn:
    @pytest.mark.parametrize('kind', ['cost', 'info'])
    def test_creates_a_column(self, staff_client, kind):
        response = staff_client.post(COLUMNS_URL, {'name': 'Insurance', 'kind': kind}, format='json')
        assert response.status_code == 201
        column = ExpenseColumn.objects.get()
        assert response.json() == {'id': column.id, 'name': 'Insurance', 'kind': kind}

    def test_trims_the_name(self, staff_client):
        response = staff_client.post(COLUMNS_URL, {'name': '  Insurance  ', 'kind': 'cost'}, format='json')
        assert response.json()['name'] == 'Insurance'

    def test_allows_30_characters(self, staff_client):
        response = staff_client.post(COLUMNS_URL, {'name': 'x' * 30, 'kind': 'info'}, format='json')
        assert response.status_code == 201

    @pytest.mark.parametrize(
        'body',
        [
            pytest.param({'name': '', 'kind': 'cost'}, id='blank'),
            pytest.param({'name': '    ', 'kind': 'cost'}, id='spaces'),
            pytest.param({'kind': 'cost'}, id='missing'),
            pytest.param({'name': 'x' * 31, 'kind': 'cost'}, id='too-long'),
        ],
    )
    def test_rejects_a_bad_name(self, staff_client, body):
        response = staff_client.post(COLUMNS_URL, body, format='json')
        assert response.status_code == 400
        assert list(response.json()) == ['name']
        assert not ExpenseColumn.objects.exists()

    @pytest.mark.parametrize('name', ['insurance', 'INSURANCE', ' InSuRaNcE '])
    def test_rejects_a_duplicate_in_any_case(self, staff_client, make_column, name):
        make_column('Insurance')
        response = staff_client.post(COLUMNS_URL, {'name': name, 'kind': 'info'}, format='json')
        assert response.status_code == 400
        assert list(response.json()) == ['name']
        assert ExpenseColumn.objects.count() == 1

    def test_two_people_adding_the_same_name_gives_400(self, staff_client, make_column):
        make_column('Insurance')
        with patch('apps.expense.serializers.ExpenseColumn.objects.filter') as no_match_seen:
            no_match_seen.return_value.exists.return_value = False
            response = staff_client.post(COLUMNS_URL, {'name': 'insurance', 'kind': 'info'}, format='json')
        assert response.status_code == 400
        assert list(response.json()) == ['name']
        assert ExpenseColumn.objects.count() == 1

    def test_rejects_every_built_in_name_in_any_case(self, staff_client):
        for name in BUILT_IN_NAMES:
            for attempt in (name, name.lower(), name.upper()):
                response = staff_client.post(COLUMNS_URL, {'name': attempt, 'kind': 'cost'}, format='json')
                assert response.status_code == 400, attempt
                assert list(response.json()) == ['name'], attempt
        assert not ExpenseColumn.objects.exists()

    @pytest.mark.parametrize('body', [{'name': 'Tax', 'kind': 'other'}, {'name': 'Tax', 'kind': ''}, {'name': 'Tax'}])
    def test_rejects_a_bad_kind(self, staff_client, body):
        response = staff_client.post(COLUMNS_URL, body, format='json')
        assert response.status_code == 400
        assert list(response.json()) == ['kind']


@pytest.mark.django_db
class TestDeleteColumn:
    def test_removes_the_column_and_its_values(self, staff_client, make_car, make_column, set_value):
        column = make_column()
        set_value(make_car(), column, Decimal('10.00'))
        set_value(make_car(), column, Decimal('20.00'))
        response = staff_client.delete(column_url(column.id))
        assert response.status_code == 204
        assert not ExpenseColumn.objects.exists()
        assert not ExpenseColumnValue.objects.exists()

    def test_leaves_other_columns_and_cars_alone(self, staff_client, make_car, make_column, set_value):
        car = make_car()
        gone, kept = make_column('Gone'), make_column('Kept')
        set_value(car, gone, Decimal('1.00'))
        set_value(car, kept, Decimal('2.00'))
        staff_client.delete(column_url(gone.id))
        assert ExpenseCar.objects.filter(pk=car.pk).exists()
        assert stored(car, kept).amount == Decimal('2.00')

    def test_unknown_id_is_404(self, staff_client):
        assert staff_client.delete(column_url(999999)).status_code == 404

    @pytest.mark.parametrize('method', ['get', 'put', 'patch'])
    def test_other_methods_are_not_allowed(self, staff_client, make_column, method):
        column = make_column()
        assert getattr(staff_client, method)(column_url(column.id)).status_code == 405


@pytest.mark.django_db
class TestCarJson:
    def test_list_has_values_keyed_by_string_id(self, staff_client, make_car, make_column, set_value):
        car = make_car()
        cost, info = make_column('Insurance', 'cost'), make_column('Colour', 'info')
        set_value(car, cost, Decimal('250.00'))
        set_value(car, info, 'Blue')
        body = staff_client.get(CARS_URL).json()[0]
        assert body['custom_values'] == {str(cost.id): '250.00', str(info.id): 'Blue'}

    def test_is_empty_when_there_are_no_values(self, staff_client, make_car, make_column):
        make_car()
        make_column()
        assert staff_client.get(CARS_URL).json()[0]['custom_values'] == {}

    def test_post_returns_empty_values(self, staff_client, make_column):
        make_column()
        response = staff_client.post(CARS_URL, {'name': 'Ford Fiesta'}, format='json')
        assert response.status_code == 201
        assert response.json()['custom_values'] == {}

    def test_post_cannot_set_values(self, staff_client, make_column):
        column = make_column()
        response = staff_client.post(
            CARS_URL, {'name': 'Ford Fiesta', 'custom_values': {str(column.id): 5}}, format='json'
        )
        assert response.status_code == 201
        assert response.json()['custom_values'] == {}
        assert not ExpenseColumnValue.objects.exists()

    def test_put_returns_the_saved_values(self, staff_client, make_car, make_column):
        car = make_car()
        cost, info = make_column('Insurance', 'cost'), make_column('Colour', 'info')
        response = put_values(staff_client, car, {str(cost.id): 250.5, str(info.id): 'Blue'})
        assert response.status_code == 200
        assert response.json()['custom_values'] == {str(cost.id): '250.50', str(info.id): 'Blue'}

    @pytest.mark.parametrize('url', [CARS_URL, EXPORT_URL, SUMMARY_URL])
    def test_does_not_run_one_query_per_car(self, staff_client, make_car, make_column, set_value, url):
        cost, info = make_column('Insurance', 'cost'), make_column('Colour', 'info')

        def add_cars(count):
            for _ in range(count):
                car = make_car()
                set_value(car, cost, Decimal('1.00'))
                set_value(car, info, 'Blue')

        add_cars(2)
        with CaptureQueriesContext(connection) as few:
            assert staff_client.get(url).status_code == 200
        add_cars(8)
        with CaptureQueriesContext(connection) as many:
            assert staff_client.get(url).status_code == 200
        assert len(many) == len(few)


@pytest.mark.django_db
class TestPutCustomValues:
    def test_saves_cost_and_info_values(self, staff_client, make_car, make_column):
        car = make_car()
        cost, info = make_column('Insurance', 'cost'), make_column('Colour', 'info')
        assert put_values(staff_client, car, {str(cost.id): 250.5, str(info.id): ' Blue '}).status_code == 200
        assert stored(car, cost).amount == Decimal('250.50')
        assert stored(car, cost).text == ''
        assert stored(car, info).text == 'Blue'
        assert stored(car, info).amount is None

    def test_changes_an_existing_value_without_a_second_row(self, staff_client, make_car, make_column, set_value):
        car, column = make_car(), make_column()
        set_value(car, column, Decimal('1.00'))
        put_values(staff_client, car, {str(column.id): '2.50'})
        assert ExpenseColumnValue.objects.count() == 1
        assert stored(car, column).amount == Decimal('2.50')

    @pytest.mark.parametrize('blank', [None, '', '   '])
    @pytest.mark.parametrize('kind, existing', [('cost', Decimal('1.00')), ('info', 'Blue')])
    def test_blank_removes_the_row(self, staff_client, make_car, make_column, set_value, kind, existing, blank):
        car, column = make_car(), make_column(kind=kind)
        set_value(car, column, existing)
        response = put_values(staff_client, car, {str(column.id): blank})
        assert response.status_code == 200
        assert response.json()['custom_values'] == {}
        assert stored(car, column) is None

    def test_blank_for_a_value_that_never_existed_is_fine(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column()
        assert put_values(staff_client, car, {str(column.id): None}).status_code == 200
        assert not ExpenseColumnValue.objects.exists()

    def test_zero_is_a_real_cost(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column()
        response = put_values(staff_client, car, {str(column.id): 0})
        assert response.json()['custom_values'] == {str(column.id): '0.00'}
        assert stored(car, column).amount == Decimal('0.00')

    def test_absent_leaves_values_alone(self, staff_client, make_car, make_column, set_value):
        car, column = make_car(), make_column()
        set_value(car, column, Decimal('1.00'))
        response = staff_client.put(car_url(car), {'wash': 10}, format='json')
        assert response.status_code == 200
        assert response.json()['custom_values'] == {str(column.id): '1.00'}
        assert stored(car, column).amount == Decimal('1.00')

    def test_empty_object_leaves_values_alone(self, staff_client, make_car, make_column, set_value):
        car, column = make_car(), make_column()
        set_value(car, column, Decimal('1.00'))
        assert put_values(staff_client, car, {}).status_code == 200
        assert stored(car, column).amount == Decimal('1.00')

    @pytest.mark.parametrize('unknown', ['999999', 'abc', '', '99999999999999999999999'])
    def test_ignores_unknown_ids(self, staff_client, make_car, make_column, unknown):
        car, column = make_car(), make_column()
        response = put_values(staff_client, car, {unknown: 5, str(column.id): 7})
        assert response.status_code == 200
        assert list(response.json()['custom_values']) == [str(column.id)]
        assert ExpenseColumnValue.objects.count() == 1

    def test_column_deleted_during_the_save_is_ignored(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column()
        column_id = column.id
        real_select = ExpenseColumn.objects.select_for_update

        def deleted_first():
            ExpenseColumn.objects.filter(pk=column_id).delete()
            return real_select()

        with patch.object(ExpenseColumn.objects, 'select_for_update', side_effect=deleted_first):
            response = put_values(staff_client, car, {str(column_id): 7})
        assert response.status_code == 200
        assert not ExpenseColumnValue.objects.exists()

    @pytest.mark.parametrize(
        'value, message',
        [
            (-1, 'Enter a number of 0 or more.'),
            ('abc', 'Enter a number of 0 or more.'),
            (True, 'Enter a number of 0 or more.'),
            ('NaN', 'Enter a number of 0 or more.'),
            ([1], 'Enter a number of 0 or more.'),
            (12.345, 'Enter a number with up to 2 decimal places.'),
            (123456789, 'Enter a number with at most 10 digits.'),
            ('123456789.12', 'Enter a number with at most 10 digits.'),
        ],
    )
    def test_bad_cost_is_reported_under_its_column(self, staff_client, make_car, make_column, value, message):
        car, column = make_car(), make_column()
        response = put_values(staff_client, car, {str(column.id): value})
        assert response.status_code == 400
        assert response.json() == {'custom_values': {str(column.id): [message]}}
        assert not ExpenseColumnValue.objects.exists()

    def test_largest_cost_is_allowed(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column()
        assert put_values(staff_client, car, {str(column.id): '99999999.99'}).status_code == 200

    def test_info_length_limit(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column(kind='info')
        assert put_values(staff_client, car, {str(column.id): 'x' * 255}).status_code == 200
        response = put_values(staff_client, car, {str(column.id): 'x' * 256})
        assert response.status_code == 400
        assert list(response.json()['custom_values']) == [str(column.id)]
        assert isinstance(response.json()['custom_values'][str(column.id)][0], str)

    def test_reports_every_bad_column_and_saves_none(self, staff_client, make_car, make_column):
        car = make_car()
        good, bad_cost, bad_info = make_column('Good'), make_column('Bad'), make_column('Long', 'info')
        response = put_values(
            staff_client, car, {str(good.id): 5, str(bad_cost.id): -1, str(bad_info.id): 'x' * 256}
        )
        assert response.status_code == 400
        assert set(response.json()['custom_values']) == {str(bad_cost.id), str(bad_info.id)}
        assert not ExpenseColumnValue.objects.exists()

    def test_bad_value_does_not_save_the_car_either(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column()
        response = staff_client.put(car_url(car), {'wash': 10, 'custom_values': {str(column.id): -1}}, format='json')
        assert response.status_code == 400
        car.refresh_from_db()
        assert car.wash is None

    @pytest.mark.parametrize('body', ['text', 5, [1, 2]])
    def test_custom_values_must_be_an_object(self, staff_client, make_car, body):
        response = put_values(staff_client, make_car(), body)
        assert response.status_code == 400
        assert list(response.json()) == ['custom_values']

    def test_car_and_values_save_in_one_transaction(self, staff_client, make_car, make_column):
        car, column = make_car(), make_column()
        staff_client.raise_request_exception = False
        with patch.object(ExpenseColumnValue.objects, 'update_or_create', side_effect=RuntimeError('boom')):
            response = staff_client.put(car_url(car), {'wash': 10, 'custom_values': {str(column.id): 5}}, format='json')
        assert response.status_code == 500
        car.refresh_from_db()
        assert car.wash is None


@pytest.mark.django_db
class TestSummaryWithColumns:
    def test_cost_column_adds_to_money_tied_up(self, staff_client, make_car, make_column, set_value):
        car = make_car(purchase=Decimal('100.00'))
        set_value(car, make_column(), Decimal('25.50'))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '125.50'

    def test_cost_column_reduces_profit(self, staff_client, make_car, make_column, set_value):
        car = make_car(status='sold', sale_price=Decimal('500.00'), purchase=Decimal('100.00'))
        set_value(car, make_column(), Decimal('25.50'))
        assert staff_client.get(SUMMARY_URL).json()['profit_from_sold'] == '374.50'

    def test_info_column_changes_nothing(self, staff_client, make_car, make_column, set_value):
        available = make_car(purchase=Decimal('100.00'))
        sold = make_car(status='sold', sale_price=Decimal('500.00'), purchase=Decimal('100.00'))
        column = make_column('Colour', 'info')
        set_value(available, column, '999')
        set_value(sold, column, '999')
        body = staff_client.get(SUMMARY_URL).json()
        assert body['money_tied_up'] == '100.00'
        assert body['profit_from_sold'] == '400.00'

    def test_only_available_cars_count_as_tied_up(self, staff_client, make_car, make_column, set_value):
        sold = make_car(status='sold', sale_price=Decimal('500.00'))
        set_value(sold, make_column(), Decimal('25.00'))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '0.00'

    def test_sold_car_with_no_sale_price_adds_nothing(self, staff_client, make_car, make_column, set_value):
        sold = make_car(status='sold')
        set_value(sold, make_column(), Decimal('25.00'))
        assert staff_client.get(SUMMARY_URL).json()['profit_from_sold'] == '0.00'

    def test_sums_pennies_exactly(self, staff_client, make_car, make_column, set_value):
        first, second = make_column('One'), make_column('Two')
        for _ in range(10):
            car = make_car()
            set_value(car, first, Decimal('0.10'))
            set_value(car, second, Decimal('0.20'))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '3.00'

    def test_deleting_a_cost_column_removes_it_from_totals(self, staff_client, make_car, make_column, set_value):
        column = make_column()
        set_value(make_car(purchase=Decimal('100.00')), column, Decimal('25.00'))
        staff_client.delete(column_url(column.id))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '100.00'

    def test_total_cost_is_a_decimal(self, make_car, make_column, set_value):
        car = make_car(wash=Decimal('0.10'))
        set_value(car, make_column(), Decimal('0.20'))
        assert isinstance(car.total_cost, Decimal)
        assert car.total_cost == Decimal('0.30')


@pytest.mark.django_db
class TestExportWithColumns:
    def test_column_order(self, staff_client, make_column):
        make_column('Tax', 'cost')
        make_column('Colour', 'info')
        make_column('Insurance', 'cost')
        make_column('Keys', 'info')
        assert read_rows(staff_client.get(EXPORT_URL))[0] == [
            *BASE_HEADER_COSTS,
            'Tax',
            'Insurance',
            *BASE_HEADER_TOTALS,
            'Colour',
            'Keys',
        ]

    def test_row_values_line_up_with_the_header(self, staff_client, make_car, make_column, set_value):
        car = make_car(purchase=Decimal('100.00'), sale_price=Decimal('500.00'), status='sold', notes='Note')
        tax, insurance = make_column('Tax'), make_column('Insurance')
        colour, keys = make_column('Colour', 'info'), make_column('Keys', 'info')
        set_value(car, insurance, Decimal('1234.5'))
        set_value(car, colour, 'Blue')
        header, row = read_rows(staff_client.get(EXPORT_URL))
        cells = dict(zip(header, row))
        assert cells['Tax'] == ''
        assert cells['Insurance'] == '1234.50'
        assert cells['Colour'] == 'Blue'
        assert cells['Keys'] == ''
        assert cells['Notes'] == 'Note'

    def test_totals_include_cost_columns_only(self, staff_client, make_car, make_column, set_value):
        car = make_car(purchase=Decimal('100.00'), sale_price=Decimal('500.00'), status='sold')
        set_value(car, make_column('Tax'), Decimal('25.50'))
        set_value(car, make_column('Colour', 'info'), '999')
        header, row = read_rows(staff_client.get(EXPORT_URL))
        cells = dict(zip(header, row))
        assert cells['Total Cost'] == '125.50'
        assert cells['Profit'] == '374.50'

    @pytest.mark.parametrize('value', ['=SUM(A1)', '+44', '-5', '@risk'])
    def test_prefixes_info_values(self, staff_client, make_car, make_column, set_value, value):
        set_value(make_car(), make_column('Colour', 'info'), value)
        header, row = read_rows(staff_client.get(EXPORT_URL))
        assert dict(zip(header, row))['Colour'] == f"'{value}"

    @pytest.mark.parametrize('kind', ['cost', 'info'])
    @pytest.mark.parametrize('name', ['=Tax', '+Tax', '-Tax', '@Tax'])
    def test_prefixes_column_names(self, staff_client, make_column, kind, name):
        make_column(name, kind)
        assert f"'{name}" in read_rows(staff_client.get(EXPORT_URL))[0]

    def test_leaves_ordinary_text_alone(self, staff_client, make_car, make_column, set_value):
        set_value(make_car(), make_column('Colour', 'info'), 'a=b')
        header, row = read_rows(staff_client.get(EXPORT_URL))
        assert dict(zip(header, row))['Colour'] == 'a=b'

    def test_filters_still_apply(self, staff_client, make_car, make_column, set_value):
        column = make_column('Colour', 'info')
        set_value(make_car(name='Ford', status='sold'), column, 'Blue')
        set_value(make_car(name='BMW'), column, 'Red')
        rows = read_rows(staff_client.get(EXPORT_URL, {'status': 'sold'}))
        assert len(rows) == 2
        assert rows[1][0] == 'Ford'
