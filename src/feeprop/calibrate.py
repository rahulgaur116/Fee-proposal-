"""Calibration: turn past submissions into hours benchmarks.

This is the tooling behind the calibration engagement - feed it the firm's last
N submissions (as structured YAML records, or extracted from old proposal
documents with `extract_past`) and it produces the benchmarks the estimator
anchors to, plus win/loss fee positioning.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

import yaml

from . import llm
from .models import Benchmarks, DeliverableBenchmark, PastSubmission

EXTRACT_SYSTEM = """You are reconstructing the hours build-up behind a past fee \
proposal from an owner's-representation / cost-management firm, so it can be used \
to calibrate future estimates. Extract what the document supports; do not invent \
hours that are not stated or clearly derivable from a fee and a rate."""


def load_submissions(paths: list[str | Path]) -> list[PastSubmission]:
    subs = []
    for p in paths:
        data = yaml.safe_load(Path(p).read_text(encoding="utf-8"))
        subs.append(PastSubmission.model_validate(data))
    return subs


def extract_past(document_text: str) -> PastSubmission:
    """LLM-assisted extraction of a past proposal document into a record."""
    prompt = (
        "Extract this past fee proposal into a structured submission record. "
        "Hours lines: one per deliverable (and per role where the document shows "
        "the split). duration_months and fee are required - infer duration from "
        "the schedule if needed.\n\n"
        f"<past_proposal>\n{document_text}\n</past_proposal>"
    )
    return llm.extract(EXTRACT_SYSTEM, prompt, PastSubmission, max_tokens=16000)


def _norm(name: str) -> str:
    return " ".join(name.lower().replace("_", " ").replace("-", " ").split())


def build_benchmarks(subs: list[PastSubmission]) -> Benchmarks:
    # hours per deliverable, normalized per month of term (recurring work scales
    # with term; per-project medians would punish short jobs and flatter long ones)
    per_month: dict[str, list[float]] = defaultdict(list)
    for s in subs:
        by_deliv: dict[str, float] = defaultdict(float)
        for ln in s.lines:
            by_deliv[_norm(ln.deliverable)] += ln.hours
        for name, hours in by_deliv.items():
            if s.duration_months > 0:
                per_month[name].append(hours / s.duration_months)

    benchmarks = []
    for name, vals in sorted(per_month.items()):
        vals = sorted(vals)
        benchmarks.append(DeliverableBenchmark(
            deliverable=name,
            unit="per_month",
            n=len(vals),
            p25=round(_quantile(vals, 0.25), 2),
            p50=round(_quantile(vals, 0.50), 2),
            p75=round(_quantile(vals, 0.75), 2),
        ))

    won_pcts, lost_pcts = [], []
    for s in subs:
        if s.construction_value and s.construction_value > 0:
            pct = s.fee / s.construction_value * 100.0
            if s.won is True:
                won_pcts.append(pct)
            elif s.won is False:
                lost_pcts.append(pct)

    return Benchmarks(
        n_submissions=len(subs),
        deliverables=benchmarks,
        fee_pct_won_median=round(statistics.median(won_pcts), 3) if won_pcts else None,
        fee_pct_lost_median=round(statistics.median(lost_pcts), 3) if lost_pcts else None,
        notes=(f"Calibrated from {len(subs)} submissions. per_month = total hours on "
               "that deliverable divided by contract months."),
    )


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def save_benchmarks(b: Benchmarks, path: str | Path) -> None:
    Path(path).write_text(
        yaml.safe_dump(b.model_dump(mode="json"), sort_keys=False), encoding="utf-8")


def load_benchmarks(path: str | Path) -> Benchmarks:
    return Benchmarks.model_validate(
        yaml.safe_load(Path(path).read_text(encoding="utf-8")))
