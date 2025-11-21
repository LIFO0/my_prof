import json

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .decorators import director_required, employee_or_director_required
from .models import UserProfile
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
    }
    return render(request, 'dashboard_app/report.html', context)


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
