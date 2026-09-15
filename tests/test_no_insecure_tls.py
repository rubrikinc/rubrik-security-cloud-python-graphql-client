"""CI guard: fail the build if a TLS-verification bypass ever appears in
`src/`. Mechanically enforces "we never skip certificate validation" instead
of relying on it being merely documented or asserted in review.

Matches `verify=False` / `verify = False` (requests), `CERT_NONE` (ssl), and
`InsecureSkipVerify` (a marker sometimes copied from Go-derived snippets or
docs) anywhere under `src/`.
"""
import re
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

_BANNED_PATTERNS = [
    re.compile(r"verify\s*=\s*False"),
    re.compile(r"CERT_NONE"),
    re.compile(r"InsecureSkipVerify"),
]


def test_no_tls_verification_bypass_in_src():
    offenders = []
    for path in _SRC_ROOT.rglob("*.py"):
        text = path.read_text()
        for pattern in _BANNED_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(_SRC_ROOT.parent)}: matched {pattern.pattern!r}")
    assert not offenders, (
        "TLS verification bypass found (this repo never disables certificate "
        f"validation): {offenders}"
    )
