import copy

import pytest

_CONSISTENT = {
    "vendor_name": "Northwind Supplies Ltd",
    "invoice_number": "T-1",
    "invoice_date": "2026-01-10",
    "due_date": "2026-02-09",
    "currency": "USD",
    "line_items": [
        {"description": "Widget", "quantity": "2", "unit_price": "10.00", "amount": "20.00"},
        {"description": "Gadget", "quantity": "3", "unit_price": "5.50", "amount": "16.50"},
    ],
    "subtotal": "36.50",
    "tax": "3.65",
    "total": "40.15",
}


@pytest.fixture
def invoice_data() -> dict:
    """A consistent invoice: 2 x 10.00 + 3 x 5.50 = 36.50, plus 3.65 tax = 40.15."""
    return copy.deepcopy(_CONSISTENT)
