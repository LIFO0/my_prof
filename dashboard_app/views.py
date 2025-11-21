import json
import logging
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

from .decorators import director_required, employee_or_director_required
from .models import Notification, UserProfile
from .services import (
    apply_filters,
    available_filter_options,
    calculate_bounds,
    calculate_stats,
    get_accreditations_for_inns,
    load_dataset,
    parse_filter_payload,
    sync_accreditation_statuses,
)


def login_view(request):
    """Страница входа в систему."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Проверяем, что у пользователя есть профиль
            try:
                profile = user.profile
            except UserProfile.DoesNotExist:
                messages.error(request, 'У пользователя отсутствует профиль. Обратитесь к администратору.')
                return render(request, 'dashboard_app/login.html')
            
            # Проверяем, что пользователь активен
            if not user.is_active:
                messages.error(request, 'Ваш аккаунт деактивирован. Обратитесь к администратору.')
                return render(request, 'dashboard_app/login.html')
            
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Неверное имя пользователя или пароль.')
    return render(request, 'dashboard_app/login.html')


def logout_view(request):
    """Выход из системы."""
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы.')
    return redirect('login')


def _describe_active_filters(filters: dict) -> list[str]:
    descriptions: list[str] = []
    if filters.get('search'):
        descriptions.append(f'Поиск: "{filters["search"]}"')
    if filters.get('okved'):
        descriptions.append(f'ОКВЭД: {filters["okved"]}')
    if filters.get('uses_usn') is True:
        descriptions.append('Только компании на УСН')
    elif filters.get('uses_usn') is False:
        descriptions.append('Без УСН')
    if filters.get('is_accredited') is True:
        descriptions.append('Только аккредитованные')
    elif filters.get('is_accredited') is False:
        descriptions.append('Только неаккредитованные')
    if filters.get('min_revenue') is not None:
        descriptions.append(f'Выручка ≥ {filters["min_revenue"]:,} ₽'.replace(',', ' '))
    if filters.get('max_revenue') is not None:
        descriptions.append(f'Выручка ≤ {filters["max_revenue"]:,} ₽'.replace(',', ' '))
    if filters.get('min_taxes') is not None:
        descriptions.append(f'Налоги ≥ {filters["min_taxes"]:,} ₽'.replace(',', ' '))
    if filters.get('min_staff') is not None:
        descriptions.append(f'Численность ≥ {filters["min_staff"]}')
    if filters.get('tax_year') is not None:
        descriptions.append(f'Год уплаты налогов: {filters["tax_year"]}')
    if filters.get('staff_year') is not None:
        descriptions.append(f'Год численности: {filters["staff_year"]}')
    return descriptions


def _generate_excel_workbook(companies: list[dict]):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Компании'

    headers = [
        'Короткое название',
        'Полное название',
        'ИНН',
        'ОКВЭД',
        'Выручка',
        'Расходы',
        'Налоги',
        'Год налогов',
        'Средняя численность',
        'Год численности',
        'УСН',
        'Аккредитация',
        'Финансовый результат',
        'Руководитель',
        'Дата постановки на учёт',
        'Дата в реестре МСП',
    ]
    sheet.append(headers)

    def format_money(value):
        return value if value is not None else ''

    def format_bool(value):
        if value is True:
            return 'Да'
        if value is False:
            return 'Нет'
        return ''

    for company in companies:
        accreditation_status = ''
        accreditation = company.get('accreditation')
        if accreditation:
            if isinstance(accreditation, dict):
                accreditation_status = accreditation.get('status', '')
            else:
                accreditation_status = getattr(accreditation, 'status', '')
        sheet.append([
            company.get('short_name') or '',
            company.get('full_name') or '',
            company.get('inn') or '',
            company.get('okved') or '',
            format_money(company.get('revenue')),
            format_money(company.get('expenses')),
            format_money(company.get('taxes')),
            company.get('tax_year') or '',
            company.get('staff') or '',
            company.get('staff_year') or '',
            format_bool(company.get('uses_usn')),
            accreditation_status,
            format_money(company.get('financial_result')),
            company.get('ceo') or '',
            company.get('registered_at') or '',
            company.get('msme_at') or '',
        ])

    for column in sheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            cell_value = cell.value or ''
            max_length = max(max_length, len(str(cell_value)))
        adjusted_width = min(max_length + 2, 60)
        sheet.column_dimensions[column_letter].width = adjusted_width

    return workbook


def _build_excel_response(companies: list[dict], filename_prefix: str = 'report'):
    workbook = _generate_excel_workbook(companies)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    timestamp = timezone.now().strftime('%Y%m%d_%H%M')
    filename = f'{filename_prefix}_{timestamp}.xlsx'

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@employee_or_director_required
def dashboard_view(request):
    from django.core.paginator import Paginator
    
    dataset = load_dataset()
    # Загружаем аккредитации для всех компаний до применения фильтров
    all_inns = [row.get('inn') for row in dataset if row.get('inn')]
    accreditation_map = get_accreditations_for_inns(all_inns)
    
    # Прикрепляем аккредитации к компаниям
    for row in dataset:
        row['accreditation'] = accreditation_map.get(row.get('inn'))
    
    filters = parse_filter_payload(request.GET)
    filtered_rows = apply_filters(dataset, filters)
    
    # Пагинация: 10 компаний на страницу
    paginator = Paginator(filtered_rows, 10)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except:
        page_obj = paginator.get_page(1)

    user_profile = request.user.profile
    User = get_user_model()
    report_recipients = User.objects.filter(
        profile__role=UserProfile.ROLE_EMPLOYEE
    ).order_by('first_name', 'username')

    # Получаем только непрочитанные уведомления (не письма)
    unread_notifications = list(
        request.user.notifications.filter(
            is_read=False
        ).exclude(
            notification_type=Notification.Type.EMAIL
        ).order_by('created_at')
    )
    notifications_payload = [
        {
            'id': note.id,
            'title': note.title,
            'message': note.message,
            'type': note.notification_type,
            'created_at': timezone.localtime(note.created_at).strftime('%d.%m.%Y %H:%M'),
            'download_url': reverse('notification_download', args=[note.id])
            if (note.payload or {}).get('inns')
            else None,
            'companies_preview': (note.payload or {}).get('companies_preview', []),
            'count': (note.payload or {}).get('count'),
        }
        for note in unread_notifications
    ]
    # Помечаем только уведомления (не письма) как прочитанные
    if unread_notifications:
        Notification.objects.filter(
            id__in=[note.id for note in unread_notifications]
        ).exclude(
            notification_type=Notification.Type.EMAIL
        ).update(is_read=True)

    # Подсчет непрочитанных писем
    unread_emails_count = Notification.objects.filter(
        recipient=request.user,
        notification_type=Notification.Type.EMAIL,
        is_read=False
    ).count()

    # Список всех ИНН отфильтрованных компаний (для функции "Выбрать всё")
    all_filtered_inns = [row.get('inn') for row in filtered_rows if row.get('inn')]
    
    context = {
        'filters': filters,
        'active_filters': _describe_active_filters(filters),
        'dataset_stats': calculate_stats(dataset),
        'selection_stats': calculate_stats(filtered_rows),
        'bounds': calculate_bounds(dataset),
        'filter_options': available_filter_options(dataset),
        'companies': page_obj,
        'page_obj': page_obj,
        'accreditations': accreditation_map,
        'is_director': user_profile.is_director,
        'user': request.user,
        'report_recipients': report_recipients,
        'notifications_payload': notifications_payload,
        'unread_emails_count': unread_emails_count,
        'all_filtered_inns': all_filtered_inns,  # Все ИНН отфильтрованных компаний
    }
    return render(request, 'dashboard_app/dashboard.html', context)


@director_required
def report_view(request):
    if request.method != 'POST':
        messages.error(request, 'Создать отчёт можно только из списка компаний.')
        return redirect('dashboard')

    selected_inns = request.POST.getlist('company_inn')
    if not selected_inns:
        messages.warning(request, 'Выберите хотя бы одну компанию для отчёта.')
        return redirect('dashboard')

    dataset = load_dataset()
    companies = [row for row in dataset if row.get('inn') in selected_inns]

    stats = calculate_stats(companies)

    context = {
        'companies': companies,
        'stats': stats,
        'count': len(companies),
        'selected_inns': selected_inns,
    }
    return render(request, 'dashboard_app/report.html', context)


@require_POST
@director_required
def report_export_excel_view(request):
    selected_inns = request.POST.getlist('company_inn')
    if not selected_inns:
        messages.warning(request, 'Выберите хотя бы одну компанию для экспорта.')
        return redirect('dashboard')

    dataset = load_dataset()
    companies = [row for row in dataset if row.get('inn') in selected_inns]

    if not companies:
        messages.error(request, 'Не удалось найти данные для выбранных компаний.')
        return redirect('dashboard')

    return _build_excel_response(companies)


@require_POST
@director_required
def send_report_notification_view(request):
    selected_inns = request.POST.getlist('company_inn')
    send_method = request.POST.get('send_method', 'user')
    recipient_id = request.POST.get('recipient_id')
    recipient_email = request.POST.get('recipient_email', '').strip()
    use_email = request.POST.get('use_email', 'false') == 'true'

    if not selected_inns:
        messages.warning(request, 'Отметьте компании, чтобы сформировать отчёт.')
        return redirect('dashboard')

    User = get_user_model()
    recipient = None

    if send_method == 'email':
        # Отправка по указанному email
        if not recipient_email:
            messages.error(request, 'Укажите email адрес получателя.')
            return redirect('dashboard')
        
        # Ищем пользователя с таким internal_email
        try:
            recipient = User.objects.get(profile__internal_email=recipient_email)
        except User.DoesNotExist:
            messages.error(
                request,
                f'Пользователь с email {recipient_email} не найден в системе. '
                'Убедитесь, что email адрес указан правильно.'
            )
            return redirect('dashboard')
    else:
        # Отправка выбранному пользователю
        if not recipient_id:
            messages.error(request, 'Выберите получателя отчёта.')
            return redirect('dashboard')
        
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            messages.error(request, 'Выбранный пользователь не найден.')
            return redirect('dashboard')

    dataset = load_dataset()
    companies = [row for row in dataset if row.get('inn') in selected_inns]
    if not companies:
        messages.error(request, 'Не удалось найти данные для выбранных компаний.')
        return redirect('dashboard')

    preview = [
        row.get('short_name') or row.get('full_name') or row.get('inn')
        for row in companies[:3]
    ]

    sender_email = request.user.profile.get_internal_email()
    recipient_internal_email = recipient.profile.get_internal_email()

    if use_email:
        # Отправка как внутреннее письмо
        subject = f'Отчёт по IT-компаниям ({len(companies)} организаций)'
        message_body = f'''Здравствуйте!

Вам отправлен отчёт по {len(companies)} IT-компаниям Калининградской области.

Отправитель: {request.user.get_full_name() or request.user.username} ({sender_email})
Дата формирования: {timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")}

Отчёт прикреплён в формате Excel.

---
Это автоматическое сообщение от системы дашборда IT-компаний.
'''
        
        Notification.objects.create(
            recipient=recipient,
            sender=request.user,
            notification_type=Notification.Type.EMAIL,
            title='Новое письмо с отчётом',
            subject=subject,
            message=message_body,
            is_read=False,
            payload={
                'inns': selected_inns,
                'count': len(companies),
                'companies_preview': preview,
                'sent_at': timezone.now().isoformat(),
                'sender_email': sender_email,
                'recipient_email': recipient_internal_email,
            },
        )
        messages.success(
            request,
            f'Письмо с отчётом отправлено на {recipient_internal_email}'
        )
    else:
        # Старый способ - уведомление
        Notification.objects.create(
            recipient=recipient,
            sender=request.user,
            notification_type=Notification.Type.REPORT,
            title='Получен новый Excel-отчёт',
            message=f'Директор {request.user.get_full_name() or request.user.username} отправил вам отчёт по {len(companies)} компаниям.',
            payload={
                'inns': selected_inns,
                'count': len(companies),
                'companies_preview': preview,
                'sent_at': timezone.now().isoformat(),
            },
        )
        messages.success(request, f'Отчёт отправлен пользователю {recipient.get_full_name() or recipient.username}.')

    employees = User.objects.filter(profile__role=UserProfile.ROLE_EMPLOYEE)
    Notification.objects.bulk_create(
        [
            Notification(
                recipient=user,
                sender=request.user,
                notification_type=Notification.Type.DATA,
                title='Обновлены данные отчёта',
                message='Директор обновил выборку компаний и пересоздал отчёт.',
                payload={
                    'count': len(companies),
                    'companies_preview': preview,
                    'updated_at': timezone.now().isoformat(),
                },
            )
            for user in employees
        ]
    )

    return redirect('dashboard')


@employee_or_director_required
def notification_download_report_view(request, pk: int):
    # Пользователь может скачивать только свои входящие или отправленные письма/уведомления
    notification = get_object_or_404(
        Notification,
        pk=pk
    )
    
    # Проверяем доступ
    if notification.recipient != request.user and notification.sender != request.user:
        messages.error(request, 'У вас нет доступа к этому отчёту.')
        return redirect('dashboard')
    
    payload = notification.payload or {}
    inns = payload.get('inns')
    if not inns:
        messages.error(request, 'В этом уведомлении нет вложенного отчёта.')
        return redirect('dashboard')

    dataset = load_dataset()
    companies = [row for row in dataset if row.get('inn') in inns]
    if not companies:
        messages.error(request, 'Данные компаний устарели или недоступны.')
        return redirect('dashboard')

    return _build_excel_response(companies, filename_prefix=f'notification_{pk}')

@require_POST
@director_required
def accreditation_sync_view(request):
    if request.content_type == 'application/json':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'message': 'Некорректный формат данных'},
                status=400,
            )
        inns = payload.get('inns') or []
    else:
        inns = request.POST.getlist('company_inn')

    if not inns:
        return JsonResponse(
            {'success': False, 'message': 'Выберите хотя бы одну компанию'},
            status=400,
        )

    results = sync_accreditation_statuses(inns)
    
    # Очищаем кэш датасета, чтобы статистика обновилась
    from .services import load_dataset
    load_dataset.cache_clear()
    
    return JsonResponse({'success': True, 'results': results})


@employee_or_director_required
def mail_inbox_view(request):
    """Страница входящих писем."""
    from django.core.paginator import Paginator
    
    # Получаем все письма (EMAIL) для текущего пользователя
    emails = Notification.objects.filter(
        recipient=request.user,
        notification_type=Notification.Type.EMAIL
    ).select_related('sender').order_by('-created_at')
    
    # Фильтр по прочитанным/непрочитанным
    filter_read = request.GET.get('filter', 'all')
    if filter_read == 'unread':
        emails = emails.filter(is_read=False)
    elif filter_read == 'read':
        emails = emails.filter(is_read=True)
    
    # Пагинация
    paginator = Paginator(emails, 15)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except:
        page_obj = paginator.get_page(1)
    
    # Статистика
    total_count = Notification.objects.filter(
        recipient=request.user,
        notification_type=Notification.Type.EMAIL
    ).count()
    unread_count = Notification.objects.filter(
        recipient=request.user,
        notification_type=Notification.Type.EMAIL,
        is_read=False
    ).count()
    
    # Подсчет непрочитанных писем для header
    unread_emails_count = unread_count
    
    context = {
        'emails': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'unread_count': unread_count,
        'filter_read': filter_read,
        'user_email': request.user.profile.get_internal_email(),
        'unread_emails_count': unread_emails_count,
    }
    return render(request, 'dashboard_app/mail_inbox.html', context)


@employee_or_director_required
def mail_sent_view(request):
    """Страница отправленных писем."""
    from django.core.paginator import Paginator
    
    # Получаем все письма, отправленные текущим пользователем
    emails = Notification.objects.filter(
        sender=request.user,
        notification_type=Notification.Type.EMAIL
    ).select_related('recipient').order_by('-created_at')
    
    # Пагинация
    paginator = Paginator(emails, 15)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except:
        page_obj = paginator.get_page(1)
    
    # Подсчет непрочитанных писем для header
    unread_emails_count = Notification.objects.filter(
        recipient=request.user,
        notification_type=Notification.Type.EMAIL,
        is_read=False
    ).count()
    
    context = {
        'emails': page_obj,
        'page_obj': page_obj,
        'user_email': request.user.profile.get_internal_email(),
        'unread_emails_count': unread_emails_count,
    }
    return render(request, 'dashboard_app/mail_sent.html', context)


@employee_or_director_required
def mail_view_view(request, pk: int):
    """Просмотр конкретного письма."""
    # Пользователь может просматривать только свои входящие или отправленные письма
    email = get_object_or_404(
        Notification,
        pk=pk,
        notification_type=Notification.Type.EMAIL
    )
    
    # Проверяем доступ
    if email.recipient != request.user and email.sender != request.user:
        messages.error(request, 'У вас нет доступа к этому письму.')
        return redirect('mail_inbox')
    
    # Отмечаем как прочитанное, если это входящее письмо
    if email.recipient == request.user and not email.is_read:
        email.is_read = True
        email.save()
    
    # Загружаем данные компаний, если есть вложение
    companies = []
    payload = email.payload or {}
    inns = payload.get('inns')
    if inns:
        dataset = load_dataset()
        companies = [row for row in dataset if row.get('inn') in inns]
    
    # Подсчет непрочитанных писем для header
    unread_emails_count = Notification.objects.filter(
        recipient=request.user,
        notification_type=Notification.Type.EMAIL,
        is_read=False
    ).count()
    
    context = {
        'email': email,
        'companies': companies,
        'is_incoming': email.recipient == request.user,
        'sender_email': email.sender.profile.get_internal_email() if email.sender else '',
        'recipient_email': email.recipient.profile.get_internal_email(),
        'unread_emails_count': unread_emails_count,
    }
    return render(request, 'dashboard_app/mail_view.html', context)
