"""Assumptions and exclusions: rendered deterministically from the gap list.

No LLM here on purpose. The assumptions section is the contractual perimeter of
the fee; it is generated 1:1 from the gaps the scope analysis found, so nothing
the fee was priced on can drift out of the document.
"""

from __future__ import annotations

from .models import FeeModel, ScopeAnalysis


def render_assumptions(analysis: ScopeAnalysis, fee_model: FeeModel | None = None) -> str:
    lines: list[str] = []
    n = 0
    for gap in analysis.gaps:
        n += 1
        lines.append(
            f"{n}. **{gap.topic}.** {gap.proposed_assumption} "
            f"(Basis of fee: {gap.pricing_basis})")
    if fee_model:
        for w in fee_model.warnings:
            if w.startswith("Scope states no contract term"):
                n += 1
                lines.append(
                    f"{n}. **Contract term.** Our fee assumes a "
                    f"{fee_model.term_months}-month term from notice to proceed.")
    if not lines:
        lines.append("_No open assumptions - the scope fully defines the basis of fee._")
    return "\n".join(lines)


def render_exclusions(analysis: ScopeAnalysis) -> str:
    if not analysis.exclusions_suggested:
        return "_None._"
    return "\n".join(f"- {x}" for x in analysis.exclusions_suggested)
