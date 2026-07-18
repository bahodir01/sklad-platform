"""
Contract validator (SQLAlchemy 2.0 + Pydantic v2) — enforces that backend code
matches the data dictionary.

This is the SQLAlchemy/Pydantic port of `contract_validator.py`, which does the
same job for Django models + DRF serializers. Both files are kept: pick the one
that matches the project's stack. Nothing here imports SQLAlchemy or Pydantic —
it is pure `ast`, so it runs anywhere.

The data dictionary (Excel) and its JSON contract are produced together from the
same rows, so they always agree. This validator closes the loop: it parses the
generated SQLAlchemy models (and, optionally, the Pydantic schemas) and checks
that every table, column, type, constraint, and API CRUD flag matches the
contract EXACTLY.

If the backend agent renamed a column, changed a type, dropped `nullable=`,
forgot a `ForeignKey`'s `ondelete`, or exposed a field in a request schema that
the dictionary marks as not-exposed, this script reports it and exits non-zero —
so the feature-development command halts instead of shipping code that diverges
from the table.

Usage:
    python contract_validator_sqlalchemy.py contract.json models.py [schemas.py ...]

Exit code 0 = match. 1 = mismatches found (printed). 2 = bad invocation.

Every source file after the contract is scanned for both kinds of class —
mapped classes are recognised by `__tablename__`, Pydantic schemas by
`BaseModel` / `model_config` — so a modular layout works by passing every file:

    python contract_validator_sqlalchemy.py 02-contract.json \
        backend/app/modules/*/models.py backend/app/modules/*/schemas.py

The schema checks stay opt-in: if no Pydantic class is found in any file, only
the model checks run.


What is checked
---------------
Models (`models.py`, required):
  * every contract table has a mapped class whose `__tablename__` equals the
    table name — the class name is NOT used for matching (key difference from
    the Django port, where the model class name IS the identity);
  * every contract attribute exists as a `mapped_column`;
  * column type, `nullable=`, `unique=`, index presence, `default=` /
    `server_default=`, and `ForeignKey('table.col', ondelete=...)`;
  * columns present in the model but absent from the dictionary ([extra]);
  * `relationship()` attributes are ignored — they are not columns.

Schemas (`schemas.py ...`, optional):
  * a field is in `XxxCreate` if and only if `api.create` is true, in
    `XxxUpdate` iff `api.update`, in `XxxRead` iff `api.get_single`, and in
    `XxxList` iff `api.get_index`;
  * a schema carrying `model_config = ConfigDict(from_attributes=True)` but
    declaring no fields of its own (nor via a local base class) cannot honour
    per-field flags — reported, as the Django port reports `fields = "__all__"`.


Schema -> table name resolution
-------------------------------
Resolved in this order; the first rule that fires wins:

  1. explicit `__contract_table__ = "warehouses"` on the class — always wins.
     `__contract_table__ = None` opts the class out entirely (use it for
     schemas that back no table at all, e.g. `TokenCreate`, `LoginCreate`).
  2. strip the suffix (`Create` / `Update` / `Read` / `List`) from the class
     name and look for a mapped class of exactly that name in the parsed
     models; if found, take its `__tablename__`.
     `WarehouseCreate` -> class `Warehouse` -> table `warehouses`.
     This is the primary rule and the one that handles irregular names
     (`MoneyIncomeCreate` -> `MoneyIncome` -> `money_income`).
  3. snake_case the stripped name and try it against the contract's table
     names directly, then with naive plurals (+s, +es, y->ies).
     `WarehouseCreate` -> `warehouse` -> `warehouses`.

A class whose name ends in none of the four suffixes is not a request/response
schema and is skipped silently (base classes and mixins like `WarehouseBase`
live here). A class that DOES carry a suffix but resolves to nothing is
reported as `[unmatched]` rather than guessed at — a schema the gate cannot
map is a schema the gate cannot check.

Escape hatch: `__contract_extra_fields__ = {"items", "qty_remaining"}` on a
schema whitelists field names that legitimately are not dictionary attributes
(nested relation payloads, computed/derived values).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

SCHEMA_SUFFIXES: Tuple[str, ...] = ("Create", "Update", "Read", "List")

# schema suffix -> the contract api.* flag that governs it
SUFFIX_TO_API_FLAG: Dict[str, str] = {
    "Create": "create",
    "Update": "update",
    "Read": "get_single",
    "List": "get_index",
}


# --------------------------------------------------------------------------- #
# Small helpers.
# --------------------------------------------------------------------------- #
def _unparse(node: Optional[ast.AST]) -> str:
    """Render an AST node back to source, tolerating None."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return ""


