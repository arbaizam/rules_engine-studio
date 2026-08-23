"""One-line text form for operands, used where a full form would not fit.

Function arguments can nest arbitrarily, and a nested form inside a nested form
is unreadable in a Streamlit column, so arguments are typed one per line:

    field:job_family        a column
    str:Engineering         a string literal
    int:5                   an integer literal
    num:0.8                 a float literal
    bool:true               a boolean literal
    list:a,b,c              a list literal
    null                    a null literal
    fn:upper(field:region)  a nested call; separate its arguments with |

Anything without a recognised prefix is read as a string literal, so
``Engineering`` and ``str:Engineering`` mean the same thing.
"""

from __future__ import annotations

from .schema import Operand

_PREFIXES = {
    "str": "string",
    "int": "integer",
    "num": "number",
    "bool": "boolean",
    "date": "date",
    "list": "list",
}


def parse_operand_text(text: str) -> Operand:
    raw = (text or "").strip()
    if not raw or raw == "null":
        return Operand(kind="literal", value=None, value_type="null")

    if raw.startswith("field:"):
        return Operand(kind="field", field_name=raw[6:].strip())

    if raw.startswith("fn:"):
        body = raw[3:].strip()
        if "(" not in body or not body.endswith(")"):
            raise ValueError(f"Function argument needs parentheses: {raw}")
        name, _, inner = body.partition("(")
        inner = inner[:-1]
        args = [parse_operand_text(part) for part in split_top_level(inner)] if inner.strip() else []
        return Operand(kind="function", function=name.strip(), args=args)

    prefix, sep, rest = raw.partition(":")
    if sep and prefix in _PREFIXES:
        value_type = _PREFIXES[prefix]
        rest = rest.strip()
        if value_type == "list":
            value: object = [p.strip() for p in rest.split(",") if p.strip()]
        elif value_type == "integer":
            value = int(rest)
        elif value_type == "number":
            value = float(rest)
        elif value_type == "boolean":
            value = rest.lower() in ("true", "1", "yes", "y")
        else:
            value = rest
        return Operand(kind="literal", value=value, value_type=value_type)

    return Operand(kind="literal", value=raw, value_type="string")


def format_operand_text(operand: Operand) -> str:
    if operand.kind == "field":
        return f"field:{operand.field_name}"
    if operand.kind == "function":
        inner = "|".join(format_operand_text(a) for a in operand.args)
        return f"fn:{operand.function}({inner})"
    if operand.value_type == "null" or operand.value is None:
        return "null"
    if operand.value_type == "list":
        items = operand.value if isinstance(operand.value, (list, tuple)) else [operand.value]
        return "list:" + ",".join(str(i) for i in items)
    prefix = {v: k for k, v in _PREFIXES.items()}.get(operand.value_type, "str")
    if operand.value_type == "boolean":
        return f"bool:{str(bool(operand.value)).lower()}"
    return f"{prefix}:{operand.value}"


def split_top_level(text: str, separator: str = "|") -> list[str]:
    """Split on ``separator`` while ignoring separators inside parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced parentheses in function arguments.")
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if depth != 0:
        raise ValueError("Unbalanced parentheses in function arguments.")
    parts.append("".join(current))
    return [p for p in parts if p.strip()]


def parse_arg_lines(text: str) -> list[Operand]:
    return [parse_operand_text(line) for line in (text or "").splitlines() if line.strip()]


def format_arg_lines(args: list[Operand]) -> str:
    return "\n".join(format_operand_text(a) for a in args)
