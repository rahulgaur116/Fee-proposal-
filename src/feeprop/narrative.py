"""Narrative drafting around a locked number.

The template is markdown with two kinds of slots:

  {{key}}                 - filled deterministically from the fee model/analysis
  {{draft:slot|guidance}} - prose drafted by the model, with the locked numbers
                            injected read-only

After assembly, every dollar figure in the document is checked against the
locked fee model; anything the drafting step invented gets flagged. The number
was decided at pricing time - drafting is not allowed to move it.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from . import llm
from .assumptions import render_assumptions, render_exclusions
from .models import FeeModel, RateCard, ScopeAnalysis

DRAFT_SLOT_RE = re.compile(r"\{\{draft:([a-zA-Z0-9_-]+)(?:\|([^}]*))?\}\}")
KEY_SLOT_RE = re.compile(r"\{\{(?!draft:)([a-zA-Z0-9_.-]+)\}\}")
MONEY_RE = re.compile(r"\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?")

SYSTEM = """You are writing fee-proposal narrative for a US owner's-representation \
and cost-management firm. Confident, specific, client-facing prose - no filler, no \
generic consulting language. You write around numbers that are already decided: you \
may repeat a provided figure verbatim, but you never compute, estimate, round, or \
invent a dollar amount, hour count, or rate that was not given to you."""


class DraftSection(BaseModel):
    slot: str
    text: str = Field(description="Markdown prose for this slot, no heading")


class DraftSections(BaseModel):
    sections: list[DraftSection]


def fmt_money(x: float) -> str:
    if abs(x - round(x)) < 0.005:
        return f"${round(x):,.0f}"
    return f"${x:,.2f}"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def fee_by_year_table(m: FeeModel) -> str:
    rows = [[f"Year {y}", fmt_money(v)] for y, v in sorted(m.fee_by_year.items())]
    if m.contingency_amount:
        rows.append([f"Contingency ({m.contingency_pct:g}%)", fmt_money(m.contingency_amount)])
    if m.rounding_adjustment:
        rows.append(["Rounding", fmt_money(m.rounding_adjustment)])
    rows.append(["**Total**", f"**{fmt_money(m.total_fee)}**"])
    return _md_table(["Period", "Fee"], rows)


def fee_by_role_table(m: FeeModel, rate_card: RateCard) -> str:
    rows = []
    for code in sorted(m.fee_by_role):
        role = rate_card.role(code)
        rows.append([role.title, f"{m.hours_by_role.get(code, 0):,.0f}",
                     fmt_money(role.bill_rate), fmt_money(m.fee_by_role[code])])
    rows.append(["**Total**", f"**{sum(m.hours_by_role.values()):,.0f}**", "",
                 f"**{fmt_money(m.subtotal)}**"])
    return _md_table(["Role", "Hours", "Base Rate", "Fee"], rows)


def fee_detail_table(m: FeeModel) -> str:
    rows = [[pl.deliverable, pl.role_title, pl.basis,
             f"{pl.total_hours:,.0f}", fmt_money(pl.amount)] for pl in m.lines]
    return _md_table(["Deliverable", "Role", "Basis", "Hours", "Fee"], rows)


def deterministic_fills(analysis: ScopeAnalysis, m: FeeModel,
                        rate_card: RateCard) -> dict[str, str]:
    facts = analysis.facts
    return {
        "firm": rate_card.firm,
        "client_name": facts.client_name,
        "project_name": facts.project_name,
        "date": date.today().strftime("%B %d, %Y"),
        "total_fee": fmt_money(m.total_fee),
        "term_months": str(m.term_months),
        "escalation_pct": f"{m.escalation_pct:g}",
        "lock_id": m.lock.lock_id,
        "fee_pct_of_construction": (
            f"{m.fee_pct_of_construction:.2f}%" if m.fee_pct_of_construction else "n/a"),
        "fee_by_year_table": fee_by_year_table(m),
        "fee_by_role_table": fee_by_role_table(m, rate_card),
        "fee_detail_table": fee_detail_table(m),
        "assumptions_section": render_assumptions(analysis, m),
        "exclusions_section": render_exclusions(analysis),
    }


