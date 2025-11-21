from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def director_required(view_func):
    """Декоратор для проверки, что пользователь является директором."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'profile'):
            raise PermissionDenied("Профиль пользователя не найден")
        if not request.user.profile.is_director:
            raise PermissionDenied("Доступ разрешён только директору")
        return view_func(request, *args, **kwargs)
    return wrapper


def employee_or_director_required(view_func):
    """Декоратор для проверки, что пользователь авторизован (сотрудник или директор)."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, 'profile'):
            raise PermissionDenied("Профиль пользователя не найден")
        return view_func(request, *args, **kwargs)
    return wrapper