def _const_str(node: Optional[ast.AST]) -> Optional[str]:
    """Return the value of a string constant node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_true(node: Optional[ast.AST]) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _call_name(node: ast.AST) -> str:
    """`sa.ForeignKey(...)` / `ForeignKey(...)` -> 'ForeignKey'. '' if not a call."""
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    return getattr(func, "attr", getattr(func, "id", "")) or ""


def _snake(name: str) -> str:
    """MoneyIncome -> money_income."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _plural_candidates(singular: str) -> List[str]:
    """Naive plurals, used only as the last-resort mapping rule."""
    out = [singular]
    if singular.endswith("y"):
        out.append(singular[:-1] + "ies")
    if singular.endswith(("s", "x", "z", "ch", "sh")):
        out.append(singular + "es")
    out.append(singular + "s")
    return out


def _contract_bool(value: str) -> Optional[bool]:
    """Contract cells hold strings: 'True' / 'False' / '' / 'True (PK)'.

    Returns True/False for a recognised leading token, None for blank.
    """
    s = (value or "").strip()
    if not s:
        return None
    head = re.split(r"[\s(]", s, maxsplit=1)[0].strip().lower()
    if head in ("true", "yes", "✓"):
        return True
    if head in ("false", "no", "—", "-"):
        return False
    return None


def normalize_type(type_str: str) -> str:
    """Normalize a column type for comparison.

    The contract stores the type as the architect wrote it, sometimes with a
    trailing prose annotation and sometimes with the FK glued on after a '·':

        "BigInteger · ForeignKey('users.id', ondelete='RESTRICT')" -> "BigInteger"
        "INET (postgresql.INET)"                                   -> "INET"
        "Numeric(14, 3)"                                           -> "Numeric(14,3)"
        "SAEnum(CatalogStatus, name='catalog_status')"
            -> "SAEnum(CatalogStatus,name='catalog_status')"

    A parenthetical separated by whitespace is prose and is dropped; a
    parenthetical glued to the identifier is real type arguments and is kept.
    """
    s = (type_str or "").split("·")[0].strip()
    m = re.match(r"^(\w+(?:\.\w+)*)\s+\(", s)
    if m:
        s = m.group(1)
    s = s.replace('"', "'")
    return re.sub(r"\s+", "", s)


def type_family(type_str: str) -> str:
    """'String(32)' -> 'String'. Used to phrase the error, not to pass it."""
    s = normalize_type(type_str)
    return re.split(r"[(\[]", s, maxsplit=1)[0]


def parse_contract_fk(type_str: str) -> Optional[Tuple[str, str]]:
    """Pull ('users.id', 'RESTRICT') out of a contract type string, else None."""
    m = re.search(
        r"ForeignKey\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*ondelete\s*=\s*['\"]([^'\"]+)['\"])?",
        type_str or "",
    )
    if not m:
        return None
    return m.group(1), (m.group(2) or "")


