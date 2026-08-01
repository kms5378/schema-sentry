import re
from dataclasses import dataclass

from schema_sentry.domain.enums import Severity
from schema_sentry.domain.models import CanonicalType

_TYPE_PATTERN = re.compile(r"^([^()]+?)(?:\(([^()]*)\))?$")
_ALIASES = {
    "bool": "boolean",
    "decimal": "numeric",
    "float8": "double precision",
    "int2": "smallint",
    "int4": "integer",
    "int8": "bigint",
    "timestamp": "timestamp without time zone",
    "timestamptz": "timestamp with time zone",
    "varchar": "character varying",
}
_INTEGER_RANK = {"smallint": 0, "integer": 1, "bigint": 2}


@dataclass(frozen=True, slots=True)
class TypeChangeAssessment:
    severity: Severity
    reason: str


def _normalize_name(name: str) -> str:
    normalized = " ".join(name.strip().lower().split())
    return _ALIASES.get(normalized, normalized)


def parse_postgres_type(type_spec: str) -> CanonicalType:
    match = _TYPE_PATTERN.fullmatch(type_spec.strip().lower())
    if match is None:
        raise ValueError(f"invalid PostgreSQL type: {type_spec}")

    name = _normalize_name(match.group(1))
    arguments = match.group(2)
    if arguments is None:
        return CanonicalType(name=name)

    values = tuple(int(value.strip()) for value in arguments.split(","))
    if name in {"character", "character varying", "bit", "bit varying"} and len(values) == 1:
        return CanonicalType(name=name, length=values[0])
    if name == "numeric" and len(values) == 2:
        return CanonicalType(name=name, precision=values[0], scale=values[1])
    if name == "numeric" and len(values) == 1:
        return CanonicalType(name=name, precision=values[0])
    raise ValueError(f"unsupported PostgreSQL type modifiers: {type_spec}")


def canonicalize_postgres_type(
    data_type: str,
    udt_name: str,
    character_maximum_length: int | None,
    numeric_precision: int | None,
    numeric_scale: int | None,
) -> CanonicalType:
    name = _normalize_name(data_type if data_type != "USER-DEFINED" else udt_name)
    if name in {"character", "character varying", "bit", "bit varying"}:
        return CanonicalType(name=name, length=character_maximum_length)
    if name == "numeric":
        return CanonicalType(name=name, precision=numeric_precision, scale=numeric_scale)
    return CanonicalType(name=name)


def classify_type_change(before: CanonicalType, after: CanonicalType) -> TypeChangeAssessment:
    if before == after:
        return TypeChangeAssessment(Severity.INFO, "unchanged")

    if before.name in _INTEGER_RANK and after.name in _INTEGER_RANK:
        if _INTEGER_RANK[after.name] > _INTEGER_RANK[before.name]:
            return TypeChangeAssessment(Severity.WARNING, "integer widened")
        return TypeChangeAssessment(Severity.BREAKING, "integer narrowed")

    if before.name == after.name == "character varying":
        if after.length is None or (before.length is not None and after.length >= before.length):
            return TypeChangeAssessment(Severity.WARNING, "character capacity widened")
        return TypeChangeAssessment(Severity.BREAKING, "character capacity narrowed")

    if before.name == "character varying" and after.name == "text":
        return TypeChangeAssessment(Severity.WARNING, "character capacity widened")
    if before.name == "text" and after.name == "character varying":
        return TypeChangeAssessment(Severity.BREAKING, "character capacity constrained")

    if before.name == after.name == "numeric":
        if after.precision is None:
            return TypeChangeAssessment(Severity.WARNING, "numeric constraint removed")
        if before.precision is None:
            return TypeChangeAssessment(Severity.BREAKING, "numeric constraint added")
        same_scale = before.scale == after.scale
        wider_precision = (
            after.precision >= before.precision
        )
        if same_scale and wider_precision:
            return TypeChangeAssessment(Severity.WARNING, "numeric precision widened")
        return TypeChangeAssessment(Severity.BREAKING, "numeric precision or scale narrowed")

    return TypeChangeAssessment(Severity.BREAKING, "incompatible type families")
