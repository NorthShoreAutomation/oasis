"""Record type and spec_version routing, run before any schema is selected."""

from tests.conformance.semantic import CATALOG
from tests.conformance.types import Diagnostic, Routing

KINDS = (
    "package",
    "asset",
    "collection",
    "storage_location",
    "metadata_definition",
    "annotation",
)
SPEC_VERSION = "2.0.0-draft.2"

# The two routing entries come from the single catalog in semantic.py.
ROUTING_CATALOG = {code: CATALOG[code] for code in ("TYPE_UNSUPPORTED", "VERSION_UNSUPPORTED")}


def _diagnostic(code, path):
    rule, severity, message = ROUTING_CATALOG[code]
    return Diagnostic(code, rule, severity, path, message)


def route(value):
    """Decide from the root ``type`` and ``spec_version`` alone.

    Never consults a schema. Diagnostics are ordered by path, then code.
    """
    root = value if isinstance(value, dict) else {}
    diagnostics = []

    kind = root.get("type")
    if not (isinstance(kind, str) and kind in KINDS):
        kind = None
        path = "/type" if "type" in root else ""
        diagnostics.append(_diagnostic("TYPE_UNSUPPORTED", path))

    version = root.get("spec_version")
    if version != SPEC_VERSION:
        version = None
        diagnostics.append(_diagnostic("VERSION_UNSUPPORTED", "/spec_version"))

    diagnostics.sort(key=lambda d: (d.path, d.code))
    return Routing(
        "unsupported" if diagnostics else "selected",
        kind,
        version,
        tuple(diagnostics),
    )
