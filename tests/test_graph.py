import json
from pathlib import Path

import pytest

from invoice_extractor.__main__ import main
from invoice_extractor.extractors import FakeExtractor, build_messages
from invoice_extractor.graph import process_invoice

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_valid_first_attempt_is_done(invoice_data):
    fake = FakeExtractor([invoice_data])
    result = process_invoice("text", fake)
    assert result["status"] == "done"
    assert result["attempts"] == 1
    assert fake.calls == [[]]


def test_retry_receives_the_specific_error_and_can_fix_it(invoice_data):
    wrong = {**invoice_data, "total": "41.05"}
    fake = FakeExtractor([wrong, invoice_data])
    result = process_invoice("text", fake)

    assert result["status"] == "done"
    assert result["attempts"] == 2
    assert fake.calls[0] == []
    assert len(fake.calls[1]) == 1
    assert fake.calls[1][0].startswith("total:")
    assert "41.05" in fake.calls[1][0]


def test_persistent_failure_goes_to_review_with_field_flagged(invoice_data):
    wrong = {**invoice_data, "total": "41.05"}
    fake = FakeExtractor([wrong, wrong])
    result = process_invoice("text", fake)

    assert result["status"] == "needs_review"
    assert result["attempts"] == 2
    assert result["flagged_fields"] == ["total"]
    assert result["invoice"]["total"] == "41.05"  # the reviewer sees what the model read


@pytest.mark.parametrize("max_retries, expected_attempts", [(0, 1), (1, 2), (3, 4)])
def test_max_retries_is_configurable(invoice_data, max_retries, expected_attempts):
    wrong = {**invoice_data, "total": "0.00"}
    fake = FakeExtractor([wrong])
    result = process_invoice("text", fake, max_retries=max_retries)
    assert result["status"] == "needs_review"
    assert result["attempts"] == expected_attempts


def test_schema_mismatch_is_retried_then_reviewed(invoice_data):
    broken = {**invoice_data, "total": "not a number"}
    fake = FakeExtractor([broken, broken])
    result = process_invoice("text", fake)
    assert result["status"] == "needs_review"
    assert result["flagged_fields"] == ["_schema"]
    assert result["invoice"] is None
    assert fake.calls[1]  # the schema error was fed back too


def test_retry_prompt_contains_feedback():
    first = build_messages("INVOICE")
    retry = build_messages("INVOICE", ["total: subtotal + tax = 10 but total is 11"])
    assert len(first) == 2
    assert "total: subtotal + tax = 10 but total is 11" in retry[-1][1]


@pytest.mark.parametrize("sample, status, attempts, flagged", [
    ("northwind_supplies", "done", 1, []),
    ("harbor_light_logistics", "done", 2, []),
    ("crestline_facility_services", "needs_review", 2, ["subtotal"]),
])
def test_cli_demo_mode(capsys, sample, status, attempts, flagged):
    exit_code = main([str(SAMPLES / f"{sample}.txt"), "--demo"])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == status
    assert result["attempts"] == attempts
    assert result["flagged_fields"] == flagged
    assert exit_code == (0 if status == "done" else 2)
