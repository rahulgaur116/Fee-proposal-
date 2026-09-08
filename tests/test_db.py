from feeprop import db as dbmod
from feeprop import pricing
from feeprop.calibrate import build_benchmarks


def _priced(rate_card, analysis, estimate):
    return pricing.price(analysis, estimate, rate_card)


def test_record_and_list(tmp_path, rate_card, analysis, estimate):
    model = _priced(rate_card, analysis, estimate)
    conn = dbmod.connect(tmp_path / "p.db")
    dbmod.record_job(conn, analysis, model)
    rows = dbmod.list_jobs(conn)
    assert len(rows) == 1
    assert rows[0]["project_name"] == "Test Project"
    assert rows[0]["total_fee"] == model.total_fee
    assert rows[0]["outcome"] == "pending"
    conn.close()


def test_reprice_replaces_but_keeps_outcome(tmp_path, rate_card, analysis, estimate):
    conn = dbmod.connect(tmp_path / "p.db")
    model = _priced(rate_card, analysis, estimate)
    dbmod.record_job(conn, analysis, model)
    dbmod.set_outcome(conn, "Test Project", "won", final_fee=50000)

    estimate.lines[0].hours_each = 8  # hours change -> reprice
    model2 = _priced(rate_card, analysis, estimate)
    assert model2.total_fee != model.total_fee
    dbmod.record_job(conn, analysis, model2)

    rows = dbmod.list_jobs(conn)
    assert len(rows) == 1
    assert rows[0]["total_fee"] == model2.total_fee
    assert rows[0]["outcome"] == "won"  # outcome survives the reprice
    conn.close()


def test_outcome_requires_unambiguous_match(tmp_path, rate_card, analysis, estimate):
    import pytest
    conn = dbmod.connect(tmp_path / "p.db")
    dbmod.record_job(conn, analysis, _priced(rate_card, analysis, estimate))
    with pytest.raises(KeyError):
        dbmod.set_outcome(conn, "no-such-project", "won")
    dbmod.set_outcome(conn, "Test Proj", "lost")  # substring match works
    assert dbmod.list_jobs(conn)[0]["outcome"] == "lost"
    conn.close()


def test_db_feeds_calibration(tmp_path, rate_card, analysis, estimate):
    conn = dbmod.connect(tmp_path / "p.db")
    dbmod.record_job(conn, analysis, _priced(rate_card, analysis, estimate))
    dbmod.set_outcome(conn, "Test Project", "won")
    subs = dbmod.load_submissions(conn)
    conn.close()

    assert len(subs) == 1
    sub = subs[0]
    assert sub.won is True
    assert sub.duration_months == 24
    # lines aggregated by (deliverable, role): monthly-report has PM+PA rows
    hours = {(l.deliverable, l.role_code): l.hours for l in sub.lines}
    assert hours[("Monthly Status Report", "PM")] == 96
    assert hours[("Monthly Status Report", "PA")] == 144

    bm = build_benchmarks(subs)
    assert bm.n_submissions == 1
    report = next(d for d in bm.deliverables if "monthly status report" in d.deliverable)
    # (96 + 144) hours over 24 months = 10 h/month
    assert report.p50 == 10.0
