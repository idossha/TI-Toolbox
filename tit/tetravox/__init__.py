"""Dynamic delivery of the Tetravox embed bundle (plan E1-E4).

Three modules, one job each:

- :mod:`tit.tetravox.protocol` -- E1: the supported protocol **range** and the
  named feature map.  The single Python-side statement of what this build can
  host; its TypeScript twin is ``desktop/src/renderer/viewer/embedProtocol.ts``.
- :mod:`tit.tetravox.store` -- E2: two install roots (the image's baked floor and
  a writable one under the user config), the pin, and the per-request resolution
  of what ``/tetravox/`` serves.
- :mod:`tit.tetravox.install` -- E3: allowlisted download, digest verified before
  unpacking, traversal-safe extraction, manifest validation, atomic activation.
- :mod:`tit.tetravox.updates` -- A2/A3/A4: the GitHub Releases API as the index,
  an ETag cache, the ``auto_update`` policy, and the one pass that checks,
  decides and (only when the protocol is in range) installs.

The HTTP surface is :mod:`tit.server.routes.tetravox`.  Nothing here imports
:mod:`tit.server` -- ``tit.server.static`` imports this, not the other way round.
"""

from tit.tetravox.protocol import (
    FEATURE_MIN_PROTOCOL,
    SUPPORTED_PROTOCOL_MAX,
    SUPPORTED_PROTOCOL_MIN,
    features_for,
    protocol_supported,
    supported_range,
)
from tit.tetravox.store import (
    BAKED,
    EmbedRelease,
    Resolution,
    StoreError,
    activate,
    active_embed_dir,
    describe,
    install_root,
    list_installed,
    read_pin,
    remove_version,
    resolve_active,
    resolve_from_settings,
)
from tit.tetravox.updates import (
    CHECK_INTERVAL_S,
    CheckResult,
    UpdateOutcome,
    check,
    last_check,
    read_policy,
    run_check_and_maybe_install,
    write_policy,
)

__all__ = [
    "BAKED",
    "CHECK_INTERVAL_S",
    "CheckResult",
    "EmbedRelease",
    "FEATURE_MIN_PROTOCOL",
    "Resolution",
    "SUPPORTED_PROTOCOL_MAX",
    "SUPPORTED_PROTOCOL_MIN",
    "StoreError",
    "UpdateOutcome",
    "activate",
    "active_embed_dir",
    "check",
    "describe",
    "features_for",
    "install_root",
    "last_check",
    "list_installed",
    "protocol_supported",
    "read_pin",
    "read_policy",
    "remove_version",
    "resolve_active",
    "resolve_from_settings",
    "run_check_and_maybe_install",
    "supported_range",
    "write_policy",
]
