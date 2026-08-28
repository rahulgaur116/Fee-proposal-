// Word version of the Central Synagogue ECM concept-estimate fee proposal,
// formatted to match the firm's sample estimating proposal PDF:
// wordmark + right-aligned address block (first page), red all-caps section
// headings, Calibri justified body, numbered scope with lettered sub-items,
// yellow-slash brand footer, side-by-side sign-off, rates page at the end.
// Fee figures come from the locked fee model (out/fee_model.json).

const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, Footer, Header, LevelFormat,
  Packer, PageBreak, Paragraph, Table, TableCell, TableRow, TextRun,
  VerticalAlign, WidthType,
} = require("docx");

const OUT = path.join(__dirname, "out");
const model = JSON.parse(fs.readFileSync(path.join(OUT, "fee_model.json")));
const analysis = JSON.parse(fs.readFileSync(path.join(OUT, "analysis.json")));

const fmtMoney = (x) => "$" + Math.round(x).toLocaleString("en-US");
const TOTAL = fmtMoney(model.total_fee);
if (model.total_fee !== 18420) {
  throw new Error(`fee model total ${model.total_fee} != expected 18420 - reprice first`);
}

const RED = "C00000";
const GOLD = "FFB81C";
const GRAY = "808080";
const FONT = "Calibri";
const SIZE = 20; // 10pt in half-points

const body = (children, opts = {}) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 160 },
  children: typeof children === "string"
    ? [new TextRun({ text: children, font: FONT, size: SIZE })]
    : children,
  ...opts,
});
const run = (text, opts = {}) => new TextRun({ text, font: FONT, size: SIZE, ...opts });
const heading = (text) => new Paragraph({
  spacing: { before: 240, after: 160 },
  children: [run(text, { color: RED })],
});

const NOBORDER = {
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
  insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE },
};
const bareCell = (width, children, opts = {}) => new TableCell({
  width: { size: width, type: WidthType.DXA },
  borders: NOBORDER, verticalAlign: VerticalAlign.TOP,
  children, ...opts,
});

// ---- numbering ------------------------------------------------------------

const numbered = (ref, fmt, text, indent, hang) => ({
  reference: ref,
  levels: [{
    level: 0, format: fmt, text, alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: indent, hanging: hang } } },
  }],
});
const numbering = {
  config: [
    numbered("objectives", LevelFormat.DECIMAL, "%1)", 1080, 360),
    numbered("scope", LevelFormat.DECIMAL, "%1.", 720, 360),
    numbered("scope1-letters", LevelFormat.LOWER_LETTER, "%1)", 1440, 360),
    numbered("scope2-letters", LevelFormat.LOWER_LETTER, "%1)", 1440, 360),
    numbered("fee-items", LevelFormat.DECIMAL, "%1.", 1080, 360),
    numbered("assumptions", LevelFormat.DECIMAL, "%1.", 720, 360),
    numbered("exclusions", LevelFormat.DECIMAL, "%1.", 1080, 360),
  ],
};
const listItem = (ref, children) => new Paragraph({
  numbering: { reference: ref, level: 0 },
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 80 },
  children: typeof children === "string" ? [run(children)] : children,
});

// ---- first-page header: wordmark left, address right ----------------------

const wordmark = [
  new Paragraph({
    children: [new TextRun({
      text: "C U M M I N G", font: "Calibri Light", size: 40, bold: true,
    })],
  }),
  new Paragraph({
    indent: { left: 720 },
    children: [new TextRun({
      text: "G R O U P", font: "Calibri Light", size: 40, bold: true,
    })],
  }),
];
const addressLines = ["151 West 42nd Street", "12th Floor", "New York, NY 10036", "", "T 212 459 1818", ""];
const addressBlock = addressLines.map((t) => new Paragraph({
  alignment: AlignmentType.LEFT,
  children: [run(t, { size: 18 })],
})).concat([new Paragraph({
  alignment: AlignmentType.LEFT,
  children: [run("cumming-group.com", { size: 18, color: RED })],
})]);

const firstHeader = new Header({
  children: [
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [6160, 3200],
      borders: NOBORDER,
      rows: [new TableRow({
        children: [bareCell(6160, wordmark), bareCell(3200, addressBlock)],
      })],
    }),
    new Paragraph({ children: [] }),
  ],
});

const brandFooter = new Footer({
  children: [new Paragraph({
    children: [
      new TextRun({ text: "////////////////////////////////  ", font: FONT, size: 17, color: GOLD, bold: true }),
      new TextRun({ text: "B U I L D I N G   V A L U E   T H R O U G H   E X P E R T I S E", font: FONT, size: 15, color: GRAY }),
    ],
  })],
});

// ---- letter body ----------------------------------------------------------

const today = new Date();
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
const day = today.getDate();
const ord = day % 10 === 1 && day !== 11 ? "st" : day % 10 === 2 && day !== 12 ? "nd"
  : day % 10 === 3 && day !== 13 ? "rd" : "th";

