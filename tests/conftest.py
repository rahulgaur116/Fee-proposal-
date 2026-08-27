import pytest

from feeprop.models import (
    Cadence,
    DeliverableSpec,
    Escalation,
    Estimate,
    FeeBand,
    HoursLine,
    Phase,
    Policies,
    ProjectFacts,
    RateCard,
    Role,
    ScopeAnalysis,
    ScopeGap,
)


@pytest.fixture
def rate_card() -> RateCard:
    return RateCard(
        firm="Test Advisors",
        effective_date="2026-01-01",
        escalation=Escalation(annual_pct=4.0, cost_annual_pct=3.5),
        roles=[
            Role(code="PIC", title="Principal-in-Charge", bill_rate=300, cost_rate=180),
            Role(code="PM", title="Project Manager", bill_rate=200, cost_rate=120),
            Role(code="PA", title="Project Analyst", bill_rate=100, cost_rate=90),
        ],
        policies=Policies(margin_floor_pct=30, contingency_pct=0, rounding=500,
                          fee_pct_band=FeeBand(low_pct=0.8, high_pct=3.5)),
    )


@pytest.fixture
def analysis() -> ScopeAnalysis:
    return ScopeAnalysis(
        facts=ProjectFacts(
            project_name="Test Project",
            client_name="Test District",
            project_type="owners_rep",
            construction_value=40_000_000,
            duration_months=24,
            duration_basis="stated",
            phases=[
                Phase(name="Preconstruction", start_month=1, duration_months=6),
                Phase(name="Construction", start_month=7, duration_months=18),
            ],
        ),
        deliverables=[
            DeliverableSpec(id="monthly-report", name="Monthly Status Report",
                            description="Written monthly report", cadence=Cadence.monthly),
            DeliverableSpec(id="closeout", name="Project Closeout",
                            description="Closeout", cadence=Cadence.once,
                            phase="Construction"),
        ],
        gaps=[
            ScopeGap(topic="Meeting cadence",
                     question="How often are OAC meetings?",
                     why_it_matters="Weekly vs biweekly doubles attendance hours",
                     proposed_assumption="One weekly OAC meeting during construction.",
                     pricing_basis="1 x 2-hour meeting per week plus prep"),
        ],
        exclusions_suggested=["Claims and litigation support"],
    )


@pytest.fixture
def estimate() -> Estimate:
    return Estimate(lines=[
        HoursLine(deliverable_id="monthly-report", deliverable="Monthly Status Report",
                  role_code="PM", cadence=Cadence.monthly, hours_each=4,
                  rationale="draft + review"),
        HoursLine(deliverable_id="monthly-report", deliverable="Monthly Status Report",
                  role_code="PA", cadence=Cadence.monthly, hours_each=6,
                  rationale="assembly"),
        HoursLine(deliverable_id="closeout", deliverable="Project Closeout",
                  role_code="PM", phase="Construction", cadence=Cadence.once,
                  hours_each=60, rationale="closeout"),
    ])
