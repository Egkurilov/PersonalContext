# ADR-012 — Python patch baseline for PC-001

ADR-011 requires a fixed Python 3.12 patch. The initial build baseline is
CPython 3.12.16, specified in `.python-version`; development scripts and CI
select it through uv and verify the interpreter before running checks. CI pins
uv 0.13.10. Python and npm dependencies remain separately locked. This fixes
the selected interpreter version, not every input needed for bit-identical builds.

Python 3.12.16 is a security release; python.org distributes it as source only.
uv supplies its managed prebuilt CPython for Windows and Linux. The provider
and its binary provenance remain part of the build trust model. The earlier
local 3.12.10 build is superseded and was not a secure release baseline.
Upgrades require an ADR update, refreshed lockfiles if needed, and full
Windows/Linux validation including clean-machine acceptance. Security fixes
must be reviewed rather than indefinitely deferred by the pin.

Reference: https://www.python.org/downloads/release/python-31216/
