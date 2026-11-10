from decimal import Decimal

import pytest

SUMMARY_URL = '/api/expenses/summary/'


@pytest.mark.django_db
class TestSummary:
    def test_is_zero_with_no_cars(self, staff_client):
        assert staff_client.get(SUMMARY_URL).json() == {
            'cars_in_stock': 0,
            'cars_sold': 0,
            'money_tied_up': '0.00',
            'profit_from_sold': '0.00',
        }

    def test_totals_across_available_and_sold_cars(self, staff_client, make_car):
        make_car(purchase=Decimal('1000.10'), other=Decimal('0.20'))
        make_car()
        make_car(status='sold', sale_price=Decimal('2000.00'), purchase=Decimal('1500.55'), mot=Decimal('49.45'))
        make_car(status='sold', sale_price=Decimal('100.00'), purchase=Decimal('150.25'))
        assert staff_client.get(SUMMARY_URL).json() == {
            'cars_in_stock': 2,
            'cars_sold': 2,
            'money_tied_up': '1000.30',
            'profit_from_sold': '399.75',
        }

    def test_blank_costs_count_as_zero(self, staff_client, make_car):
        make_car(purchase=None, wash=Decimal('25.50'))
        make_car(status='sold', sale_price=Decimal('500.00'))
        body = staff_client.get(SUMMARY_URL).json()
        assert body['money_tied_up'] == '25.50'
        assert body['profit_from_sold'] == '500.00'

    def test_sold_car_with_no_sale_price_adds_nothing_to_profit(self, staff_client, make_car):
        make_car(status='sold', sale_price=None, purchase=Decimal('700.00'))
        body = staff_client.get(SUMMARY_URL).json()
        assert body['cars_sold'] == 1
        assert body['profit_from_sold'] == '0.00'

    def test_available_car_with_a_sale_price_adds_nothing_to_profit(self, staff_client, make_car):
        make_car(status='available', sale_price=Decimal('900.00'), purchase=Decimal('100.00'))
        assert staff_client.get(SUMMARY_URL).json()['profit_from_sold'] == '0.00'

    def test_sold_car_costs_are_not_money_tied_up(self, staff_client, make_car):
        make_car(status='sold', sale_price=Decimal('900.00'), purchase=Decimal('100.00'))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '0.00'

    def test_tyre_depth_and_sale_price_are_not_costs(self, staff_client, make_car):
        make_car(purchase=Decimal('100.00'), tyre_tread_depth=Decimal('5.00'), sale_price=Decimal('900.00'))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '100.00'

    def test_all_thirteen_costs_are_counted(self, staff_client, make_car):
        make_car(
            purchase=Decimal('1.00'), delivery=Decimal('1.00'), mot=Decimal('1.00'), wash=Decimal('1.00'),
            denting_painting=Decimal('1.00'), oil_coolant_repairs=Decimal('1.00'), fuel=Decimal('1.00'),
            timing_chain=Decimal('1.00'), electrical_work=Decimal('1.00'), brakes=Decimal('1.00'),
            exhaust=Decimal('1.00'), clutch_gearbox=Decimal('1.00'), other=Decimal('1.00'),
        )
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '13.00'

    def test_sums_pennies_exactly(self, staff_client, make_car):
        for _ in range(100):
            make_car(wash=Decimal('0.10'), fuel=Decimal('0.20'))
        assert staff_client.get(SUMMARY_URL).json()['money_tied_up'] == '30.00'

    def test_ignores_filters(self, staff_client, make_car):
        make_car(name='Ford Fiesta', purchase=Decimal('10.00'))
        make_car(name='BMW 320d', status='sold', sale_price=Decimal('50.00'))
        body = staff_client.get(SUMMARY_URL, {'status': 'sold', 'search': 'nothing matches'}).json()
        assert body['cars_in_stock'] == 1
        assert body['cars_sold'] == 1
        assert body['money_tied_up'] == '10.00'
        assert body['profit_from_sold'] == '50.00'
