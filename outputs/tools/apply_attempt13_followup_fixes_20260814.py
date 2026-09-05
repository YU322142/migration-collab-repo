#!/usr/bin/env python3
"""Run the audited DnT/Tracks/Iron follow-up transaction on Attempt13.

The implementation is shared with the reviewed Attempt11 transaction; only
the disposable target/report/backup paths are rebound here.  MCModSync,
maid.js, world, and config remain outside the mutation allowlist.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
SOURCE = TOOLS / "apply_attempt11_followup_fixes_20260814.py"
spec = importlib.util.spec_from_file_location("attempt11_followup_impl", SOURCE)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load audited Attempt11 follow-up implementation")
impl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = impl
spec.loader.exec_module(impl)

ROOT = Path(r"<AUDIT_ROOT>")
impl.SERVER = ROOT / "mechanomania-matched-runtime-attempt13-20260814"
impl.CLIENT = ROOT / "mechanomania-matched-client-attempt13-20260814"
impl.BACKUP = ROOT / "attempt13-followup-fixes-backup-20260814"
impl.PREFLIGHT_REPORT = ROOT / "attempt13-followup-fixes-preflight-20260814.json"
impl.APPLY_REPORT = ROOT / "attempt13-followup-fixes-apply-20260814.json"
impl.POSTVERIFY_REPORT = ROOT / "attempt13-followup-fixes-postverify-20260814.json"


def ensure_attempt13_root_safety() -> None:
    expected = {
        impl.SERVER: "mechanomania-matched-runtime-attempt13-20260814",
        impl.CLIENT: "mechanomania-matched-client-attempt13-20260814",
    }
    forbidden = Path(r"<TRANS_ROOT>\20260807").resolve()
    for value, leaf in expected.items():
        if not value.is_dir() or value.is_symlink():
            raise impl.FollowupError(f"unsafe Attempt13 target root: {value}")
        resolved = value.resolve()
        if resolved.name != leaf:
            raise impl.FollowupError(f"Attempt13 target leaf mismatch: {resolved}")
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise impl.FollowupError(f"target outside D audit root: {resolved}") from exc
        try:
            resolved.relative_to(forbidden)
        except ValueError:
            pass
        else:
            raise impl.FollowupError(f"target overlaps authoritative migration source: {resolved}")
        for runtime_name in ("logs", "crash-reports", impl.GATE_MARKER):
            if (resolved / runtime_name).exists():
                raise impl.FollowupError(
                    f"Attempt13 root already has runtime state: {resolved / runtime_name}"
                )


impl.ensure_root_safety = ensure_attempt13_root_safety


if __name__ == "__main__":
    raise SystemExit(impl.main())
