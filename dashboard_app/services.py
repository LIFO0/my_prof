from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import AccreditationStatus


DATA_FILE = settings.BASE_DIR / 'data' / 'dop_material.csv'
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetBounds:
    revenue: tuple[Optional[int], Optional[int]]
    expenses: tuple[Optional[int], Optional[int]]
    taxes: tuple[Optional[int], Optional[int]]
    staff: tuple[Optional[int], Optional[int]]


def _clean_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower().startswith('нет данных'):
        return None
    return text


def _parse_money(value: Optional[str]) -> Optional[int]:
    text = _clean_str(value)
    if not text:
        return None
    cleaned = (
        text.replace('₽', '')
        .replace(' ', '')
        .replace('\xa0', '')
        .replace(',', '.')
    )
    try:
        amount = Decimal(cleaned)
    except Exception:
        return None
    return int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _parse_int(value: Optional[str]) -> Optional[int]:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    text = _clean_str(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {'да', 'yes'}:
        return True
    if lowered in {'нет', 'no'}:
        return False
    return None


def _normalize_row(row: Dict[str, str]) -> Dict[str, Optional[str | int | bool]]:
    revenue = _parse_money(row.get('Выручка, руб.'))
    expenses = _parse_money(row.get('Расходы, руб.'))
    taxes = _parse_money(row.get('Сумма уплаченных налогов, руб.'))
    staff = _parse_int(row.get('Среднесписочная численность'))
    return {
        'full_name': row.get('Полное наименование', '').strip(),
        'short_name': row.get('Сокращенное наименование', '').strip(),
        'inn': row.get('ИНН', '').strip(),
        'registered_at': _clean_str(row.get('Дата постановки на учёт')),
        'ceo': row.get('ИНН, ФИО руководителя', '').strip(),
        'okved': _clean_str(row.get('Основной ОКВЭД')),
        'revenue': revenue,
        'expenses': expenses,
        'taxes': taxes,
        'tax_year': _parse_int(row.get('Год уплаты налогов')),
        'staff': staff,
        'staff_year': _parse_int(row.get('Год данных о численности')),
        'uses_usn': _parse_bool(row.get('Применяет УСН')),
        'msme_at': _clean_str(row.get('Дата включения в реестр МСП')),
        'financial_result': (
            revenue - expenses if revenue is not None and expenses is not None else None
        ),
    }


@lru_cache(maxsize=1)
def load_dataset() -> List[Dict]:
    if not Path(DATA_FILE).exists():
        raise FileNotFoundError(
            f'Не удалось найти файл с данными по пути: {DATA_FILE}'
        )

    with open(DATA_FILE, encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh, delimiter=';')
        return [_normalize_row(row) for row in reader]


def calculate_bounds(rows: Iterable[Dict]) -> DatasetBounds:
    def field_bounds(field: str) -> tuple[Optional[int], Optional[int]]:
        values = [row[field] for row in rows if row[field] is not None]
        if not values:
            return (None, None)
        return (min(values), max(values))

    return DatasetBounds(
        revenue=field_bounds('revenue'),
        expenses=field_bounds('expenses'),
        taxes=field_bounds('taxes'),
        staff=field_bounds('staff'),
    )


def calculate_stats(rows: Iterable[Dict]) -> Dict[str, Optional[float | int]]:
    rows = list(rows)

    def total(field: str) -> Optional[int]:
        values = [row[field] for row in rows if row[field] is not None]
        return sum(values) if values else None

    def average(field: str) -> Optional[float]:
        values = [row[field] for row in rows if row[field] is not None]
        return float(sum(values) / len(values)) if values else None

    def share(predicate) -> Optional[float]:
        if not rows:
            return None
        matched = sum(1 for row in rows if predicate(row))
        return matched * 100 / len(rows)

    top_company = None
    accredited_count = 0
    for row in rows:
        revenue = row.get('revenue')
        if revenue is None:
            continue
        if not top_company or revenue > top_company['revenue']:
            top_company = row
        accreditation = row.get('accreditation')
        if accreditation:
            status = getattr(accreditation, 'status', '') or (
                accreditation.get('status') if isinstance(accreditation, dict) else ''
            )
            if isinstance(status, str) and 'действ' in status.lower():
                accredited_count += 1

    return {
        'count': len(rows),
        'total_revenue': total('revenue'),
        'total_expenses': total('expenses'),
        'total_taxes': total('taxes'),
        'avg_staff': average('staff'),
        'usn_share': share(lambda r: r.get('uses_usn') is True),
        'top_company': top_company,
        'accredited': accredited_count,
    }


def available_filter_options(rows: Iterable[Dict]) -> Dict[str, List]:
    rows = list(rows)
    okveds = sorted({row['okved'] for row in rows if row['okved']})
    tax_years = sorted(
        {row['tax_year'] for row in rows if row['tax_year'] is not None},
        reverse=True,
    )
    staff_years = sorted(
        {row['staff_year'] for row in rows if row['staff_year'] is not None},
        reverse=True,
    )

    return {
        'okveds': okveds,
        'tax_years': tax_years,
        'staff_years': staff_years,
    }


def apply_filters(rows: Iterable[Dict], filters: Dict) -> List[Dict]:
    rows = list(rows)
    filtered = []
    search = filters.get('search')
    okved = filters.get('okved')
    uses_usn = filters.get('uses_usn')
    is_accredited = filters.get('is_accredited')
    min_revenue = filters.get('min_revenue')
    max_revenue = filters.get('max_revenue')
    min_taxes = filters.get('min_taxes')
    min_staff = filters.get('min_staff')
    tax_year = filters.get('tax_year')
    staff_year = filters.get('staff_year')

    for row in rows:
        if search:
            haystack = ' '.join(
                filter(
                    None,
                    [
                        row.get('full_name', ''),
                        row.get('short_name', ''),
                        row.get('ceo', ''),
                        row.get('okved', ''),
                    ],
                )
            ).lower()
            if search.lower() not in haystack:
                continue
        if okved and row.get('okved') != okved:
            continue
        if uses_usn is not None and row.get('uses_usn') != uses_usn:
            continue
        if is_accredited is not None:
            accreditation = row.get('accreditation')
            is_company_accredited = (
                accreditation is not None
                and accreditation.status == 'Действует'
            )
            if is_accredited != is_company_accredited:
                continue
        revenue = row.get('revenue')
        if min_revenue is not None and (
            revenue is None or revenue < min_revenue
        ):
            continue
        if max_revenue is not None and (
            revenue is None or revenue > max_revenue
        ):
            continue
        taxes = row.get('taxes')
        if min_taxes is not None and (taxes is None or taxes < min_taxes):
            continue
        staff_val = row.get('staff')
        if min_staff is not None and (
            staff_val is None or staff_val < min_staff
        ):
            continue
        if tax_year is not None and row.get('tax_year') != tax_year:
            continue
        if staff_year is not None and row.get('staff_year') != staff_year:
            continue
        filtered.append(row)
    return filtered


def parse_filter_payload(query_params) -> Dict:
    def parse_int_param(name: str) -> Optional[int]:
        value = query_params.get(name)
        if value in (None, ''):
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def parse_bool_param(name: str) -> Optional[bool]:
        value = query_params.get(name)
        if value in (None, ''):
            return None
        if value.lower() == 'yes':
            return True
        if value.lower() == 'no':
            return False
        return None

    return {
        'search': query_params.get('search', '').strip() or None,
        'okved': query_params.get('okved') or None,
        'uses_usn': parse_bool_param('uses_usn'),
        'is_accredited': parse_bool_param('is_accredited'),
        'min_revenue': parse_int_param('min_revenue'),
        'max_revenue': parse_int_param('max_revenue'),
        'min_taxes': parse_int_param('min_taxes'),
        'min_staff': parse_int_param('min_staff'),
        'tax_year': parse_int_param('tax_year'),
        'staff_year': parse_int_param('staff_year'),
    }


# Accreditation helpers
def _build_accreditation_payload(inn: str) -> Dict:
    return {
        'filter': {
            'simple': {
                'attributeName': 'INN',
                'condition': 'EQUALS',
                'value': {'asString': inn},
            }
        },
        'treeFiltering': 'ONELEVEL',
        'pageNum': 1,
        'pageSize': 10,
        'parentRefItemValue': '',
        'selectAttributes': ['*'],
    }


def _parse_api_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _post_json(url: str, payload: Dict) -> Dict:
    data = json.dumps(payload).encode('utf-8')
    req = Request(
        url,
        data=data,
        headers=settings.NSI_API_HEADERS,
        method='POST',
    )
    with urlopen(req, timeout=15) as response:
        body = response.read().decode('utf-8')
    return json.loads(body)


def fetch_accreditation_entry(inn: str) -> Dict:
    """Call external NSI API for a single INN and return the raw payload."""
    payload = _build_accreditation_payload(inn)
    data = _post_json(settings.NSI_IT_DICTIONARY_URL, payload)
    items = data.get('items', [])
    return items[0] if items else {}


def sync_accreditation_statuses(inns: Iterable[str]) -> List[Dict]:
    """
    Fetch accreditation info for provided INNs and persist it.

    Returns a list with execution summary for UI.
    """
    results: List[Dict] = []
    unique_inns = sorted({inn.strip() for inn in inns if inn})
    for inn in unique_inns:
        try:
            entry = fetch_accreditation_entry(inn)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.exception('Ошибка запроса аккредитации: %s', inn)
            results.append(
                {'inn': inn, 'success': False, 'error': str(exc)}
            )
            continue

        if not entry:
            AccreditationStatus.objects.update_or_create(
                inn=inn,
                defaults={
                    'name': inn,
                    'status': 'Нет записи в реестре',
                    'decision_number': '',
                    'decision_date': None,
                    'registry_record_date': None,
                    'raw_payload': {},
                    'checked_at': timezone.now(),
                },
            )
            results.append(
                {
                    'inn': inn,
                    'success': True,
                    'status': 'Нет записи в реестре',
                }
            )
            continue

        attrs = entry.get('attributeValues', {})
        status = attrs.get('Status', 'Неизвестно')
        name = attrs.get('Name_Organization') or attrs.get('Name_INN') or inn
        AccreditationStatus.objects.update_or_create(
            inn=inn,
            defaults={
                'name': name,
                'status': status,
                'decision_number': attrs.get('Number_Decision', ''),
                'decision_date': _parse_api_date(attrs.get('Date_Decision')),
                'registry_record_date': _parse_api_date(
                    attrs.get('Date_record')
                ),
                'raw_payload': entry,
                'checked_at': timezone.now(),
            },
        )
        results.append({'inn': inn, 'success': True, 'status': status})
    return results


def get_accreditations_for_inns(
    inns: Iterable[str],
) -> Dict[str, AccreditationStatus]:
    records = AccreditationStatus.objects.filter(inn__in=inns)
    return {record.inn: record for record in records}
