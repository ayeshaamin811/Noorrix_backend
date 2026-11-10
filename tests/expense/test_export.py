import codecs
import csv
import io
from datetime import date
from decimal import Decimal

import pytest

EXPORT_URL = '/api/expenses/export/'
HEADER = [
    'Car', 'Status', 'Date Added', 'Purchase', 'Delivery', 'MOT', 'Wash', 'Denting/Painting',
    'Oil Change/Coolant/Repairs', 'Fuel', 'Timing Chain', 'Electrical Work', 'Brakes', 'Exhaust',
    'Clutch and Gearbox', 'Other', 'Total Cost', 'Tyre Tread Depth (mm)', 'Sale Price', 'Profit',
    'Date Sold', 'Notes',
]


def read_rows(response):
    text = response.content.decode('utf-8-sig')
    return list(csv.reader(io.StringIO(text, newline='')))


def read_cars(response):
    header, *rows = read_rows(response)
    return [dict(zip(header, row)) for row in rows]


@pytest.mark.django_db
class TestExportFormat:
    def test_is_csv_with_a_byte_order_mark(self, staff_client):
        response = staff_client.get(EXPORT_URL)
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/csv')
        assert response.content.startswith(codecs.BOM_UTF8)
        assert 'attachment' in response['Content-Disposition']

    def test_has_the_columns_in_order(self, staff_client):
        assert read_rows(staff_client.get(EXPORT_URL)) == [HEADER]

    def test_full_row(self, staff_client, make_car):
        make_car(
            name='BMW 320d',
            status='sold',
            date_added=date(2026, 10, 6),
            date_sold=date(2026, 11, 1),
            purchase=Decimal('14300.00'),
            delivery=Decimal('220.00'),
            mot=Decimal('54.85'),
            wash=Decimal('35.00'),
            denting_painting=Decimal('420.00'),
            oil_coolant_repairs=Decimal('189.99'),
            fuel=Decimal('55.00'),
            other=Decimal('95.00'),
            tyre_tread_depth=Decimal('4.90'),
            sale_price=Decimal('17495.00'),
            notes='HPI clear.',
        )
        assert read_rows(staff_client.get(EXPORT_URL))[1] == [
            'BMW 320d', 'Sold', '06/10/2026',
            '14300.00', '220.00', '54.85', '35.00', '420.00', '189.99', '55.00',
            '', '', '', '', '',
            '95.00', '15369.84', '4.90', '17495.00', '2125.16', '01/11/2026', 'HPI clear.',
        ]

    def test_blank_car_has_empty_cells_and_zero_total(self, staff_client, make_car):
        make_car(name='Ford Fiesta')
        car = read_cars(staff_client.get(EXPORT_URL))[0]
        assert car['Status'] == 'Available'
        assert car['Date Added'] == ''
        assert car['Purchase'] == ''
        assert car['Total Cost'] == '0.00'
        assert car['Sale Price'] == ''
        assert car['Profit'] == ''
        assert car['Date Sold'] == ''
        assert car['Notes'] == ''

    def test_money_is_plain_with_two_decimals(self, staff_client, make_car):
        make_car(purchase=Decimal('1234.50'))
        response = staff_client.get(EXPORT_URL)
        assert read_cars(response)[0]['Purchase'] == '1234.50'
        assert '£'.encode() not in response.content

    def test_loss_is_a_negative_number(self, staff_client, make_car):
        make_car(status='sold', purchase=Decimal('100.00'), sale_price=Decimal('60.50'))
        assert read_cars(staff_client.get(EXPORT_URL))[0]['Profit'] == '-39.50'

    def test_profit_follows_sale_price_on_an_available_car(self, staff_client, make_car):
        make_car(status='available', purchase=Decimal('100.00'), sale_price=Decimal('150.00'))
        assert read_cars(staff_client.get(EXPORT_URL))[0]['Profit'] == '50.00'

    def test_keeps_non_ascii_text_and_commas(self, staff_client, make_car):
        make_car(name='Citroën C3, 1.2', notes='Paid £50 cash\nSecond line')
        car = read_cars(staff_client.get(EXPORT_URL))[0]
        assert car['Car'] == 'Citroën C3, 1.2'
        assert car['Notes'] == 'Paid £50 cash\nSecond line'

    def test_accept_text_csv_is_served(self, staff_client):
        response = staff_client.get(EXPORT_URL, HTTP_ACCEPT='text/csv')
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/csv')

    def test_accept_text_csv_still_gets_a_403_for_customers(self, auth_client):
        response = auth_client.get(EXPORT_URL, HTTP_ACCEPT='text/csv')
        assert response.status_code == 403


@pytest.mark.django_db
class TestFormulaPrefixing:
    @pytest.mark.parametrize('value', ['=SUM(A1:A2)', '+44 7700', '-5 discount', '@risk'])
    def test_prefixes_name_and_notes(self, staff_client, make_car, value):
        make_car(name=value, notes=value)
        car = read_cars(staff_client.get(EXPORT_URL))[0]
        assert car['Car'] == f"'{value}"
        assert car['Notes'] == f"'{value}"

    @pytest.mark.parametrize('value', ['BMW 320d', 'a=b', '2019 + extras', "'quoted"])
    def test_leaves_other_text_alone(self, staff_client, make_car, value):
        make_car(name=value, notes=value)
        car = read_cars(staff_client.get(EXPORT_URL))[0]
        assert car['Car'] == value
        assert car['Notes'] == value


@pytest.mark.django_db
class TestExportFilters:
    def names(self, client, **params):
        return [car['Car'] for car in read_cars(client.get(EXPORT_URL, params))]

    def test_is_newest_first_with_no_filters(self, staff_client, make_car):
        make_car(name='First')
        make_car(name='Second', status='sold')
        assert self.names(staff_client) == ['Second', 'First']

    def test_status_filter(self, staff_client, make_car):
        make_car(name='In stock')
        make_car(name='Gone', status='sold')
        assert self.names(staff_client, status='sold') == ['Gone']
        assert self.names(staff_client, status='available') == ['In stock']

    def test_search_covers_name_and_notes(self, staff_client, make_car):
        make_car(name='Ford Fiesta')
        make_car(name='BMW 320d', notes='fiesta part exchange')
        make_car(name='Audi A3')
        assert self.names(staff_client, search='FIESTA') == ['BMW 320d', 'Ford Fiesta']

    def test_status_and_search_combine(self, staff_client, make_car):
        make_car(name='Ford Fiesta')
        make_car(name='Ford Focus', status='sold')
        assert self.names(staff_client, status='sold', search='ford') == ['Ford Focus']
