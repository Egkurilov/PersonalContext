"""Parse explicit firewall addresses and conservatively classify port selectors."""

import ipaddress

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def networks(values: tuple[str, ...]) -> list[Network] | None:
    if not isinstance(values, tuple) or not 1 <= len(values) <= 64:
        return None
    result: list[Network] = []
    try:
        for value in values:
            if not isinstance(value, str) or len(value) > 100:
                return None
            if "-" in value:
                begin, end = value.split("-", 1)
                first, last = ipaddress.ip_address(begin), ipaddress.ip_address(end)
                if first.version != last.version or int(first) > int(last):
                    return None
                result.extend(ipaddress.summarize_address_range(first, last))
            else:
                result.append(ipaddress.ip_network(value, strict=False))
            if len(result) > 256:
                return None
    except ValueError:
        return None
    return result


def port_match(values: tuple[str, ...], port: int) -> tuple[bool, bool]:
    """Return (possibly matches, known match); unknown selectors cannot prove coverage."""
    if not isinstance(values, tuple) or not 1 <= len(values) <= 64:
        return True, False
    possible = known = False
    for value in values:
        if not isinstance(value, str):
            return True, False
        if value.lower() in ("any", "*"):
            possible = known = True
            continue
        try:
            parts = value.split("-")
            if len(parts) not in (1, 2) or not all(part.isascii() and part.isdecimal() for part in parts):
                return True, False
            first, last = int(parts[0]), int(parts[-1])
            if not 0 <= first <= last <= 65535:
                return True, False
            if first <= port <= last:
                possible = known = True
        except ValueError:
            return True, False
    return possible, known
