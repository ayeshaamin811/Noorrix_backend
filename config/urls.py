from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.auth.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/', include('apps.contact.urls')),
    path('api/', include('apps.newsletter.urls')),
    path('api/', include('apps.part_exchange.urls')),
    path('api/', include('apps.vehicle_sourcing.urls')),
    path('api/', include('apps.delivery.urls')),
    path('api/', include('apps.expense.urls')),
    path('', include('apps.blog.urls')),
    path('', include('apps.faq.urls')),
    path('', include('apps.cars.urls')),
    path('', include('apps.appointments.urls')),
    path('', include('apps.testimonials.urls')),

    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
