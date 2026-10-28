"""Offline JSON Schema 2020-12 bundle loader and Python structural adapter.

Each bundle root and manifest snapshot gets its own ``referencing.Registry``.
The registry never retrieves a resource: every schema comes from the bundle
manifest, and each file digest is verified before it is parsed. Setup checks
every bundle schema against the 2020-12 metaschema, then audits every
reachable subschema before any validation:

- ``$schema`` is absent or equal to the 2020-12 dialect;
- every ``$ref`` resolves inside the registry;
- every ``pattern`` translates from ECMA-262 to Python syntax;
- ``format`` is one of ``date-time``, ``date``, ``regex``, ``uri``;
- ``multipleOf`` and ``patternProperties`` are refused.

Validation uses an extended 2020-12 validator with an exact-number type
checker, the translated ``pattern`` keyword, and a format checker that holds
only the four audited formats.
"""

import functools
import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import attrs
import jsonschema_specifications
import referencing
import referencing.exceptions
from jsonschema import Draft202012Validator, FormatChecker, validators
from jsonschema.exceptions import ValidationError
from referencing.jsonschema import DRAFT202012

from tests.conformance import ecma_regex, formats
from tests.conformance.bundle import DIALECT, BundleManifest, parse_bundle_manifest, read_manifest_bytes
from tests.conformance.formats import check_date, check_date_time
from tests.conformance.strict_json import parse_schema_bytes
from tests.conformance.types import InputInvalid, ParsedInput, SetupFailed

_DIALECTS = (DIALECT, DIALECT + "#")
_FORMATS = ("date-time", "date", "regex", "uri")
_REFERENCE_ERRORS = (referencing.exceptions.Unresolvable, referencing.exceptions.NoSuchResource)


# Format checks. Each takes a string and returns True when it conforms.
# check_date_time and check_date live in formats.py and are re-exported here.


def check_regex(value: str) -> bool:
    """A valid ECMA-262 regular expression.

    ``RegexResourceLimit`` propagates: a pattern nested beyond the checker's
    limit is neither valid nor invalid, and ``EntryPoint.validate`` reports it
    as a setup failure.
    """
    return ecma_regex.is_valid(value)


# RFC 3986 Appendix A, built production by production. Only the `URI`
# production is accepted, so a relative reference is refused.
_ALPHA = "A-Za-z"
_DIGIT = "0-9"
_HEXDIG = "0-9A-Fa-f"
_UNRESERVED = "[" + _ALPHA + _DIGIT + "._~-]"
_PCT_ENCODED = "%[" + _HEXDIG + "]{2}"
_SUB_DELIMS = "[!$&'()*+,;=]"
_PCHAR = "(?:" + _UNRESERVED + "|" + _PCT_ENCODED + "|" + _SUB_DELIMS + "|[:@])"

_SCHEME = "[" + _ALPHA + "][" + _ALPHA + _DIGIT + "+.-]*"
_USERINFO = "(?:" + _UNRESERVED + "|" + _PCT_ENCODED + "|" + _SUB_DELIMS + "|:)*"
_DEC_OCTET = "(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])"
_IPV4ADDRESS = _DEC_OCTET + r"\." + _DEC_OCTET + r"\." + _DEC_OCTET + r"\." + _DEC_OCTET
_H16 = "[" + _HEXDIG + "]{1,4}"
_LS32 = "(?:" + _H16 + ":" + _H16 + "|" + _IPV4ADDRESS + ")"


def _h16_prefix(count):
    # [ *count( h16 ":" ) h16 ]
    return "(?:(?:" + _H16 + ":){0," + str(count) + "}" + _H16 + ")?"


_IPV6ADDRESS = "(?:" + "|".join(
    (
        "(?:" + _H16 + ":){6}" + _LS32,
        "::(?:" + _H16 + ":){5}" + _LS32,
        "(?:" + _H16 + ")?::(?:" + _H16 + ":){4}" + _LS32,
        _h16_prefix(1) + "::(?:" + _H16 + ":){3}" + _LS32,
        _h16_prefix(2) + "::(?:" + _H16 + ":){2}" + _LS32,
        _h16_prefix(3) + "::" + _H16 + ":" + _LS32,
        _h16_prefix(4) + "::" + _LS32,
        _h16_prefix(5) + "::" + _H16,
        _h16_prefix(6) + "::",
    )
) + ")"
_IPVFUTURE = "[vV][" + _HEXDIG + r"]+\.(?:" + _UNRESERVED + "|" + _SUB_DELIMS + "|:)+"
_IP_LITERAL = r"\[(?:" + _IPV6ADDRESS + "|" + _IPVFUTURE + r")\]"
_REG_NAME = "(?:" + _UNRESERVED + "|" + _PCT_ENCODED + "|" + _SUB_DELIMS + ")*"
_HOST = "(?:" + _IP_LITERAL + "|" + _IPV4ADDRESS + "|" + _REG_NAME + ")"
_PORT = "[" + _DIGIT + "]*"
_AUTHORITY = "(?:" + _USERINFO + "@)?" + _HOST + "(?::" + _PORT + ")?"

