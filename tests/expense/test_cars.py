from datetime import date
from decimal import Decimal

import pytest

from apps.expense.models import COST_FIELDS, ExpenseCar

CARS_URL = '/api/expenses/cars/'
CAR_KEYS = [
    'id', 'name', 'status', 'date_added', 'date_sold',
    'purchase', 'delivery', 'mot', 'wash', 'denting_painting', 'oil_coolant_repairs', 'fuel',
    'timing_chain', 'electrical_work', 'brakes', 'exhaust', 'clutch_gearbox', 'other',
    'tyre_tread_depth', 'sale_price', 'notes', 'custom_values',
]

# The exact shape the Edit dialog sends: never a name, numbers as JSON numbers.
PUT_BODY = {
    'status': 'sold',
    'date_added': '2026-10-06',
    'date_sold': '2026-11-01',
    'sale_price': 17495,
    'tyre_tread_depth': 4.9,
    'notes': 'HPI clear. Two keys.',
    'purchase': 14300,
    'delivery': 220,
    'mot': 54.85,
    'wash': 35,
    'denting_painting': 420,
    'oil_coolant_repairs': 189.99,
    'fuel': 55,
    'timing_chain': None,
    'electrical_work': None,
    'brakes': None,
    'exhaust': None,
    'clutch_gearbox': None,
    'other': 95,
}


def detail_url(car):
    return f'{CARS_URL}{car.id}/'


def ids(response):
    return [car['id'] for car in response.json()]


@pytest.mark.django_db
class TestList:
    def test_is_a_plain_array_with_no_pagination(self, staff_client, make_car):
        for _ in range(60):
            make_car()
        body = staff_client.get(CARS_URL).json()
        assert isinstance(body, list)
        assert len(body) == 60

    def test_is_newest_first(self, staff_client, make_car):
        first, second, third = make_car(), make_car(), make_car()
        assert ids(staff_client.get(CARS_URL)) == [third.id, second.id, first.id]

    def test_newest_first_holds_when_timestamps_tie(self, staff_client, make_car):
        first, second, third = make_car(), make_car(), make_car()
        ExpenseCar.objects.update(created_at=first.created_at)
        assert ids(staff_client.get(CARS_URL)) == [third.id, second.id, first.id]

    def test_car_json_shape_and_formats(self, staff_client, make_car):
        car = make_car(
            date_added=date(2026, 10, 6),
            purchase=Decimal('14300.00'),
            tyre_tread_depth=Decimal('4.90'),
            sale_price=Decimal('17495.00'),
            notes='HPI clear.',
        )
        body = staff_client.get(CARS_URL).json()[0]
        assert list(body) == CAR_KEYS
        assert body['id'] == car.id
        assert body['status'] == 'available'
        assert body['date_added'] == '2026-10-06'
        assert body['date_sold'] is None
        assert body['purchase'] == '14300.00'
        assert body['tyre_tread_depth'] == '4.90'
        assert body['sale_price'] == '17495.00'
        assert body['timing_chain'] is None
        assert body['notes'] == 'HPI clear.'

    def test_does_not_expose_calculated_or_internal_fields(self, staff_client, make_car):
        make_car()
        body = staff_client.get(CARS_URL).json()[0]
        for key in ('total_cost', 'profit', 'days_in_stock', 'created_at', 'updated_at'):
            assert key not in body

    @pytest.mark.parametrize('status, expected', [('available', 'available'), ('sold', 'sold')])
    def test_status_filter(self, staff_client, make_car, status, expected):
        cars = {
            'available': make_car(status='available'),
            'sold': make_car(status='sold'),
        }
        assert ids(staff_client.get(CARS_URL, {'status': status})) == [cars[expected].id]

    def test_no_status_returns_all(self, staff_client, make_car):
        make_car(status='available')
        make_car(status='sold')
        assert len(staff_client.get(CARS_URL).json()) == 2

    def test_empty_status_and_search_return_all(self, staff_client, make_car):
        make_car(status='available')
        make_car(status='sold')
        assert len(staff_client.get(CARS_URL, {'status': '', 'search': ''}).json()) == 2

    def test_unknown_status_returns_nothing(self, staff_client, make_car):
        make_car()
        assert staff_client.get(CARS_URL, {'status': 'reserved'}).json() == []

    def test_search_matches_name_case_insensitively(self, staff_client, make_car):
        match = make_car(name='Ford FIESTA')
        make_car(name='BMW 320d')
        assert ids(staff_client.get(CARS_URL, {'search': 'fiesta'})) == [match.id]

    def test_search_matches_notes_case_insensitively(self, staff_client, make_car):
        match = make_car(name='Ford Focus', notes='Needs NEW tyres')
        make_car(name='BMW 320d', notes='HPI clear')
        assert ids(staff_client.get(CARS_URL, {'search': 'new tyres'})) == [match.id]

    def test_status_and_search_combine(self, staff_client, make_car):
        match = make_car(name='Ford Fiesta', status='sold')
        make_car(name='Ford Fiesta', status='available')
        make_car(name='BMW 320d', status='sold')
        response = staff_client.get(CARS_URL, {'status': 'sold', 'search': 'ford'})
        assert ids(response) == [match.id]


