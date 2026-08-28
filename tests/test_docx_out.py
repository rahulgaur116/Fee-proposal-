import pytest

docx = pytest.importorskip("docx")

from feeprop.docx_out import markdown_to_docx

SAMPLE = """# Fee Proposal

**Riverbend Aquatic Center**
Prepared for Riverbend USD

---

## Fee

Our lump-sum fee is **$1,234,500**, billed monthly.

| Period | Fee |
| --- | --- |
| Year 1 | $600,000 |
| **Total** | **$1,234,500** |

## Assumptions

1. **Meeting cadence.** One weekly OAC meeting. (Basis of fee: 1 x 2-hour meeting per week)

## Exclusions

- Claims and litigation support

_Basis of fee reference: abc123_
"""


def test_markdown_to_docx_round_trip(tmp_path):
    out = tmp_path / "proposal.docx"
    markdown_to_docx(SAMPLE, out)
    assert out.exists()

    d = docx.Document(str(out))
    text = "\n".join(p.text for p in d.paragraphs)
    assert "Fee Proposal" in text
    assert "Our lump-sum fee is $1,234,500, billed monthly." in text
    assert "Claims and litigation support" in text

    assert len(d.tables) == 1
    table = d.tables[0]
    assert table.cell(0, 0).text == "Period"
    assert table.cell(1, 1).text == "$600,000"
    assert table.cell(2, 1).text == "$1,234,500"  # bold markers stripped in cells


def test_bold_run_preserved(tmp_path):
    out = tmp_path / "b.docx"
    markdown_to_docx("Total is **$500** exactly.", out)
    d = docx.Document(str(out))
    runs = d.paragraphs[0].runs
    bold_texts = [r.text for r in runs if r.bold]
    assert bold_texts == ["$500"]
