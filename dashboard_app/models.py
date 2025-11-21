from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """Профиль пользователя с ролью."""

    ROLE_DIRECTOR = 'director'
    ROLE_EMPLOYEE = 'employee'
    ROLE_CHOICES = [
        (ROLE_DIRECTOR, 'Директор'),
        (ROLE_EMPLOYEE, 'Сотрудник'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Пользователь',
    )
    role = models.CharField(
        'Роль',
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_EMPLOYEE,
    )
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()}"

    @property
    def is_director(self):
        return self.role == self.ROLE_DIRECTOR

    @property
    def is_employee(self):
        return self.role == self.ROLE_EMPLOYEE


class AccreditationStatus(models.Model):
    """Stores accreditation snapshot for a single company."""

    inn = models.CharField("ИНН", max_length=20, unique=True)
    name = models.CharField("Наименование", max_length=512)
    status = models.CharField("Статус", max_length=128)
    decision_number = models.CharField(
        "Номер решения", max_length=128, blank=True, default=""
    )
    decision_date = models.DateField(
        "Дата решения", null=True, blank=True
    )
    registry_record_date = models.DateField(
        "Дата записи в реестре", null=True, blank=True
    )
    raw_payload = models.JSONField("Исходные данные", default=dict, blank=True)
    checked_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-checked_at"]
        verbose_name = "Аккредитация компании"
        verbose_name_plural = "Аккредитации компаний"

    def __str__(self):
        return f"{self.inn} — {self.status}"
