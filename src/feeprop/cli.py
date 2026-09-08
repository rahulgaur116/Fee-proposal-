"""feeprop CLI.

Staged pipeline with editable artifacts between stages - the person who signs
the proposal reviews and edits the hours before the number locks:

    feeprop analyze scope.pdf -o out/            -> out/analysis.json
    feeprop estimate -o out/ --rate-card rc.yaml -> out/estimate.json   (edit it)
    feeprop price -o out/ --rate-card rc.yaml    -> out/fee_model.json + fee_workbook.xlsx
    feeprop draft -o out/ --rate-card rc.yaml --template t.md -> out/proposal.md

    feeprop propose scope.pdf --rate-card rc.yaml --template t.md -o out/   (all four)

    feeprop calibrate past/*.yaml -o benchmarks.yaml
    feeprop extract-past old_proposal.pdf -o past/job.yaml
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
import yaml

from . import calibrate as cal
from . import db as dbmod
from . import estimator, ingest, narrative, pricing, scope
from .models import Estimate, FeeModel, RateCard, ScopeAnalysis
from .workbook import write_workbook

ANALYSIS = "analysis.json"
ESTIMATE = "estimate.json"
FEE_MODEL = "fee_model.json"
WORKBOOK = "fee_workbook.xlsx"
BUILDUP_XLSX = "fee_buildup.xlsx"
PROPOSAL = "proposal.md"
PROPOSAL_DOCX = "proposal.docx"


def _out(outdir: str) -> Path:
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_rate_card(path: str) -> RateCard:
    return RateCard.model_validate(
        yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _read_json(path: Path, model):
    if not path.exists():
        raise click.ClickException(
            f"{path} not found - run the earlier pipeline stage first.")
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _write_json(path: Path, model) -> None:
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _print_warnings(warnings: list[str]) -> None:
    for w in warnings:
        click.secho(f"  ! {w}", fg="yellow", err=True)


@click.group()
def main() -> None:
    """Turn a scope of work into a priced, drafted fee proposal."""


@main.command()
@click.argument("scope_doc", type=click.Path(exists=True))
@click.option("-o", "--outdir", default="out", show_default=True)
def analyze(scope_doc: str, outdir: str) -> None:
    """Extract facts, deliverables, and every scope gap from an RFP/scope."""
    out = _out(outdir)
    text = ingest.read_document(scope_doc)
    click.echo(f"Analyzing {scope_doc} ({len(text):,} chars)...")
    analysis = scope.analyze(text)
    _write_json(out / ANALYSIS, analysis)
    click.echo(f"  {len(analysis.deliverables)} deliverables, "
               f"{len(analysis.gaps)} scope gaps -> {out / ANALYSIS}")


@main.command()
@click.option("-o", "--outdir", default="out", show_default=True)
@click.option("--rate-card", "rate_card_path", required=True, type=click.Path(exists=True))
@click.option("--benchmarks", "benchmarks_path", type=click.Path(exists=True))
def estimate(outdir: str, rate_card_path: str, benchmarks_path: str | None) -> None:
    """Propose the bottom-up hours build (edit estimate.json before pricing)."""
    out = _out(outdir)
    analysis = _read_json(out / ANALYSIS, ScopeAnalysis)
    rc = _load_rate_card(rate_card_path)
    bm = cal.load_benchmarks(benchmarks_path) if benchmarks_path else None
    click.echo("Building bottom-up hours estimate...")
    est = estimator.estimate(analysis, rc, bm)
    _write_json(out / ESTIMATE, est)
    click.echo(f"  {len(est.lines)} hours lines -> {out / ESTIMATE}")
    click.echo("  Review and edit the estimate, then run `feeprop price`.")


@main.command()
@click.option("-o", "--outdir", default="out", show_default=True)
@click.option("--rate-card", "rate_card_path", required=True, type=click.Path(exists=True))
@click.option("--buildup", "buildup_flag", is_flag=True,
              help="Also write fee_buildup.xlsx (client-format BUILDUP + CLIENT VIEW)")
@click.option("--db", "db_path", default=None,
              help="Proposal database path (default: FEEPROP_DB or ~/.feeprop/proposals.db)")
@click.option("--no-record", is_flag=True, help="Skip recording this job in the database")
def price(outdir: str, rate_card_path: str, buildup_flag: bool = False,
          db_path: str | None = None, no_record: bool = False) -> None:
    """Deterministically price the estimate, lock the number, write the workbook."""
    out = _out(outdir)
    analysis = _read_json(out / ANALYSIS, ScopeAnalysis)
    est = _read_json(out / ESTIMATE, Estimate)
    rc = _load_rate_card(rate_card_path)
    model = pricing.price(analysis, est, rc)
    _write_json(out / FEE_MODEL, model)
    write_workbook(model, analysis, out / WORKBOOK)
    if not no_record:
        conn = dbmod.connect(db_path)
        dbmod.record_job(conn, analysis, model)
        conn.close()
        click.echo(f"  Recorded in proposal database "
                   f"({db_path or dbmod.default_path()}) - log the result later "
                   f"with `feeprop outcome`.")
    if buildup_flag:
        from .buildup import write_buildup
        write_buildup(model, rc, out / BUILDUP_XLSX)
        click.echo(f"  -> {out / BUILDUP_XLSX} (formulas need one recalc pass in "
                   "Excel/LibreOffice before values display)")
    click.echo(f"  Total fee: {narrative.fmt_money(model.total_fee)}  "
               f"(lock {model.lock.lock_id})")
    click.echo(f"  Escalation capture vs flat year-1 pricing: "
               f"{narrative.fmt_money(model.escalation_capture)}")
    _print_warnings(model.warnings)
    click.echo(f"  -> {out / FEE_MODEL}, {out / WORKBOOK}")


@main.command()
@click.option("-o", "--outdir", default="out", show_default=True)
@click.option("--rate-card", "rate_card_path", required=True, type=click.Path(exists=True))
@click.option("--template", "template_path", required=True, type=click.Path(exists=True))
@click.option("--docx", "docx_flag", is_flag=True, help="Also write proposal.docx")
def draft(outdir: str, rate_card_path: str, template_path: str,
          docx_flag: bool = False) -> None:
    """Draft the proposal narrative around the locked fee."""
    out = _out(outdir)
    analysis = _read_json(out / ANALYSIS, ScopeAnalysis)
    model = _read_json(out / FEE_MODEL, FeeModel)
    rc = _load_rate_card(rate_card_path)
    template = Path(template_path).read_text(encoding="utf-8")
    click.echo(f"Drafting around locked fee {narrative.fmt_money(model.total_fee)} "
               f"(lock {model.lock.lock_id})...")
    doc, warnings = narrative.draft(template, analysis, model, rc)
    (out / PROPOSAL).write_text(doc, encoding="utf-8")
    _print_warnings(warnings)
    click.echo(f"  -> {out / PROPOSAL}")
    if docx_flag:
        from .docx_out import markdown_to_docx
        docx_path = out / PROPOSAL_DOCX
        markdown_to_docx(doc, docx_path)
        click.echo(f"  -> {docx_path}")


@main.command()
@click.argument("scope_doc", type=click.Path(exists=True))
@click.option("-o", "--outdir", default="out", show_default=True)
@click.option("--rate-card", "rate_card_path", required=True, type=click.Path(exists=True))
@click.option("--template", "template_path", required=True, type=click.Path(exists=True))
@click.option("--benchmarks", "benchmarks_path", type=click.Path(exists=True))
@click.option("--docx", "docx_flag", is_flag=True, help="Also write proposal.docx")
def propose(scope_doc: str, outdir: str, rate_card_path: str,
            template_path: str, benchmarks_path: str | None,
            docx_flag: bool = False) -> None:
    """Full pipeline: analyze -> estimate -> price -> draft."""
    ctx = click.get_current_context()
    ctx.invoke(analyze, scope_doc=scope_doc, outdir=outdir)
    ctx.invoke(estimate, outdir=outdir, rate_card_path=rate_card_path,
               benchmarks_path=benchmarks_path)
    ctx.invoke(price, outdir=outdir, rate_card_path=rate_card_path)
    ctx.invoke(draft, outdir=outdir, rate_card_path=rate_card_path,
               template_path=template_path, docx_flag=docx_flag)
    click.echo("\nDone. Review order: fee_workbook.xlsx (the number), "
               "then proposal.md (the words).")


@main.command()
@click.argument("submissions", nargs=-1, type=click.Path(exists=True))
@click.option("-o", "--output", default="benchmarks.yaml", show_default=True)
@click.option("--from-db", "from_db", is_flag=True,
              help="Include every proposal recorded in the database")
@click.option("--db", "db_path", default=None,
              help="Proposal database path (default: FEEPROP_DB or ~/.feeprop/proposals.db)")
def calibrate(submissions: tuple[str, ...], output: str,
              from_db: bool = False, db_path: str | None = None) -> None:
    """Build hours benchmarks from past submissions (YAML files and/or the database)."""
    subs = cal.load_submissions(list(submissions)) if submissions else []
    if from_db:
        conn = dbmod.connect(db_path)
        subs += dbmod.load_submissions(conn)
        conn.close()
    if not subs:
        raise click.ClickException(
            "Nothing to calibrate from - pass YAML records and/or --from-db.")
    bm = cal.build_benchmarks(subs)
    cal.save_benchmarks(bm, output)
    click.echo(f"  {bm.n_submissions} submissions, "
               f"{len(bm.deliverables)} deliverable benchmarks -> {output}")
    if bm.fee_pct_won_median is not None:
        click.echo(f"  Median fee % of construction (won): {bm.fee_pct_won_median:.3f}%")
    if bm.fee_pct_lost_median is not None:
        click.echo(f"  Median fee % of construction (lost): {bm.fee_pct_lost_median:.3f}%")


@main.command()
@click.option("--db", "db_path", default=None,
              help="Proposal database path (default: FEEPROP_DB or ~/.feeprop/proposals.db)")
def history(db_path: str | None = None) -> None:
    """List every proposal recorded in the database."""
    conn = dbmod.connect(db_path)
    rows = dbmod.list_jobs(conn)
    conn.close()
    if not rows:
        click.echo("No proposals recorded yet - run `feeprop price` on a job.")
        return
    for r in rows:
        click.echo(f"  [{r['outcome']:>7}] {r['project_name']}")
        click.echo(f"           {r['client_name']} | {r['duration_months']} mo | "
                   f"{r['total_hours']:,.0f} h | ${r['total_fee']:,.0f} | "
                   f"lock {r['lock_id']} | priced {r['priced_at'][:10]}")


@main.command()
@click.argument("project_name")
@click.option("--won", "outcome", flag_value="won")
@click.option("--lost", "outcome", flag_value="lost")
@click.option("--pending", "outcome", flag_value="pending")
@click.option("--final-fee", type=float, default=None,
              help="Negotiated/contracted fee if it differs from the proposal")
@click.option("--notes", default=None)
@click.option("--db", "db_path", default=None,
              help="Proposal database path (default: FEEPROP_DB or ~/.feeprop/proposals.db)")
def outcome(project_name: str, outcome: str | None, final_fee: float | None,
            notes: str | None, db_path: str | None = None) -> None:
    """Log a win/loss so the fee positioning stats learn from it."""
    if not outcome:
        raise click.ClickException("Pass --won, --lost, or --pending.")
    conn = dbmod.connect(db_path)
    try:
        dbmod.set_outcome(conn, project_name, outcome, final_fee, notes)
    except KeyError as e:
        raise click.ClickException(str(e)) from e
    finally:
        conn.close()
    click.echo(f"  Recorded {outcome} for '{project_name}'. "
               "Re-run `feeprop calibrate --from-db` to refresh benchmarks.")


@main.command()
@click.option("--db", "db_path", default=None)
def doctor(db_path: str | None = None) -> None:
    """Check this machine's setup: deps, API key, extras, database."""
    import importlib
    import sys as _sys

    def check(label: str, ok: bool, hint: str = "") -> None:
        mark = "ok " if ok else "MISSING"
        click.echo(f"  [{mark:>7}] {label}" + (f" - {hint}" if not ok and hint else ""))

    click.echo(f"feeprop doctor (python {_sys.version.split()[0]})")
    check("python >= 3.10", _sys.version_info >= (3, 10), "install Python 3.10+")
    for mod, hint in [("anthropic", "pip install anthropic"),
                      ("pydantic", "pip install pydantic"),
                      ("openpyxl", "pip install openpyxl"),
                      ("yaml", "pip install PyYAML")]:
        try:
            importlib.import_module(mod)
            check(f"dependency: {mod}", True)
        except ImportError:
            check(f"dependency: {mod}", False, hint)
    for mod, feat in [("pypdf", "PDF scope ingestion"), ("docx", "DOCX output/ingestion")]:
        try:
            importlib.import_module(mod)
            check(f"optional: {mod} ({feat})", True)
        except ImportError:
            check(f"optional: {mod} ({feat})", False, "pip install 'feeprop[docs]'")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    check("ANTHROPIC_API_KEY (needed for analyze/estimate/draft)", has_key,
          "export ANTHROPIC_API_KEY=sk-ant-... ; price/calibrate/history work without it")
    try:
        conn = dbmod.connect(db_path)
        n = len(dbmod.list_jobs(conn))
        conn.close()
        check(f"proposal database ({db_path or dbmod.default_path()}): {n} proposals", True)
    except Exception as e:
        check("proposal database", False, str(e))


@main.command("extract-past")
@click.argument("document", type=click.Path(exists=True))
@click.option("-o", "--output", required=True)
def extract_past(document: str, output: str) -> None:
    """Extract a past proposal document into a submission record (YAML)."""
    text = ingest.read_document(document)
    sub = cal.extract_past(text)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        yaml.safe_dump(sub.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    click.echo(f"  {sub.name}: {len(sub.lines)} hours lines -> {output}")


if __name__ == "__main__":
    sys.exit(main())
