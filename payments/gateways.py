"""
Ödəniş gateway abstraksiyası.

Kart məlumatı heç vaxt bu kodda görünmür — yalnız server→gateway invoice.
Real açarlar settings / Restaurant.payment_api_key ilə gəlir.
PAYMENTS_MOCK=True olanda MockGateway işləyir (dev).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class InvoiceResult:
    payment_url: str
    qr_code_url: str = ''
    invoice_id: str = ''
    raw: dict | None = None


class PaymentGateway(ABC):
    name: str = ''

    @abstractmethod
    def create_invoice(
        self,
        *,
        amount: Decimal,
        currency: str,
        order_id: int,
        description: str,
        callback_url: str,
        redirect_url: str,
        api_key: str,
    ) -> InvoiceResult:
        ...

    @abstractmethod
    def verify_webhook(self, body: bytes, signature: str | None, secret: str) -> bool:
        ...

    @abstractmethod
    def parse_webhook(self, data: dict) -> dict:
        """
        Vahid forma:
        {order_id, status: success|failed, transaction_id, amount?}
        """
        ...


class MockGateway(PaymentGateway):
    """Dev: real bank olmadan axını yoxlamaq üçün."""

    name = 'mock'

    def create_invoice(self, *, amount, currency, order_id, description, callback_url, redirect_url, api_key):
        base = getattr(settings, 'PUBLIC_API_BASE', 'http://127.0.0.1:8000')
        invoice_id = f'mock-{order_id}-{int(amount * 100)}'
        # Mock QR = eyni payment URL (frontend göstərir)
        payment_url = f'{base}/api/payments/mock-pay/{invoice_id}/'
        return InvoiceResult(
            payment_url=payment_url,
            qr_code_url=payment_url,
            invoice_id=invoice_id,
            raw={'mock': True, 'amount': str(amount), 'redirect_url': redirect_url},
        )

    def verify_webhook(self, body, signature, secret):
        # Mock-da imza optional; secret varsa yoxla
        if not secret:
            return True
        if not signature:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def parse_webhook(self, data):
        return {
            'order_id': int(data.get('order_id')),
            'status': data.get('status', 'success'),
            'transaction_id': data.get('transaction_id') or data.get('invoice_id'),
            'amount': data.get('amount'),
        }


class PayriffGateway(PaymentGateway):
    """
    Payriff — invoice/link/QR.
    Endpoint və field adları müqavilə sənədinə görə tənzimlənməlidir.
    """

    name = 'payriff'

    def create_invoice(self, *, amount, currency, order_id, description, callback_url, redirect_url, api_key):
        url = getattr(
            settings,
            'PAYRIFF_INVOICE_URL',
            'https://api.payriff.com/api/v3/invoices',
        )
        payload = {
            'amount': str(amount),
            'currency': currency,
            'orderId': str(order_id),
            'description': description,
            'callbackUrl': callback_url,
            'redirectUrl': redirect_url,
        }
        resp = requests.post(
            url,
            json=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        # Cavab strukturu gateway-ə görə fərqlənə bilər
        payment_url = (
            data.get('paymentUrl')
            or data.get('payment_url')
            or data.get('payload', {}).get('paymentUrl')
            or ''
        )
        qr_url = (
            data.get('qrCodeUrl')
            or data.get('qr_code_url')
            or data.get('payload', {}).get('qrCodeUrl')
            or ''
        )
        invoice_id = str(
            data.get('id')
            or data.get('invoiceId')
            or data.get('payload', {}).get('id')
            or ''
        )
        return InvoiceResult(
            payment_url=payment_url,
            qr_code_url=qr_url,
            invoice_id=invoice_id,
            raw=data,
        )

    def verify_webhook(self, body, signature, secret):
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def parse_webhook(self, data):
        status_raw = (data.get('status') or data.get('paymentStatus') or '').lower()
        ok = status_raw in ('success', 'paid', 'approved', 'completed')
        return {
            'order_id': int(data.get('orderId') or data.get('order_id')),
            'status': 'success' if ok else 'failed',
            'transaction_id': str(
                data.get('transactionId')
                or data.get('transaction_id')
                or data.get('id')
                or ''
            ),
            'amount': data.get('amount'),
        }


class EpointGateway(PaymentGateway):
    """Epoint — QR/link + split; field mapping müqaviləyə görə."""

    name = 'epoint'

    def create_invoice(self, *, amount, currency, order_id, description, callback_url, redirect_url, api_key):
        url = getattr(
            settings,
            'EPOINT_INVOICE_URL',
            'https://epoint.az/api/1/invoice',
        )
        payload = {
            'amount': str(amount),
            'currency': currency,
            'order_id': str(order_id),
            'description': description,
            'result_url': redirect_url,
            'callback_url': callback_url,
        }
        resp = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return InvoiceResult(
            payment_url=data.get('payment_url') or data.get('redirect_url') or '',
            qr_code_url=data.get('qr_code_url') or data.get('qr') or '',
            invoice_id=str(data.get('invoice_id') or data.get('id') or ''),
            raw=data,
        )

    def verify_webhook(self, body, signature, secret):
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def parse_webhook(self, data):
        status_raw = (data.get('status') or '').lower()
        ok = status_raw in ('success', 'paid', '1', 'ok')
        return {
            'order_id': int(data.get('order_id')),
            'status': 'success' if ok else 'failed',
            'transaction_id': str(data.get('transaction_id') or data.get('bank_transaction') or ''),
            'amount': data.get('amount'),
        }


def get_gateway(name: str | None) -> PaymentGateway:
    mock = getattr(settings, 'PAYMENTS_MOCK', True)
    key = (name or '').lower()
    if mock or key in ('', 'mock'):
        return MockGateway()
    if key == 'payriff':
        return PayriffGateway()
    if key == 'epoint':
        return EpointGateway()
    return MockGateway()


def public_api_base() -> str:
    return getattr(settings, 'PUBLIC_API_BASE', 'http://127.0.0.1:8000').rstrip('/')


def build_callback_url(gateway: str) -> str:
    return urljoin(public_api_base() + '/', f'api/payments/webhook/{gateway}/')


def build_redirect_url(order_id: int) -> str:
    menu = getattr(settings, 'PUBLIC_MENU_BASE', 'http://127.0.0.1:5173').rstrip('/')
    return f'{menu}/order/{order_id}/paid'
