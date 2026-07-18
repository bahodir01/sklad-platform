"""
Test-case generator — derives QA test cases from the data-dictionary contract.

This is the QA counterpart to the backend/frontend generators: it reads the same
contract.json that database-architect produced and emits a structured list of test
cases from each attribute's rules (required, unique, choice/enum, type, boundary,
default) and the API flags. The functional-tester works from this checklist and
the automation-engineer parametrizes automated tests from it, so field-level
coverage is complete by construction.

Usage (CLI):
    python testcase_generator.py contract.json [out.json] [--markdown out.md]

Usage (library):
    from testcase_generator import generate_cases
    cases = generate_cases(json.load(open("contract.json")))

Output: a list of cases, each:
    {
      "id": "order.email::required",
      "table": "order", "attribute": "email",
      "type": "functional", "technique": "negative/required",
      "priority": "P0",
      "title": "Reject create when required field 'email' is missing",
      "steps": [...], "expected": "..."
    }
"""

from __future__ import annotations

import json
import sys
from typing import List


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"true", "yes", "✓", "y", "1", "да"}


def _priority(attr: dict) -> str:
    """Rough risk-based priority: writable + constrained fields matter most."""
    api = attr.get("api", {})
    be = attr.get("backend", {})
    if api.get("create") or api.get("update"):
        if _truthy(be.get("unique")) or _truthy(be.get("nullable")) is False:
            return "P0"
        return "P1"
    return "P2"


def _type_family(type_str: str) -> str:
    s = (type_str or "").strip()
    for sep in ("(", "[", " "):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s


def generate_cases(contract: dict) -> List[dict]:
    cases: List[dict] = []

    def add(table, attr, kind, technique, title, steps, expected, ttype="functional", prio="P1"):
        cases.append({
            "id": f"{table}.{attr}::{kind}",
            "table": table, "attribute": attr,
            "type": ttype, "technique": technique, "priority": prio,
            "title": title, "steps": steps, "expected": expected,
        })

    for table in contract.get("tables", []):
        tname = table["name"]
        for a in table["attributes"]:
            name = a["name"]
            be = a.get("backend", {})
            api = a.get("api", {})
            prio = _priority(a)
            writable = api.get("create") or api.get("update")

            # required / nullable
            nullable = str(be.get("nullable", "")).strip().lower()
            if writable and nullable in ("false", ""):
                add(tname, name, "required", "negative/required",
                    f"Reject when required field '{name}' is missing",
                    [f"Submit a create request for '{tname}' omitting '{name}'."],
                    "Request is rejected with a validation error for that field.",
                    prio="P0" if prio == "P0" else "P1")

            # unique
            if _truthy(be.get("unique")):
                add(tname, name, "unique", "negative/unique",
                    f"Reject duplicate value for unique field '{name}'",
                    [f"Create a '{tname}' with a value for '{name}'.",
                     f"Create another '{tname}' with the same '{name}' value."],
                    "The second request is rejected as a uniqueness violation.",
                    prio="P0")

            # choice / enum
            enum = be.get("choice_enum") or ""
            if enum:
                values = [v.strip() for v in str(enum).replace("|", "/").split("/") if v.strip()]
                if values:
                    add(tname, name, "choice_valid", "positive/equivalence",
                        f"Accept each valid choice for '{name}' ({', '.join(values)})",
                        [f"For each of {values}, submit '{tname}' with '{name}' set to it."],
                        "Each valid choice is accepted.", prio=prio)
                    add(tname, name, "choice_invalid", "negative/equivalence",
                        f"Reject an invalid choice for '{name}'",
                        [f"Submit '{tname}' with '{name}' set to a value not in {values}."],
                        "The request is rejected as an invalid choice.", prio=prio)

            # type-based format
            fam = _type_family(be.get("type") or a.get("new_type", ""))
            type_negatives = {
                "IntegerField": "a non-integer string",
                "BigIntegerField": "a non-integer string",
                "DecimalField": "a non-numeric string",
                "FloatField": "a non-numeric string",
                "EmailField": "a string that is not a valid email",
                "DateField": "a non-date string",
                "DateTimeField": "a non-datetime string",
                "BooleanField": "a non-boolean value",
                "UUIDField": "a malformed UUID",
            }
            if writable and fam in type_negatives:
                add(tname, name, "type", "negative/type",
                    f"Reject invalid type for '{name}' ({fam})",
                    [f"Submit '{tname}' with '{name}' set to {type_negatives[fam]}."],
                    "The request is rejected with a type/format validation error.", prio=prio)

            # boundary (max)
            mx = be.get("filter")  # placeholder guard; real max often in type string
            max_val = a.get("frontend", {}).get("max") or ""
            if writable and str(max_val).strip():
                add(tname, name, "boundary", "boundary-value",
                    f"Boundary values for '{name}' (max={max_val})",
                    [f"Submit '{name}' at the limit ({max_val}), just below, and just above."],
                    "At and below the limit pass; above the limit is rejected.", prio=prio)

            # default
            if str(be.get("default", "")).strip() and writable:
                add(tname, name, "default", "positive/default",
                    f"Default applied for '{name}' when omitted",
                    [f"Create a '{tname}' omitting '{name}'."],
                    f"The stored value equals the declared default ({be.get('default')}).",
                    prio="P2")

            # API exposure
            if api.get("get_index"):
                add(tname, name, "api_list", "contract/exposure",
                    f"List endpoint exposes '{name}'",
                    [f"GET the '{tname}' list endpoint."],
                    f"Each item includes '{name}'.", ttype="functional", prio="P1")
            if writable and not (api.get("create") or api.get("update")):
                pass  # not writable; no create/update payload case

        # Cross-field: create payload contains exactly the create-flagged fields
        create_fields = [a["name"] for a in table["attributes"] if a.get("api", {}).get("create")]
        if create_fields:
            cases.append({
                "id": f"{tname}::create_payload_shape",
                "table": tname, "attribute": "*",
                "type": "functional", "technique": "contract/payload", "priority": "P0",
                "title": f"Create payload for '{tname}' accepts exactly the create fields",
                "steps": [f"POST '{tname}' with exactly {create_fields}.",
                          "POST again including a non-create field."],
                "expected": "The first succeeds; the extra field is ignored or rejected.",
            })

    return cases


def to_markdown(cases: List[dict]) -> str:
    lines = ["# Generated QA test cases", "",
             f"Total: {len(cases)} cases", ""]
    by_table: dict = {}
    for c in cases:
        by_table.setdefault(c["table"], []).append(c)
    for table, cs in by_table.items():
        lines.append(f"## Table: {table}")
        lines.append("")
        for c in cs:
            lines.append(f"- **[{c['priority']}] {c['id']}** ({c['technique']}) — {c['title']}")
            for s in c["steps"]:
                lines.append(f"    - step: {s}")
            lines.append(f"    - expected: {c['expected']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python testcase_generator.py contract.json [out.json] [--markdown out.md]")
        return 2
    contract = json.load(open(argv[1], encoding="utf-8"))
    cases = generate_cases(contract)
    out_json = None
    md_path = None
    rest = argv[2:]
    if "--markdown" in rest:
        i = rest.index("--markdown")
        md_path = rest[i + 1] if i + 1 < len(rest) else "testcases.md"
        rest = rest[:i] + rest[i + 2:]
    if rest:
        out_json = rest[0]

    if out_json:
        json.dump(cases, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"wrote {out_json} ({len(cases)} cases)")
    if md_path:
        open(md_path, "w", encoding="utf-8").write(to_markdown(cases))
        print(f"wrote {md_path}")
    if not out_json and not md_path:
        print(json.dumps(cases, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
