from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from dashboard_app.models import UserProfile


class Command(BaseCommand):
    help = 'Создаёт тестовых пользователей: директора и сотрудника'

    def handle(self, *args, **options):
        # Создаём директора
        director, created = User.objects.get_or_create(
            username='director',
            defaults={
                'first_name': 'Иван',
                'last_name': 'Иванов',
                'email': 'director@example.com',
                'is_staff': True,
                'is_active': True,
            }
        )
        # Всегда устанавливаем пароль и активируем пользователя
        director.set_password('director123')
        director.is_active = True
        director.is_staff = True
        director.save()
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Создан пользователь директора: {director.username}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Обновлён пароль для пользователя директора: {director.username}')
            )

        # Создаём профиль директора
        profile, created = UserProfile.objects.get_or_create(
            user=director,
            defaults={
                'role': UserProfile.ROLE_DIRECTOR,
                'internal_email': 'admin@metrika.com'
            }
        )
        if not created:
            if profile.role != UserProfile.ROLE_DIRECTOR:
                profile.role = UserProfile.ROLE_DIRECTOR
            if not profile.internal_email:
                profile.internal_email = 'admin@metrika.com'
            profile.save()
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Обновлена роль пользователя {director.username} на директора')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Создан профиль директора для {director.username}')
            )

        # Создаём сотрудника
        employee, created = User.objects.get_or_create(
            username='employee',
            defaults={
                'first_name': 'Петр',
                'last_name': 'Петров',
                'email': 'employee@example.com',
                'is_active': True,
            }
        )
        # Всегда устанавливаем пароль и активируем пользователя
        employee.set_password('employee123')
        employee.is_active = True
        employee.save()
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Создан пользователь сотрудника: {employee.username}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Обновлён пароль для пользователя сотрудника: {employee.username}')
            )

        # Создаём профиль сотрудника
        profile, created = UserProfile.objects.get_or_create(
            user=employee,
            defaults={
                'role': UserProfile.ROLE_EMPLOYEE,
                'internal_email': 'employee@metrika.com'
            }
        )
        if not created:
            if profile.role != UserProfile.ROLE_EMPLOYEE:
                profile.role = UserProfile.ROLE_EMPLOYEE
            if not profile.internal_email:
                profile.internal_email = 'employee@metrika.com'
            profile.save()
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Обновлена роль пользователя {employee.username} на сотрудника')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'[OK] Создан профиль сотрудника для {employee.username}')
            )

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Учётные данные для входа:'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('Директор:'))
        self.stdout.write(self.style.SUCCESS('  Логин: director'))
        self.stdout.write(self.style.SUCCESS('  Пароль: director123'))
        director_profile = UserProfile.objects.get(user=director)
        self.stdout.write(self.style.SUCCESS(f'  Внутренний email: {director_profile.get_internal_email()}'))
        self.stdout.write(self.style.SUCCESS('\nСотрудник:'))
        self.stdout.write(self.style.SUCCESS('  Логин: employee'))
        self.stdout.write(self.style.SUCCESS('  Пароль: employee123'))
        employee_profile = UserProfile.objects.get(user=employee)
        self.stdout.write(self.style.SUCCESS(f'  Внутренний email: {employee_profile.get_internal_email()}'))
        self.stdout.write(self.style.SUCCESS('='*60))

