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

import sys
from pathlib import Path

import click
import yaml

from . import calibrate as cal
from . import estimator, ingest, narrative, pricing, scope
from .models import Estimate, FeeModel, RateCard, ScopeAnalysis
from .workbook import write_workbook

ANALYSIS = "analysis.json"
ESTIMATE = "estimate.json"
FEE_MODEL = "fee_model.json"
WORKBOOK = "fee_workbook.xlsx"
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
def price(outdir: str, rate_card_path: str) -> None:
    """Deterministically price the estimate, lock the number, write the workbook."""
    out = _out(outdir)
    analysis = _read_json(out / ANALYSIS, ScopeAnalysis)
    est = _read_json(out / ESTIMATE, Estimate)
    rc = _load_rate_card(rate_card_path)
    model = pricing.price(analysis, est, rc)
    _write_json(out / FEE_MODEL, model)
    write_workbook(model, analysis, out / WORKBOOK)
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
@click.argument("submissions", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-o", "--output", default="benchmarks.yaml", show_default=True)
def calibrate(submissions: tuple[str, ...], output: str) -> None:
    """Build hours benchmarks from past submission records (YAML)."""
    subs = cal.load_submissions(list(submissions))
    bm = cal.build_benchmarks(subs)
    cal.save_benchmarks(bm, output)
    click.echo(f"  {bm.n_submissions} submissions, "
               f"{len(bm.deliverables)} deliverable benchmarks -> {output}")
    if bm.fee_pct_won_median is not None:
        click.echo(f"  Median fee % of construction (won): {bm.fee_pct_won_median:.3f}%")
    if bm.fee_pct_lost_median is not None:
        click.echo(f"  Median fee % of construction (lost): {bm.fee_pct_lost_median:.3f}%")


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
