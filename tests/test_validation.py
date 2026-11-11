from decimal import Decimal

import pytest

from invoice_extractor.models import Invoice
from invoice_extractor.validation import validate_invoice


def fields(data: dict, **kwargs) -> list[str]:
    return [i.field for i in validate_invoice(Invoice.model_validate(data), **kwargs)]


def test_consistent_invoice_has_no_issues(invoice_data):
    assert fields(invoice_data) == []


def test_line_items_must_sum_to_subtotal(invoice_data):
    invoice_data["subtotal"] = "46.50"
    invoice_data["total"] = "50.15"  # keep subtotal + tax == total so only one rule fails
    assert fields(invoice_data) == ["subtotal"]


def test_subtotal_plus_tax_must_equal_total(invoice_data):
    invoice_data["total"] = "41.15"
    assert fields(invoice_data) == ["total"]


def test_line_amount_must_equal_quantity_times_price(invoice_data):
    invoice_data["line_items"][1]["amount"] = "15.50"
    invoice_data["subtotal"] = "35.50"
    invoice_data["total"] = "39.15"
    assert fields(invoice_data) == ["line_items[1].amount"]


@pytest.mark.parametrize("total, expected", [("40.16", []), ("40.14", []), ("40.17", ["total"])])
def test_rounding_tolerance_is_one_cent_by_default(invoice_data, total, expected):
    invoice_data["total"] = total
    assert fields(invoice_data) == expected


def test_tolerance_is_configurable(invoice_data):
    invoice_data["total"] = "40.20"
    assert fields(invoice_data) == ["total"]
    assert fields(invoice_data, tolerance=Decimal("0.05")) == []


def test_decimal_avoids_float_drift():
    # 0.1 + 0.2 != 0.3 in floats; with Decimal it holds even at zero tolerance.
    data = {
        "vendor_name": "V", "invoice_number": "1", "invoice_date": "2026-01-01", "currency": "USD",
        "line_items": [
            {"description": "a", "quantity": 1, "unit_price": 0.1, "amount": 0.1},
            {"description": "b", "quantity": 1, "unit_price": 0.2, "amount": 0.2},
        ],
        "subtotal": 0.3, "tax": 0, "total": 0.3,
    }
    assert fields(data, tolerance=Decimal("0")) == []


@pytest.mark.parametrize("bad", ["19/01/2026", "2026-02-30", "next Tuesday", ""])
def test_invoice_date_must_be_iso(invoice_data, bad):
    invoice_data["invoice_date"] = bad
    assert "invoice_date" in fields(invoice_data)


def test_due_date_cannot_precede_invoice_date(invoice_data):
    invoice_data["due_date"] = "2026-01-01"
    assert fields(invoice_data) == ["due_date"]


def test_due_date_is_optional(invoice_data):
    invoice_data["due_date"] = None
    assert fields(invoice_data) == []


def test_empty_line_items_is_flagged(invoice_data):
    invoice_data["line_items"] = []
    assert "line_items" in fields(invoice_data)


def test_negative_total_is_flagged(invoice_data):
    invoice_data.update(subtotal="-36.50", tax="0", total="-36.50", line_items=[])
    assert "total" in fields(invoice_data)


def test_money_strings_with_separators_and_symbols_parse():
    invoice = Invoice.model_validate({
        "vendor_name": "V", "invoice_number": "1", "invoice_date": "2026-01-01", "currency": "USD",
        "line_items": [], "subtotal": "$1,242.50", "tax": "124.25", "total": "1,366.75",
    })
    assert invoice.subtotal == Decimal("1242.50")
    assert invoice.total == Decimal("1366.75")


def test_all_failures_are_reported_not_just_the_first(invoice_data):
    invoice_data["subtotal"] = "99.00"
    invoice_data["invoice_date"] = "bad"
    assert set(fields(invoice_data)) == {"subtotal", "total", "invoice_date"}
