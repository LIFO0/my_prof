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
            if not hasattr(user, 'profile'):
                messages.error(request, 'У пользователя отсутствует профиль. Обратитесь к администратору.')
            else:
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

    unread_notifications = list(
        request.user.notifications.filter(is_read=False).order_by('created_at')
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
    if unread_notifications:
        Notification.objects.filter(id__in=[note.id for note in unread_notifications]).update(is_read=True)

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
    recipient_id = request.POST.get('recipient_id')

    if not recipient_id:
        messages.error(request, 'Выберите получателя отчёта.')
        return redirect('dashboard')

    if not selected_inns:
        messages.warning(request, 'Отметьте компании, чтобы сформировать отчёт.')
        return redirect('dashboard')

    User = get_user_model()
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

    messages.success(request, f'Отчёт отправлен пользователю {recipient.get_full_name() or recipient.username}.')
    return redirect('dashboard')


@employee_or_director_required
def notification_download_report_view(request, pk: int):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
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
    return JsonResponse({'success': True, 'results': results})