def allowed_amounts(m: FeeModel, analysis: ScopeAnalysis,
                    rate_card: RateCard) -> set[str]:
    values: list[float] = [
        m.total_fee, m.subtotal, m.flat_rate_subtotal, m.escalation_capture,
        m.contingency_amount, m.rounding_adjustment,
        *m.fee_by_year.values(), *m.fee_by_role.values(),
        *m.fee_by_phase.values(), *m.fee_by_deliverable.values(),
        *(pl.amount for pl in m.lines), *(pl.flat_amount for pl in m.lines),
        *(r.bill_rate for r in rate_card.roles),
    ]
    if analysis.facts.construction_value:
        cv = analysis.facts.construction_value
        values += [cv, cv / 1e6]
    allowed = set()
    for v in values:
        allowed.add(fmt_money(v))
        allowed.add(f"${v:,.2f}")
        allowed.add(f"${round(v):,.0f}")
    return allowed


def verify_numbers(doc: str, allowed: set[str]) -> list[str]:
    """Every dollar figure in the doc must trace to the locked model."""
    flagged = []
    for match in MONEY_RE.findall(doc):
        if match not in allowed:
            flagged.append(match)
    return sorted(set(flagged))


def draft(template: str, analysis: ScopeAnalysis, m: FeeModel,
          rate_card: RateCard) -> tuple[str, list[str]]:
    """Returns (document, warnings)."""
    fills = deterministic_fills(analysis, m, rate_card)

    def fill_key(match: re.Match) -> str:
        key = match.group(1)
        return fills.get(key, match.group(0))

    doc = KEY_SLOT_RE.sub(fill_key, template)

    warnings = [f"Template placeholder {{{{{k}}}}} has no known fill."
                for k in KEY_SLOT_RE.findall(doc)]

    slots = DRAFT_SLOT_RE.findall(doc)
    if slots:
        slot_desc = "\n".join(
            f"- {name}: {guidance or 'write this section'}" for name, guidance in slots)
        locked = {
            "total_fee": fmt_money(m.total_fee),
            "fee_by_year": {f"Year {y}": fmt_money(v)
                            for y, v in sorted(m.fee_by_year.items())},
            "term_months": m.term_months,
            "escalation_pct": m.escalation_pct,
            "total_hours": round(sum(m.hours_by_role.values())),
            "team": {rate_card.role(c).title: h for c, h in m.hours_by_role.items()},
        }
        prompt = (
            "Draft the following proposal sections. Return one section per slot.\n\n"
            f"Sections to write:\n{slot_desc}\n\n"
            "Locked figures - repeat verbatim if referenced, never derive new ones:\n"
            f"{locked}\n\n"
            "<scope_analysis>\n"
            f"{analysis.model_dump_json(indent=2)}\n"
            "</scope_analysis>\n\n"
            "<fee_summary>\n"
            f"{m.model_dump_json(indent=2, exclude={'lines'})}\n"
            "</fee_summary>"
        )
        result = llm.extract(SYSTEM, prompt, DraftSections, max_tokens=32000)
        by_slot = {s.slot: s.text for s in result.sections}

        def fill_draft(match: re.Match) -> str:
            name = match.group(1)
            if name in by_slot:
                return by_slot[name]
            warnings.append(f"Draft slot '{name}' was not returned by the model.")
            return f"_[section '{name}' missing]_"

        doc = DRAFT_SLOT_RE.sub(fill_draft, doc)

    flagged = verify_numbers(doc, allowed_amounts(m, analysis, rate_card))
    for f in flagged:
        warnings.append(
            f"Dollar figure {f} in the draft does not trace to the locked fee model "
            f"(lock {m.lock.lock_id}) - review before sending.")
    return doc, warnings
