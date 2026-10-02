"""Offline schema loader and Python structural adapter.

Each bundle root and manifest snapshot gets its own ``referencing.Registry``.
The registry never retrieves a resource that the bundle manifest does not
list. Setup checks every bundle schema against the Draft 7 metaschema, then
audits every reachable schema before any validation: each ``$ref`` must resolve
inside the bundle, each regular expression must be in the audited
translation table, ``multipleOf`` is refused, and ``format`` must be
``date-time``. Validation uses an extended Draft 7 validator with an
exact-number type checker and the contract date-time grammar.
"""

import calendar
import functools
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import attrs
import referencing
import referencing.exceptions
from jsonschema import Draft7Validator, FormatChecker, validators
from jsonschema.exceptions import ValidationError
from referencing.jsonschema import DRAFT7

from tests.conformance.bundle import BundleManifest, load_bundle_manifest, parse_bundle_manifest, read_manifest_bytes
from tests.conformance.strict_json import parse_schema_bytes
from tests.conformance.types import InputInvalid, ParsedInput, SetupFailed

# Audited ECMA-262 translations for the exact expressions in the bundle.
# "\d" becomes "[0-9]" and a final "$" becomes "\Z" (absolute end).
_PATTERN_TRANSLATIONS = {
    r"^\d{8}_\d{6}$": r"^[0-9]{8}_[0-9]{6}\Z",
    r"^\d+\.\d+\.\d+$": r"^[0-9]+\.[0-9]+\.[0-9]+\Z",
    r"^\d{1,2}:\d{2}:\d{2}[:'\.]?\d{0,2}$": r"^[0-9]{1,2}:[0-9]{2}:[0-9]{2}[:'\.]?[0-9]{0,2}\Z",
    r"^x_": r"^x_",
}
_COMPILED_PATTERNS = {source: re.compile(target) for source, target in _PATTERN_TRANSLATIONS.items()}

_DATE_TIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?"
    r"(?:[Zz]|[+-]([0-9]{2}):([0-9]{2}))"
)

_DRAFT7_DIALECTS = ("http://json-schema.org/draft-07/schema#", "http://json-schema.org/draft-07/schema")

_REFERENCE_ERRORS = (referencing.exceptions.Unresolvable, referencing.exceptions.NoSuchResource)


def _compiled(expression):
    try:
        return _COMPILED_PATTERNS[expression]
    except (KeyError, TypeError):
        raise SetupFailed("schema regular expression is not in the audited translation table") from None


# Type checker: exact numbers only. bool is never a number.

def _is_integral(value: Decimal) -> bool:
    _sign, digits, exponent = value.as_tuple()
    return exponent >= 0 or all(digit == 0 for digit in digits[exponent:])


def _is_number(_checker, instance):
    if isinstance(instance, bool):
        return False
    if isinstance(instance, int):
        return True
    return isinstance(instance, Decimal) and instance.is_finite()


def _is_integer(_checker, instance):
    if isinstance(instance, bool):
        return False
    if isinstance(instance, int):
        return True
    return isinstance(instance, Decimal) and instance.is_finite() and _is_integral(instance)


# Keyword overrides that use the audited regular expressions.

def _pattern(validator, expression, instance, _schema):
    if validator.is_type(instance, "string") and not _compiled(expression).search(instance):
        yield ValidationError("string does not match pattern %r" % (expression,))


def _pattern_properties(validator, pattern_properties, instance, _schema):
    if not validator.is_type(instance, "object"):
        return
    for expression, subschema in pattern_properties.items():
        compiled = _compiled(expression)
        for key, value in instance.items():
            if compiled.search(key):
                yield from validator.descend(value, subschema, path=key, schema_path=expression)


_NATIVE_ADDITIONAL_PROPERTIES = Draft7Validator.VALIDATORS["additionalProperties"]


def _additional_properties(validator, additional, instance, schema):
    if "patternProperties" not in schema:
        yield from _NATIVE_ADDITIONAL_PROPERTIES(validator, additional, instance, schema)
        return
    if not validator.is_type(instance, "object"):
        return
    properties = schema.get("properties", {})
    compiled = [_compiled(expression) for expression in schema["patternProperties"]]
    extras = [
        key for key in instance
        if key not in properties and not any(c.search(key) for c in compiled)
    ]
    if validator.is_type(additional, "object"):
        for extra in extras:
            yield from validator.descend(instance[extra], additional, path=extra)
    elif not additional and extras:
        yield ValidationError("additional properties do not match any allowed pattern")


