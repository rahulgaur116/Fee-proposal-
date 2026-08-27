from pathlib import Path

from feeprop.calibrate import build_benchmarks, load_submissions, _quantile

EXAMPLES = Path(__file__).parent.parent / "examples" / "past_submissions"


def test_quantile():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert _quantile(vals, 0.5) == 2.5
    assert _quantile(vals, 0.0) == 1.0
    assert _quantile(vals, 1.0) == 4.0
    assert _quantile([5.0], 0.75) == 5.0


def test_benchmarks_from_examples():
    subs = load_submissions(sorted(EXAMPLES.glob("*.yaml")))
    bm = build_benchmarks(subs)
    assert bm.n_submissions == 2

    report = next(d for d in bm.deliverables if d.deliverable == "monthly status report")
    # Lincoln: (96+144)/24 = 10 h/mo; Harbor: (180+252)/36 = 12 h/mo
    assert report.unit == "per_month"
    assert report.n == 2
    assert report.p50 == 11.0

    # fee positioning: Lincoln won at 512k/22M = 2.327%; Harbor lost at 2.185%
    assert bm.fee_pct_won_median == 2.327
    assert bm.fee_pct_lost_median == 2.185


def test_workbook_writes(tmp_path, rate_card, analysis, estimate):
    from feeprop import pricing
    from feeprop.workbook import write_workbook

    model = pricing.price(analysis, estimate, rate_card)
    out = tmp_path / "fee.xlsx"
    write_workbook(model, analysis, out)
    assert out.exists() and out.stat().st_size > 4000