_SEGMENT = _PCHAR + "*"
_SEGMENT_NZ = _PCHAR + "+"
_PATH_ABEMPTY = "(?:/" + _SEGMENT + ")*"
_PATH_ABSOLUTE = "/(?:" + _SEGMENT_NZ + "(?:/" + _SEGMENT + ")*)?"
_PATH_ROOTLESS = _SEGMENT_NZ + "(?:/" + _SEGMENT + ")*"
_PATH_EMPTY = ""
_HIER_PART = (
    "(?:" + "//" + _AUTHORITY + _PATH_ABEMPTY
    + "|" + _PATH_ABSOLUTE
    + "|" + _PATH_ROOTLESS
    + "|" + _PATH_EMPTY + ")"
)
_QUERY = "(?:" + _PCHAR + "|[/?])*"
_FRAGMENT = "(?:" + _PCHAR + "|[/?])*"
_URI = re.compile(_SCHEME + ":" + _HIER_PART + r"(?:\?" + _QUERY + ")?(?:#" + _FRAGMENT + ")?")


def check_uri(value: str) -> bool:
    """RFC 3986 `URI`: an absolute URI with an optional fragment."""
    return _URI.fullmatch(value) is not None


def _format_checker() -> FormatChecker:
    """Build a format checker that holds exactly the four audited formats."""
    if formats.validate_rfc3339 is None:
        raise SetupFailed("rfc3339-validator is not available")
    checker = FormatChecker(formats=())
    for name, check in (
        ("date-time", check_date_time),
        ("date", check_date),
        ("regex", check_regex),
        ("uri", check_uri),
    ):
        checker.checks(name)(functools.partial(_strings_only, check))
    if "date-time" not in checker.checkers or set(checker.checkers) != set(_FORMATS):
        raise SetupFailed("date-time format checker is not registered")
    return checker


def _strings_only(check, instance):
    return not isinstance(instance, str) or check(instance)


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


TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine_many(
    {"number": _is_number, "integer": _is_integer}
)


# ECMA-262 patterns, translated once and cached by source text.

@functools.lru_cache(maxsize=None)
def _compiled(expression):
    if not isinstance(expression, str):
        raise SetupFailed("schema pattern is not a string")
    try:
        return re.compile(ecma_regex.to_python(expression))
    except (ecma_regex.RegexSyntaxError, ecma_regex.Untranslatable, ecma_regex.RegexResourceLimit, re.error):
        raise SetupFailed("schema pattern does not translate from ECMA-262") from None


def _pattern(validator, expression, instance, _schema):
    if validator.is_type(instance, "string") and not _compiled(expression).search(instance):
        yield ValidationError("%r does not match %r" % (instance, expression))


def _pattern_properties(_validator, _pattern_properties, _instance, _schema):
    # The audit refuses patternProperties, so this is never reached for an
    # audited bundle. Refuse rather than fall back to Python regex syntax.
    raise SetupFailed("patternProperties is not supported by this loader")
    yield  # pragma: no cover - makes this a generator like every keyword


_Validator = validators.extend(
    Draft202012Validator,
    validators={
        "pattern": _pattern,
        "patternProperties": _pattern_properties,
        "propertyNames": Draft202012Validator.VALIDATORS["propertyNames"],
    },
    type_checker=TYPE_CHECKER,
)


def _evolve_keeping_class(self, **changes):
    # The stock evolve switches to the stock validator class whenever a
    # referenced resource declares "$schema", which would drop these
    # overrides after every cross-file reference. Setup refuses any dialect
    # but 2020-12, so keeping this class is correct.
    cls = type(self)
    changes.setdefault("schema", self.schema)
    for attribute in attrs.fields(cls):
        if attribute.init and attribute.alias not in changes:
            changes[attribute.alias] = getattr(self, attribute.name)
    return cls(**changes)


_Validator.evolve = _evolve_keeping_class


# Checks bundle schemas against the 2020-12 metaschema with the same
# exact-number type checker, so int and Decimal bounds count as numbers.
# The metaschema and its vocabularies ship with jsonschema. They are copied
# into a registry that refuses retrieval, so no path can fetch a schema.
_MetaschemaValidator = validators.extend(Draft202012Validator, type_checker=TYPE_CHECKER)
_MetaschemaValidator.evolve = _evolve_keeping_class


def _check_metaschema(tree):
    try:
        conforms = _METASCHEMA.is_valid(tree)
    except RecursionError:
        conforms = False
    if not conforms:
        raise SetupFailed("schema does not conform to the 2020-12 metaschema")


