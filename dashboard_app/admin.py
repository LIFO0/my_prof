from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import AccreditationStatus, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at', 'updated_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AccreditationStatus)
class AccreditationStatusAdmin(admin.ModelAdmin):
    list_display = ('inn', 'name', 'status', 'decision_date', 'checked_at')
    list_filter = ('status', 'checked_at', 'decision_date')
    search_fields = ('inn', 'name', 'decision_number')
    readonly_fields = ('checked_at',)


# Добавляем профиль в админку пользователя
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль'


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
