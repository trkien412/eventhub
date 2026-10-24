"""Bộ lọc hiển thị dùng chung cho giao diện EventHub."""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def vnd(value):
    """Định dạng số tiền theo kiểu Việt Nam: 150000 -> 150.000."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{amount:,.0f}".replace(",", ".")
