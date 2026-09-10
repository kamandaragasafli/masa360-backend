"""
KOT (Kitchen Order Ticket) — ESC/POS termal çap.

Async: threading (UI gözləmir). Production-da Celery ilə əvəz edilə bilər:
  @shared_task
  def run_print_job_task(job_id): ...
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _dry_run() -> bool:
    return getattr(settings, 'KOT_DRY_RUN', True)


def build_ticket_payload(order, items: Iterable) -> dict:
    items = list(items)
    title = (
        f'Masa {order.table.number}'
        if order.table_id and order.table
        else f'Al-apar #{order.pk}'
    )
    return {
        'order_id': order.pk,
        'title': title,
        'time': timezone.localtime(order.created_at).strftime('%H:%M'),
        'notes': (order.notes or '').strip(),
        'station': None,
        'lines': [
            {
                'quantity': item.quantity,
                'name': item.menu_item.name,
                'note': (item.special_instructions or '').strip(),
            }
            for item in items
        ],
    }


def build_test_payload(printer_name: str) -> dict:
    now = timezone.localtime()
    return {
        'order_id': None,
        'title': 'TEST ÇAP',
        'time': now.strftime('%H:%M'),
        'notes': f'Printer: {printer_name}',
        'station': printer_name,
        'lines': [
            {'quantity': 1, 'name': 'Sınaq səhifəsi', 'note': 'Quraşdırma OK'},
        ],
    }


def _money_line(label: str, value: str, width: int = 32) -> str:
    label = str(label)
    value = str(value)
    space = max(1, width - len(label) - len(value))
    return f'{label}{" " * space}{value}\n'


def render_escpos(printer_host: str, port: int, payload: dict) -> None:
    """Real ESC/POS şəbəkə çapı (və ya dry-run log). KOT və ya müştəri qəbzi."""
    if _dry_run():
        logger.info(
            'PRINT DRY-RUN → %s:%s | kind=%s | %s | %s',
            printer_host,
            port,
            payload.get('kind', 'kot'),
            payload.get('title'),
            payload.get('lines'),
        )
        return

    from escpos.printer import Network

    printer = Network(printer_host, port=port, timeout=5)
    try:
        if payload.get('kind') == 'receipt':
            _render_receipt_escpos(printer, payload)
        else:
            _render_kot_escpos(printer, payload)
    finally:
        try:
            printer.close()
        except Exception:
            pass


def _render_kot_escpos(printer, payload: dict) -> None:
    printer.set(align='center', bold=True, width=2, height=2)
    printer.text(f"{payload.get('title', '')}\n")
    printer.set(align='left', bold=False, width=1, height=1)
    printer.text(f"Vaxt: {payload.get('time', '')}\n")
    if payload.get('station'):
        printer.text(f"Stansiya: {payload['station']}\n")
    if payload.get('order_id'):
        printer.text(f"Sifariş #{payload['order_id']}\n")
    printer.text('-' * 32 + '\n')
    for line in payload.get('lines') or []:
        printer.set(bold=True)
        printer.text(f"{line['quantity']}x {line['name']}\n")
        if line.get('note'):
            printer.set(bold=False)
            printer.text(f"  -> {line['note']}\n")
    if payload.get('notes'):
        printer.set(bold=False)
        printer.text('-' * 32 + '\n')
        printer.text(f"Qeyd: {payload['notes']}\n")
    printer.text('-' * 32 + '\n')
    printer.cut()


def _render_receipt_escpos(printer, payload: dict) -> None:
    currency = payload.get('currency_symbol') or '₼'
    printer.set(align='center', bold=True, width=2, height=2)
    printer.text(f"{payload.get('restaurant_name') or payload.get('title', '')}\n")
    printer.set(align='center', bold=False, width=1, height=1)
    printer.text('QƏBZ\n')
    if payload.get('subtitle'):
        printer.text(f"{payload['subtitle']}\n")
    printer.set(align='left', bold=False, width=1, height=1)
    printer.text(f"Sifariş #{payload.get('order_id', '')}\n")
    printer.text(f"Vaxt: {payload.get('time', '')}\n")
    printer.text(f"Ödəniş: {payload.get('method_label', '')}\n")
    printer.text('-' * 32 + '\n')
    for line in payload.get('lines') or []:
        printer.set(bold=True)
        printer.text(f"{line['quantity']}x {line['name']}\n")
        printer.set(bold=False)
        amt = line.get('amount') or line.get('line_total') or ''
        if amt != '':
            printer.text(_money_line('  ', f'{amt} {currency}'))
    printer.text('-' * 32 + '\n')
    printer.set(bold=True)
    printer.text(
        _money_line('Yekun', f"{payload.get('total', '')} {currency}")
    )
    printer.set(bold=False)
    if payload.get('tendered') is not None:
        printer.text(
            _money_line('Verildi', f"{payload['tendered']} {currency}")
        )
    if payload.get('change') is not None and str(payload.get('change')) not in (
        '0',
        '0.00',
        '',
    ):
        printer.text(
            _money_line('Qaytarılacaq', f"{payload['change']} {currency}")
        )
    printer.text('-' * 32 + '\n')
    printer.set(align='center')
    printer.text('Təşəkkür edirik!\n')
    printer.cut()

def execute_print_job(job_id: int) -> None:
    from orders.models import PrintJob

    try:
        job = PrintJob.objects.select_related('printer').get(pk=job_id)
    except PrintJob.DoesNotExist:
        return

    job.status = 'printing'
    job.error_message = ''
    job.save(update_fields=['status', 'error_message', 'updated_at'])

    printer = job.printer
    try:
        if not printer.is_active:
            raise RuntimeError('Printer deaktivdir')
        render_escpos(printer.ip_address, printer.port, job.payload or {})
        job.status = 'success'
        if _dry_run():
            job.error_message = 'dry_run: şəbəkəyə göndərilmədi (KOT_DRY_RUN=True)'
        job.save(update_fields=['status', 'error_message', 'updated_at'])
    except Exception as exc:
        logger.exception('KOT çap uğursuz: job=%s', job_id)
        job.status = 'failed'
        job.error_message = str(exc)[:500]
        job.save(update_fields=['status', 'error_message', 'updated_at'])


def enqueue_print_job(job_id: int) -> None:
    """UI-ni gözlətmədən çap — thread (Celery əvəzinə lokal)."""
    thread = threading.Thread(
        target=execute_print_job,
        args=(job_id,),
        daemon=True,
        name=f'kot-print-{job_id}',
    )
    thread.start()


def enqueue_kitchen_tickets(order) -> list:
    """
    OrderItem-ləri kateqoriya.printer-ə görə qruplayıb KOT çapını başladır.
    Printer təyin olunmayanlar → restoranin ilk aktiv printeri.
    """
    from orders.models import PrintJob

    restaurant = order.restaurant
    if not restaurant.uses_printer:
        return []

    default_printer = (
        restaurant.printers.filter(is_active=True).order_by('id').first()
    )
    groups = defaultdict(list)

    items = order.items.select_related(
        'menu_item__category__printer'
    ).all()

    for item in items:
        printer = None
        cat = item.menu_item.category
        if cat is not None and cat.printer_id:
            p = cat.printer
            if p and p.is_active:
                printer = p
        if printer is None:
            printer = default_printer
        if printer is None:
            continue
        groups[printer.id].append(item)

    jobs = []
    printers = {
        p.id: p
        for p in restaurant.printers.filter(id__in=groups.keys())
    }
    for printer_id, group_items in groups.items():
        printer = printers.get(printer_id)
        if not printer:
            continue
        payload = build_ticket_payload(order, group_items)
        payload['station'] = printer.name
        job = PrintJob.objects.create(
            order=order,
            printer=printer,
            payload=payload,
            status='pending',
        )
        jobs.append(job)
        enqueue_print_job(job.id)

    return jobs


def enqueue_test_print(printer) -> 'PrintJob':
    from orders.models import PrintJob

    job = PrintJob.objects.create(
        order=None,
        printer=printer,
        payload=build_test_payload(printer.name),
        status='pending',
        is_test=True,
    )
    enqueue_print_job(job.id)
    return job


_CURRENCY_SYMBOL = {
    'AZN': '₼',
    'USD': '$',
    'EUR': '€',
    'TRY': '₺',
}


def build_receipt_payload(
    order,
    *,
    amount,
    method: str,
    tendered=None,
    change=None,
) -> dict:
    """Müştəri qəbzi — UI çapı və ESC/POS üçün eyni snapshot."""
    restaurant = order.restaurant
    currency = (restaurant.currency if restaurant else None) or 'AZN'
    symbol = _CURRENCY_SYMBOL.get(currency, currency)
    subtitle = (
        f'Masa {order.table.number}'
        if order.table_id and order.table
        else f'Al-apar #{order.pk}'
    )
    method_label = 'Nağd' if method == 'cash' else 'Kart'
    lines = []
    for item in order.items.select_related('menu_item').all():
        unit = item.unit_price
        line_total = (unit * item.quantity).quantize(Decimal('0.01'))
        lines.append(
            {
                'quantity': item.quantity,
                'name': item.menu_item.name,
                'unit_price': str(unit),
                'amount': str(line_total),
                'line_total': str(line_total),
            }
        )

    paid_at = timezone.localtime()
    return {
        'kind': 'receipt',
        'order_id': order.pk,
        'restaurant_name': (restaurant.name if restaurant else '') or 'Restoran',
        'title': subtitle,
        'subtitle': subtitle,
        'time': paid_at.strftime('%d.%m.%Y %H:%M'),
        'method': method,
        'method_label': method_label,
        'currency': currency,
        'currency_symbol': symbol,
        'lines': lines,
        'subtotal': str(order.total_amount),
        'total': str(amount),
        'tendered': str(tendered) if tendered is not None else None,
        'change': str(change) if change is not None else None,
        'notes': (order.notes or '').strip(),
    }


def enqueue_customer_receipt(
    order,
    *,
    amount,
    method: str,
    tendered=None,
    change=None,
):
    """
    Ödənişdən sonra müştəri qəbzini çap edir.
    İlk aktiv printerə gedir (kassa printeri yoxdursa mətbəx printeri).
    Printer yoxdursa None — frontend browser çapı istifadə edir.
    """
    from orders.models import PrintJob

    restaurant = order.restaurant
    if not restaurant:
        return None

    printer = restaurant.printers.filter(is_active=True).order_by('id').first()
    if not printer:
        return None

    payload = build_receipt_payload(
        order,
        amount=amount,
        method=method,
        tendered=tendered,
        change=change,
    )
    job = PrintJob.objects.create(
        order=order,
        printer=printer,
        payload=payload,
        status='pending',
    )
    enqueue_print_job(job.id)
    return job
