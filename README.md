# feeprop — fee proposals with pricing discipline

`feeprop` turns a scope of work into a priced, drafted fee proposal for US
owner's-representative and cost-management firms. Feed it the RFP or scope, your
proposal template, and your rate card; it builds the fee bottom-up as **hours ×
role × deliverable**, writes the narrative around a **locked number**, and
generates the assumptions section from **every gap in the scope**.

The wedge is not drafting speed — it is pricing discipline:

- **No fee from vibes.** Every dollar traces to a line: deliverable × role ×
  unit-hours × occurrence count. Recurring deliverables get their counts derived
  from the contract term by code, not guessed by anyone.
- **No flat pricing on multi-year terms.** Rates escalate at each contract
  anniversary. The engine also shows the *flat trap* on every job: what the fee
  would have been at year-one rates flat, and how much margin the escalation
  protected (`escalation_capture`).
- **The number is locked before the words are written.** The fee model carries a
  content hash. The drafting stage injects locked figures into the template and
  is forbidden from computing new ones; a verifier flags any dollar amount in
  the final document that doesn't trace to the locked model. Hand-editing the
  fee JSON breaks the lock loudly.
- **Every scope gap becomes a priced assumption.** The analyzer hunts the scope
  against a checklist (term, meeting cadence, site presence, deliverable counts,
  reimbursables, escalation language, closeout, claims…). Each gap becomes an
  assumption with a stated pricing basis — the contractual perimeter of the fee.
- **Margin is checked before you see the number.** Per-role margin against
  loaded cost (with its own escalation), a margin floor, and a fee-as-%-of-
  construction sanity band, all from your rate card policies.

## How the LLM is used — and where it isn't

| Stage | Who does it |
|---|---|
| Read the scope, extract deliverables and gaps | Claude (structured output) |
| Propose unit hours and role mix | Claude, anchored to your calibrated benchmarks |
| Derive quantities, escalate, total, check margins, **lock** | **Deterministic Python — no LLM** |
| Draft the narrative around the locked number | Claude, verified against the lock |
| Render assumptions from gaps | Deterministic — 1:1 from the gap list |

## Install

```bash
pip install -e ".[docs,dev]"       # docs extra adds PDF/DOCX ingestion
export ANTHROPIC_API_KEY=sk-ant-...
```

Uses Claude Opus 5 by default (`FEEPROP_MODEL` to override). Drafting calls
enable server-side refusal fallbacks so a safety decline reroutes instead of
failing the run.

## Quickstart

```bash
feeprop propose examples/scope_example.md \
    --rate-card examples/rate_card.yaml \
    --template examples/template.md \
    -o out/
```

Review order: `out/fee_workbook.xlsx` (the number — summary, detail lines,
margins, warnings), then `out/proposal.md` (the words).

### The staged workflow (recommended)

The person who signs the proposal should own the hours. Run the stages
separately and edit between them:

```bash
feeprop analyze rfp.pdf -o out/                      # facts, deliverables, gaps
feeprop estimate -o out/ --rate-card rc.yaml \
    --benchmarks benchmarks.yaml                     # bottom-up hours proposal
$EDITOR out/estimate.json                            # your judgment goes here
feeprop price -o out/ --rate-card rc.yaml            # deterministic; locks the number
feeprop draft -o out/ --rate-card rc.yaml --template template.md --docx
```

`--docx` (on `draft` and `propose`) also writes `proposal.docx` for submission.

Change the hours after pricing? Re-run `price` — the lock id changes and the
draft is re-verified against the new number. Edit `fee_model.json` by hand and
the lock check refuses it.

## Calibration: your last forty submissions

The estimator is only as good as its anchors. Calibration turns past
submissions into per-deliverable hours benchmarks (normalized per month of
term) and win/loss fee positioning:

```bash
# structured records you write, or extracted from old proposal docs:
feeprop extract-past old/riverview_proposal.pdf -o past/riverview.yaml
feeprop calibrate past/*.yaml -o benchmarks.yaml
```

`benchmarks.yaml` then feeds `feeprop estimate --benchmarks`: the model anchors
to your p50 and justifies any move toward p75 in the line rationale. It also
reports median fee-%-of-construction for won vs lost work, which is where the
"we priced from the last job that felt similar" habit becomes visible.

## Inputs

- **Rate card** (`examples/rate_card.yaml`): roles with bill rates and loaded
  cost rates, annual escalation %, and policies — margin floor, contingency %,
  total rounding, fee-% band.
- **Template** (`examples/template.md`): markdown with `{{key}}` slots filled
  deterministically (fee tables, assumptions, totals, lock id) and
  `{{draft:slot|guidance}}` slots drafted by the model around the locked
  figures.
- **Scope** : `.md`/`.txt` natively, `.pdf`/`.docx` with the `docs` extra.

## Artifacts

| File | What it is |
|---|---|
| `analysis.json` | Facts, deliverables (with cadence + source language), gaps, suggested exclusions |
| `estimate.json` | Hours lines — deliverable × role × cadence × unit hours, with rationale. **Edit this one.** |
| `fee_model.json` | Priced lines, per-year/role/phase totals, flat-vs-escalated comparison, margins, warnings, lock |
| `fee_workbook.xlsx` | Summary / Detail / Assumptions sheets for principal review |
| `proposal.md` | The drafted proposal, numbers verified against the lock |
| `proposal.docx` | Word version of the proposal (with `--docx`) |

## Tests

The pricing engine is fully covered offline (no API key needed):

```bash
pytest
```
