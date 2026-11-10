from django.urls import path

from .views import SellMyCarAvailabilityView, SellMyCarLookupView, SellMyCarSubmitView

urlpatterns = [
    path("sell-my-car/lookup/", SellMyCarLookupView.as_view(), name="sell-my-car-lookup"),
    path("sell-my-car/availability/", SellMyCarAvailabilityView.as_view(), name="sell-my-car-availability"),
    path("sell-my-car/", SellMyCarSubmitView.as_view(), name="sell-my-car-submit"),
]
