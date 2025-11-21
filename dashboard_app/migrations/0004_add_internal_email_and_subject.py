# Generated manually for internal email support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard_app', '0003_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='internal_email',
            field=models.CharField(
                blank=True,
                help_text='Виртуальный email адрес для внутренней почты (например, admin@metrika.com)',
                max_length=255,
                verbose_name='Внутренний email',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='subject',
            field=models.CharField(
                blank=True,
                help_text='Тема письма (для типа EMAIL)',
                max_length=255,
                verbose_name='Тема письма',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[('report', 'Отчёт'), ('data', 'Обновление данных'), ('email', 'Письмо')],
                max_length=20,
                verbose_name='Тип',
            ),
        ),
    ]

