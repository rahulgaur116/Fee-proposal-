"""Scope analysis: extract facts and deliverables, and hunt every gap.

The gap hunt is the point. Every question the scope leaves open is a place
where the fee is either underpriced or undefended; each gap becomes a priced
assumption in the proposal, not a silent guess.
"""

from __future__ import annotations

from . import llm
from .models import ScopeAnalysis

SYSTEM = """You are a senior proposal manager at a US owner's-representation and \
cost-management firm. You have written and priced hundreds of fee proposals and you \
know exactly where scopes hide unpriced work. You read a scope of work the way an \
estimator reads drawings: what is being asked for, how often, for how long, and what \
was left unsaid that will cost hours."""

GAP_CHECKLIST = """
Hunt for gaps against this checklist. For every item the scope does NOT pin down,
emit a gap with a concrete proposed assumption and a pricing basis (a number:
a cadence, a count, a duration, a headcount). Do not skip an item because it
seems minor - minor items are where margin leaks.

- Contract term / duration, and whether the schedule is realistic (delay risk)
- Phase breakdown: preconstruction, construction, closeout durations
- Meeting cadence and length: OAC meetings, design reviews, board/committee
  presentations - and whether attendance is on site or remote
- Site presence: full-time vs part-time, how many days per week, how many staff
- Deliverable counts: number of reports, estimates, schedule updates, audits,
  pay application reviews per month
- Number of design packages / bid packages / GMP amendments to review
- Change order volume expectations
- Travel and reimbursables: included or billed separately
- Rate escalation on multi-year terms: does the RFP allow annual escalation
- Level of document control / PMIS administration expected
- Move management, FF&E, commissioning oversight - in or out
- Claims support, litigation support - in or out (usually excluded)
- Number of funding sources / reporting formats (federal grants mean more reporting)
- Response/turnaround expectations that force staffing levels

Rules:
- ALWAYS produce a duration_months figure. If the scope does not state one,
  infer or assume it, set duration_basis accordingly, and emit a gap for it.
- Every deliverable gets an id slug, a cadence, and the scope language that
  requires it when quotable.
- Cadence 'total' is for countable non-periodic items (e.g. '3 design reviews').
- Suggested exclusions are things a disciplined firm carves out of this scope.
"""


def analyze(scope_text: str) -> ScopeAnalysis:
    prompt = (
        "Analyze this scope of work / RFP for a fee proposal.\n"
        f"{GAP_CHECKLIST}\n"
        "<scope_of_work>\n"
        f"{scope_text}\n"
        "</scope_of_work>"
    )
    return llm.extract(SYSTEM, prompt, ScopeAnalysis, max_tokens=32000)
