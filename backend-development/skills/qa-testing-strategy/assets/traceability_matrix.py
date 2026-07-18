"""
Traceability matrix generator — proves every ТЗ requirement is covered by a test.

Links requirement (ТЗ id) -> test case(s) -> status -> defect(s), and flags gaps:
  * orphan requirements (no test case covers them) — a coverage hole,
  * orphan cases (no requirement) — possibly out-of-scope or a missing requirement.

It reads two small JSON files the QA agents produce:

  requirements.json  (from the analyst's ТЗ, one entry per acceptance criterion/rule)
    [
      {"id": "REQ-1", "text": "A user can create an order with items", "priority": "P0"},
      {"id": "REQ-2", "text": "An order total must be >= 0", "priority": "P1"}
    ]

  cases.json  (from test-case-designer and/or functional-tester)
    [
      {"id": "TC-1", "title": "Create order happy path", "covers": ["REQ-1"], "status": "pass"},
      {"id": "TC-2", "title": "Reject negative total", "covers": ["REQ-2"], "status": "fail",
       "defects": ["BUG-14"]}
    ]

Usage:
    python traceability_matrix.py requirements.json cases.json [--markdown matrix.md] [--json matrix.json]

Exit code 1 if there are uncovered (orphan) requirements, else 0 — so the pipeline
can gate on "every requirement has a test".
"""

from __future__ import annotations

import json
import sys
from typing import Dict, List


def build_matrix(requirements: List[dict], cases: List[dict]) -> dict:
    req_index: Dict[str, dict] = {r["id"]: r for r in requirements}

    # requirement -> list of covering cases
    coverage: Dict[str, List[dict]] = {rid: [] for rid in req_index}
    orphan_cases: List[dict] = []

    for c in cases:
        covers = c.get("covers", []) or []
        if not covers:
            orphan_cases.append(c)
            continue
        for rid in covers:
            if rid in coverage:
                coverage[rid].append(c)
            else:
                # case references a requirement id that doesn't exist
                orphan_cases.append({**c, "_bad_ref": rid})

    rows = []
    for rid, req in req_index.items():
        cs = coverage[rid]
        statuses = [c.get("status", "unknown") for c in cs]
        defects = sorted({d for c in cs for d in (c.get("defects") or [])})
        if not cs:
            overall = "UNCOVERED"
        elif any(s == "fail" for s in statuses):
            overall = "failing"
        elif all(s == "pass" for s in statuses):
            overall = "pass"
        else:
            overall = "partial"
        rows.append({
            "requirement": rid,
            "text": req.get("text", ""),
            "priority": req.get("priority", ""),
            "cases": [c["id"] for c in cs],
            "status": overall,
            "defects": defects,
        })

    uncovered = [r for r in rows if r["status"] == "UNCOVERED"]
    return {
        "rows": rows,
        "orphan_cases": orphan_cases,
        "summary": {
            "requirements": len(req_index),
            "covered": len(req_index) - len(uncovered),
            "uncovered": len(uncovered),
            "orphan_cases": len(orphan_cases),
        },
    }


def to_markdown(matrix: dict) -> str:
    s = matrix["summary"]
    lines = ["# Traceability matrix", "",
             f"Requirements: {s['requirements']} · covered: {s['covered']} · "
             f"uncovered: {s['uncovered']} · orphan cases: {s['orphan_cases']}", "",
             "| Requirement | Priority | Covering cases | Status | Defects |",
             "|---|---|---|---|---|"]
    for r in matrix["rows"]:
        cases = ", ".join(r["cases"]) or "— none —"
        defects = ", ".join(r["defects"]) or ""
        lines.append(f"| {r['requirement']}: {r['text'][:60]} | {r['priority']} | "
                     f"{cases} | {r['status']} | {defects} |")
    if matrix["orphan_cases"]:
        lines += ["", "## Orphan cases (no valid requirement)"]
        for c in matrix["orphan_cases"]:
            bad = f" (bad ref: {c['_bad_ref']})" if "_bad_ref" in c else ""
            lines.append(f"- {c.get('id','?')}: {c.get('title','')}{bad}")
    if matrix["summary"]["uncovered"]:
        lines += ["", "## ⚠ Uncovered requirements (no test case)"]
        for r in matrix["rows"]:
            if r["status"] == "UNCOVERED":
                lines.append(f"- {r['requirement']}: {r['text']}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("usage: python traceability_matrix.py requirements.json cases.json "
              "[--markdown matrix.md] [--json matrix.json]")
        return 2
    requirements = json.load(open(argv[1], encoding="utf-8"))
    cases = json.load(open(argv[2], encoding="utf-8"))
    matrix = build_matrix(requirements, cases)

    rest = argv[3:]
    md_path = json_path = None
    if "--markdown" in rest:
        i = rest.index("--markdown"); md_path = rest[i + 1]
    if "--json" in rest:
        i = rest.index("--json"); json_path = rest[i + 1]

    if md_path:
        open(md_path, "w", encoding="utf-8").write(to_markdown(matrix))
        print(f"wrote {md_path}")
    if json_path:
        json.dump(matrix, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"wrote {json_path}")
    if not md_path and not json_path:
        print(to_markdown(matrix))

    s = matrix["summary"]
    print(f"\nSummary: {s['covered']}/{s['requirements']} requirements covered, "
          f"{s['uncovered']} uncovered, {s['orphan_cases']} orphan case(s).")
    return 1 if s["uncovered"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
