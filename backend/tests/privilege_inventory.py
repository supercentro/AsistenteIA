"""Mechanical inventory of the database privileges that the application code needs.

Change `database-least-privilege`, task 2.2. The inventory reads the source of `app/` with the
`ast` module, follows the call graph from the entry points of each actor (API, worker, CLI) and
lists, per actor and table, the privileges and columns that the statements need:

* SQLAlchemy ORM and Core: `select`, `insert`, `update`, `delete`, `session.get`, constructors of
  mapped classes (an `INSERT`), attribute assignments on mapped objects (an `UPDATE`), column
  attributes used in `WHERE`/`ORDER BY`/`RETURNING`, `with_for_update`.
* Raw `text()` statements: parsed for tables, aliases, columns, `SET` targets, `INSERT` columns,
  `RETURNING` and `FOR UPDATE`.

Everything is derived from the code; nothing is typed in by hand except the SQLAlchemy
behaviours listed in `ASSUMPTIONS`, which task 5.4 proves against a live database. Calls that
cannot be resolved to a function of the application and that share a name with one that reaches a
statement are reported in `Inventory.unresolved`; the tests require that list to be empty.
"""

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Column

import app.models  # noqa: F401  (registers every mapped class)
from app.core.database import Base

APP_DIR = Path(__file__).resolve().parents[1] / "app"

ASSUMPTIONS = (
    "ORM INSERT lists the columns passed to the constructor AND every other column that has no "
    "server default and is not a `FetchedValue()`, as NULL (proved against PostgreSQL in group 5, "
    "task 5.4: the first version of this assumption, 'only the columns passed', was refuted; and "
    "in group 8A for `FetchedValue()`, which keeps a column out of the INSERT), and returns the "
    "primary key and the server-generated columns (SELECT on them), unless the mapper sets "
    "`eager_defaults=False`, which returns only the primary key.",
    "A Core insert(Model) executed with a list of rows may return the primary key "
    "(INSERT ... RETURNING pk), observed in the spike (H4); it needs SELECT on the key.",
    "An ORM attribute assignment flushes UPDATE <t> SET <attrs> WHERE <pk> (SELECT on the key).",
    "SELECT ... FOR UPDATE needs the UPDATE privilege on at least one column of the locked table.",
    "session.get(Model, id) and select(Model) read every mapped column.",
)

ACTORS = ("api", "worker", "cli")
ENTRY_MODULES = {"api": "app.api", "worker": "app.worker", "cli": "app.cli"}

TABLES: dict[str, list[str]] = {
    name: [column.name for column in table.columns] for name, table in Base.metadata.tables.items()
}
MODEL_BY_CLASS: dict[str, str] = {
    mapper.class_.__name__: str(mapper.class_.__tablename__) for mapper in Base.registry.mappers
}
_SERVER_GENERATED: dict[str, set[str]] = {}
_PRIMARY_KEY: dict[str, str] = {}
for _name, _table in Base.metadata.tables.items():
    _SERVER_GENERATED[_name] = {
        column.name
        for column in _table.columns
        if isinstance(column, Column) and column.server_default is not None
    }
    _PRIMARY_KEY[_name] = _table.primary_key.columns.values()[0].name

# Columns the INSERT ... RETURNING asks for: the key and the server-generated columns, or only the
# key when the mapper does not fetch defaults eagerly.
_EAGER_FALSE = {
    str(mapper.class_.__tablename__)
    for mapper in Base.registry.mappers
    if mapper.eager_defaults is False
}
_RETURNED: dict[str, set[str]] = {
    name: {_PRIMARY_KEY[name]} | (set() if name in _EAGER_FALSE else _SERVER_GENERATED[name])
    for name in Base.metadata.tables
}

_SQL_KEYWORDS = {
    "where", "set", "join", "on", "left", "right", "inner", "order", "for", "limit", "using",
    "select", "group", "returning", "from", "values", "and", "or", "as", "union", "offset",
}  # fmt: skip


@dataclass(frozen=True)
class Need:
    """One privilege one actor needs on one table, with the place of the statement."""

    actor: str
    table: str
    kind: str  # SELECT, INSERT, UPDATE, DELETE, LOCK
    columns: frozenset[str]
    source: str  # "path:line function"
    origin: str  # orm, core, sql