def normalize_default(value: str) -> str:
    """Reduce a default to a comparable token.

    Contract cells:                     Model source:
        "now()"                     <->  server_default=func.now()
        "active (server_default='active')" <-> server_default=text("'active'")
        "True (server_default=true)"   <->  server_default=text("true")
        "0 (server_default='0')"       <->  server_default=text("0")
    """
    s = (value or "").strip()
    if not s:
        return ""
    # drop a trailing prose/annotation parenthetical: "active (server_default='active')"
    m = re.match(r"^(.*?)\s+\(", s)
    if m:
        s = m.group(1).strip()
    s = s.strip("'\"")
    # func.now() / text("now()") / now() all collapse to now()
    s = re.sub(r"^(sa\.)?func\.", "", s)
    m = re.match(r"^text\(\s*(.*?)\s*\)$", s)
    if m:
        s = m.group(1).strip().strip("'\"")
    return s.strip().lower()


# --------------------------------------------------------------------------- #
# Parse generated SQLAlchemy models via AST.
# --------------------------------------------------------------------------- #
class Column:
    """One mapped_column()."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.type: Optional[str] = None       # None = not written explicitly
        self.nullable_kw: Optional[bool] = None
        self.optional_hint: Optional[bool] = None  # from Mapped[T | None]
        self.unique: bool = False
        self.index: bool = False
        self.primary_key: bool = False
        self.has_default: bool = False
        self.default_src: str = ""
        self.fk: Optional[Tuple[str, str]] = None  # (target, ondelete)

    @property
    def effective_nullable(self) -> bool:
        """SQLAlchemy's own precedence: explicit kwarg > PK > Mapped[] hint."""
        if self.nullable_kw is not None:
            return self.nullable_kw
        if self.primary_key:
            return False
        if self.optional_hint is not None:
            return self.optional_hint
        return False


class Model:
    def __init__(self, class_name: str, tablename: str) -> None:
        self.class_name = class_name
        self.tablename = tablename
        self.columns: Dict[str, Column] = {}
        self.relationships: Set[str] = set()
        # names touched by a table-level Index(...) or UniqueConstraint(...)
        self.indexed_by_table_args: Set[str] = set()
        # single-column UniqueConstraint("col") only — composite uniques do NOT
        # make their member columns unique
        self.unique_by_table_args: Set[str] = set()
        # composite ForeignKeyConstraint([...], [...], ondelete=...)
        self.fk_by_table_args: Dict[str, Tuple[str, str]] = {}


def _annotation_is_optional(annotation: Optional[ast.AST]) -> Optional[bool]:
    """Mapped[str | None] -> True, Mapped[str] -> False, anything else -> None."""
    src = _unparse(annotation)
    if not src.startswith("Mapped["):
        return None
    inner = src[len("Mapped[") : -1].strip()
    if re.search(r"\|\s*None\b", inner) or inner.startswith("Optional["):
        return True
    # Mapped["User | None"] — the forward-ref string form
    if re.search(r"\|\s*None", inner):
        return True
    return False


def _parse_mapped_column(col: Column, call: ast.Call) -> None:
    for arg in call.args:
        cname = _call_name(arg)
        if cname == "ForeignKey":
            target = _const_str(arg.args[0]) if arg.args else None
            ondelete = ""
            for kw in arg.keywords:
                if kw.arg == "ondelete":
                    ondelete = _const_str(kw.value) or ""
            if target:
                col.fk = (target, ondelete)
        elif cname in ("ForeignKeyConstraint",):
            continue
        elif col.type is None:
            # first non-FK positional arg is the column type
            src = _unparse(arg)
            if src and not src.startswith(("'", '"')):
                col.type = src
    for kw in call.keywords:
        if kw.arg == "nullable":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
                col.nullable_kw = kw.value.value
        elif kw.arg == "unique":
            col.unique = _is_true(kw.value)
        elif kw.arg == "index":
            col.index = _is_true(kw.value)
        elif kw.arg == "primary_key":
            col.primary_key = _is_true(kw.value)
        elif kw.arg in ("default", "server_default"):
            col.has_default = True
            col.default_src = _unparse(kw.value)


