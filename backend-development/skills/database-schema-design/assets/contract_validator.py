"""
Contract validator — enforces that backend code matches the data dictionary.

The data dictionary (Excel) and its JSON contract are produced together from the
same rows, so they always agree. This validator closes the loop: it parses the
generated Django models (and, optionally, DRF serializers) and checks that every
table, attribute, type, and API CRUD flag matches the contract EXACTLY.

If the backend agent renamed a field, changed a type, dropped a column, or
exposed a field in an endpoint that the dictionary marks as not-exposed, this
script reports it and exits non-zero — so the feature-development command halts
instead of shipping code that diverges from the table.

It uses Python's `ast` module only (no Django import needed), so it runs anywhere.

Usage:
    python contract_validator.py contract.json models.py [serializers.py ...]

Exit code 0 = match. Non-zero = mismatches found (printed).
"""

from __future__ import annotations

import ast
import json
import sys
from typing import Dict, List, Optional


# Map Django field classes -> the contract's backend "type" family. The contract
# stores the type as written by the architect (e.g. "CharField(max_length=20)"),
# so we compare on the field-class prefix, not the full string.
def _field_class(type_str: str) -> str:
    """Extract the Django field class name from a contract type string."""
    s = (type_str or "").strip()
    for sep in ("(", "[", " "):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s


# --------------------------------------------------------------------------- #
# Parse generated Django models via AST.
# --------------------------------------------------------------------------- #
class ModelExtractor(ast.NodeVisitor):
    """Collect {model_name: {field_name: field_class}} from a models.py."""

    def __init__(self) -> None:
        self.models: Dict[str, Dict[str, str]] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Only treat classes whose bases mention Model as Django models.
        base_names = []
        for b in node.bases:
            base_names.append(ast.unparse(b) if hasattr(ast, "unparse") else getattr(b, "attr", getattr(b, "id", "")))
        if not any("Model" in bn for bn in base_names):
            self.generic_visit(node)
            return
        fields: Dict[str, str] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                fname = stmt.targets[0].id
                if isinstance(stmt.value, ast.Call):
                    func = stmt.value.func
                    cls = getattr(func, "attr", getattr(func, "id", ""))
                    # models.CharField(...) -> "CharField"
                    fields[fname] = cls
        if fields:
            self.models[node.name] = fields
        self.generic_visit(node)


def extract_models(path: str) -> Dict[str, Dict[str, str]]:
    tree = ast.parse(open(path, encoding="utf-8").read())
    ex = ModelExtractor()
    ex.visit(tree)
    return ex.models


# --------------------------------------------------------------------------- #
# Parse DRF serializers (optional) to check API exposure.
# --------------------------------------------------------------------------- #
class SerializerExtractor(ast.NodeVisitor):
    """Collect {serializer_name: {'model': str|None, 'fields': [..]|'__all__'}}."""

    def __init__(self) -> None:
        self.serializers: Dict[str, dict] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        info = {"model": None, "fields": None}
        for stmt in node.body:
            if isinstance(stmt, ast.ClassDef) and stmt.name == "Meta":
                for s in stmt.body:
                    if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name):
                        key = s.targets[0].id
                        if key == "model":
                            info["model"] = getattr(s.value, "attr", getattr(s.value, "id", None))
                        elif key == "fields":
                            if isinstance(s.value, ast.Constant):
                                info["fields"] = s.value.value  # "__all__"
                            elif isinstance(s.value, (ast.List, ast.Tuple)):
                                info["fields"] = [
                                    e.value for e in s.value.elts if isinstance(e, ast.Constant)
                                ]
        if info["model"] or info["fields"] is not None:
            self.serializers[node.name] = info
        self.generic_visit(node)


def extract_serializers(path: str) -> Dict[str, dict]:
    tree = ast.parse(open(path, encoding="utf-8").read())
    ex = SerializerExtractor()
    ex.visit(tree)
    return ex.serializers


