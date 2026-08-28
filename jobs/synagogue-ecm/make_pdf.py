"""Render the ECM concept-estimate fee proposal as a PDF in the firm's
letter format (per the sample estimating proposal): right-aligned letterhead,
date/addressee blocks, bold Re: line, all-caps section headings, lettered
sub-items, deliverable-based lump sums, numbered exclusions, sign-off with
Accepted by line, and the hourly-rate schedule on its own page.

Numbers come from the locked fee model; the assembled text is run through
the same dollar-figure verifier the drafting stage uses.
"""

import json
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from feeprop.models import FeeModel, RateCard, ScopeAnalysis  # noqa: E402
from feeprop.narrative import allowed_amounts, fmt_money, verify_numbers  # noqa: E402
import yaml  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"

model = FeeModel.model_validate_json((OUT / "fee_model.json").read_text())
analysis = ScopeAnalysis.model_validate_json((OUT / "analysis.json").read_text())
rc = RateCard.model_validate(yaml.safe_load((HERE / "rate_card.yaml").read_text()))

FEE_A = fmt_money(model.fee_by_deliverable[
    "Concept Level Estimate — Energy Conservation Measures"])
FEE_B = fmt_money(model.fee_by_deliverable["Estimate Review & Final Issue"])
TOTAL = fmt_money(model.total_fee)

# ---- styles ---------------------------------------------------------------

BASE = dict(fontName="Helvetica", fontSize=9.5, leading=13.5)
body = ParagraphStyle("body", spaceAfter=8, **BASE)
letterhead = ParagraphStyle("letterhead", alignment=TA_RIGHT, leading=12,
                            fontName="Helvetica", fontSize=9)
heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=9.5,
                         leading=13.5, spaceBefore=10, spaceAfter=6)
item = ParagraphStyle("item", leftIndent=18, spaceAfter=4, **BASE)
subitem = ParagraphStyle("subitem", leftIndent=40, spaceAfter=2, **BASE)
ratehead = ParagraphStyle("ratehead", fontName="Helvetica-Bold", fontSize=11,
                          leading=14, spaceAfter=14)

story = []


def p(text, style=body):
    story.append(Paragraph(text, style))


# ---- page 1+: the letter --------------------------------------------------

p("151 West 42nd Street<br/>12th Floor<br/>New York, NY 10036<br/><br/>"
  "T 212 459 1818<br/><br/>cumming-group.com", letterhead)
story.append(Spacer(1, 18))

p(date.today().strftime("%B %d, %Y").replace(" 0", " "))
story.append(Spacer(1, 10))
p("[Client Contact]<br/>[Title]<br/>[Client Name]<br/>[Client Address]")
story.append(Spacer(1, 10))

p("<b>Re: Synagogue &amp; Community House Energy Conservation Measures &ndash; "
  "Fee Proposal for cost estimating services (Concept Level Estimate)</b>")
story.append(Spacer(1, 6))

p("Dear [Client Contact],")
p("Thank you for contacting Cumming regarding the above project. We are pleased "
  "to submit the following fee proposal for cost estimating services for the "
  "Energy Conservation Measures program at the Synagogue and Community House, "
  "comprising approximately 100,000 gross square feet across the two buildings.")
p("It is our understanding that an energy study and facility condition assessment "
  "have identified a program of energy conservation measures across both "
  "buildings, including: conversion of the steam distribution to hot water, with "
  "two conversion options to be compared &ndash; central conversion at the "
  "Synagogue with a street crossing (Option 1), versus conversion at each "
  "building&rsquo;s cellar (Option 2); steam condensate recovery with associated "
  "tanks, pump sets, and coil resizing for 120&deg;F supply water; replacement of "
  "perimeter fan coils and air handling units with two-way valve conversions; "
  "full BMS integration with demand control ventilation, outdoor air metering, "
  "off-hours retuning, and DOAS heat recovery; LED lighting and plug-load "
  "control upgrades to unrenovated floors; and envelope measures comprising "
  "Community House window replacement (with a triple-pane alternate) and wall "
  "insulation at renovated floors. You have asked us to prepare a "
  "<b>concept level estimate only</b>, to establish the program budget and "
  "support the selection between the conversion options.")

p("APPROACH TO COST ESTIMATING", heading)
p("Our goal as cost estimator is to achieve three key objectives: 1) cost "
  "certainty; 2) cost predictability; and 3) to avoid any financial surprises. "
  "At concept level, our estimate establishes the total program budget as early "
  "as possible: we price what is described, we measure what is not yet drawn "
  "through clearly identified allowances, and we communicate every assumption "
  "back to the team for confirmation during the estimate review process. Our "
  "specialized MEP cost estimating team &ndash; which exclusively focuses on "
  "mechanical, electrical, and plumbing scope &ndash; will lead this assignment, "
  "as the steam conversion, condensate recovery, and controls measures represent "
  "the substantial majority of the program value. Each allowance, markup, "
  "escalation, and premium is shown as a separately identified line, so the "
  "estimate remains transparent and auditable as the design develops.")

