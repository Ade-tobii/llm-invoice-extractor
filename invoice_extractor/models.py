"""Pydantic schema the LLM must fill in.

Money is Decimal end to end: floats cannot represent 0.10 exactly, and an
invoice check that fails because of binary rounding is a false alarm.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, field_validator


def _to_decimal(value: object) -> object:
    """Accept '1,284.50', '$1,284.50' or 1284.5 and turn them into Decimal."""
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip().lstrip("$£€").strip()
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return value  # let Pydantic raise a normal validation error
    if isinstance(value, float):
        return Decimal(str(value))  # avoid Decimal(0.1) == 0.1000000000000000055...
    return value


class LineItem(BaseModel):
    description: str
    quantity: Decimal = Field(description="Units billed, as printed")
    unit_price: Decimal = Field(description="Price per unit, as printed")
    amount: Decimal = Field(description="Line total, as printed on the invoice")

    _money = field_validator("quantity", "unit_price", "amount", mode="before")(_to_decimal)


class Invoice(BaseModel):
    vendor_name: str
    invoice_number: str
    invoice_date: str = Field(description="Invoice date as ISO 8601 (YYYY-MM-DD)")
    due_date: str | None = Field(default=None, description="Due date as ISO 8601, if present")
    currency: str = Field(description="ISO 4217 code, e.g. USD")
    line_items: list[LineItem]
    subtotal: Decimal = Field(description="Subtotal exactly as printed on the invoice")
    tax: Decimal = Field(default=Decimal("0"), description="Total tax as printed")
    total: Decimal = Field(description="Amount due exactly as printed on the invoice")

    _money = field_validator("subtotal", "tax", "total", mode="before")(_to_decimal)
