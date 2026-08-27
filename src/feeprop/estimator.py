"""Hours estimator: propose the bottom-up build, line by line.

The model proposes hours; it never prices. Quantities for recurring work are
derived downstream from the term by the pricing engine, so the estimator's job
is unit hours and role mix, anchored to calibrated benchmarks when available.
"""

from __future__ import annotations

import yaml

from . import llm
from .models import Benchmarks, Estimate, RateCard, ScopeAnalysis

SYSTEM = """You are the operations principal at a US owner's-representation and \
cost-management firm, building the hours behind a fee. You estimate the way the firm \
delivers: every deliverable decomposed into role x unit-hours x occurrences, never a \
lump sum. You know that monthly reports take senior time to review but junior time to \
assemble, that OAC meetings cost prep and follow-up hours beyond the meeting itself, \
and that the principal-in-charge bills light oversight hours every month whether the \
scope mentions it or not."""

RULES = """
Estimation rules:
- Every deliverable in the analysis gets at least one hours line. A deliverable
  with no line is free work.
- Recurring deliverables: give hours_each (per occurrence) and let the cadence
  drive the count - do NOT bake the term into hours_each. Leave quantity null
  for weekly/monthly/quarterly cadences; the pricing engine derives it.
- Cadence 'total': set quantity to the count (e.g. 3 design reviews).
- Cadence 'once': quantity is 1 (project setup, closeout report).
- Split senior/junior: assembly and analysis hours to PA/analyst-level roles,
  review and client-facing hours to PM/SPM, oversight to the principal.
- Include the unglamorous standing lines every real engagement carries:
  principal oversight (monthly), internal QA on major deliverables,
  project setup (once), closeout (once).
- Meetings cost prep + attendance + minutes/follow-up. Say so in the rationale.
- Where benchmarks are provided, anchor to the p50 and move toward p75 only
  when the scope signals complexity (multiple funding sources, aggressive
  schedule, difficult stakeholders); say which benchmark you used in the
  rationale.
- Use only role codes from the rate card.
- rationale is one line per line: the basis, not prose.
"""


def estimate(analysis: ScopeAnalysis, rate_card: RateCard,
             benchmarks: Benchmarks | None = None) -> Estimate:
    roles_desc = "\n".join(
        f"- {r.code}: {r.title}" for r in rate_card.roles)
    bench_block = ""
    if benchmarks and benchmarks.deliverables:
        bench_yaml = yaml.safe_dump(
            benchmarks.model_dump(mode="json"), sort_keys=False)
        bench_block = (
            "\n<calibrated_benchmarks>\n"
            "Hours benchmarks from this firm's past submissions "
            f"(n={benchmarks.n_submissions}). Units: per_month means hours per month "
            "of term across all roles for that deliverable; per_project means total.\n"
            f"{bench_yaml}"
            "</calibrated_benchmarks>\n")
    prompt = (
        "Build the bottom-up hours estimate for this engagement.\n"
        f"{RULES}\n"
        "<available_roles>\n"
        f"{roles_desc}\n"
        "</available_roles>\n"
        f"{bench_block}"
        "<scope_analysis>\n"
        f"{analysis.model_dump_json(indent=2)}\n"
        "</scope_analysis>"
    )
    result = llm.extract(SYSTEM, prompt, Estimate, max_tokens=32000)

    # Hard discipline: drop lines with unknown role codes rather than crash later
    known = {r.code for r in rate_card.roles}
    bad = [ln for ln in result.lines if ln.role_code not in known]
    if bad:
        result.lines = [ln for ln in result.lines if ln.role_code in known]
        names = ", ".join(sorted({ln.role_code for ln in bad}))
        result.staffing_notes += (
            f"\n[feeprop] Dropped {len(bad)} line(s) with role codes not in the "
            f"rate card: {names}. Re-run or add the roles.")
    return result