def _parse_table_args(model: Model, value: ast.AST) -> None:
    elts: List[ast.AST] = []
    if isinstance(value, (ast.Tuple, ast.List)):
        elts = list(value.elts)
    elif isinstance(value, ast.Call):
        elts = [value]
    for elt in elts:
        cname = _call_name(elt)
        if cname == "Index":
            # Index("ix_name", "col_a", "col_b", ...) — args[0] is the index name
            for arg in elt.args[1:]:
                model.indexed_by_table_args.update(_index_arg_columns(arg))
        elif cname == "UniqueConstraint":
            cols = [s for s in (_const_str(a) for a in elt.args) if s]
            model.indexed_by_table_args.update(cols)
            if len(cols) == 1:
                model.unique_by_table_args.add(cols[0])
        elif cname == "ForeignKeyConstraint":
            if len(elt.args) >= 2:
                local = [s for s in (_const_str(a) for a in _elts(elt.args[0])) if s]
                remote = [s for s in (_const_str(a) for a in _elts(elt.args[1])) if s]
                ondelete = ""
                for kw in elt.keywords:
                    if kw.arg == "ondelete":
                        ondelete = _const_str(kw.value) or ""
                for lcol, rcol in zip(local, remote):
                    model.fk_by_table_args[lcol] = (rcol, ondelete)
                    model.indexed_by_table_args.add(lcol)


def _elts(node: ast.AST) -> List[ast.AST]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return list(node.elts)
    return []


def _index_arg_columns(node: ast.AST) -> List[str]:
    """Column names named by one positional argument of `Index(...)`.

    Handles both the plain form and the SQL-expression form that carries the
    sort direction, which is how DESC indexes have to be written:

        Index("ix_x", "product_id", text("created_at DESC"), text("id DESC"))
                       ^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^
    """
    s = _const_str(node)
    if s:
        return [s]
    if _call_name(node) == "text":
        raw = _const_str(node.args[0]) if getattr(node, "args", None) else None
        if raw:
            out = []
            for part in raw.split(","):
                m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)", part)
                if m:
                    out.append(m.group(1))
            return out
    return []


class ModelExtractor(ast.NodeVisitor):
    """Collect mapped classes keyed by __tablename__."""

    def __init__(self) -> None:
        self.models: Dict[str, Model] = {}          # tablename -> Model
        self.by_class: Dict[str, Model] = {}        # class name -> Model

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        tablename: Optional[str] = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                tgt = stmt.targets[0]
                if isinstance(tgt, ast.Name) and tgt.id == "__tablename__":
                    tablename = _const_str(stmt.value)
        if not tablename:
            # `class Base(DeclarativeBase)` and abstract mixins land here.
            self.generic_visit(node)
            return

        model = Model(node.name, tablename)
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                tgt = stmt.targets[0]
                if isinstance(tgt, ast.Name) and tgt.id == "__table_args__":
                    _parse_table_args(model, stmt.value)
                    continue
                # `col = mapped_column(...)` — legal, un-annotated form
                if isinstance(tgt, ast.Name) and _call_name(stmt.value) == "mapped_column":
                    col = Column(tgt.id)
                    _parse_mapped_column(col, stmt.value)  # type: ignore[arg-type]
                    model.columns[col.name] = col
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fname = stmt.target.id
                if fname.startswith("__"):
                    continue
                called = _call_name(stmt.value) if stmt.value is not None else ""
                if called == "relationship":
                    model.relationships.add(fname)
                    continue
                ann = _unparse(stmt.annotation)
                if not ann.startswith("Mapped["):
                    continue
                if called and called != "mapped_column":
                    continue
                col = Column(fname)
                col.optional_hint = _annotation_is_optional(stmt.annotation)
                if called == "mapped_column":
                    _parse_mapped_column(col, stmt.value)  # type: ignore[arg-type]
                model.columns[fname] = col

        self.models[tablename] = model
        self.by_class[node.name] = model
        self.generic_visit(node)