@pytest.mark.django_db
class TestCreate:
    def test_creates_an_available_car_and_returns_full_json(self, staff_client):
        response = staff_client.post(
            CARS_URL,
            {'name': 'Ford Fiesta 1.0', 'date_added': '2026-11-09', 'purchase': 5000.5},
            format='json',
        )
        assert response.status_code == 201
        body = response.json()
        assert list(body) == CAR_KEYS
        assert body['name'] == 'Ford Fiesta 1.0'
        assert body['status'] == 'available'
        assert body['date_added'] == '2026-11-09'
        assert body['purchase'] == '5000.50'
        assert body['notes'] == ''
        car = ExpenseCar.objects.get(pk=body['id'])
        assert car.status == ExpenseCar.STATUS_AVAILABLE
        assert car.purchase == Decimal('5000.50')

    def test_accepts_null_purchase_and_date(self, staff_client):
        response = staff_client.post(
            CARS_URL,
            {'name': 'Ford Fiesta', 'date_added': None, 'purchase': None},
            format='json',
        )
        assert response.status_code == 201
        assert response.json()['purchase'] is None
        assert response.json()['date_added'] is None

    def test_cannot_set_other_fields(self, staff_client):
        response = staff_client.post(
            CARS_URL,
            {'name': 'Ford Fiesta', 'status': 'sold', 'sale_price': 9000, 'wash': 10},
            format='json',
        )
        assert response.status_code == 201
        body = response.json()
        assert body['status'] == 'available'
        assert body['sale_price'] is None
        assert body['wash'] is None

    @pytest.mark.parametrize('name', ['', '   '])
    def test_rejects_a_blank_name(self, staff_client, name):
        response = staff_client.post(CARS_URL, {'name': name}, format='json')
        assert response.status_code == 400
        assert 'name' in response.json()
        assert ExpenseCar.objects.count() == 0

    def test_rejects_a_missing_name(self, staff_client):
        response = staff_client.post(CARS_URL, {'purchase': 100}, format='json')
        assert response.status_code == 400
        assert 'name' in response.json()

    def test_rejects_a_negative_purchase(self, staff_client):
        response = staff_client.post(CARS_URL, {'name': 'Ford Fiesta', 'purchase': -1}, format='json')
        assert response.status_code == 400
        assert 'purchase' in response.json()
        assert ExpenseCar.objects.count() == 0


