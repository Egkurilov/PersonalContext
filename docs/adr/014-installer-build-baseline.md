# ADR-014 — Installer compiler baseline for PC-001

Builds use Inno Setup 6.7.4. The build script and Windows CI download the
official installer from its immutable GitHub release, check the committed
SHA-256 and run it with `/PORTABLE=1` into the ignored workspace tool cache.
No system Inno Setup installation is replaced or registered. The installer
script rejects other compiler versions using Inno's preprocessor version.
Updates require review of the upstream release and checksum, an ADR change,
and renewed Windows installer and clean-machine testing. A version pin does
not prove bit-identical builds or independently authenticate cached files.
Embedded files omit source timestamps. A smoke test recompiles from the same
packaged tree after changing a fixture file's timestamp and compares installer
bytes; this does not establish reproducibility from separate source checkouts.
PyInstaller uses a fixed Python hash seed and the Git commit timestamp while
packaging; the build checks every file and directory against a second packaging
run in the same workspace. CI also compares two offline, separately created
local clones of the exact checked-out commit, including their installers.
Cross-machine reproducibility is not yet established.
CI retains a seven-day report containing only the Git revision, relative bundle
paths, directory markers, and SHA-256 digests; it contains no absolute paths or
machine identifiers. This report allows comparison with a local clone build.
The generated `base_library.zip` is sorted by member name after rejecting
duplicates and unexpected compression/flags; module bytes are preserved.
The bundled Alembic RECORD omits the virtualenv-generated `alembic.exe`
launcher, which is not shipped and whose hash depends on the virtualenv path.
Other metadata is retained; SBOM generation reads the unchanged environment.
During PyInstaller execution, DLL search uses only Windows system directories
and the pinned Python environment; inherited Python path overrides are cleared
and restored afterward. The packaged migration tree contains source `.py`
files only, excluding generated caches. Smoke tests reject application-local
UCRT/API-set DLLs, which Windows 11 supplies as OS components, while the Python
distribution's VC runtime remains bundled. Clean-Windows validation is pending.
The bundled HTML entry point, JSON schemas and Python migration sources use
UTF-8 with CRLF normalized to LF. This avoids platform checkout settings
changing their packaged bytes; the source working tree is never rewritten.

Reference: https://learn.microsoft.com/en-us/cpp/windows/universal-crt-deployment

Reference: https://github.com/jrsoftware/issrc/releases/tag/is-6_7_4