def extract_models(paths: List[str]) -> ModelExtractor:
    ex = ModelExtractor()
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            ex.visit(ast.parse(fh.read()))
    return ex


# --------------------------------------------------------------------------- #
# Parse Pydantic v2 schemas (optional).
# --------------------------------------------------------------------------- #
class Schema:
    def __init__(self, name: str) -> None:
        self.name = name
        self.bases: List[str] = []
        self.own_fields: Set[str] = set()
        self.from_attributes: bool = False
        self.contract_table: Optional[str] = None
        self.contract_table_declared: bool = False   # __contract_table__ present
        self.extra_fields: Set[str] = set()


class SchemaExtractor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.schemas: Dict[str, Schema] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # A mapped class is never a schema, even if its name carries a suffix.
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "__tablename__"
            ):
                self.generic_visit(node)
                return

        sch = Schema(node.name)
        sch.bases = [_unparse(b) for b in node.bases]
        looks_pydantic = any(
            "BaseModel" in b or b in self.schemas for b in sch.bases
        )
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(
                stmt.targets[0], ast.Name
            ):
                key = stmt.targets[0].id
                if key == "model_config":
                    looks_pydantic = True
                    for kw in getattr(stmt.value, "keywords", []):
                        if kw.arg == "from_attributes" and _is_true(kw.value):
                            sch.from_attributes = True
                elif key == "__contract_table__":
                    sch.contract_table_declared = True
                    sch.contract_table = _const_str(stmt.value)
                elif key == "__contract_extra_fields__":
                    # set / list / tuple literal of field names
                    for e in getattr(stmt.value, "elts", []):
                        s = _const_str(e)
                        if s:
                            sch.extra_fields.add(s)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fname = stmt.target.id
                if fname.startswith("__") or fname == "model_config":
                    continue
                ann = _unparse(stmt.annotation)
                if ann.startswith("ClassVar"):
                    continue
                sch.own_fields.add(fname)

        if looks_pydantic:
            self.schemas[node.name] = sch
        self.generic_visit(node)


def extract_schemas(paths: List[str]) -> Dict[str, Schema]:
    ex = SchemaExtractor()
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            ex.visit(ast.parse(fh.read()))
    return ex.schemas