const children = [
  new Paragraph({
    spacing: { after: 240 },
    children: [
      run(`${MONTHS[today.getMonth()]} ${day}`),
      run(ord, { superScript: true }),
      run(` ${today.getFullYear()}`),
    ],
  }),
  body([run("[Client Contact]")], { alignment: AlignmentType.LEFT, spacing: { after: 0 } }),
  body([run("[Title]")], { alignment: AlignmentType.LEFT, spacing: { after: 0 } }),
  body([run("Central Synagogue")], { alignment: AlignmentType.LEFT, spacing: { after: 0 } }),
  body([run("652 Lexington Avenue")], { alignment: AlignmentType.LEFT, spacing: { after: 0 } }),
  body([run("New York, NY 10022")], { alignment: AlignmentType.LEFT, spacing: { after: 240 } }),

  new Paragraph({
    spacing: { after: 240 },
    indent: { left: 1080, hanging: 1080 },
    children: [run("Re:\t"), run(
      "Synagogue & Community House Energy Conservation Measures – Fee "
      + "Proposal for cost estimating services (Concept Level Estimate)")],
    tabStops: [{ type: "left", position: 1080 }],
  }),

  body("Dear [Client Contact],", { alignment: AlignmentType.LEFT }),
  body("Thank you for contacting Cumming regarding the above project. We are "
    + "pleased to submit the following fee proposal for cost estimating services "
    + "for the Energy Conservation Measures program at the Synagogue and "
    + "Community House, comprising approximately 100,000 gross square feet "
    + "across the two buildings."),
  body("It is our understanding that an energy study and facility condition "
    + "assessment have identified a program of energy conservation measures "
    + "across both buildings, including: conversion of the steam distribution to "
    + "hot water, with two conversion options to be compared – central "
    + "conversion at the Synagogue with a street crossing (Option 1), versus "
    + "conversion at each building’s cellar (Option 2); steam condensate "
    + "recovery with associated tanks, pump sets, and coil resizing for 120°F "
    + "supply water; replacement of perimeter fan coils and air handling units "
    + "with two-way valve conversions; full BMS integration with demand control "
    + "ventilation, outdoor air metering, off-hours retuning, and DOAS heat "
    + "recovery; LED lighting and plug-load control upgrades to unrenovated "
    + "floors; and envelope measures comprising Community House window "
    + "replacement (with a triple-pane alternate) and wall insulation at "
    + "renovated floors. You have asked us to prepare a concept level estimate "
    + "only, to establish the program budget and support the selection between "
    + "the conversion options."),

  heading("APPROACH TO COST ESTIMATING"),
  body("Our firm understands the importance of accurate estimating in support of "
    + "the overall team for design, logistics, planning and budgeting, and our "
    + "goal as Cost Estimator would be to achieve three key objectives:"),
  listItem("objectives", "Cost certainty"),
  listItem("objectives", "Cost Predictability; and"),
  listItem("objectives", "to avoid any financial surprises."),
  body("At concept level, our estimate establishes the total program budget as "
    + "early as possible: we price what is described, we measure what is not yet "
    + "drawn through clearly identified allowances, and we communicate every "
    + "assumption back to the team for confirmation during the estimate review "
    + "process. Our specialized MEP cost estimating team – which exclusively "
    + "focuses on mechanical, electrical, and plumbing scope – will lead "
    + "this assignment, as the steam conversion, condensate recovery, and "
    + "controls measures represent the substantial majority of the program "
    + "value. Each allowance, markup, escalation, and premium is shown as a "
    + "separately identified line, so the estimate remains transparent and "
    + "auditable as the design develops."),

  heading("SCOPE OF SERVICES"),
  body("Our fee covers the following scope of services:"),
  listItem("scope", "Concept Level Estimate – Energy Conservation Measures"),
  ...[
    "Kickoff meeting; review of the ECM scope narrative, the facility condition "
    + "assessment recommendations, and any available drawings and equipment schedules.",
    "One site walk of both the Synagogue and the Community House to confirm "
    + "existing conditions, floor counts, equipment counts, and window quantities.",
    "Concept (ROM) level construction cost estimate covering all listed energy "
    + "conservation measures at both buildings, organized in Uniformat.",
    "Comparative pricing of the steam-to-hot-water conversion: Option 2 "
    + "(conversion at each building) carried in the base estimate, with Option 1 "
    + "(central conversion at the Synagogue including the street crossing) "
    + "presented as a cost delta.",
    "Pricing of the triple-pane window upgrade as an add alternate to the "
    + "double-pane IGU base.",
    "Identified allowances for escalation, off-hours work premiums in occupied "
    + "buildings, hazardous materials abatement, and street excavation permitting "
    + "and restoration.",
    "Issue of the draft concept estimate with a written basis-of-estimate narrative.",
  ].map((t) => listItem("scope1-letters", t)),
  listItem("scope", "Estimate Review & Final Issue"),
  ...[
    "One estimate review meeting with the Owner and design team to walk through "
    + "findings, cost drivers, and the option comparison.",
    "Incorporation of one consolidated round of review comments.",
    "Final issue of the concept estimate.",
  ].map((t) => listItem("scope2-letters", t)),

  heading("FEE PROPOSAL"),
  body(`For the above outlined scope of services, we propose a lump sum fee of `
    + `${TOTAL} to be billed upon completion of the deliverable as outlined below:`),
  listItem("fee-items", [
    run("Concept Level Estimate – Energy Conservation Measures, including "
      + "estimate review and final issue – "),
    run(`${TOTAL} lump sum`, { bold: true }),
  ]),
  body("Additional services beyond the scope above – including an on-site "
    + "estimate presentation, additional revision cycles, milestone estimates as "
    + "the design develops, or an updated estimate upon receipt of schematic "
    + "design documents – can be provided at the hourly rates attached or "
    + "as an agreed lump sum."),

  heading("ASSUMPTIONS"),
  body("The fee above is priced on the following assumptions, which will also "
    + "form the basis of the estimate. Where the eventual scope differs, we will "
    + "adjust accordingly:"),
  ...analysis.gaps.map((g) => listItem("assumptions", [
    run(`${g.topic}. `, { bold: true }),
    run(`${g.proposed_assumption} `),
    run(`(Basis of fee: ${g.pricing_basis})`, { italics: true }),
  ])),

  heading("EXCLUSIONS"),
  body("The following items are not included in the lump sum fee referenced above:"),
  ...analysis.exclusions_suggested.map((x) => listItem("exclusions", x)),

  body("We look forward to working with you and the rest of the project team on "
    + "this project. Should you have any questions or comments with regard to "
    + "any aspect of the proposal, please do not hesitate to contact me.",
    { spacing: { before: 160, after: 240 } }),

  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [4680, 4680],
    borders: NOBORDER,
    rows: [
      new TableRow({
        children: [
          bareCell(4680, [body("Sincerely yours,", { alignment: AlignmentType.LEFT, spacing: { after: 0 } })]),
          bareCell(4680, [body("Accepted by: _________________________", { alignment: AlignmentType.LEFT, spacing: { after: 0 } })]),
        ],
      }),
      new TableRow({
        children: [bareCell(4680, [new Paragraph({ children: [] }), new Paragraph({ children: [] }), new Paragraph({ children: [] })]),
                   bareCell(4680, [new Paragraph({ children: [] })])],
      }),
      new TableRow({
        children: [
          bareCell(4680, [
            body("[Name]", { alignment: AlignmentType.LEFT, spacing: { after: 0 } }),
            body("[Title], Cost Management", { alignment: AlignmentType.LEFT, spacing: { after: 0 } }),
          ]),
          bareCell(4680, [body("Signature: ____________________________", { alignment: AlignmentType.LEFT, spacing: { after: 0 } })]),
        ],
      }),
    ],
  }),
  new Paragraph({ spacing: { before: 300 }, children: [
    run(`This proposal is subject to our standard Terms and Conditions `
      + `(Exhibit A). Basis of fee reference: ${model.lock.lock_id}`,
      { italics: true, size: 15, color: GRAY }),
  ] }),

  // ---- rates page ---------------------------------------------------------
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({
    spacing: { before: 480, after: 400 },
    children: [run("COST MANAGEMENT HOURLY RATES 2026", { bold: true, size: 22 })],
  }),
  new Table({
    width: { size: 6480, type: WidthType.DXA },
    columnWidths: [4320, 2160],
    borders: NOBORDER,
    rows: [
      ["Vice President", 350], ["Senior Director", 300], ["Director", 250],
      ["Associate Director", 225], ["Senior Cost Manager", 190],
      ["Cost Manager", 160],
      ["Assistant Cost Manager / Estimating Technician / Intern", 110],
    ].map(([title, rate]) => new TableRow({
      children: [
        bareCell(4320, [body(String(title), { alignment: AlignmentType.LEFT, spacing: { after: 200 } })]),
        bareCell(2160, [body(`$${Number(rate).toFixed(2)} per hour`, { alignment: AlignmentType.LEFT, spacing: { after: 200 } })]),
      ],
    })),
  }),
];

const doc = new Document({
  numbering,
  styles: { default: { document: { run: { font: FONT, size: SIZE } } } },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1000, bottom: 1100, left: 1150, right: 1150 },
      },
      titlePage: true,
    },
    headers: { first: firstHeader, default: new Header({ children: [] }) },
    footers: { first: brandFooter, default: brandFooter },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(OUT, "Central_Synagogue_ECM_Fee_Proposal.docx");
  fs.writeFileSync(out, buf);
  console.log(`OK ${out} - total ${TOTAL}, lock ${model.lock.lock_id}`);
});
