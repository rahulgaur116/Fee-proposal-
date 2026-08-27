"""Domain models for the fee proposal pipeline.

Three families:
  - Rate card / policies (firm configuration, loaded from YAML)
  - Scope analysis (LLM-extracted facts, deliverables, and gaps)
  - Estimate and priced fee model (hours lines in, locked fee out)

Everything that crosses a pipeline stage boundary is a Pydantic model so
artifacts round-trip through JSON and can be hand-edited between stages.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------
# Rate card
# --------------------------------------------------------------------------

class Role(BaseModel):
    code: str
    title: str
    bill_rate: float
    cost_rate: Optional[float] = None
    escalation_pct: Optional[float] = None  # per-role override of the default


class Escalation(BaseModel):
    annual_pct: float = 4.0
    cost_annual_pct: Optional[float] = None  # defaults to annual_pct

    @property
    def cost_pct(self) -> float:
        return self.cost_annual_pct if self.cost_annual_pct is not None else self.annual_pct


class FeeBand(BaseModel):
    low_pct: float
    high_pct: float


class Policies(BaseModel):
    margin_floor_pct: float = 25.0
    contingency_pct: float = 0.0
    rounding: int = 500
    fee_pct_band: Optional[FeeBand] = None


class RateCard(BaseModel):
    firm: str
    effective_date: str
    currency: str = "USD"
    escalation: Escalation = Field(default_factory=Escalation)
    roles: list[Role]
    policies: Policies = Field(default_factory=Policies)

    def role(self, code: str) -> Role:
        for r in self.roles:
            if r.code == code:
                return r
        raise KeyError(f"Role code {code!r} not in rate card "
                       f"(have: {', '.join(r.code for r in self.roles)})")

    def bill_rate(self, code: str, contract_year: int) -> float:
        r = self.role(code)
        pct = r.escalation_pct if r.escalation_pct is not None else self.escalation.annual_pct
        return r.bill_rate * (1.0 + pct / 100.0) ** (contract_year - 1)

    def cost_rate(self, code: str, contract_year: int) -> Optional[float]:
        r = self.role(code)
        if r.cost_rate is None:
            return None
        return r.cost_rate * (1.0 + self.escalation.cost_pct / 100.0) ** (contract_year - 1)


# --------------------------------------------------------------------------
# Scope analysis
# --------------------------------------------------------------------------

class Phase(BaseModel):
    name: str
    start_month: int = Field(description="1-based month from notice to proceed")
    duration_months: int


class ProjectFacts(BaseModel):
    project_name: str
    client_name: str
    project_type: str = Field(
        description="e.g. owners_rep, cost_management, program_management")
    sector: Optional[str] = Field(
        default=None, description="e.g. K-12, healthcare, transit, commercial")
    construction_value: Optional[float] = Field(
        default=None, description="Stated or inferred construction value in dollars")
    duration_months: Optional[int] = Field(
        default=None, description="Contract term in months; assume if not stated")
    duration_basis: str = Field(
        default="stated", description="stated | inferred | assumed")
    delivery_method: Optional[str] = None
    location: Optional[str] = None
    phases: list[Phase] = Field(default_factory=list)
    notes: Optional[str] = None


class Cadence(str, Enum):
    once = "once"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
    total = "total"  # quantity supplied explicitly, not derived from term


class DeliverableSpec(BaseModel):
    id: str = Field(description="short slug, e.g. monthly-report")
    name: str
    description: str
    cadence: Cadence
    phase: Optional[str] = Field(
        default=None, description="Phase name this deliverable belongs to, if phased")
    source_language: Optional[str] = Field(
        default=None, description="Quote from the scope that requires this deliverable")


class ScopeGap(BaseModel):
    topic: str
    question: str = Field(description="What the scope leaves unanswered")
    why_it_matters: str = Field(description="How the answer moves hours or fee")
    proposed_assumption: str = Field(
        description="The assumption the fee will be priced on, stated as a sentence")
    pricing_basis: str = Field(
        description="The concrete quantity/basis the assumption pins down, "
                    "e.g. 'one 4-hour OAC meeting per week, on site'")


class ScopeAnalysis(BaseModel):
    facts: ProjectFacts
    deliverables: list[DeliverableSpec]
    gaps: list[ScopeGap]
    exclusions_suggested: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Estimate (hours build-up)
# --------------------------------------------------------------------------

class HoursLine(BaseModel):
    deliverable_id: str
    deliverable: str
    role_code: str
    phase: Optional[str] = None
    cadence: Cadence
    hours_each: float = Field(description="Hours per occurrence")
    quantity: Optional[float] = Field(
        default=None,
        description="Occurrence count. Required for cadence=total/once with >1; "
                    "derived from the term for weekly/monthly/quarterly.")
    rationale: str = Field(description="One line: why these hours, e.g. benchmark used")


class Estimate(BaseModel):
    lines: list[HoursLine]
    staffing_notes: str = ""


# --------------------------------------------------------------------------
# Priced fee model
# --------------------------------------------------------------------------

class PricedLine(BaseModel):
    deliverable_id: str
    deliverable: str
    role_code: str
    role_title: str
    phase: str
    cadence: Cadence
    hours_each: float
    quantity: float
    total_hours: float
    hours_by_year: dict[int, float]
    base_rate: float
    amount: float          # escalated, the real price
    flat_amount: float     # what year-one-rates-flat would have charged
    basis: str             # human-readable, e.g. "24 monthly reports x 6.0 h"
    rationale: str


class RoleMargin(BaseModel):
    role_code: str
    role_title: str
    revenue: float
    cost: Optional[float]
    margin_pct: Optional[float]
    below_floor: bool = False


class FeeLock(BaseModel):
    lock_id: str
    total_fee: float
    locked_at: str


class FeeModel(BaseModel):
    project_name: str
    client_name: str
    currency: str
    term_months: int
    escalation_pct: float
    lines: list[PricedLine]
    hours_by_role: dict[str, float]
    fee_by_role: dict[str, float]
    fee_by_phase: dict[str, float]
    fee_by_year: dict[int, float]
    fee_by_deliverable: dict[str, float]
    subtotal: float
    contingency_pct: float
    contingency_amount: float
    rounding_adjustment: float
    total_fee: float
    flat_rate_subtotal: float
    escalation_capture: float  # subtotal - flat_rate_subtotal: margin saved vs flat pricing
    fee_pct_of_construction: Optional[float]
    margins: list[RoleMargin]
    warnings: list[str]
    lock: FeeLock

    @model_validator(mode="after")
    def _verify_lock(self) -> "FeeModel":
        expected = compute_lock_id(self)
        if self.lock.lock_id and self.lock.lock_id != expected:
            raise ValueError(
                f"Fee model lock mismatch: model says {self.lock.lock_id}, "
                f"recomputed {expected}. The fee model was edited after locking - "
                f"re-run `feeprop price` to reprice and relock.")
        return self


def compute_lock_id(model: "FeeModel") -> str:
    """Hash of everything that defines the number. Stable across serialization."""
    payload = model.model_dump(mode="json", exclude={"lock", "warnings"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------
# Calibration (past submissions -> benchmarks)
# --------------------------------------------------------------------------

class PastLine(BaseModel):
    deliverable: str
    role_code: Optional[str] = None
    hours: float


class PastSubmission(BaseModel):
    name: str
    project_type: str
    sector: Optional[str] = None
    construction_value: Optional[float] = None
    duration_months: int
    fee: float
    won: Optional[bool] = None
    lines: list[PastLine] = Field(default_factory=list)


class DeliverableBenchmark(BaseModel):
    deliverable: str
    unit: str  # "per_month" or "per_project"
    n: int
    p25: float
    p50: float
    p75: float


class Benchmarks(BaseModel):
    n_submissions: int
    deliverables: list[DeliverableBenchmark]
    fee_pct_won_median: Optional[float] = None
    fee_pct_lost_median: Optional[float] = None
    notes: str = ""
