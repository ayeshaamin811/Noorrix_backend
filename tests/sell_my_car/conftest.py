from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.sell_my_car.models import SellMyCarEnquiry

from .helpers import NOW, dvsa_response


class InlineThread:
    """Runs the email work immediately so tests can assert on it."""

    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


@pytest.fixture(autouse=True)
def isolated_environment(settings, tmp_path):
    """No real credentials or media, and throttle counts don't leak between tests."""
    settings.MEDIA_ROOT = tmp_path
    settings.ADMIN_EMAIL = "owner@noorrix.test"
    settings.DEFAULT_FROM_EMAIL = "Noorrix Motors <noreply@noorrix.test>"
    settings.DVSA_TOKEN_URL = ""
    settings.DVSA_CLIENT_ID = ""
    settings.DVSA_CLIENT_SECRET = ""
    settings.DVSA_API_KEY = ""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def frozen_time():
    with patch("django.utils.timezone.now", return_value=NOW) as now:
        yield now


@pytest.fixture(autouse=True)
def resend_send():
    with patch("apps.sell_my_car.emails.resend.Emails.send") as send:
        yield send


@pytest.fixture(autouse=True)
def email_thread():
    with patch("apps.sell_my_car.views.threading") as threading_module:
        threading_module.Thread.side_effect = InlineThread
        yield threading_module.Thread


@pytest.fixture(autouse=True)
def dvsa_http():
    """Any DVSA call a test didn't set up fails instead of reaching the network."""
    unexpected = AssertionError("This test did not expect a DVSA call")
    with patch("apps.sell_my_car.dvsa.requests.post", side_effect=unexpected) as post:
        with patch("apps.sell_my_car.dvsa.requests.get", side_effect=unexpected) as get:
            yield SimpleNamespace(post=post, get=get)


@pytest.fixture
def dvsa_ready(settings, dvsa_http):
    settings.DVSA_TOKEN_URL = "https://login.example/tenant-id/oauth2/v2.0/token"
    settings.DVSA_CLIENT_ID = "the-client-id"
    settings.DVSA_CLIENT_SECRET = "the-client-secret"
    settings.DVSA_SCOPE = "https://tapi.dvsa.gov.uk/.default"
    settings.DVSA_API_KEY = "the-api-key"
    dvsa_http.post.side_effect = None
    dvsa_http.post.return_value = dvsa_response(body={"access_token": "the-token", "expires_in": 3600})
    dvsa_http.get.side_effect = None
    return dvsa_http


@pytest.fixture
def make_enquiry(db):
    def _make_enquiry(**overrides):
        fields = {
            "reg": "ZZ99ZZZ",
            "mileage": 5000,
            "name": "Existing Customer",
            "email": "existing@example.com",
            "phone": "+447701910159",
            "address": "2 Low Road, Bedford",
            "appointment_date": date(2026, 11, 3),
            "appointment_time": time(12, 0),
        }
        fields.update(overrides)
        return SellMyCarEnquiry.objects.create(**fields)

    return _make_enquiry
