# ADR-013 — Frontend build baseline for PC-001

The initial frontend build baseline is Node.js 24.22.3 and npm 11.19.1.
`.node-version` and `.npm-version` record the exact versions; development,
test and CI verify them before dependency installation. `npm ci` uses the
committed lockfile. CI selects Windows Server 2025 and Ubuntu 24.04 runner
families rather than moving `latest` labels. Runner images, action tags and
other build inputs may still change: this does not establish bit-for-bit
reproducibility. Node.js is required only for development/build, not on the
installed target. Review security updates and amend this ADR and both pins
when changing the baseline; verify on Windows and Linux.

Reference: https://nodejs.org/dist/v24.22.3/
