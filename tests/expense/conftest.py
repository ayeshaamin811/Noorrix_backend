import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.expense.models import ExpenseCar


@pytest.fixture
def staff_client(db):
    """A staff account signed in through the real login route."""
    get_user_model().objects.create_user(
        email='staff@example.com',
        password='StaffPass123!',
        name='Staff User',
        is_staff=True,
    )
    client = APIClient()
    response = client.post(
        '/api/v1/auth/token/',
        {'email': 'staff@example.com', 'password': 'StaffPass123!'},
        format='json',
    )
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
    return client


@pytest.fixture
def make_car(db):
    def _make_car(**overrides):
        fields = {'name': 'BMW 320d'}
        fields.update(overrides)
        return ExpenseCar.objects.create(**fields)

    return _make_car