_Validator = validators.extend(
    Draft7Validator,
    validators={
        "pattern": _pattern,
        "patternProperties": _pattern_properties,
        "additionalProperties": _additional_properties,
    },
    type_checker=Draft7Validator.TYPE_CHECKER.redefine_many(
        {"number": _is_number, "integer": _is_integer}
    ),
)


def _evolve_keeping_class(self, **changes):
    # The stock evolve switches to the stock validator class whenever a
    # subschema declares "$schema", which would drop these overrides after
    # every cross-root reference. Setup refuses any dialect but Draft 7, so
    # keeping this class is correct.
    cls = type(self)
    changes.setdefault("schema", self.schema)
    for field in attrs.fields(cls):
        if field.init and field.alias not in changes:
            changes[field.alias] = getattr(self, field.name)
    return cls(**changes)


_Validator.evolve = _evolve_keeping_class


def _date_time_checker() -> FormatChecker:
    """Build a format checker with only the contract date-time grammar."""
    try:
        from rfc3339_validator import validate_rfc3339
    except ImportError:
        raise SetupFailed("rfc3339-validator is not available") from None

    def check(instance):
        if not isinstance(instance, str):
            return True
        match = _DATE_TIME.fullmatch(instance)
        if match is None:
            return False
        year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
        if year < 1 or not 1 <= month <= 12:
            return False
        if not 1 <= day <= calendar.monthrange(year, month)[1]:
            return False
        if hour > 23 or minute > 59 or second > 59:
            return False
        offset_hour, offset_minute = match.group(7), match.group(8)
        if offset_hour is not None and (int(offset_hour) > 23 or int(offset_minute) > 59):
            return False
        # The grammar has already matched, so the only letters are T/t and Z/z.
        # rfc3339-validator accepts only upper case, so compare in upper case.
        return validate_rfc3339(instance.upper()) is True

    checker = FormatChecker(formats=())
    checker.checks("date-time")(check)
    if "date-time" not in checker.checkers:
        raise SetupFailed("date-time format checker is not registered")
    return checker


def _refuse_retrieval(uri):
    raise referencing.exceptions.NoSuchResource(ref=uri)


def _read_schema(root: Path, entry):
    try:
        data = (root / entry.path).read_bytes()
    except OSError:
        raise SetupFailed("schema file cannot be read") from None
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        raise SetupFailed("schema digest does not match file bytes")
    try:
        tree = parse_schema_bytes(data)
    except InputInvalid:
        raise SetupFailed("schema file is not strict JSON") from None
    if not isinstance(tree, (dict, bool)):
        raise SetupFailed("schema is not an object or boolean")
    return tree


def _entry(manifest, name):
    for entry in manifest.schemas:
        if entry.name == name:
            return entry
    raise SetupFailed("schema name is not in the bundle manifest")


def load_schema(name: str, root: Path) -> dict:
    """Read and strictly parse one bundle schema. Each call returns a fresh tree."""
    root = Path(root)
    return _read_schema(root, _entry(load_bundle_manifest(root), name))


def _audit_keywords(contents):
    if "$schema" in contents and contents["$schema"] not in _DRAFT7_DIALECTS:
        raise SetupFailed("only the Draft 7 dialect is configured")
    if "pattern" in contents:
        _compiled(contents["pattern"])
    if "patternProperties" in contents:
        if not isinstance(contents["patternProperties"], dict):
            raise SetupFailed("patternProperties is not an object")
        for expression in contents["patternProperties"]:
            _compiled(expression)
    if "multipleOf" in contents:
        raise SetupFailed("multipleOf is refused: its evaluation could round")
    if "format" in contents and contents["format"] != "date-time":
        raise SetupFailed("only the date-time format is configured")


def _audit(resolver, resource, seen):
    """Walk every schema reachable from resource; fail setup on any gap."""
    contents = resource.contents
    if id(contents) in seen:
        return
    seen.add(id(contents))
    if isinstance(contents, dict):
        _audit_keywords(contents)
        if "$ref" in contents:
            reference = contents["$ref"]
            if not isinstance(reference, str):
                raise SetupFailed("$ref is not a string")
            try:
                resolved = resolver.lookup(reference)
            except _REFERENCE_ERRORS:
                raise SetupFailed("schema reference does not resolve inside the bundle") from None
            _audit(resolved.resolver, DRAFT7.create_resource(resolved.contents), seen)
    for subresource in resource.subresources():
        _audit(resolver.in_subresource(subresource), subresource, seen)


