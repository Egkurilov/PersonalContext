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
bytes; this does not establish reproducibility of independently built trees.

Reference: https://github.com/jrsoftware/issrc/releases/tag/is-6_7_4
