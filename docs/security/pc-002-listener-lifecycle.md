# PC-002 private listener lifecycle

The private listener is off on every process start. Its API and limitations are:

1. A local owner with a valid session, exact Origin and CSRF explicitly asks to
   start the currently saved candidate by revision. Restart does not activate it.
2. Before binding, check that the selected interface is physical and up, every
   permitted peer range is within its actual private subnet, and the active
   firewall policy is restrictive. VPN and nonlocal ranges are excluded. Then
   validate the certificate and key under locked files, and repeat the owner
   authorization and revision checks. Failure, ambiguity, timeout or a port
   conflict must leave the local HTTP listener running and the private one off.
3. A settings change must not race an active or starting listener. Stop and
   process shutdown close the listening socket and request active connections
   to close; in-flight work may take time to finish. The listener must
   not enable forwarding headers, plaintext HTTP, wildcard binding or capture.
4. A monitor repeats the firewall assessment after 15-second waits. The snapshot
   itself may take up to 45 seconds. A non-restricted or unavailable assessment,
   a failed security worker or an exited server closes the listener. Changes may
   remain undetected until the next assessment completes; snapshots cannot see
   every Windows Filtering Platform rule. TLS and the per-request peer/Host/Origin
   checks remain independent, but the firewall state is not continuously proven.
   Routers or bridges that present remote clients as local IPs cannot be
   distinguished by these checks and require separate network controls.
5. Synthetic tests start real TLS sockets on loopback and a private interface;
   the latter exercises owner start, login and shutdown on an observed firewall
   failure. Firewall and certificate-vault checks are mocked, and client and
   server run on the same host, so this does not prove LAN routing or a real firewall.
   Remote client trust, allowed and disallowed peers, forged Host/Origin,
   plaintext, port conflict, restart and shutdown still need real LAN tests.

`POST /api/v1/network/private/start` requires owner Origin, CSRF and the saved
revision in JSON; `POST /api/v1/network/private/stop` requires the same owner
authorization. Both are local-only. Start makes two firewall assessments around
TLS preparation, then rechecks the owner and revision before binding. Each
firewall assessment has a 45-second subprocess timeout, so start can take more
than a minute; no database transaction is held during those checks. A stop
cancels a pending preflight without waiting for its background worker. Changes
to the candidate are rejected while startup or the listener owns the lifecycle
lock. The `private_listener_attempt` and `private_listener_stop` audit categories
contain no addresses or request data; an attempt records an authorized attempt,
not a guarantee that startup succeeded. If audit storage fails, stop still closes
the listener, but its audit event may be unavailable. Migration `0015` adds the
categories and rejects downgrade if their history would be lost.

`python scripts/check_wfp_subscription.py` performs a read-only, short-lived
attempt to subscribe to all WFP filter additions and deletions and immediately
unsubscribes; it changes no firewall rules. It reports `unavailable` on error
and exits nonzero. The local Windows test account could open the WFP engine but
the subscription returned access denied. Microsoft documents that the API
requires [subscribe access to the filter container](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfiltersubscribechanges0)
and that [WFP access is controlled by security descriptors](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control).
This result is specific to that account and machine. A successful probe only
proves subscription and unsubscription succeeded at that moment; it does not
prove complete monitoring, notification delivery or effective firewall policy.
Microsoft explicitly describes [BFE change notifications](https://learn.microsoft.com/en-us/windows/win32/fwp/change-notifications)
as asynchronous and not guaranteed to be delivered. Therefore even a
successful subscription cannot serve as the sole enforcement mechanism or
guarantee immediate shutdown after a policy change. Network peer enforcement
must remain independent, and any monitoring delay and firewall assumptions
must be stated in the eventual security review.
The application does not elevate, change WFP permissions or start the listener
on the basis of this probe.
