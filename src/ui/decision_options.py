from __future__ import annotations


def decision_options_for_packet(packet: dict[str, object]) -> list[str]:
    action_state = str(packet.get("action_state", "verify first")).lower()
    if action_state == "hold":
        return ["hold", "needs verification"]
    if action_state == "verify first":
        return ["needs verification", "hold"]
    return ["approved", "needs verification", "hold"]
