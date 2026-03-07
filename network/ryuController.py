"""
ryuController.py — Wrapper for RYU REST API interactions.
"""

import os
import requests

RYU_REST = os.getenv("RYU_REST_URL", "http://127.0.0.1:8080")


class RyuController:
    """Handles all communication with the RYU SDN controller via REST."""

    def __init__(self, base_url: str = RYU_REST):
        self.base_url = base_url

    # ── QUERIES ───────────────────────────────────────────────────────────────

    def get_switches(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/stats/switches", timeout=2)
            return r.json()
        except Exception as e:
            print(f"[⚠️] GET switches: {e}")
            return []

    def get_flows(self, num_switches: int) -> list:
        """Fetch all flows from all switches. Returns a flat list."""
        flows = []
        try:
            for dpid in range(1, num_switches + 1):
                r = requests.get(f"{self.base_url}/stats/flow/{dpid}", timeout=1)
                if r.status_code == 200:
                    for f in r.json().get(str(dpid), []):
                        f["dpid"] = dpid
                        flows.append(f)
        except Exception:
            pass
        return flows

    def get_port_stats(self, dpid: int) -> dict:
        try:
            r = requests.get(f"{self.base_url}/stats/port/{dpid}", timeout=2)
            return r.json()
        except Exception:
            return {}

    def get_network_state(self, num_switches: int) -> dict:
        """
        Build a compact network state snapshot suitable for LLM consumption.
        Includes switches, flows, and port stats.
        """
        switches = self.get_switches()
        flows    = self.get_flows(num_switches)

        port_stats = {}
        for dpid in range(1, num_switches + 1):
            stats = self.get_port_stats(dpid)
            if stats:
                port_stats[str(dpid)] = stats

        return {
            "switches":   switches,
            "num_flows":  len(flows),
            "flows":      flows[:20],
            "port_stats": port_stats,
        }

    # ── COMMANDS ──────────────────────────────────────────────────────────────

    def install_flow(self, dpid: int, port: int,
                     src_mac: str = None, dst_mac: str = None,
                     priority: int = 100, queue_id: int = 0,
                     in_port: int = None):
        """
        Install a flow rule on a switch.
        queue_id: 0 = default, 1 = high-priority slice, 2 = high-throughput slice
        """
        match = {}
        if in_port is not None:
            match["in_port"] = int(in_port)
        if src_mac:
            match["eth_src"] = src_mac
        if dst_mac:
            match["eth_dst"] = dst_mac

        actions = []
        if queue_id > 0:
            actions.append({"type": "SET_QUEUE", "queue_id": queue_id})
        actions.append({"type": "OUTPUT", "port": int(port)})

        flow = {
            "dpid":     dpid,
            "priority": priority,
            "match":    match,
            "actions":  actions,
        }
        try:
            r = requests.post(
                f"{self.base_url}/stats/flowentry/add",
                json=flow,
                timeout=2,
            )
            queue_label = f"queue={queue_id}" if queue_id > 0 else "no queue"
            print(f"[✅] Flow → dpid={dpid} porta={port} {queue_label}, HTTP {r.status_code}")
        except Exception as e:
            print(f"[⚠️] install_flow: {e}")

    def install_drop_rule(self, dpid: int, port: int, src_mac: str):
        """Install a high-priority drop rule to block a host."""
        flow = {
            "dpid":     dpid,
            "priority": 65535,
            "match":    {"in_port": int(port), "eth_src": src_mac},
            "actions":  [],
        }
        try:
            r = requests.post(
                f"{self.base_url}/stats/flowentry/add",
                json=flow,
                timeout=2,
            )
            print(f"[🚫] Drop rule → dpid={dpid} porta={port} mac={src_mac}, HTTP {r.status_code}")
        except Exception as e:
            print(f"[⚠️] install_drop_rule: {e}")

    def delete_flow(self, dpid: int, match: dict):
        body = {"dpid": dpid, "match": match}
        try:
            requests.post(
                f"{self.base_url}/stats/flowentry/delete",
                json=body,
                timeout=2,
            )
        except Exception as e:
            print(f"[⚠️] delete_flow: {e}")