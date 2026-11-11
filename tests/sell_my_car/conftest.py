from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache

from apps.sell_my_car import dvla
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
    settings.DVLA_API_KEY = ""
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
def http():
    """Stands in for the network, so a call a test didn't set up fails instead of going out.

    DVLA and DVSA both use requests.post, so posts are routed by URL.
    """

    def unexpected(name):
        return Mock(side_effect=AssertionError(f"This test did not expect a {name} call"))

    fakes = SimpleNamespace(
        dvla=unexpected("DVLA"),
        dvsa_token=unexpected("DVSA token"),
        dvsa_vehicle=unexpected("DVSA vehicle"),
    )

    def post(url, *args, **kwargs):
        target = fakes.dvla if url == dvla.VEHICLE_URL else fakes.dvsa_token
        return target(url, *args, **kwargs)

    def get(*args, **kwargs):
        return fakes.dvsa_vehicle(*args, **kwargs)

    with patch("requests.post", side_effect=post), patch("requests.get", side_effect=get):
        yield fakes


@pytest.fixture
def dvla_post(http):
    return http.dvla


@pytest.fixture
def dvla_ready(settings, dvla_post):
    """A configured key. Set return_value or side_effect for DVLA's reply."""
    settings.DVLA_API_KEY = "the-api-key"
    dvla_post.side_effect = None
    return dvla_post


@pytest.fixture
def dvsa_http(http):
    return SimpleNamespace(post=http.dvsa_token, get=http.dvsa_vehicle)


@pytest.fixture
def dvsa_ready(settings, dvsa_http):
    """Configured credentials and a token. Set dvsa_ready.get for DVSA's reply."""
    settings.DVSA_TOKEN_URL = "https://login.example/tenant-id/oauth2/v2.0/token"
    settings.DVSA_CLIENT_ID = "the-client-id"
    settings.DVSA_CLIENT_SECRET = "the-client-secret"
    settings.DVSA_SCOPE = "https://tapi.dvsa.gov.uk/.default"
    settings.DVSA_API_KEY = "the-dvsa-api-key"
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