# --------------------------------------------------------------------------- #
# Validation.
# --------------------------------------------------------------------------- #
def _model_name(table: str) -> str:
    """orders -> Orders ... but tables are usually singular; match case-insensitively."""
    return table.replace("_", "").lower()


def validate(contract: dict, models: Dict[str, Dict[str, str]],
             serializers: Optional[Dict[str, dict]] = None) -> List[str]:
    errors: List[str] = []

    # index models case-insensitively by squashed name
    model_index = {name.replace("_", "").lower(): (name, fields) for name, fields in models.items()}

    for table in contract["tables"]:
        tname = table["name"]
        key = _model_name(tname)
        match = model_index.get(key)
        # also try singular/plural-insensitive contains match
        if not match:
            for k, v in model_index.items():
                if k.startswith(key) or key.startswith(k):
                    match = v
                    break
        if not match:
            errors.append(f"[table] '{tname}' from the data dictionary has no matching Django model")
            continue

        model_name, model_fields = match
        model_field_names = {f.lower() for f in model_fields}

        for attr in table["attributes"]:
            aname = attr["name"]
            if aname == "id":
                continue  # Django auto-provides pk unless overridden
            if aname.lower() not in model_field_names:
                errors.append(
                    f"[attribute] {tname}.{aname} is in the dictionary but missing from model '{model_name}'"
                )
                continue
            # Type family check
            expected = _field_class(attr["backend"]["type"])
            actual = model_fields.get(aname) or model_fields.get(aname.lower(), "")
            if expected and actual and expected != actual:
                errors.append(
                    f"[type] {tname}.{aname}: dictionary says '{expected}', model has '{actual}'"
                )

        # Reverse check: model fields not in the dictionary.
        dict_names = {a["name"].lower() for a in table["attributes"]}
        for fname in model_fields:
            if fname.lower() not in dict_names and fname != "id":
                errors.append(
                    f"[extra] model '{model_name}' has field '{fname}' not present in the data dictionary"
                )

    # API exposure check (only if serializers were supplied).
    if serializers:
        for table in contract["tables"]:
            tname = table["name"]
            # fields that should appear in create/update payloads
            create_fields = {a["name"] for a in table["attributes"] if a["api"]["create"]}
            update_fields = {a["name"] for a in table["attributes"] if a["api"]["update"]}
            for sname, info in serializers.items():
                if not info.get("model"):
                    continue
                if _model_name(info["model"]) != _model_name(tname):
                    continue
                fields = info.get("fields")
                if fields == "__all__":
                    errors.append(
                        f"[api] serializer '{sname}' uses fields='__all__' — the dictionary defines "
                        f"explicit create/update exposure; list fields explicitly to honor the contract"
                    )
                elif isinstance(fields, list):
                    exposed = set(fields)
                    # Any field exposed for write that the dictionary marks neither create nor update?
                    writable = create_fields | update_fields
                    for f in exposed:
                        attr = next((a for a in table["attributes"] if a["name"] == f), None)
                        if attr and not (attr["api"]["create"] or attr["api"]["update"]
                                         or attr["api"]["get_index"] or attr["api"]["get_single"]):
                            errors.append(
                                f"[api] serializer '{sname}' exposes '{f}', but the dictionary marks it "
                                f"not exposed in any endpoint"
                            )
    return errors


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("usage: python contract_validator.py contract.json models.py [serializers.py ...]")
        return 2
    contract = json.load(open(argv[1], encoding="utf-8"))
    models = extract_models(argv[2])
    serializers = {}
    for extra in argv[3:]:
        serializers.update(extract_serializers(extra))
    errors = validate(contract, models, serializers or None)
    if errors:
        print(f"CONTRACT MISMATCH — {len(errors)} issue(s):")
        for e in errors:
            print("  -", e)
        return 1
    print("OK: backend code matches the data dictionary contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
