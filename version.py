"""Resolves the version from git instead of a hand-maintained string --
the previous plain `__version__ = "1.0.0"` never got bumped across three
tagged releases (v1.0.0, v1.1.0, v1.2.0 all shipped "1.0.0") because
nothing forced it to change when a tag was cut.

Two distribution paths, two resolution strategies:
- A plain `git clone` (the maintainer's own checkout): `_RAW` below is
  still the literal, unexpanded "$Format:...$" placeholder (git only
  substitutes it during `git archive`, never on a normal checkout/pull),
  so `_resolve_version()` falls through to calling `git describe --tags`
  directly. Tagging a release is then the only step needed -- no file to
  remember to edit.
- A distribution zip built via `git archive` (see README.md's "Quick
  start" / the student-lab zip): `.gitattributes` marks this file
  `export-subst`, so git replaces `_RAW` with the real tag description
  (e.g. "v1.2.0", or "v1.2.0-15-g6ccb4f3" if archived 15 commits past
  the last tag) at the moment the archive is created. The zip has no
  .git directory for `git describe` to read from, but by then the
  correct value is already baked into the file as plain text.
"""
import subprocess
from pathlib import Path

_FALLBACK_VERSION = "0.0.0+unknown"
_RAW = "$Format:%(describe)$"


def _resolve_version():
    if not _RAW.startswith("$Format"):
        return _RAW  # already substituted by `git archive` -- use as-is
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return _FALLBACK_VERSION


__version__ = _resolve_version()
