"""
UI contract validator — enforces that the frontend matches the data dictionary.

The frontend can be React, Vue, or Angular, so we don't AST-parse framework code.
Instead the frontend developer emits a small **field manifest** describing what
each view renders, and this script checks it against the same contract.json the
backend uses. It is the client-side mirror of contract_validator.py.

It fails (exit 1) when:
  * a view references a field not present in the contract for that table,
  * a table/list view shows a field NOT flagged get_index,
  * a detail view shows a field NOT flagged get_single,
  * a create form includes a field NOT flagged create,
  * an edit/update form includes a field NOT flagged update.

Manifest format (ui_manifest.json):
{
  "views": [
    {"name": "OrderTable",     "table": "order", "kind": "list",   "fields": ["customer", "status", "total_amount"]},
    {"name": "OrderDetail",    "table": "order", "kind": "detail", "fields": ["customer", "status", "total_amount", "created_at"]},
    {"name": "OrderCreateForm","table": "order", "kind": "create", "fields": ["customer", "status", "total_amount"]},
    {"name": "OrderEditForm",  "table": "order", "kind": "update", "fields": ["status", "total_amount"]}
  ]
}

Usage:
    python ui_contract_validator.py contract.json ui_manifest.json

Exit code 0 = the UI matches the contract. Non-zero = mismatches (printed).
"""

from __future__ import annotations

import json
import sys
from typing import Dict, List

# kind -> the API flag that must be true for a field to appear in that view.
KIND_FLAG = {
    "list": "get_index",
    "table": "get_index",
    "detail": "get_single",
    "create": "create",
    "update": "update",
    "edit": "update",
}


def _index_contract(contract: dict) -> Dict[str, Dict[str, dict]]:
    """Return {table_name: {attr_name: attr_dict}}."""
    idx: Dict[str, Dict[str, dict]] = {}
    for table in contract.get("tables", []):
        idx[table["name"]] = {a["name"]: a for a in table["attributes"]}
    return idx


def validate(contract: dict, manifest: dict) -> List[str]:
    errors: List[str] = []
    idx = _index_contract(contract)

    for view in manifest.get("views", []):
        vname = view.get("name", "<unnamed>")
        table = view.get("table")
        kind = (view.get("kind") or "").lower()
        fields = view.get("fields", [])

        if table not in idx:
            errors.append(f"[view] '{vname}' targets table '{table}' not in the contract")
            continue
        if kind not in KIND_FLAG:
            errors.append(
                f"[view] '{vname}' has unknown kind '{kind}' "
                f"(expected one of {sorted(set(KIND_FLAG))})"
            )
            continue

        flag = KIND_FLAG[kind]
        attrs = idx[table]

        for f in fields:
            if f not in attrs:
                errors.append(
                    f"[field] view '{vname}' renders '{table}.{f}' which is not in the contract"
                )
                continue
            api = attrs[f].get("api", {})
            if not api.get(flag, False):
                errors.append(
                    f"[exposure] view '{vname}' ({kind}) renders '{table}.{f}', "
                    f"but the contract does not flag it '{flag}'"
                )

    return errors


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("usage: python ui_contract_validator.py contract.json ui_manifest.json")
        return 2
    contract = json.load(open(argv[1], encoding="utf-8"))
    manifest = json.load(open(argv[2], encoding="utf-8"))
    errors = validate(contract, manifest)
    if errors:
        print(f"UI CONTRACT MISMATCH — {len(errors)} issue(s):")
        for e in errors:
            print("  -", e)
        return 1
    print("OK: UI matches the data dictionary contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