@pytest.mark.django_db
class TestUpdate:
    def test_saves_costs_and_status_without_a_name(self, staff_client, make_car):
        car = make_car(name='BMW 320d')
        response = staff_client.put(detail_url(car), PUT_BODY, format='json')
        assert response.status_code == 200
        body = response.json()
        assert list(body) == CAR_KEYS
        assert body['name'] == 'BMW 320d'
        assert body['status'] == 'sold'
        assert body['mot'] == '54.85'
        assert body['oil_coolant_repairs'] == '189.99'
        assert body['tyre_tread_depth'] == '4.90'
        assert body['date_sold'] == '2026-11-01'
        car.refresh_from_db()
        assert car.status == ExpenseCar.STATUS_SOLD
        assert car.sale_price == Decimal('17495.00')
        assert car.oil_coolant_repairs == Decimal('189.99')

    def test_null_clears_numbers_and_dates(self, staff_client, make_car):
        car = make_car(
            date_added=date(2026, 1, 1),
            date_sold=date(2026, 2, 1),
            wash=Decimal('10.00'),
            sale_price=Decimal('100.00'),
            tyre_tread_depth=Decimal('4.00'),
        )
        body = {
            'date_added': None,
            'date_sold': None,
            'sale_price': None,
            'tyre_tread_depth': None,
            **{field: None for field in COST_FIELDS},
        }
        response = staff_client.put(detail_url(car), body, format='json')
        assert response.status_code == 200
        car.refresh_from_db()
        assert car.date_added is None
        assert car.date_sold is None
        assert car.wash is None
        assert car.sale_price is None
        assert car.tyre_tread_depth is None

    def test_accepts_empty_notes(self, staff_client, make_car):
        car = make_car(notes='Old note')
        response = staff_client.put(detail_url(car), {'notes': ''}, format='json')
        assert response.status_code == 200
        assert response.json()['notes'] == ''
        car.refresh_from_db()
        assert car.notes == ''

    def test_name_in_the_body_does_not_rename(self, staff_client, make_car):
        car = make_car(name='BMW 320d')
        response = staff_client.put(detail_url(car), {'name': 'Renamed'}, format='json')
        assert response.status_code == 200
        car.refresh_from_db()
        assert car.name == 'BMW 320d'

    @pytest.mark.parametrize('field, value', [
        ('wash', -1),
        ('wash', 12.345),
        ('wash', 123456789.00),
        ('wash', 'abc'),
        ('sale_price', -1),
        ('tyre_tread_depth', -0.01),
        ('tyre_tread_depth', 100),
        ('status', 'reserved'),
        ('date_sold', '09/11/2026'),
    ])
    def test_bad_value_returns_400_under_the_api_field_name(self, staff_client, make_car, field, value):
        car = make_car()
        response = staff_client.put(detail_url(car), {field: value}, format='json')
        assert response.status_code == 400
        assert list(response.json()) == [field]

    def test_unknown_car_is_404(self, staff_client):
        assert staff_client.put(f'{CARS_URL}999999/', PUT_BODY, format='json').status_code == 404

    @pytest.mark.parametrize('method', ['get', 'patch'])
    def test_other_methods_are_not_allowed(self, staff_client, make_car, method):
        car = make_car()
        assert getattr(staff_client, method)(detail_url(car)).status_code == 405
        assert ExpenseCar.objects.filter(pk=car.pk).exists()


@pytest.mark.django_db
class TestDelete:
    def test_removes_the_car_with_204_and_no_body(self, staff_client, make_car):
        car = make_car()
        response = staff_client.delete(detail_url(car))
        assert response.status_code == 204
        assert response.content == b''
        assert not ExpenseCar.objects.filter(pk=car.pk).exists()

    def test_leaves_other_cars_alone(self, staff_client, make_car):
        gone, kept = make_car(name='Gone'), make_car(name='Kept')
        staff_client.delete(detail_url(gone))
        assert list(ExpenseCar.objects.values_list('name', flat=True)) == ['Kept']
        assert ids(staff_client.get(CARS_URL)) == [kept.id]

    def test_unknown_car_is_404(self, staff_client):
        assert staff_client.delete(f'{CARS_URL}999999/').status_code == 404

    def test_deleting_twice_is_404(self, staff_client, make_car):
        car = make_car()
        staff_client.delete(detail_url(car))
        assert staff_client.delete(detail_url(car)).status_code == 404

    def test_put_still_works(self, staff_client, make_car):
        car = make_car()
        response = staff_client.put(detail_url(car), PUT_BODY, format='json')
        assert response.status_code == 200
        car.refresh_from_db()
        assert car.status == ExpenseCar.STATUS_SOLD


@pytest.mark.django_db
class TestCalculatedValues:
    def test_total_profit_and_days_are_not_stored(self):
        columns = {field.name for field in ExpenseCar._meta.get_fields()}
        assert not columns & {'total_cost', 'profit', 'days_in_stock'}

    def test_total_cost_is_an_exact_decimal(self):
        car = ExpenseCar(name='Test', wash=Decimal('0.10'), fuel=Decimal('0.20'))
        assert isinstance(car.total_cost, Decimal)
        assert car.total_cost == Decimal('0.30')

    def test_total_cost_excludes_tyre_depth_and_sale_price(self):
        car = ExpenseCar(
            name='Test',
            purchase=Decimal('100.00'),
            tyre_tread_depth=Decimal('5.00'),
            sale_price=Decimal('900.00'),
        )
        assert car.total_cost == Decimal('100.00')

    def test_profit_is_none_without_a_sale_price(self):
        assert ExpenseCar(name='Test', purchase=Decimal('100.00')).profit is None

    def test_profit_can_be_a_loss(self):
        car = ExpenseCar(name='Test', purchase=Decimal('100.00'), sale_price=Decimal('60.50'))
        assert car.profit == Decimal('-39.50')
