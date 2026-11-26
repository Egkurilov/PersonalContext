from typing import BinaryIO

STAGES = {
    "PersonalContext: preparing Python dependencies",
    "PersonalContext: checking Git hooks",
    "PersonalContext: installing frontend dependencies",
    "PersonalContext: building frontend",
    "PersonalContext: starting application",
}


def observe_setup(stream: BinaryIO, state: dict[str, str]) -> None:
    for raw in stream:
        line = raw.decode("utf-8", errors="replace").strip()
        if line in STAGES:
            state["stage"] = line
        lowered = line.lower()
        if "enotcached" in lowered or "not found in the cache" in lowered or "network is disabled" in lowered:
            state["reason"] = "offline dependency cache incomplete"
        elif "no module named uv" in lowered:
            state["reason"] = "uv Python module missing"