def _refuse_retrieval(uri):
    raise referencing.exceptions.NoSuchResource(ref=uri)


_METASCHEMA_REGISTRY = referencing.Registry(retrieve=_refuse_retrieval).with_resources(
    (uri, jsonschema_specifications.REGISTRY[uri]) for uri in jsonschema_specifications.REGISTRY
)
_METASCHEMA = _MetaschemaValidator(Draft202012Validator.META_SCHEMA, registry=_METASCHEMA_REGISTRY)


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


def _audit_keywords(contents):
    if "$schema" in contents and contents["$schema"] not in _DIALECTS:
        raise SetupFailed("only the 2020-12 dialect is configured")
    if "pattern" in contents:
        _compiled(contents["pattern"])
    if "patternProperties" in contents:
        raise SetupFailed("patternProperties is not supported by this loader")
    if "$dynamicRef" in contents or "$dynamicAnchor" in contents:
        raise SetupFailed("$dynamicRef and $dynamicAnchor are not supported by this loader")
    if "multipleOf" in contents:
        raise SetupFailed("multipleOf is refused: its evaluation could round")
    if "format" in contents and contents["format"] not in _FORMATS:
        raise SetupFailed("format is not one of date-time, date, regex, uri")


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
            _audit(resolved.resolver, DRAFT202012.create_resource(resolved.contents), seen)
    for subresource in resource.subresources():
        _audit(resolver.in_subresource(subresource), subresource, seen)


@dataclass(frozen=True)
class EntryPoint:
    """One document root of the bundle, compiled for validation."""

    kind: str
    _validator: object = field(repr=False, compare=False)

    def validate(self, document: ParsedInput) -> list:
        """Return the 2020-12 structural errors for document. An empty list means valid."""
        if not isinstance(document, ParsedInput):
            raise TypeError("document must be a ParsedInput from parse_input")
        try:
            return list(self._validator.iter_errors(document.value))
        except _REFERENCE_ERRORS:
            raise SetupFailed("schema reference does not resolve inside the bundle") from None
        except RecursionError:
            raise SetupFailed("validation nesting exceeds the Python interpreter recursion limit") from None
        except ecma_regex.RegexResourceLimit:
            raise SetupFailed("pattern nesting exceeds the checker's resource limit") from None


@dataclass(frozen=True)
class Bundle:
    """An audited bundle compiled from one verified manifest snapshot."""

    root: Path
    manifest_sha256: str
    manifest: BundleManifest
    schemas: dict = field(repr=False, compare=False)
    registry: referencing.Registry = field(repr=False, compare=False)
    _entry_points: dict = field(repr=False, compare=False)

    def entry_point(self, kind: str) -> EntryPoint:
        """Select a document root by kind, or raise SetupFailed."""
        try:
            return self._entry_points[kind]
        except (KeyError, TypeError):
            raise SetupFailed("kind is not a document root of the bundle") from None


@functools.lru_cache(maxsize=None)
def _bundle_at(root: Path, manifest_sha256: str, manifest: BundleManifest) -> Bundle:
    try:
        return _build(root, manifest_sha256, manifest)
    except RecursionError:
        raise SetupFailed("schema nesting exceeds the Python interpreter recursion limit") from None


def _build(root: Path, manifest_sha256: str, manifest: BundleManifest) -> Bundle:
    schemas = {}
    pairs = []
    for entry in manifest.schemas:
        tree = _read_schema(root, entry)
        _check_metaschema(tree)
        schemas[entry.name] = tree
        pairs.append((entry.id, DRAFT202012.create_resource(tree)))
    registry = referencing.Registry(retrieve=_refuse_retrieval).with_resources(pairs)

    seen = set()
    for entry in manifest.schemas:
        _audit(registry.resolver(base_uri=entry.id), registry[entry.id], seen)

    checker = _format_checker()
    entry_points = {}
    for entry in manifest.schemas:
        if entry.name in manifest.document_roots:
            validator = _Validator({"$ref": entry.id}, registry=registry, format_checker=checker)
            entry_points[entry.name] = EntryPoint(entry.name, validator)
    return Bundle(root, manifest_sha256, manifest, schemas, registry, entry_points)


def load_bundle(root: Path, manifest_bytes: "bytes | None" = None) -> Bundle:
    """Return the audited bundle for root, compiled from one manifest snapshot.

    ``manifest_bytes`` is the snapshot to use; when omitted, the manifest is
    read once here. The snapshot is verified on every call. Compiled bundles
    are cached by the resolved root and the snapshot digest, and every schema
    file digest is verified when a bundle is compiled.
    """
    root = Path(root).resolve()
    if manifest_bytes is None:
        manifest_bytes = read_manifest_bytes(root)
    manifest = parse_bundle_manifest(manifest_bytes, root)
    return _bundle_at(root, hashlib.sha256(manifest_bytes).hexdigest(), manifest)