@dataclass
class Inventory:
    needs: list[Need] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    statements: dict[str, int] = field(default_factory=dict)
    reachable: dict[str, set[str]] = field(default_factory=dict)
    unreached: list[str] = field(default_factory=list)  # functions with statements, no actor

    def required(self, actor: str) -> dict[str, dict[str, frozenset[str]]]:
        """Per table: the columns needed for SELECT, INSERT, UPDATE; DELETE and LOCK as markers."""
        merged: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for need in self.needs:
            if need.actor == actor:
                merged[need.table][need.kind] |= need.columns
        return {
            table: {kind: frozenset(columns) for kind, columns in kinds.items()}
            for table, kinds in merged.items()
        }


@dataclass(frozen=True)
class _Func:
    module: str
    qualname: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    cls: str | None
    path: str

    @property
    def key(self) -> str:
        return f"{self.module}:{self.qualname}"


def _module_name(path: Path) -> str:
    relative = path.relative_to(APP_DIR.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _annotation_class(node: ast.expr | None) -> str | None:
    """The class named by an annotation: unwraps Annotated[T, ...], T | None, 'T'."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return _annotation_class(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        inner = node.slice
        if isinstance(inner, ast.Tuple) and inner.elts:
            return _annotation_class(inner.elts[0])
        return _annotation_class(inner)
    if isinstance(node, ast.BinOp):
        left = _annotation_class(node.left)
        return left if left not in (None, "None") else _annotation_class(node.right)
    return None


class _Project:
    def __init__(self) -> None:
        self.funcs: dict[str, _Func] = {}
        self.classes: dict[str, str] = {}  # class name -> module
        self.methods: dict[str, dict[str, _Func]] = defaultdict(dict)  # class -> name -> func
        self.module_funcs: dict[str, dict[str, _Func]] = defaultdict(dict)
        self.constants: dict[str, dict[str, str]] = defaultdict(dict)  # module -> name -> str
        self.imports: dict[str, dict[str, str]] = defaultdict(dict)  # module -> name -> module
        self.attr_types: dict[str, dict[str, str]] = defaultdict(dict)  # class -> attr -> class
        self.aliases: dict[str, dict[str, str]] = defaultdict(dict)  # module -> alias -> T
        self.protocols: set[str] = set()
        for path in sorted(APP_DIR.rglob("*.py")):
            self._load(path)
        for func in self.funcs.values():
            if func.cls and func.qualname.endswith(".__init__"):
                self._collect_attr_types(func)

    def _load(self, path: Path) -> None:
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        shown = path.relative_to(APP_DIR.parent.parent).as_posix()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    self.imports[module][alias.asname or alias.name] = node.module
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.constants[module][target.id] = node.value.value
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Subscript):
                aliased = _annotation_class(node.value)
                for target in node.targets:
                    if isinstance(target, ast.Name) and aliased:
                        self.aliases[module][target.id] = aliased
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = module
                if any(isinstance(b, ast.Name) and b.id == "Protocol" for b in node.bases):
                    self.protocols.add(node.name)
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                        func = _Func(module, f"{node.name}.{item.name}", item, node.name, shown)
                        self.funcs[func.key] = func
                        self.methods[node.name][item.name] = func
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                func = _Func(module, node.name, node, None, shown)
                self.funcs[func.key] = func
                self.module_funcs[module][node.name] = func

    def _collect_attr_types(self, init: _Func) -> None:
        assert init.cls is not None
        params = {
            arg.arg: self.norm(init.module, _annotation_class(arg.annotation))
            for arg in init.node.args.args
        }
        for stmt in ast.walk(init.node):
            if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
                continue
            target = stmt.targets[0]
            if not (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                continue
            value = stmt.value
            if isinstance(value, ast.Name) and params.get(value.id):
                self.attr_types[init.cls][target.attr] = str(params[value.id])
            elif (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in self.classes
            ):
                self.attr_types[init.cls][target.attr] = value.func.id

    def norm(self, module: str, cls: str | None) -> str | None:
        return self.aliases[module].get(cls, cls) if cls else None

    def implementations(self, owner: str, method: str) -> list[_Func]:
        """The method on `owner`, or on every concrete class if `owner` is a Protocol."""
        if owner in self.protocols:
            return [
                methods[method]
                for cls, methods in self.methods.items()
                if method in methods and cls not in self.protocols
            ]
        found = self.methods.get(owner, {}).get(method)
        return [found] if found else []

    def resolve_function(self, module: str, name: str) -> _Func | None:
        if name in self.module_funcs[module]:
            return self.module_funcs[module][name]
        source = self.imports[module].get(name)
        if source and name in self.module_funcs[source]:
            return self.module_funcs[source][name]
        return None


class _Walker:
    """Collects the statements and the calls of one function."""

    def __init__(self, project: _Project, func: _Func) -> None:
        self.project = project
        self.func = func
        self.locals: dict[str, str] = {}
        for arg in func.node.args.args + func.node.args.kwonlyargs:
            cls = project.norm(func.module, _annotation_class(arg.annotation))
            if cls:
                self.locals[arg.arg] = cls
        if func.cls:
            self.locals["self"] = func.cls
        self.callees: list[_Func] = []
        self.unresolved: set[str] = set()
        self.needs: list[tuple[str, frozenset[str], int, str]] = []  # kind/table/columns/line

    # ---- type of an expression -------------------------------------------------------------
    def type_of(self, expr: ast.expr) -> str | None:
        if isinstance(expr, ast.Name):
            return self.locals.get(expr.id)
        if isinstance(expr, ast.Attribute):
            owner = self.type_of(expr.value)
            if owner:
                return self.project.attr_types.get(owner, {}).get(expr.attr)
            return None
        if isinstance(expr, ast.Call):
            func = expr.func
            if isinstance(func, ast.Name) and func.id in self.project.classes:
                return func.id
            target = self._resolve(expr)
            if target and isinstance(target.node.returns, ast.expr):
                return self.project.norm(target.module, _annotation_class(target.node.returns))
        return None

    def _resolve(self, call: ast.Call) -> _Func | None:
        found = self._resolve_all(call)
        return found[0] if found else None

    def _resolve_all(self, call: ast.Call) -> list[_Func]:
        func = call.func
        if isinstance(func, ast.Name):
            if func.id in self.project.classes:
                init = self.project.methods[func.id].get("__init__")
                return [init] if init else []
            target = self.project.resolve_function(self.func.module, func.id)
            return [target] if target else []
        if isinstance(func, ast.Attribute):
            owner = self.type_of(func.value)
            if owner:
                return self.project.implementations(owner, func.attr)
        return []

    # ---- statements -------------------------------------------------------------------------
    def walk(self) -> None:
        body = ast.Module(body=list(self.func.node.body), type_ignores=[])
        for node in ast.walk(body):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
                if isinstance(target, ast.Name):
                    kind = self.type_of(value)
                    if kind:
                        self.locals[target.id] = kind
                if isinstance(target, ast.Attribute):
                    self._attribute_assignment(target, node.lineno)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                kind = self.project.norm(self.func.module, _annotation_class(node.annotation))
                if kind:
                    self.locals[node.target.id] = kind
        for node in ast.walk(body):
            if isinstance(node, ast.Call):
                self._call(node)
            elif isinstance(node, ast.Attribute):
                self._model_attribute(node)
                self._method_reference(node)

    def _method_reference(self, node: ast.Attribute) -> None:
        """`self._service.sweep` passed as a callback is a call edge too."""
        owner = self.type_of(node.value)
        if owner:
            self.callees.extend(self.project.implementations(owner, node.attr))

    def _add(self, kind: str, table: str, columns: set[str] | frozenset[str], line: int) -> None:
        self.needs.append((f"{kind}|{table}", frozenset(columns), line, "orm"))

    def _model_attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in MODEL_BY_CLASS:
            table = MODEL_BY_CLASS[node.value.id]
            if node.attr in TABLES[table]:
                self._add("SELECT", table, {node.attr}, node.lineno)

    def _attribute_assignment(self, target: ast.Attribute, line: int) -> None:
        owner = self.type_of(target.value)
        if owner in MODEL_BY_CLASS:
            table = MODEL_BY_CLASS[owner]
            if target.attr in TABLES[table]:
                self._add("UPDATE", table, {target.attr}, line)
                self._add("SELECT", table, {_PRIMARY_KEY[table]}, line)

    def _entity(self, expr: ast.expr) -> str | None:
        if isinstance(expr, ast.Name) and expr.id in MODEL_BY_CLASS:
            return MODEL_BY_CLASS[expr.id]
        if (
            isinstance(expr, ast.Attribute)
            and isinstance(expr.value, ast.Name)
            and expr.value.id in MODEL_BY_CLASS
        ):
            return MODEL_BY_CLASS[expr.value.id]
        return None

    def _call(self, call: ast.Call) -> None:
        func = call.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        line = call.lineno
        targets = self._resolve_all(call)
        self.callees.extend(targets)
        if not targets and isinstance(func, ast.Attribute) and not self._known_external(func):
            self.unresolved.add(func.attr)
        if isinstance(func, ast.Name) and func.id in MODEL_BY_CLASS:
            self._construct(func.id, call)
        if name == "select":
            for arg in call.args:
                table = self._entity(arg)
                if table and isinstance(arg, ast.Name):
                    self._add("SELECT", table, set(TABLES[table]), line)
        elif name == "insert" and call.args:
            self._core_insert(call)
        elif name == "update" and call.args and self._entity(call.args[0]):
            table = str(self._entity(call.args[0]))
            self._add("UPDATE", table, self._values_keys(call, table), line)
        elif name == "delete" and call.args and self._entity(call.args[0]):
            self._add("DELETE", str(self._entity(call.args[0])), set(), line)
        elif name == "get" and len(call.args) == 2 and self._entity(call.args[0]):
            table = str(self._entity(call.args[0]))
            self._add("SELECT", table, set(TABLES[table]), line)
        elif name == "returning":
            for arg in call.args:
                table = self._entity(arg)
                if table and isinstance(arg, ast.Name):
                    self._add("SELECT", table, set(TABLES[table]), line)
        elif name == "with_for_update":
            for table in self._chain_tables(func):
                self._add("LOCK", table, set(), line)
        elif name == "text" and call.args:
            self._sql(call)

    def _known_external(self, func: ast.Attribute) -> bool:
        """Calls on values that are not application objects (stdlib, SQLAlchemy, str, ...)."""
        defined = {n for methods in self.project.methods.values() for n in methods}
        if func.attr not in defined:
            return True
        owner = self.type_of(func.value)
        return owner is not None and owner not in self.project.classes

    def _construct(self, cls: str, call: ast.Call) -> None:
        table = MODEL_BY_CLASS[cls]
        columns = {kw.arg for kw in call.keywords if kw.arg}
        columns |= (
            set(TABLES[table]) - _SERVER_GENERATED[table]
        )  # unset nullable columns go as NULL
        self._add("INSERT", table, columns, call.lineno)
        self._add("SELECT", table, _RETURNED[table], call.lineno)

    def _core_insert(self, call: ast.Call) -> None:
        table = self._entity(call.args[0])
        if not table:
            return
        keys: set[str] = set()
        for node in ast.walk(ast.Module(body=list(self.func.node.body), type_ignores=[])):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and key.value in TABLES[table]:
                        keys.add(str(key.value))
        keys |= self._values_keys(call, table)
        for node in ast.walk(ast.Module(body=list(self.func.node.body), type_ignores=[])):
            if not (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", "") == "from_select"
                and node.args
                and isinstance(node.args[0], ast.List)
            ):
                continue
            keys |= {
                str(e.value)
                for e in node.args[0].elts
                if isinstance(e, ast.Constant) and e.value in TABLES[table]
            }
        self._add("INSERT", table, keys, call.lineno)
        self._add("SELECT", table, {_PRIMARY_KEY[table]}, call.lineno)

    def _values_keys(self, call: ast.Call, table: str) -> set[str]:
        keys: set[str] = set()
        node: ast.expr = call
        # Search the chain that contains this call for .values(...)
        for parent in ast.walk(ast.Module(body=list(self.func.node.body), type_ignores=[])):
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Attribute)
                and parent.func.attr == "values"
                and node is not parent
            ):
                keys |= {kw.arg for kw in parent.keywords if kw.arg in TABLES[table] if kw.arg}
        return keys

    def _chain_tables(self, func: ast.expr) -> set[str]:
        tables: set[str] = set()
        node = func
        while isinstance(node, ast.Attribute | ast.Call):
            if isinstance(node, ast.Call):
                for arg in node.args:
                    for sub in ast.walk(arg):
                        table = self._entity(sub) if isinstance(sub, ast.expr) else None
                        if table:
                            tables.add(table)
                node = node.func
            else:
                node = node.value
        return tables

    # ---- raw SQL ----------------------------------------------------------------------------
    def _fragments(self, node: ast.expr) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            parts = [""]
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts = [p + str(value.value) for p in parts]
                elif isinstance(value, ast.FormattedValue):
                    options = self._fragments(value.value)
                    parts = [p + o for p in parts for o in options]
            return parts
        if isinstance(node, ast.Name):
            module = self.func.module
            if node.id in self.project.constants[module]:
                return [self.project.constants[module][node.id]]
            imported = self.project.imports[module].get(node.id)
            if imported and node.id in self.project.constants[imported]:
                return [self.project.constants[imported][node.id]]
            return self._parameter_values(node.id)
        return [""]

    def _parameter_values(self, name: str) -> list[str]:
        """Literal arguments given for a string parameter at the call sites in the project."""
        position = [a.arg for a in self.func.node.args.args].index(name) - 1
        values: list[str] = []
        for other in self.project.funcs.values():
            for call in ast.walk(other.node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                    continue
                if call.func.attr != self.func.node.name:
                    continue
                if 0 <= position < len(call.args):
                    values.extend(self._fragments_in(call.args[position], other))
        return values or [""]

    def _fragments_in(self, node: ast.expr, owner: _Func) -> list[str]:
        saved = self.func
        self.func = owner
        try:
            return self._fragments(node)
        finally:
            self.func = saved

    def _sql(self, call: ast.Call) -> None:
        for statement in self._fragments(call.args[0]):
            for kind, table, columns in analyse_sql(statement):
                self.needs.append((f"{kind}|{table}", frozenset(columns), call.lineno, "sql"))


# ---- SQL analysis ---------------------------------------------------------------------------

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def _normalise(sql: str) -> str:
    text = re.sub(r"'(?:[^']|'')*'", "''", sql)
    text = re.sub(r":" + _IDENT, "?", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth, current = 0, ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _tables_and_aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    pattern = rf"\b(?:FROM|JOIN|UPDATE|INTO)\s+({_IDENT})(?:\s+(?:AS\s+)?({_IDENT}))?"
    for match in re.finditer(pattern, sql, re.IGNORECASE):
        table, alias = match.group(1), match.group(2)
        if table not in TABLES:
            continue
        aliases[table] = table
        if alias and alias.lower() not in _SQL_KEYWORDS and alias.upper() != "SET":
            aliases[alias] = table
    return aliases


def analyse_sql(statement: str) -> list[tuple[str, str, set[str]]]:
    """(kind, table, columns) for one raw statement; kinds: SELECT, INSERT, UPDATE, DELETE, LOCK."""
    sql = _normalise(statement)
    aliases = _tables_and_aliases(sql)
    if not aliases:
        return []
    found: dict[tuple[str, str], set[str]] = defaultdict(set)
    tables = set(aliases.values())

    # Names that are SET targets or INSERT columns are written, not read.
    written: dict[str, set[str]] = defaultdict(set)
    update = re.search(rf"(?<!FOR )\bUPDATE\s+({_IDENT})", sql)
    if update and update.group(1) in TABLES:
        target = update.group(1)
        rest = sql[update.end() :]
        set_match = re.search(r"\bSET\b(.*?)(?=\bWHERE\b|\bFROM\b|\bRETURNING\b|$)", rest)
        if set_match:
            for item in _split_top_level(set_match.group(1)):
                left = item.split("=", 1)[0].strip()
                if re.fullmatch(_IDENT, left) and left in TABLES[target]:
                    written[target].add(left)
                    found[("UPDATE", target)].add(left)
    insert = re.search(rf"\bINSERT\s+INTO\s+({_IDENT})\s*\(([^)]*)\)", sql, re.IGNORECASE)
    if insert and insert.group(1) in TABLES:
        cols = {c.strip() for c in insert.group(2).split(",")}
        found[("INSERT", insert.group(1))] |= cols
        written[insert.group(1)] |= cols
    delete = re.search(rf"\bDELETE\s+FROM\s+({_IDENT})", sql, re.IGNORECASE)
    if delete and delete.group(1) in TABLES:
        found[("DELETE", delete.group(1))] = set()

    # Reads: qualified references, and unqualified ones when the statement has one table.
    for match in re.finditer(rf"\b({_IDENT})\.({_IDENT})\b", sql):
        owner, column = match.groups()
        table_name = aliases.get(owner)
        if table_name and column in TABLES[table_name]:
            found[("SELECT", table_name)].add(column)
    if len(tables) == 1:
        only = next(iter(tables))
        without_set_targets = sql
        for column in written[only]:
            without_set_targets = re.sub(rf"\b{column}\s*=", "", without_set_targets, count=1)
        insert_cols = re.sub(r"\bINSERT\s+INTO\s+\w+\s*\([^)]*\)", "", without_set_targets)
        for token in re.findall(rf"(?<![.\w])({_IDENT})(?![\w(])", insert_cols):
            if token in TABLES[only] and token.lower() not in _SQL_KEYWORDS:
                found[("SELECT", only)].add(token)

    for lock in re.finditer(rf"\bFOR UPDATE(?: OF ({_IDENT}(?:, {_IDENT})*))?", sql):
        names = [n.strip() for n in lock.group(1).split(",")] if lock.group(1) else list(aliases)
        for name in names:
            if name in aliases:
                found[("LOCK", aliases[name])] = set()
    return [(kind, table, columns) for (kind, table), columns in sorted(found.items())]


# ---- inventory ------------------------------------------------------------------------------


def build_inventory(extra_roots: dict[str, list[str]] | None = None) -> Inventory:
    """Needs per actor; `extra_roots` adds actors defined by explicit function keys."""
    project = _Project()
    walkers = {key: _Walker(project, func) for key, func in project.funcs.items()}
    for walker in walkers.values():
        walker.walk()
    with_statements = {key for key, walker in walkers.items() if walker.needs}
    inventory = Inventory()
    actors = {
        a: [k for k, f in project.funcs.items() if f.module.startswith(p)]
        for a, p in ENTRY_MODULES.items()
    }
    actors.update(extra_roots or {})
    for actor, roots in actors.items():
        for root in roots:
            assert root in project.funcs, f"unknown root {root}"
        seen: set[str] = set()
        queue = list(roots)
        while queue:
            key = queue.pop()
            if key in seen:
                continue
            seen.add(key)
            queue.extend(callee.key for callee in walkers[key].callees)
        inventory.reachable[actor] = seen
        for key in sorted(seen):
            walker = walkers[key]
            for tag, columns, line, origin in walker.needs:
                kind, table = tag.split("|")
                where = f"{project.funcs[key].path}:{line} {project.funcs[key].qualname}"
                inventory.needs.append(Need(actor, table, kind, columns, where, origin))
            for name in sorted(walker.unresolved):
                if any(name == f.node.name for k in with_statements for f in [project.funcs[k]]):
                    inventory.unresolved.append(f"{actor}: {project.funcs[key].path} -> .{name}()")
    every_actor = set().union(*inventory.reachable.values())
    inventory.unreached = sorted(with_statements - every_actor)
    inventory.statements = {
        actor: len({n.source for n in inventory.needs if n.actor == actor}) for actor in actors
    }
    return inventory


def render(inventory: Inventory) -> str:
    """Human-readable report: per actor and table, the columns needed and where they come from."""
    lines = ["# Privilege inventory (machine-derived from app/)", ""]
    lines += ["Assumptions proved later against a live database (task 5.4):"]
    lines += [f"- {text}" for text in ASSUMPTIONS] + [""]
    for actor in inventory.statements:
        lines.append(f"## {actor}")
        required = inventory.required(actor)
        for table in sorted(required):
            for kind in ("SELECT", "INSERT", "UPDATE", "DELETE", "LOCK"):
                if kind in required[table]:
                    columns = sorted(required[table][kind])
                    shown = "(" + ", ".join(columns) + ")" if columns else ""
                    lines.append(f"- {table}: {kind} {shown}".rstrip())
        lines.append("")
        lines.append(f"Sources ({actor}):")
        seen: set[tuple[str, str, str]] = set()
        for need in inventory.needs:
            row = (need.table, need.kind, need.source)
            if need.actor == actor and row not in seen:
                seen.add(row)
                cols = ",".join(sorted(need.columns)) if need.columns else "-"
                lines.append(f"  {need.source} [{need.origin}] {need.kind} {need.table} {cols}")
        lines.append("")
    lines.append("Unresolved calls: " + (", ".join(inventory.unresolved) or "none"))
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(build_inventory()))
