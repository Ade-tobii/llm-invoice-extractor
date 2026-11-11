"""LangGraph pipeline: extract -> validate -> (retry_extract | needs_review | done)."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from invoice_extractor.extractors import Extractor
from invoice_extractor.models import Invoice
from invoice_extractor.validation import DEFAULT_TOLERANCE, Issue, validate_invoice

log = logging.getLogger(__name__)

Status = Literal["done", "needs_review"]


class State(TypedDict, total=False):
    text: str
    invoice: Invoice | None
    issues: list[Issue]
    attempts: int
    status: Status


def build_graph(
    extractor: Extractor,
    max_retries: int = 1,
    tolerance: Decimal = DEFAULT_TOLERANCE,
):
    def run_extractor(state: State, feedback: list[str]) -> State:
        attempt = state.get("attempts", 0) + 1
        try:
            invoice = extractor.extract(state["text"], feedback)
        except ValueError as exc:  # pydantic/parser errors: output did not fit the schema
            invoice, error = None, str(exc).splitlines()[0]
        else:
            error = "model returned no structured output" if invoice is None else None
        issues = [Issue("_schema", error)] if error else []
        return {"invoice": invoice, "issues": issues, "attempts": attempt}

    def extract(state: State) -> State:
        return run_extractor(state, feedback=[])

    def retry_extract(state: State) -> State:
        # Send the specific failures back so the model knows where to look.
        return run_extractor(state, feedback=[str(i) for i in state["issues"]])

    def validate(state: State) -> State:
        if state.get("invoice") is None:
            issues = state["issues"]
        else:
            issues = validate_invoice(state["invoice"], tolerance)
        if issues:
            log.info("attempt %d failed: %s", state["attempts"], "; ".join(map(str, issues)))
        else:
            log.info("attempt %d passed validation", state["attempts"])
        return {"issues": issues}

    def route(state: State) -> str:
        if not state["issues"]:
            return "done"
        if state["attempts"] <= max_retries:
            return "retry_extract"
        return "needs_review"

    def done(state: State) -> State:
        return {"status": "done"}

    def needs_review(state: State) -> State:
        # In production this would enqueue a review task; here we just mark it.
        return {"status": "needs_review"}

    graph = StateGraph(State)
    graph.add_node("extract", extract)
    graph.add_node("validate", validate)
    graph.add_node("retry_extract", retry_extract)
    graph.add_node("needs_review", needs_review)
    graph.add_node("done", done)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "validate")
    graph.add_conditional_edges("validate", route, ["retry_extract", "needs_review", "done"])
    graph.add_edge("retry_extract", "validate")
    graph.add_edge("needs_review", END)
    graph.add_edge("done", END)
    return graph.compile()


def process_invoice(
    text: str,
    extractor: Extractor,
    max_retries: int = 1,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> dict:
    """Run the pipeline and return a JSON-serialisable result."""
    final = build_graph(extractor, max_retries, tolerance).invoke({"text": text, "attempts": 0})
    invoice = final.get("invoice")
    return {
        "status": final["status"],
        "attempts": final["attempts"],
        "flagged_fields": sorted({i.field for i in final["issues"]}),
        "issues": [{"field": i.field, "message": i.message} for i in final["issues"]],
        "invoice": invoice.model_dump(mode="json") if invoice else None,
    }
