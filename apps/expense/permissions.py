from rest_framework.permissions import BasePermission


class CanUseExpenses(BasePermission):
    """Staff only. IsAuthenticated is not enough, because anyone can register on the public site."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)
