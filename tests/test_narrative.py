from feeprop import narrative, pricing
from feeprop.assumptions import render_assumptions, render_exclusions
from feeprop.narrative import (
    allowed_amounts,
    deterministic_fills,
    fmt_money,
    verify_numbers,
)


def test_fmt_money():
    assert fmt_money(46500) == "$46,500"
    assert fmt_money(46500.0) == "$46,500"
    assert fmt_money(1234.56) == "$1,234.56"


def test_deterministic_fills_carry_locked_number(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    fills = deterministic_fills(analysis, model, rate_card)
    assert fills["total_fee"] == fmt_money(model.total_fee)
    assert fills["lock_id"] == model.lock.lock_id
    assert fmt_money(model.total_fee) in fills["fee_by_year_table"]
    assert "Monthly Status Report" in fills["fee_detail_table"]


def test_template_key_fill(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    template = "Fee: {{total_fee}} for {{client_name}}. Unknown: {{nope}}"
    fills = deterministic_fills(analysis, model, rate_card)
    doc = narrative.KEY_SLOT_RE.sub(
        lambda m: fills.get(m.group(1), m.group(0)), template)
    assert fmt_money(model.total_fee) in doc
    assert "Test District" in doc
    assert "{{nope}}" in doc  # unknown keys left visible, never silently dropped


def test_verify_numbers_flags_invented_figures(rate_card, analysis, estimate):
    model = pricing.price(analysis, estimate, rate_card)
    allowed = allowed_amounts(model, analysis, rate_card)
    doc = (f"The fee is {fmt_money(model.total_fee)}, "
           f"but somebody typed $999,999 in the executive summary.")
    flagged = verify_numbers(doc, allowed)
    assert flagged == ["$999,999"]


def test_assumptions_render_from_gaps(analysis):
    text = render_assumptions(analysis)
    assert "Meeting cadence" in text
    assert "One weekly OAC meeting" in text
    assert "Basis of fee:" in text


def test_exclusions_render(analysis):
    assert "Claims and litigation support" in render_exclusions(analysis)
