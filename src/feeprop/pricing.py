"""Deterministic pricing engine.

The one rule of this module: no LLM anywhere near the number. The estimator
proposes hours; this module derives quantities, spreads hours across contract
years, escalates rates per year, checks margins, and locks the total.

Pricing discipline encoded here:
  - Recurring deliverables are quantity x unit-hours, with the quantity derived
    from the contract term - never a guessed lump sum.
  - Rates escalate at each contract anniversary. The engine also computes the
    "flat trap": what the fee would be if year-one rates were priced flat
    across the term, so the escalation capture is visible on every job.
  - Margin per role is checked against loaded cost with the same escalation.
  - The total is locked with a content hash; downstream drafting cannot move it.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import (
    Cadence,
    Estimate,
    FeeLock,
    FeeModel,
    HoursLine,
    Phase,
    PricedLine,
    RateCard,
    RoleMargin,
    ScopeAnalysis,
    compute_lock_id,
)

DEFAULT_TERM_MONTHS = 12
WEEKS_PER_MONTH = 52.0 / 12.0


def contract_year(month: int) -> int:
    """1-based contract year for a 1-based month from NTP."""
    return (month - 1) // 12 + 1


def resolve_phases(analysis: ScopeAnalysis, warnings: list[str]) -> tuple[list[Phase], int]:
    facts = analysis.facts
    term = facts.duration_months
    if term is None or term <= 0:
        term = DEFAULT_TERM_MONTHS
        warnings.append(
            f"Scope states no contract term; priced on an assumed {term}-month term. "
            "Confirm the term - it drives every recurring deliverable count.")
    phases = list(facts.phases)
    if not phases:
        phases = [Phase(name="Term", start_month=1, duration_months=term)]
    else:
        end = max(p.start_month + p.duration_months - 1 for p in phases)
        if end != term:
            warnings.append(
                f"Phases span {end} months but stated term is {term} months; "
                f"pricing follows the phases ({end} months).")
            term = end
    return phases, term


def find_phase(name: str | None, phases: list[Phase]) -> Phase:
    if name:
        for p in phases:
            if p.name.lower() == name.lower():
                return p
    return phases[0] if len(phases) == 1 else Phase(
        name="Term",
        start_month=min(p.start_month for p in phases),
        duration_months=max(p.start_month + p.duration_months - 1 for p in phases),
    )


def derive_quantity(line: HoursLine, phase: Phase, warnings: list[str]) -> float:
    """Quantity discipline: cadence lines derive their count from the term."""
    months = phase.duration_months
    derived: float | None = None
    if line.cadence == Cadence.once:
        derived = 1.0
    elif line.cadence == Cadence.monthly:
        derived = float(months)
    elif line.cadence == Cadence.weekly:
        derived = float(round(months * WEEKS_PER_MONTH))
    elif line.cadence == Cadence.quarterly:
        derived = float(math.ceil(months / 3))

    if derived is not None:
        if line.quantity is not None and abs(line.quantity - derived) > 0.5:
            warnings.append(
                f"{line.deliverable} / {line.role_code}: estimator proposed "
                f"{line.quantity:g} occurrences but the {line.cadence.value} cadence over "
                f"{months} months gives {derived:g}; using {derived:g}.")
        return derived

    # cadence == total: the estimator must say how many
    if line.quantity is None:
        warnings.append(
            f"{line.deliverable} / {line.role_code}: cadence 'total' with no quantity; "
            "assumed 1. Fix the estimate line.")
        return 1.0
    return line.quantity


def hours_by_year(total_hours: float, phase: Phase) -> dict[int, float]:
    """Spread hours uniformly over the phase months, bucketed by contract year."""
    months = list(range(phase.start_month, phase.start_month + phase.duration_months))
    per_month = total_hours / len(months)
    out: dict[int, float] = {}
    for m in months:
        y = contract_year(m)
        out[y] = out.get(y, 0.0) + per_month
    return {y: round(h, 4) for y, h in sorted(out.items())}


def price(analysis: ScopeAnalysis, estimate: Estimate, rate_card: RateCard) -> FeeModel:
    warnings: list[str] = []
    phases, term = resolve_phases(analysis, warnings)

    estimated_ids = {ln.deliverable_id for ln in estimate.lines}
    for d in analysis.deliverables:
        if d.id not in estimated_ids:
            warnings.append(
                f"Deliverable '{d.name}' ({d.id}) appears in the scope but has no "
                "hours line - it is being given away free. Add a line or an exclusion.")

    priced: list[PricedLine] = []
    for ln in estimate.lines:
        role = rate_card.role(ln.role_code)  # raises on unknown role
        phase = find_phase(ln.phase, phases)
        qty = derive_quantity(ln, phase, warnings)
        total_hours = round(qty * ln.hours_each, 2)
        by_year = hours_by_year(total_hours, phase)
        amount = sum(h * rate_card.bill_rate(ln.role_code, y) for y, h in by_year.items())
        flat = total_hours * role.bill_rate
        if ln.cadence in (Cadence.once,):
            basis = f"{ln.hours_each:g} h"
        else:
            per = {"weekly": "weekly", "monthly": "monthly",
                   "quarterly": "quarterly", "total": ""}[ln.cadence.value]
            basis = f"{qty:g} {per} occurrences x {ln.hours_each:g} h".replace("  ", " ")
        priced.append(PricedLine(
            deliverable_id=ln.deliverable_id,
            deliverable=ln.deliverable,
            role_code=ln.role_code,
            role_title=role.title,
            phase=phase.name,
            cadence=ln.cadence,
            hours_each=ln.hours_each,
            quantity=qty,
            total_hours=total_hours,
            hours_by_year=by_year,
            base_rate=role.bill_rate,
            amount=round(amount, 2),
            flat_amount=round(flat, 2),
            basis=basis,
            rationale=ln.rationale,
        ))

    hours_by_role: dict[str, float] = {}
    fee_by_role: dict[str, float] = {}
    fee_by_phase: dict[str, float] = {}
    fee_by_year: dict[int, float] = {}
    fee_by_deliverable: dict[str, float] = {}
    for pl in priced:
        hours_by_role[pl.role_code] = round(hours_by_role.get(pl.role_code, 0) + pl.total_hours, 2)
        fee_by_role[pl.role_code] = round(fee_by_role.get(pl.role_code, 0) + pl.amount, 2)
        fee_by_phase[pl.phase] = round(fee_by_phase.get(pl.phase, 0) + pl.amount, 2)
        fee_by_deliverable[pl.deliverable] = round(
            fee_by_deliverable.get(pl.deliverable, 0) + pl.amount, 2)
        for y, h in pl.hours_by_year.items():
            fee_by_year[y] = round(
                fee_by_year.get(y, 0) + h * rate_card.bill_rate(pl.role_code, y), 2)

    subtotal = round(sum(pl.amount for pl in priced), 2)
    flat_subtotal = round(sum(pl.flat_amount for pl in priced), 2)
    escalation_capture = round(subtotal - flat_subtotal, 2)
    if term > 12 and escalation_capture <= 0 and subtotal > 0:
        warnings.append(
            f"Multi-year term ({term} months) with zero escalation capture - "
            "check the rate card's escalation settings before submitting.")

    pol = rate_card.policies
    contingency = round(subtotal * pol.contingency_pct / 100.0, 2)
    raw_total = subtotal + contingency
    if pol.rounding > 0:
        total = float(round(raw_total / pol.rounding) * pol.rounding)
    else:
        total = round(raw_total, 2)
    rounding_adjustment = round(total - raw_total, 2)

    # Margin check per role: escalated revenue vs escalated loaded cost
    margins: list[RoleMargin] = []
    for code in sorted(fee_by_role):
        role = rate_card.role(code)
        revenue = fee_by_role[code]
        cost = 0.0
        has_cost = role.cost_rate is not None
        if has_cost:
            for pl in priced:
                if pl.role_code != code:
                    continue
                for y, h in pl.hours_by_year.items():
                    cost += h * (rate_card.cost_rate(code, y) or 0.0)
        margin_pct = (round((revenue - cost) / revenue * 100.0, 1)
                      if has_cost and revenue > 0 else None)
        below = margin_pct is not None and margin_pct < pol.margin_floor_pct
        if below:
            warnings.append(
                f"Role {code} ({role.title}) margin {margin_pct:.1f}% is below the "
                f"{pol.margin_floor_pct:.0f}% floor - raise the rate or rebalance the mix.")
        margins.append(RoleMargin(
            role_code=code, role_title=role.title, revenue=round(revenue, 2),
            cost=round(cost, 2) if has_cost else None,
            margin_pct=margin_pct, below_floor=below))

    fee_pct = None
    cv = analysis.facts.construction_value
    if cv and cv > 0:
        fee_pct = round(total / cv * 100.0, 3)
        band = pol.fee_pct_band
        if band and not (band.low_pct <= fee_pct <= band.high_pct):
            warnings.append(
                f"Fee is {fee_pct:.2f}% of construction value, outside the firm's "
                f"{band.low_pct:g}-{band.high_pct:g}% band - justify or revisit before submitting.")

    model = FeeModel(
        project_name=analysis.facts.project_name,
        client_name=analysis.facts.client_name,
        currency=rate_card.currency,
        term_months=term,
        escalation_pct=rate_card.escalation.annual_pct,
        lines=priced,
        hours_by_role=hours_by_role,
        fee_by_role=fee_by_role,
        fee_by_phase=fee_by_phase,
        fee_by_year=fee_by_year,
        fee_by_deliverable=fee_by_deliverable,
        subtotal=subtotal,
        contingency_pct=pol.contingency_pct,
        contingency_amount=contingency,
        rounding_adjustment=rounding_adjustment,
        total_fee=total,
        flat_rate_subtotal=flat_subtotal,
        escalation_capture=escalation_capture,
        fee_pct_of_construction=fee_pct,
        margins=margins,
        warnings=warnings,
        lock=FeeLock(lock_id="", total_fee=total, locked_at=""),
    )
    model.lock = FeeLock(
        lock_id=compute_lock_id(model),
        total_fee=total,
        locked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return model
