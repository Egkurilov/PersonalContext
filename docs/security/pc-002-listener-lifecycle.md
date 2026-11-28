# PC-002 private listener lifecycle

The private listener is currently unavailable. Its activation contract is:

1. A local owner with a valid session, exact Origin and CSRF explicitly asks to
   start the currently saved candidate by revision. Restart does not activate it.
2. Before binding, check the selected interface and active firewall policy,
   validate the certificate and key under locked files, and repeat the owner
   authorization and revision checks. Failure, ambiguity, timeout or a port
   conflict must leave the local HTTP listener running and the private one off.
3. A settings change must not race an active or starting listener. Stop and
   process shutdown close the socket and all private requests. The listener must
   not enable forwarding headers, plaintext HTTP, wildcard binding or capture.
4. Changes in interface or firewall policy must cause private access to stop.
   A point-in-time rule snapshot is not a durable guarantee: the implementation
   must explain and test how it handles changes and cannot present a diagnostic
   result as proof of continuously effective Windows Filtering Platform policy.
5. Remote client certificate trust, allowed and disallowed peers, forged
   Host/Origin, plaintext, port conflict, restart and shutdown require real
   platform acceptance in addition to synthetic tests.

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
The application does not elevate, change WFP permissions or start the listener
on the basis of this probe.
