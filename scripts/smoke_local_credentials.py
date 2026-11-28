"""Compose the synthetic local credential smoke checks."""

from smoke_extension_pairing import check_extension
from smoke_mcp_scope import check_mcp


def check_local_credentials(opener, base, csrf):
    check_extension(opener, base, csrf)
    check_mcp(opener, base, csrf)
