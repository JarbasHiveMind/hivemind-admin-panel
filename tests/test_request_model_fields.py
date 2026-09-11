"""Every field a request model declares is referenced by the handler that takes it.

A model that advertises a field its handler never touches accepts the value, answers
200, and does nothing with it. The caller is told the change was made. This is how
``can_broadcast`` could be denied on a client for as long as it was: the API accepted
the denial and the permission stayed granted.

This is a tripwire, and its name says what it checks. It finds a field the handler has
no line for. It does not establish that a value is applied: a handler that names a
field and then ignores it passes. The stronger claim belongs in each endpoint's own
behavioural tests.

A body field shadowed by a handler parameter of the same name is excluded: it duplicates
a value the route already supplies, so the handler reading its own parameter is reading
that value. ``ACLUpdateRequest.client_id`` is the case in point — the route carries
``client_id`` in the path and the handler uses it from there.

A handler that reaches its fields dynamically, through ``getattr`` on the model, is
skipped rather than guessed at. Substring-matching the field name against the whole
handler body would cover that case and would also let any coincidental string literal
— a dict key, a log message — hide a field nobody references. A tripwire that can be
silenced by an unrelated literal is worse than one with a stated blind spot.
"""
import ast
import pathlib

import hivemind_admin_panel


API = pathlib.Path(hivemind_admin_panel.__file__).parent / "api.py"


def _request_models(tree):
    """Map each pydantic model name to the field names it declares."""
    return {
        node.name: {
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        }
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(getattr(base, "id", None) == "BaseModel" for base in node.bases)
    }


def _reads_dynamically(handler, param):
    """True when the handler pulls attributes off ``param`` by computed name."""
    return any(
        isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "getattr"
        and node.args
        and getattr(node.args[0], "id", None) == param
        for node in ast.walk(handler)
    )


def _referenced(handler, param):
    """Field names reached as ``param.field``."""
    return {
        node.attr for node in ast.walk(handler)
        if isinstance(node, ast.Attribute)
        and getattr(node.value, "id", None) == param
    }


def _handlers_with_unreferenced_fields(tree, models):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for arg in node.args.args:
            model = getattr(arg.annotation, "id", None)
            if model not in models or _reads_dynamically(node, arg.arg):
                continue
            from_route = {a.arg for a in node.args.args}
            missing = sorted(
                models[model] - _referenced(node, arg.arg) - from_route
            )
            if missing:
                yield node.name, model, missing


def test_no_request_model_field_is_declared_and_never_referenced():
    tree = ast.parse(API.read_text())
    models = _request_models(tree)
    assert models, "no pydantic request models found: the check is looking in the wrong place"

    gaps = list(_handlers_with_unreferenced_fields(tree, models))
    assert not gaps, "\n".join(
        f"{handler}({model}) accepts but never references: {', '.join(fields)}"
        for handler, model, fields in gaps
    )
