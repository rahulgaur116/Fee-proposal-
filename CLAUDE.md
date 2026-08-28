# feeprop

Fee-proposal agent for US owner's-rep / cost-management firms: scope of work in,
priced and drafted fee proposal out. See README.md for the product story.

## Layout

- `src/feeprop/` — the package
  - `models.py` — all Pydantic domain models; every cross-stage artifact is one
  - `pricing.py` — deterministic pricing engine. **No LLM calls may be added
    here or to `assumptions.py`**: the fee math and the assumptions perimeter
    are code on purpose (that's the product's pricing-discipline guarantee)
  - `scope.py` / `estimator.py` / `narrative.py` — the three LLM stages
    (structured extraction via `llm.extract`, drafting via `llm.draft_stream`)
  - `llm.py` — the only module that touches the Anthropic SDK
  - `workbook.py` — xlsx output; `docx_out.py` — markdown→docx converter
  - `cli.py` — click CLI; stages read/write JSON artifacts in the outdir
- `examples/` — rate card, template, sample RFP, past-submission records
- `tests/` — fully offline; no API key needed, keep it that way

## Commands

```bash
pip install -e ".[docs,dev]"
python -m pytest -q            # must stay green offline
python -m pyflakes src/feeprop tests
```

## Invariants to preserve

- The fee model lock (`compute_lock_id`) hashes everything except `lock` and
  `warnings`; any change to priced fields must keep round-trip stability
  (JSON dump → validate must not change the hash).
- Recurring-cadence quantities are always derived from the term by
  `pricing.derive_quantity`; estimator-supplied quantities only win for
  cadence `total`.
- Every dollar figure in a drafted document must trace to the locked model
  (`narrative.verify_numbers`); extend `allowed_amounts` if you add new
  computed figures to templates.
- Templates: `{{key}}` fills are deterministic and run **before**
  `{{draft:slot|guidance}}` extraction, so guidance may reference `{{key}}`s.
