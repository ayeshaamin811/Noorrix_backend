from django.urls import path

from .views import (
    ExpenseCarListCreateView,
    ExpenseCarUpdateView,
    ExpenseColumnDeleteView,
    ExpenseColumnListCreateView,
    ExpenseExportView,
    ExpenseSummaryView,
)

urlpatterns = [
    path('expenses/cars/', ExpenseCarListCreateView.as_view(), name='expense-cars'),
    path('expenses/cars/<int:pk>/', ExpenseCarUpdateView.as_view(), name='expense-car-detail'),
    path('expenses/columns/', ExpenseColumnListCreateView.as_view(), name='expense-columns'),
    path('expenses/columns/<int:pk>/', ExpenseColumnDeleteView.as_view(), name='expense-column-detail'),
    path('expenses/summary/', ExpenseSummaryView.as_view(), name='expense-summary'),
    path('expenses/export/', ExpenseExportView.as_view(), name='expense-export'),
]
