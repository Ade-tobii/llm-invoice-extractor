"""Deterministic checks on an extracted invoice.

Pure Python, no LLM imports. Every issue names the field it concerns so the
retry prompt and the human reviewer both know exactly where to look.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from invoice_extractor.models import Invoice

DEFAULT_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class Issue:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def _parse_iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_invoice(invoice: Invoice, tolerance: Decimal = DEFAULT_TOLERANCE) -> list[Issue]:
    """Return every rule the invoice breaks. An empty list means it is consistent."""
    issues: list[Issue] = []

    def off(a: Decimal, b: Decimal) -> bool:
        return abs(a - b) > tolerance

    if not invoice.line_items:
        issues.append(Issue("line_items", "no line items extracted"))

    for i, item in enumerate(invoice.line_items):
        expected = item.quantity * item.unit_price
        if off(expected, item.amount):
            issues.append(Issue(
                f"line_items[{i}].amount",
                f"quantity x unit_price = {expected} but amount is {item.amount}",
            ))

    items_sum = sum((item.amount for item in invoice.line_items), Decimal("0"))
    if invoice.line_items and off(items_sum, invoice.subtotal):
        issues.append(Issue(
            "subtotal",
            f"line items sum to {items_sum} but subtotal is {invoice.subtotal}",
        ))

    if off(invoice.subtotal + invoice.tax, invoice.total):
        issues.append(Issue(
            "total",
            f"subtotal + tax = {invoice.subtotal + invoice.tax} but total is {invoice.total}",
        ))

    for name in ("subtotal", "tax", "total"):
        if getattr(invoice, name) < 0:
            issues.append(Issue(name, "must not be negative"))

    invoice_date = _parse_iso(invoice.invoice_date)
    if invoice_date is None:
        issues.append(Issue("invoice_date", f"{invoice.invoice_date!r} is not a YYYY-MM-DD date"))

    if invoice.due_date is not None:
        due_date = _parse_iso(invoice.due_date)
        if due_date is None:
            issues.append(Issue("due_date", f"{invoice.due_date!r} is not a YYYY-MM-DD date"))
        elif invoice_date is not None and due_date < invoice_date:
            issues.append(Issue("due_date", "is before invoice_date"))

    return issues
