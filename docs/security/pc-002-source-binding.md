# PC-002: source binding and device configuration

The owner can create a browser or Windows source for an enrolled device with
the ingest scope. Creation needs a valid owner session and CSRF token. A random
source identifier is bound to that device; the source starts paused. Limits are
16 sources per device and 256 in total. Creating or pausing a source records a
fixed audit category without recording its identifier or captured content.

The owner-only `/api/v1/sources` endpoint lists sources with bounded cursor
pagination and creates them. `PATCH /api/v1/sources/{id}` changes the owner's
pause setting with an expected revision; stale updates fail. An active device
cannot impersonate another device: its bearer credential and device identifier
must match the source binding. Revocation invalidates device authentication.

`GET /api/v1/device/config` requires the device's config scope and returns only
its own sources. It reports policy expiry and the local pause latch. Each source
is marked `unverified`, paused, and has no capture scopes; the response reports
`collection_enabled: false` even when the owner has requested a grant. These
settings describe owner intent, not evidence of private-mode detection, OS
permission, or a trustworthy collector. The identity check alone is not an
ingestion authorization. No real activity collection is enabled by this change.

Migration 0010 preserves existing audit rows and creates the source registry.
Restore of a 0010 backup revokes device credentials and pauses every source,
in addition to resetting owner credentials and pausing the global policy.
Downgrade refuses to discard source records or source audit history; to roll
back, restore a pre-migration backup using the supported recovery procedure.
Migration and recovery tests use synthetic records only.

Remaining work includes trusted source adapters and their permission/private
mode verification, real ingestion enforcement, policy distribution and TTL
enforcement by offline clients, and source-specific pause at the collector.
These controls must be completed and tested before granting capture scopes.
