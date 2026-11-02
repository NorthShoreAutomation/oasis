"""Root checks of an exchange document, run before any schema is selected (REC-2, UNS-1).

The checks run in a fixed order after ``DOC-1``, and the first that fails
stops the run with one diagnostic:

1. The exchange document test: the root is an object with ``spec_version``.
   Otherwise ``NOT_EXCHANGE_DOCUMENT`` at the root.
2. The version check: ``spec_version`` equals a supported version exactly.
   Otherwise ``VERSION_UNSUPPORTED`` at ``/spec_version`` and no other finding.
3. The root ``type`` test: ``type`` is present and is ``package``. Otherwise
   ``NOT_EXCHANGE_DOCUMENT`` at the root when ``type`` is absent, or at
   ``/type`` when it has another value.
"""

from tests.conformance.semantic import CATALOG
from tests.conformance.types import Diagnostic, Routing

# Each supported version, bound to the record types its rule set routes.
SUPPORTED_VERSIONS = {"2.0.0-draft.3": ("package",)}
KINDS = ("package",)

# The two routing entries come from the single catalog in semantic.py.
ROUTING_CATALOG = {code: CATALOG[code] for code in ("NOT_EXCHANGE_DOCUMENT", "VERSION_UNSUPPORTED")}


def _diagnostic(code, path):
    rule, severity, message = ROUTING_CATALOG[code]
    return Diagnostic(code, rule, severity, path, message)


def _unsupported(code, path, version=None):
    return Routing("unsupported", None, version, (_diagnostic(code, path),))


def route(value):
    """Decide from the root ``spec_version`` and ``type`` alone.

    Never consults a schema. The version compare is exact: a value of any
    other JSON type, or any other string, is not supported. ``spec_version``
    in the result is set only when it is supported, and ``kind`` only when
    the document routes.
    """
    if not isinstance(value, dict) or "spec_version" not in value:
        return _unsupported("NOT_EXCHANGE_DOCUMENT", "")
    version = value["spec_version"]
    if not isinstance(version, str) or version not in SUPPORTED_VERSIONS:
        return _unsupported("VERSION_UNSUPPORTED", "/spec_version")
    if "type" not in value:
        return _unsupported("NOT_EXCHANGE_DOCUMENT", "", version)
    kind = value["type"]
    if not isinstance(kind, str) or kind not in SUPPORTED_VERSIONS[version]:
        return _unsupported("NOT_EXCHANGE_DOCUMENT", "/type", version)
    return Routing("selected", kind, version, ())
