from django.urls import path

from .views import (
    ExpenseCarListCreateView,
    ExpenseCarUpdateView,
    ExpenseExportView,
    ExpenseSummaryView,
)

urlpatterns = [
    path('expenses/cars/', ExpenseCarListCreateView.as_view(), name='expense-cars'),
    path('expenses/cars/<int:pk>/', ExpenseCarUpdateView.as_view(), name='expense-car-detail'),
    path('expenses/summary/', ExpenseSummaryView.as_view(), name='expense-summary'),
    path('expenses/export/', ExpenseExportView.as_view(), name='expense-export'),
]