def resolve_fields(sch: Schema, all_schemas: Dict[str, Schema]) -> Set[str]:
    """Own fields plus everything inherited from locally-defined base classes."""
    seen: Set[str] = set()
    out: Set[str] = set()

    def walk(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        s = all_schemas.get(name)
        if not s:
            return
        out.update(s.own_fields)
        for b in s.bases:
            walk(b)

    walk(sch.name)
    return out


def resolve_extra_fields(sch: Schema, all_schemas: Dict[str, Schema]) -> Set[str]:
    seen: Set[str] = set()
    out: Set[str] = set()

    def walk(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        s = all_schemas.get(name)
        if not s:
            return
        out.update(s.extra_fields)
        for b in s.bases:
            walk(b)

    walk(sch.name)
    return out


def resolve_from_attributes(sch: Schema, all_schemas: Dict[str, Schema]) -> bool:
    seen: Set[str] = set()

    def walk(name: str) -> bool:
        if name in seen:
            return False
        seen.add(name)
        s = all_schemas.get(name)
        if not s:
            return False
        if s.from_attributes:
            return True
        return any(walk(b) for b in s.bases)

    return walk(sch.name)


def split_suffix(class_name: str) -> Optional[Tuple[str, str]]:
    """'WarehouseCreate' -> ('Warehouse', 'Create'). None if no known suffix."""
    for suf in SCHEMA_SUFFIXES:
        if class_name.endswith(suf) and len(class_name) > len(suf):
            return class_name[: -len(suf)], suf
    return None


def resolve_table(
    sch: Schema, stem: str, models: ModelExtractor, table_names: Set[str]
) -> Optional[str]:
    """Apply the mapping rules documented in the module docstring."""
    # 1. explicit override
    if sch.contract_table_declared:
        return sch.contract_table
    # 2. stripped name -> mapped class -> __tablename__
    model = models.by_class.get(stem)
    if model:
        return model.tablename
    # 3. snake_case + naive plurals against the contract's own table names
    base = _snake(stem)
    for cand in _plural_candidates(base):
        if cand in table_names:
            return cand
    return None


# --------------------------------------------------------------------------- #
# Validation.
# --------------------------------------------------------------------------- #
def validate_models(contract: dict, models: ModelExtractor) -> Tuple[List[str], List[str]]:
    """Returns (errors, notes). Notes never fail the gate."""
    errors: List[str] = []
    notes: List[str] = []

    for table in contract["tables"]:
        tname = table["name"]
        model = models.models.get(tname)
        if not model:
            errors.append(
                f"[table] '{tname}' from the data dictionary has no mapped class "
                f"with __tablename__ = '{tname}'"
            )
            continue

        for attr in table["attributes"]:
            aname = attr["name"]
            col = model.columns.get(aname)
            if col is None:
                if aname in model.relationships:
                    errors.append(
                        f"[attribute] {tname}.{aname} is a column in the dictionary but "
                        f"'{model.class_name}.{aname}' is a relationship(), not a mapped_column()"
                    )
                else:
                    errors.append(
                        f"[attribute] {tname}.{aname} is in the dictionary but missing "
                        f"from class '{model.class_name}'"
                    )
                continue

            be = attr.get("backend", {})

            # --- type ------------------------------------------------------ #
            expected_type = normalize_type(be.get("type", ""))
            if not expected_type:
                pass
            elif col.type is None:
                notes.append(
                    f"{tname}.{aname}: type not written explicitly in mapped_column() — "
                    f"dictionary says '{be.get('type')}'; cannot verify"
                )
            else:
                actual_type = normalize_type(col.type)
                if expected_type != actual_type:
                    if type_family(expected_type) == type_family(actual_type):
                        errors.append(
                            f"[type] {tname}.{aname}: dictionary says '{be.get('type').split('·')[0].strip()}', "
                            f"model has '{col.type}' (same family, different parameters)"
                        )
                    else:
                        errors.append(
                            f"[type] {tname}.{aname}: dictionary says "
                            f"'{be.get('type').split('·')[0].strip()}', model has '{col.type}'"
                        )

            # --- foreign key ------------------------------------------------ #
            expected_fk = parse_contract_fk(be.get("type", ""))
            declared_ondelete = (be.get("on_delete") or "").strip()
            if expected_fk and not declared_ondelete:
                declared_ondelete = expected_fk[1]
            actual_fk = col.fk or model.fk_by_table_args.get(aname)
            if expected_fk and not actual_fk:
                errors.append(
                    f"[fk] {tname}.{aname}: dictionary declares "
                    f"ForeignKey('{expected_fk[0]}'), model has no ForeignKey"
                )
            elif actual_fk and not expected_fk and col.fk is not None:
                # Only column-level ForeignKey(...) is held to the reverse check.
                # A composite ForeignKeyConstraint is ONE constraint spanning
                # several columns, and the dictionary documents it on the
                # driving column alone — the trailing members (e.g. a copied
                # discriminator flag) are legitimately not marked as FKs.
                errors.append(
                    f"[fk] {tname}.{aname}: model declares ForeignKey('{actual_fk[0]}'), "
                    f"the dictionary declares none"
                )
            elif expected_fk and actual_fk:
                if expected_fk[0] != actual_fk[0]:
                    errors.append(
                        f"[fk] {tname}.{aname}: dictionary points at '{expected_fk[0]}', "
                        f"model points at '{actual_fk[0]}'"
                    )
                exp_od = (declared_ondelete or expected_fk[1] or "").upper()
                act_od = (actual_fk[1] or "").upper()
                if exp_od and not act_od:
                    errors.append(
                        f"[fk] {tname}.{aname}: dictionary requires ondelete='{exp_od}', "
                        f"model's ForeignKey has no ondelete"
                    )
                elif exp_od and act_od and exp_od != act_od:
                    errors.append(
                        f"[fk] {tname}.{aname}: dictionary requires ondelete='{exp_od}', "
                        f"model has ondelete='{act_od}'"
                    )

            # --- nullable --------------------------------------------------- #
            expected_nullable = _contract_bool(be.get("nullable", ""))
            if expected_nullable is not None:
                if col.effective_nullable != expected_nullable:
                    how = (
                        f"nullable={col.nullable_kw}"
                        if col.nullable_kw is not None
                        else (
                            "primary_key=True"
                            if col.primary_key
                            else f"inferred from the Mapped[] hint ({col.optional_hint})"
                        )
                    )
                    errors.append(
                        f"[nullable] {tname}.{aname}: dictionary says nullable="
                        f"{expected_nullable}, model is nullable={col.effective_nullable} ({how})"
                    )
            if (
                col.nullable_kw is not None
                and col.optional_hint is not None
                and col.nullable_kw != col.optional_hint
                and not col.primary_key
            ):
                errors.append(
                    f"[nullable] {tname}.{aname}: mapped_column(nullable={col.nullable_kw}) "
                    f"contradicts the Mapped[] type hint (optional={col.optional_hint})"
                )

            # --- unique ----------------------------------------------------- #
            expected_unique = _contract_bool(be.get("unique", "")) or False
            actual_unique = (
                col.unique or col.primary_key or aname in model.unique_by_table_args
            )
            if expected_unique and not actual_unique:
                errors.append(
                    f"[unique] {tname}.{aname}: dictionary requires unique, model has "
                    f"neither unique=True, a primary key, nor a single-column UniqueConstraint"
                )
            elif not expected_unique and col.unique:
                errors.append(
                    f"[unique] {tname}.{aname}: model declares unique=True, the dictionary "
                    f"does not mark it unique"
                )

            # --- index ------------------------------------------------------ #
            # Positive direction only: the dictionary demanding an index must be
            # honoured. The reverse is not checked — composite indexes routinely
            # cover columns the dictionary does not flag individually.
            expected_index = _contract_bool(be.get("db_index", "")) or False
            actual_index = (
                col.index
                or col.primary_key
                or col.unique
                or aname in model.indexed_by_table_args
            )
            if expected_index and not actual_index:
                errors.append(
                    f"[index] {tname}.{aname}: dictionary requires an index "
                    f"('{be.get('db_index')}'), model declares none"
                )

            # --- default ---------------------------------------------------- #
            expected_default = (be.get("default") or "").strip()
            if expected_default and not col.has_default:
                errors.append(
                    f"[default] {tname}.{aname}: dictionary says default "
                    f"'{expected_default}', model declares no default= / server_default="
                )
            elif not expected_default and col.has_default:
                errors.append(
                    f"[default] {tname}.{aname}: model declares a default "
                    f"({col.default_src}), the dictionary declares none"
                )
            elif expected_default and col.has_default:
                exp = normalize_default(expected_default)
                act = normalize_default(col.default_src)
                if exp and act and exp != act:
                    errors.append(
                        f"[default] {tname}.{aname}: dictionary says '{expected_default}', "
                        f"model has {col.default_src}"
                    )

        # --- reverse check: columns absent from the dictionary --------------- #
        dict_names = {a["name"] for a in table["attributes"]}
        for cname in model.columns:
            if cname not in dict_names:
                errors.append(
                    f"[extra] class '{model.class_name}' ({tname}) has column '{cname}' "
                    f"not present in the data dictionary"
                )

    # Mapped classes with no table in the dictionary at all.
    contract_tables = {t["name"] for t in contract["tables"]}
    for tname, model in models.models.items():
        if tname not in contract_tables:
            errors.append(
                f"[extra] class '{model.class_name}' maps table '{tname}', which is not "
                f"in the data dictionary"
            )

    return errors, notes


def validate_schemas(
    contract: dict, models: ModelExtractor, schemas: Dict[str, Schema]
) -> List[str]:
    errors: List[str] = []
    table_names = {t["name"] for t in contract["tables"]}
    by_table = {t["name"]: t for t in contract["tables"]}

    for name, sch in sorted(schemas.items()):
        split = split_suffix(name)
        if not split:
            # Base classes / mixins / anything not a request-response schema.
            continue
        stem, suffix = split
        if sch.contract_table_declared and sch.contract_table is None:
            continue  # explicit opt-out

        tname = resolve_table(sch, stem, models, table_names)
        if not tname:
            errors.append(
                f"[unmatched] schema '{name}': could not map it to a dictionary table "
                f"(no mapped class '{stem}', no table '{_snake(stem)}'/plural). Set "
                f"__contract_table__ = \"<table>\" to bind it, or "
                f"__contract_table__ = None to opt out."
            )
            continue
        if tname not in by_table:
            errors.append(
                f"[unmatched] schema '{name}': __contract_table__ = '{tname}' is not a "
                f"table in the data dictionary"
            )
            continue

        table = by_table[tname]
        flag = SUFFIX_TO_API_FLAG[suffix]
        fields = resolve_fields(sch, schemas)
        extra_ok = resolve_extra_fields(sch, schemas)

        # Analogue of DRF's fields = "__all__": a from_attributes schema that
        # never names a field cannot honour per-field flags.
        if not fields and resolve_from_attributes(sch, schemas):
            errors.append(
                f"[api] schema '{name}' ({tname}) sets "
                f"model_config = ConfigDict(from_attributes=True) but declares no fields — "
                f"it mirrors the whole model and cannot honour the dictionary's "
                f"per-field api.{flag} flags; list the fields explicitly"
            )
            continue

        expected = {a["name"] for a in table["attributes"] if a.get("api", {}).get(flag)}
        for missing in sorted(expected - fields):
            errors.append(
                f"[api] {tname}.{missing}: dictionary marks api.{flag} = true, but it is "
                f"missing from schema '{name}'"
            )
        dict_names = {a["name"] for a in table["attributes"]}
        for got in sorted(fields - expected - extra_ok):
            if got in dict_names:
                errors.append(
                    f"[api] schema '{name}' exposes '{got}', but the dictionary marks "
                    f"{tname}.{got} api.{flag} = false"
                )
            else:
                errors.append(
                    f"[api] schema '{name}' declares field '{got}', which is not an "
                    f"attribute of '{tname}' in the data dictionary (whitelist it via "
                    f"__contract_extra_fields__ if it is a nested or computed field)"
                )

    return errors


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: python contract_validator_sqlalchemy.py contract.json models.py "
            "[schemas.py ...]"
        )
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        contract = json.load(fh)

    # Every source file is scanned for both kinds of class: mapped classes are
    # identified by __tablename__, schemas by BaseModel/model_config. A modular
    # layout (models.py + schemas.py per module) therefore just works — pass
    # them all. The API checks stay opt-in: with no schema class anywhere, there
    # is nothing to check.
    sources = argv[2:]
    models = extract_models(sources)
    errors, notes = validate_models(contract, models)

    schemas = extract_schemas(sources)
    if schemas:
        errors.extend(validate_schemas(contract, models, schemas))

    if notes:
        print(f"NOTES — {len(notes)} thing(s) could not be verified:")
        for n in notes:
            print("  ~", n)
    if errors:
        print(f"CONTRACT MISMATCH — {len(errors)} issue(s):")
        for e in errors:
            print("  -", e)
        return 1
    print("OK: backend code matches the data dictionary contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
