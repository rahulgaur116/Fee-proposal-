"""Local proposal database: every priced job is recorded, outcomes are logged,
and calibration benchmarks are rebuilt from the accumulated history.

SQLite, single file, no server. Default location is ~/.feeprop/proposals.db,
overridable with FEEPROP_DB or --db. No LLM calls in this module - the
learning loop is: price records the job -> outcome logs won/lost -> calibrate
rebuilds benchmarks -> the next estimate anchors on them.
"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import FeeModel, PastLine, PastSubmission, ScopeAnalysis

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY,
    project_name TEXT NOT NULL UNIQUE,
    client_name TEXT,
    project_type TEXT,
    sector TEXT,
    construction_value REAL,
    duration_months INTEGER,
    total_fee REAL NOT NULL,
    total_hours REAL NOT NULL,
    currency TEXT,
    lock_id TEXT NOT NULL,
    priced_at TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'pending',  -- pending | won | lost
    final_fee REAL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS lines (
    id INTEGER PRIMARY KEY,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    deliverable TEXT NOT NULL,
    role_code TEXT NOT NULL,
    hours REAL NOT NULL,
    fee REAL NOT NULL
);
"""


def default_path() -> Path:
    env = os.environ.get("FEEPROP_DB")
    if env:
        return Path(env)
    return Path.home() / ".feeprop" / "proposals.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def record_job(conn: sqlite3.Connection, analysis: ScopeAnalysis,
               model: FeeModel) -> int:
    """Insert or replace the priced job, keyed by project name. A reprice
    replaces the numbers but preserves a previously logged outcome."""
    facts = analysis.facts
    cur = conn.execute(
        "SELECT outcome, final_fee, notes FROM proposals WHERE project_name = ?",
        (model.project_name,))
    prior = cur.fetchone()
    outcome, final_fee, notes = prior if prior else ("pending", None, None)
    conn.execute("DELETE FROM proposals WHERE project_name = ?", (model.project_name,))
    cur = conn.execute(
        """INSERT INTO proposals (project_name, client_name, project_type, sector,
               construction_value, duration_months, total_fee, total_hours,
               currency, lock_id, priced_at, outcome, final_fee, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (model.project_name, model.client_name, facts.project_type, facts.sector,
         facts.construction_value, model.term_months, model.total_fee,
         sum(model.hours_by_role.values()), model.currency, model.lock.lock_id,
         datetime.now(timezone.utc).isoformat(timespec="seconds"),
         outcome, final_fee, notes))
    pid = cur.lastrowid
    # aggregate hours/fee per (deliverable, role) - the calibration grain
    agg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for pl in model.lines:
        agg[(pl.deliverable, pl.role_code)][0] += pl.total_hours
        agg[(pl.deliverable, pl.role_code)][1] += pl.amount
    conn.executemany(
        "INSERT INTO lines (proposal_id, deliverable, role_code, hours, fee) "
        "VALUES (?, ?, ?, ?, ?)",
        [(pid, d, r, h, f) for (d, r), (h, f) in sorted(agg.items())])
    conn.commit()
    return pid


def set_outcome(conn: sqlite3.Connection, project_name: str, outcome: str,
                final_fee: float | None = None, notes: str | None = None) -> None:
    if outcome not in ("won", "lost", "pending"):
        raise ValueError("outcome must be won, lost, or pending")
    cur = conn.execute(
        "UPDATE proposals SET outcome = ?, final_fee = COALESCE(?, final_fee), "
        "notes = COALESCE(?, notes) WHERE project_name LIKE ?",
        (outcome, final_fee, notes, f"%{project_name}%"))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(f"No proposal matching {project_name!r} in the database")
    if cur.rowcount > 1:
        raise KeyError(f"{project_name!r} matches {cur.rowcount} proposals - be more specific")


def list_jobs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(conn.execute(
        "SELECT project_name, client_name, project_type, duration_months, "
        "total_fee, total_hours, outcome, lock_id, priced_at "
        "FROM proposals ORDER BY priced_at DESC"))


def load_submissions(conn: sqlite3.Connection) -> list[PastSubmission]:
    """The database as calibration input - same shape as YAML past records."""
    conn.row_factory = sqlite3.Row
    subs = []
    for row in conn.execute("SELECT * FROM proposals"):
        lines = [PastLine(deliverable=l["deliverable"], role_code=l["role_code"],
                          hours=l["hours"])
                 for l in conn.execute(
                     "SELECT deliverable, role_code, hours FROM lines "
                     "WHERE proposal_id = ?", (row["id"],))]
        subs.append(PastSubmission(
            name=row["project_name"],
            project_type=row["project_type"] or "unknown",
            sector=row["sector"],
            construction_value=row["construction_value"],
            duration_months=row["duration_months"] or 1,
            fee=row["final_fee"] or row["total_fee"],
            won={"won": True, "lost": False}.get(row["outcome"]),
            lines=lines))
    return subs
