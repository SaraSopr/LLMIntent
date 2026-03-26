"""
ryuController.py — Wrapper for RYU REST API interactions.
"""

import os
import requests
from typing import Optional

RYU_REST = os.getenv("RYU_REST_URL", "http://127.0.0.1:8080")


class RyuController:
    """Handles all communication with the RYU SDN controller via REST."""

    def __init__(self, base_url: str = RYU_REST, net=None):
        self.base_url = base_url
        self.net = net

    def set_net(self, net):
        """Attach live Mininet instance for write operations on links."""
        self.net = net

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
            print(f"[✅] Flow → dpid={dpid} port={port} {queue_label}, HTTP {r.status_code}")
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
            print(f"[🚫] Drop rule → dpid={dpid} port={port} mac={src_mac}, HTTP {r.status_code}")
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

    # ── GENERIC WRITE ACTIONS (MININET WRAPPER) ─────────────────────────────

    @staticmethod
    def _delay_to_tc(delay: Optional[str]) -> Optional[str]:
        if delay is None:
            return None
        value = str(delay).strip()
        if not value:
            return None
        if value.endswith(("ms", "s", "us")):
            return value
        return f"{value}ms"

    def set_link_tc(self, node1: str, node2: str,
                    bw: Optional[float] = None,
                    delay: Optional[str] = None) -> dict:
        if self.net is None:
            return {
                "success": False,
                "action": "set_link_tc",
                "node1": node1,
                "node2": node2,
                "error": "Mininet net not connected to controller",
            }

        try:
            n1 = self.net.get(node1)
            n2 = self.net.get(node2)
            links = self.net.linksBetween(n1, n2)
            if not links:
                return {
                    "success": False,
                    "action": "set_link_tc",
                    "node1": node1,
                    "node2": node2,
                    "error": "link not found",
                }

            params = {}
            if bw is not None:
                params["bw"] = float(bw)
            tc_delay = self._delay_to_tc(delay)
            if tc_delay is not None:
                params["delay"] = tc_delay

            if not params:
                return {
                    "success": False,
                    "action": "set_link_tc",
                    "node1": node1,
                    "node2": node2,
                    "error": "no valid TC parameter (bw/delay)",
                }

            for link in links:
                link.intf1.config(**params)
                link.intf2.config(**params)

            return {
                "success": True,
                "action": "set_link_tc",
                "node1": node1,
                "node2": node2,
                "params": params,
            }
        except Exception as e:
            return {
                "success": False,
                "action": "set_link_tc",
                "node1": node1,
                "node2": node2,
                "error": str(e),
            }

    def add_link(self, node1: str, node2: str,
                 bw: Optional[float] = None,
                 delay: Optional[str] = None) -> dict:
        if self.net is None:
            return {
                "success": False,
                "action": "add_link",
                "node1": node1,
                "node2": node2,
                "error": "Mininet net not connected to controller",
            }

        try:
            n1 = self.net.get(node1)
            n2 = self.net.get(node2)

            if self.net.linksBetween(n1, n2):
                return {
                    "success": False,
                    "action": "add_link",
                    "node1": node1,
                    "node2": node2,
                    "error": "link already exists",
                }

            link_params = {}
            if bw is not None:
                link_params["bw"] = float(bw)
            tc_delay = self._delay_to_tc(delay)
            if tc_delay is not None:
                link_params["delay"] = tc_delay

            link = self.net.addLink(n1, n2, **link_params)
            return {
                "success": True,
                "action": "add_link",
                "node1": node1,
                "node2": node2,
                "intf1": getattr(link.intf1, "name", None),
                "intf2": getattr(link.intf2, "name", None),
                "params": link_params,
            }
        except Exception as e:
            return {
                "success": False,
                "action": "add_link",
                "node1": node1,
                "node2": node2,
                "error": str(e),
            }

    def remove_link(self, node1: str, node2: str) -> dict:
        if self.net is None:
            return {
                "success": False,
                "action": "remove_link",
                "node1": node1,
                "node2": node2,
                "error": "Mininet net not connected to controller",
            }

        try:
            n1 = self.net.get(node1)
            n2 = self.net.get(node2)
            links = self.net.linksBetween(n1, n2)
            if not links:
                return {
                    "success": False,
                    "action": "remove_link",
                    "node1": node1,
                    "node2": node2,
                    "error": "link not present",
                }

            for link in links:
                self.net.delLink(link)

            return {
                "success": True,
                "action": "remove_link",
                "node1": node1,
                "node2": node2,
                "removed": len(links),
            }
        except Exception as e:
            return {
                "success": False,
                "action": "remove_link",
                "node1": node1,
                "node2": node2,
                "error": str(e),
            }