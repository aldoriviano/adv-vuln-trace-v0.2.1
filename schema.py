"""Response contract checking for the experimental grader.

Uses `jsonschema` when it is installed; otherwise validates the subset of
draft 2020-12 that `schemas/response.schema.json` actually relies on
(type, required, properties, items, additionalProperties, enum, minimum,
maximum). Either path returns a list of dotted-path error strings.
"""
import json
from pathlib import Path

_OPS = {"type", "required", "properties", "items", "additionalProperties", "enum",
        "minimum", "maximum", "minLength", "title", "$schema", "description"}

_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}


def load_schema(path):
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def _validate(value, schema, path, errors):
    for key in schema:
        if key not in _OPS:
            errors.append(f"{path}: unsupported schema keyword '{key}' (validator gap)")
    stype = schema.get("type")
    if stype:
        wanted = tuple(_TYPES[t] for t in ([stype] if isinstance(stype, str) else stype))
        # bool is an int subclass in Python; keep the two types distinct.
        if isinstance(value, bool) and bool not in wanted:
            errors.append(f"{path}: expected type {stype}, got boolean")
            return
        if not isinstance(value, wanted):
            errors.append(f"{path}: expected type {stype}, got {type(value).__name__}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        errors.append(f"{path}: string is shorter than minLength {schema['minLength']}")
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")
        props = schema.get("properties", {})
        extra = [k for k in value if k not in props]
        if extra and schema.get("additionalProperties") is False:
            errors.append(f"{path}: unexpected field(s) {sorted(extra)}")
        for key, sub in props.items():
            if key in value:
                _validate(value[key], sub, f"{path}.{key}", errors)
    elif isinstance(value, list):
        sub = schema.get("items")
        if isinstance(sub, dict):
            for i, item in enumerate(value):
                _validate(item, sub, f"{path}[{i}]", errors)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is above maximum {schema['maximum']}")


def validate(value, schema):
    """Return a list of human-readable contract violations (empty means valid)."""
    try:
        import jsonschema
    except ImportError:
        errors = []
        _validate(value, schema, "$", errors)
        return errors
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'$' if not e.absolute_path else '.'.join(str(p) for p in e.absolute_path)}: {e.message}"
        for e in sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))
    ]