p("SCOPE OF SERVICES", heading)
p("Our fee covers the following scope of services:")
p("1.&nbsp;&nbsp;<b>Concept Level Estimate &ndash; Energy Conservation Measures</b>", item)
for letter_, text in [
    ("a", "Kickoff meeting; review of the ECM scope narrative, the facility "
          "condition assessment recommendations, and any available drawings and "
          "equipment schedules."),
    ("b", "One site walk of both the Synagogue and the Community House to confirm "
          "existing conditions, floor counts, equipment counts, and window "
          "quantities."),
    ("c", "Concept (ROM) level construction cost estimate covering all listed "
          "energy conservation measures at both buildings, organized in Uniformat."),
    ("d", "Comparative pricing of the steam-to-hot-water conversion: Option 2 "
          "(conversion at each building) carried in the base estimate, with "
          "Option 1 (central conversion at the Synagogue including the street "
          "crossing) presented as a cost delta."),
    ("e", "Pricing of the triple-pane window upgrade as an add alternate to the "
          "double-pane IGU base."),
    ("f", "Identified allowances for escalation, off-hours work premiums in "
          "occupied buildings, hazardous materials abatement, and street "
          "excavation permitting and restoration."),
    ("g", "Issue of the draft concept estimate with a written basis-of-estimate "
          "narrative."),
]:
    p(f"{letter_})&nbsp;&nbsp;{text}", subitem)
story.append(Spacer(1, 4))
p("2.&nbsp;&nbsp;<b>Estimate Review &amp; Final Issue</b>", item)
for letter_, text in [
    ("a", "One estimate review meeting with the Owner and design team to walk "
          "through findings, cost drivers, and the option comparison."),
    ("b", "Incorporation of one consolidated round of review comments."),
    ("c", "Final issue of the concept estimate."),
]:
    p(f"{letter_})&nbsp;&nbsp;{text}", subitem)

p("FEE PROPOSAL", heading)
p(f"For the above outlined scope of services, we propose a lump sum fee of "
  f"<b>{TOTAL}</b> to be billed upon completion of each deliverable as outlined "
  f"below:")
p(f"1.&nbsp;&nbsp;Concept Level Estimate &ndash; Energy Conservation Measures "
  f"&ndash; <b>{FEE_A}</b> lump sum", item)
p(f"2.&nbsp;&nbsp;Estimate Review &amp; Final Issue &ndash; <b>{FEE_B}</b> "
  f"lump sum", item)
p("Additional services beyond the scope above &ndash; including an on-site "
  "estimate presentation, additional revision cycles, milestone estimates as the "
  "design develops, or an updated estimate upon receipt of schematic design "
  "documents &ndash; can be provided at the hourly rates attached or as an "
  "agreed lump sum.")

p("ASSUMPTIONS", heading)
p("The fee above is priced on the following assumptions, which will also form "
  "the basis of the estimate. Where the eventual scope differs, we will adjust "
  "accordingly:")
for i, gap in enumerate(analysis.gaps, 1):
    p(f"{i}.&nbsp;&nbsp;<b>{gap.topic}.</b> {gap.proposed_assumption} "
      f"<i>(Basis of fee: {gap.pricing_basis})</i>", item)

p("EXCLUSIONS", heading)
p("The following items are not included in the lump sum fee referenced above:")
for i, x in enumerate(analysis.exclusions_suggested, 1):
    p(f"{i}.&nbsp;&nbsp;{x}", item)

story.append(Spacer(1, 8))
p("We look forward to working with you and the rest of the project team on this "
  "project. Should you have any questions or comments with regard to any aspect "
  "of the proposal, please do not hesitate to contact me.")
story.append(Spacer(1, 8))

sign = Table(
    [["Sincerely yours,", "Accepted by: _________________________"],
     ["", ""],
     ["", ""],
     ["[Name]", "Signature: ____________________________"],
     ["[Title], Cost Management", ""]],
    colWidths=[3.4 * inch, 3.4 * inch])
sign.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
]))
story.append(sign)
story.append(Spacer(1, 14))
p(f"<i>This proposal is subject to our standard Terms and Conditions "
  f"(Exhibit A). Basis of fee reference: {model.lock.lock_id}</i>",
  ParagraphStyle("footer", fontName="Helvetica-Oblique", fontSize=8, leading=11))

# ---- rates page -----------------------------------------------------------

story.append(PageBreak())
p("COST MANAGEMENT HOURLY RATES 2026", ratehead)
rate_rows = [[r.title, f"{fmt_money(r.bill_rate)} per hour"] for r in rc.roles]
rates = Table(rate_rows, colWidths=[3.8 * inch, 1.8 * inch])
rates.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
]))
story.append(rates)

# ---- build and verify -----------------------------------------------------

out_pdf = OUT / "proposal.pdf"
doc = SimpleDocTemplate(
    str(out_pdf), pagesize=letter,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.7 * inch, bottomMargin=0.8 * inch,
    title="Fee Proposal - Synagogue & Community House ECM Concept Estimate",
    author=rc.firm)
doc.build(story)

# every dollar figure in the assembled letter must trace to the locked model
all_text = " ".join(
    getattr(f, "text", "") for f in story if hasattr(f, "text"))
flagged = verify_numbers(all_text, allowed_amounts(model, analysis, rc))
if flagged:
    raise SystemExit(f"UNTRACEABLE DOLLAR FIGURES: {flagged}")
print(f"OK {out_pdf} — total {TOTAL}, lock {model.lock.lock_id}, "
      f"all dollar figures trace to the locked model")
