import pytest
from pydantic import ValidationError

from feeprop import pricing
from feeprop.models import Cadence, FeeModel, HoursLine
from feeprop.pricing import contract_year


def test_contract_year():
    assert contract_year(1) == 1
    assert contract_year(12) == 1
    assert contract_year(13) == 2
    assert contract_year(24) == 2
    assert contract_year(25) == 3


def test_monthly_quantity_derived_from_term(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    monthly_pm = next(l for l in model.lines
                      if l.deliverable_id == "monthly-report" and l.role_code == "PM")
    assert monthly_pm.quantity == 24  # 24-month term -> 24 monthly reports
    assert monthly_pm.total_hours == 96


def test_estimator_quantity_cannot_override_cadence(rate_card, analysis, estimate):
    # estimator says 12 reports on a 24-month term; the term wins
    estimate.lines[0].quantity = 12
    model = pricing.price(analysis, estimate, rate_card)
    monthly_pm = next(l for l in model.lines
                      if l.deliverable_id == "monthly-report" and l.role_code == "PM")
    assert monthly_pm.quantity == 24
    assert any("cadence" in w for w in model.warnings)


def test_escalation_applied_by_contract_year(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    monthly_pm = next(l for l in model.lines
                      if l.deliverable_id == "monthly-report" and l.role_code == "PM")
    # 48 h in year 1 at $200, 48 h in year 2 at $208
    assert monthly_pm.hours_by_year == {1: 48.0, 2: 48.0}
    assert monthly_pm.amount == pytest.approx(48 * 200 + 48 * 200 * 1.04)
    assert monthly_pm.flat_amount == pytest.approx(96 * 200)


def test_escalation_capture_vs_flat_pricing(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    assert model.subtotal == pytest.approx(46592.0)
    assert model.flat_rate_subtotal == pytest.approx(45600.0)
    assert model.escalation_capture == pytest.approx(992.0)
    assert model.escalation_capture > 0  # multi-year job must never price flat


def test_year_bucket_hours_sum_to_total(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    for line in model.lines:
        assert sum(line.hours_by_year.values()) == pytest.approx(line.total_hours, abs=0.01)


def test_total_rounded_to_policy(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    assert model.total_fee % 500 == 0
    assert model.total_fee == pytest.approx(
        model.subtotal + model.contingency_amount + model.rounding_adjustment)


def test_unpriced_deliverable_is_flagged(rate_card, analysis, estimate):
    estimate.lines = [l for l in estimate.lines if l.deliverable_id != "closeout"]
    model = pricing.price(analysis, estimate, rate_card)
    assert any("given away free" in w for w in model.warnings)


def test_missing_term_assumed_with_warning(rate_card, analysis, estimate):
    analysis.facts.duration_months = None
    analysis.facts.phases = []
    model = pricing.price(analysis, estimate, rate_card)
    assert model.term_months == 12
    assert any("assumed 12-month term" in w for w in model.warnings)


def test_margin_floor_breach_flagged(rate_card, analysis, estimate):
    # PA bills $100 against $90 loaded cost: ~10% margin, floor is 30%
    model = pricing.price(analysis, estimate, rate_card)
    pa = next(m for m in model.margins if m.role_code == "PA")
    assert pa.below_floor
    assert any("below the 30% floor" in w for w in model.warnings)


def test_fee_band_breach_flagged(rate_card, analysis, estimate):
    # ~$46k fee on $40M construction is far under the 0.8% band floor
    model = pricing.price(analysis, estimate, rate_card)
    assert model.fee_pct_of_construction < 0.8
    assert any("outside the firm's" in w for w in model.warnings)


def test_unknown_role_raises(rate_card, analysis, estimate):
    estimate.lines.append(HoursLine(
        deliverable_id="closeout", deliverable="Project Closeout",
        role_code="NOPE", cadence=Cadence.once, hours_each=10, rationale="x"))
    with pytest.raises(KeyError):
        pricing.price(analysis, estimate, rate_card)


def test_lock_survives_round_trip(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    reloaded = FeeModel.model_validate_json(model.model_dump_json())
    assert reloaded.lock.lock_id == model.lock.lock_id


def test_lock_detects_tampering(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    data = model.model_dump(mode="json")
    data["total_fee"] = data["total_fee"] + 10000  # sweeten the number by hand
    with pytest.raises(ValidationError, match="lock mismatch"):
        FeeModel.model_validate(data)


def test_weekly_quantity(rate_card, analysis, estimate):
    estimate.lines.append(HoursLine(
        deliverable_id="monthly-report", deliverable="Monthly Status Report",
        role_code="PM", phase="Construction", cadence=Cadence.weekly,
        hours_each=2, rationale="weekly touchpoint"))
    model = pricing.price(analysis, estimate, rate_card)
    weekly = next(l for l in model.lines if l.cadence == Cadence.weekly)
    assert weekly.quantity == 78  # 18 months x 52/12, rounded
