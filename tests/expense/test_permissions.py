from datetime import timedelta

import pytest
from django.contrib import admin
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.expense.models import ExpenseCar

DETAIL = 'detail'
ENDPOINTS = [
    pytest.param('get', '/api/expenses/cars/', 200, id='list'),
    pytest.param('post', '/api/expenses/cars/', 201, id='create'),
    pytest.param('put', DETAIL, 200, id='update'),
    pytest.param('get', '/api/expenses/summary/', 200, id='summary'),
    pytest.param('get', '/api/expenses/export/', 200, id='export'),
]


@pytest.fixture
def car(make_car):
    return make_car()


def call(client, method, path, car):
    url = f'/api/expenses/cars/{car.id}/' if path == DETAIL else path
    if method == 'get':
        return client.get(url)
    body = {'name': 'Ford Fiesta'} if method == 'post' else {'wash': '10.00'}
    return getattr(client, method)(url, body, format='json')


@pytest.mark.django_db
@pytest.mark.parametrize('method, path, success', ENDPOINTS)
class TestAccess:
    def test_no_token_is_401(self, api_client, car, method, path, success):
        assert call(api_client, method, path, car).status_code == 401

    def test_bad_token_is_401(self, api_client, car, method, path, success):
        api_client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')
        assert call(api_client, method, path, car).status_code == 401

    def test_expired_token_is_401(self, api_client, user, car, method, path, success):
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=-timedelta(minutes=1))
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        assert call(api_client, method, path, car).status_code == 401

    def test_customer_is_403_with_detail_and_no_data(self, auth_client, car, method, path, success):
        response = call(auth_client, method, path, car)
        assert response.status_code == 403
        assert list(response.json()) == ['detail']

    def test_staff_succeeds(self, staff_client, car, method, path, success):
        assert call(staff_client, method, path, car).status_code == success


@pytest.mark.django_db
class TestWritesAreBlocked:
    def test_customer_cannot_add_a_car(self, auth_client):
        auth_client.post('/api/expenses/cars/', {'name': 'Ford Fiesta'}, format='json')
        assert ExpenseCar.objects.count() == 0

    def test_customer_cannot_change_a_car(self, auth_client, car):
        auth_client.put(f'/api/expenses/cars/{car.id}/', {'wash': '10.00'}, format='json')
        car.refresh_from_db()
        assert car.wash is None

    def test_no_token_cannot_add_a_car(self):
        APIClient().post('/api/expenses/cars/', {'name': 'Ford Fiesta'}, format='json')
        assert ExpenseCar.objects.count() == 0


def test_model_is_not_registered_in_admin():
    assert not admin.site.is_registered(ExpenseCar)