# Checks bundle schemas against the Draft 7 metaschema with the same
# exact-number type checker, so int and Decimal bounds count as numbers.
_MetaschemaValidator = validators.extend(Draft7Validator, type_checker=_Validator.TYPE_CHECKER)
# The metaschema recurses through "$ref": "#"; keep this class across it.
_MetaschemaValidator.evolve = _evolve_keeping_class
_METASCHEMA = _MetaschemaValidator(Draft7Validator.META_SCHEMA)


def _check_metaschema(tree):
    try:
        conforms = _METASCHEMA.is_valid(tree)
    except RecursionError:
        conforms = False
    if not conforms:
        raise SetupFailed("schema does not conform to the Draft 7 metaschema")


@dataclass(frozen=True)
class EntryPoint:
    """One selected bundle schema, compiled for one format mode."""

    name: str
    validator: object

    def validate(self, document: ParsedInput) -> list:
        """Return the Draft 7 structural errors for document. An empty list means valid."""
        if not isinstance(document, ParsedInput):
            raise TypeError("document must be a ParsedInput from parse_input")
        try:
            return list(self.validator.iter_errors(document.value))
        except _REFERENCE_ERRORS:
            raise SetupFailed("schema reference does not resolve inside the bundle") from None
        except RecursionError:
            raise SetupFailed("validation nesting exceeds the Python interpreter recursion limit") from None


@dataclass(frozen=True)
class Bundle:
    """An audited bundle compiled from one verified manifest snapshot."""

    root: Path
    manifest_sha256: str
    manifest: BundleManifest
    schemas: dict
    registry: referencing.Registry
    format_checker: FormatChecker
    validators: dict

    def entry_point(self, name: str, *, check_formats: bool) -> EntryPoint:
        """Select a schema by manifest name, or raise SetupFailed."""
        try:
            return EntryPoint(name, self.validators[name, bool(check_formats)])
        except (KeyError, TypeError):
            raise SetupFailed("schema name is not in the bundle manifest") from None


@functools.lru_cache(maxsize=None)
def _bundle_at(root: Path, manifest_sha256: str, manifest: BundleManifest) -> Bundle:
    schemas = {}
    pairs = []
    for entry in manifest.schemas:
        tree = _read_schema(root, entry)
        _check_metaschema(tree)
        schemas[entry.name] = tree
        resource = DRAFT7.create_resource(tree)
        pairs.extend((uri, resource) for uri in (entry.base_uri, *entry.aliases))
    registry = referencing.Registry(retrieve=_refuse_retrieval).with_resources(pairs)

    seen = set()
    for entry in manifest.schemas:
        _audit(registry.resolver(base_uri=entry.base_uri), registry[entry.base_uri], seen)

    checker = _date_time_checker()
    compiled = {}
    for entry in manifest.schemas:
        # Compile by base_uri so relative references resolve against it.
        entry_point = {"$ref": entry.base_uri}
        for check_formats in (True, False):
            compiled[entry.name, check_formats] = _Validator(
                entry_point,
                registry=registry,
                format_checker=checker if check_formats else None,
            )
    return Bundle(root, manifest_sha256, manifest, schemas, registry, checker, compiled)


def load_bundle(root: Path, manifest_bytes: "bytes | None" = None) -> Bundle:
    """Return the audited bundle for root, compiled from one manifest snapshot.

    ``manifest_bytes`` is the snapshot to use; when omitted, the manifest is
    read once here. The snapshot is verified on every call, including every
    schema file digest, and compiled bundles are cached by the resolved root
    and the snapshot digest. So a bundle is never served for schema bytes
    other than those the snapshot names.
    """
    root = Path(root).resolve()
    if manifest_bytes is None:
        manifest_bytes = read_manifest_bytes(root)
    manifest = parse_bundle_manifest(manifest_bytes, root)
    return _bundle_at(root, hashlib.sha256(manifest_bytes).hexdigest(), manifest)


def _bundle(root: Path) -> Bundle:
    """Return the audited bundle for root from its current manifest."""
    return load_bundle(root)


_bundle.cache_clear = _bundle_at.cache_clear


def validate_legacy(name: str, document: ParsedInput, *, root: Path, check_formats: bool = True) -> list:
    """Return the Draft 7 structural errors for document. An empty list means valid."""
    if not isinstance(document, ParsedInput):
        raise TypeError("document must be a ParsedInput from parse_input")
    return load_bundle(root).entry_point(name, check_formats=check_formats).validate(document)
