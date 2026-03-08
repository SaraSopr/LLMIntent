"""
networkMonitor.py — Monitors blocked traffic and anomalies via RYU + LLM.
"""

import json
import time
import threading
import os
from pathlib import Path
from datetime import datetime

from metricStore   import MetricsStore
from ryuController import RyuController
from llmClient     import LLMClient

TOPOLOGY_FILE = "topology.json"
GUI_ACTIONS_FILE = os.getenv("GUI_ACTIONS_FILE", "network/gui_actions.jsonl")
GUI_ACTIONS_RESULTS_FILE = os.getenv("GUI_ACTIONS_RESULTS_FILE", "network/gui_actions_results.jsonl")


class NetworkMonitor:
    """
    Continuously monitors the network for:
    - Blocked traffic (drop counters on priority-65535 flows)
    - Anomalies detected by the LLM → automatic fix via RYU
    Also refreshes the flow table in MetricsStore.
    """

    def __init__(self,
                 metrics: MetricsStore,
                 ryu: RyuController,
                 llm: LLMClient,
                 stop_event: threading.Event,
                 num_switches: int,
                 anomaly_check_interval: int = 30):
        self.metrics                = metrics
        self.ryu                    = ryu
        self.llm                    = llm
        self.stop_event             = stop_event
        self.num_switches           = num_switches
        self.anomaly_check_interval = anomaly_check_interval
        self._topo_map              = self._load_topology()
        self._last_drop_counts      = {}
        self._last_anomaly_check    = time.time()  # delay primo check
        self._prev_num_flows        = 0
        self._processed_action_ids  = set()
        self._actions_file_position = 0
        self._actions_file_path     = self._resolve_path(GUI_ACTIONS_FILE)
        self._actions_results_path  = self._resolve_path(GUI_ACTIONS_RESULTS_FILE)

    # ── MAIN LOOP ─────────────────────────────────────────────────────────────

    def monitor_blocked_traffic(self):
        while not self.stop_event.is_set():
            self._process_gui_actions()
            self._check_drops()
            self._refresh_flow_table()
            self._maybe_check_anomalies()
            time.sleep(2)

    # ── PRIVATE ───────────────────────────────────────────────────────────────

    def _check_drops(self):
        try:
            flows = self.ryu.get_flows(self.num_switches)
            for flow in flows:
                if flow.get("priority") != 65535:
                    continue
                match    = flow.get("match", {})
                curr     = flow.get("packet_count", 0)
                mac      = match.get("eth_src") or match.get("eth_dst")
                if not mac:
                    continue
                prev = self._last_drop_counts.get(mac, 0)
                if curr > prev:
                    drops     = curr - prev
                    host_name = self._mac_to_host(mac)
                    print(f"[🚫 ALERT] {host_name} ({mac}): {drops} nuovi drop")
                    self._last_drop_counts[mac] = curr
        except Exception as e:
            print(f"[⚠️] _check_drops error: {e}")

    def _refresh_flow_table(self):
        flows = self.ryu.get_flows(self.num_switches)
        flows.sort(key=lambda f: f.get("duration_sec", 0))
        self.metrics.update_flows(flows)
        self.metrics.persist()

    def _maybe_check_anomalies(self):
        """Periodically ask the LLM to detect anomalies and apply fixes."""
        now = time.time()
        if now - self._last_anomaly_check < self.anomaly_check_interval:
            return

        self._last_anomaly_check = now
        network_state = self.ryu.get_network_state(self.num_switches)
        snapshot = self.metrics.snapshot()
        network_state["node_stats"] = snapshot.get("node_stats", {})

        signals = self._build_anomaly_signals(network_state, snapshot)
        network_state["anomaly_signals"] = signals

        heuristic_result = self._heuristic_anomaly_decision(signals)

        # 1. Detect anomaly
        llm_result = self.llm.ask_anomaly(network_state)
        result = self._merge_anomaly_results(llm_result, heuristic_result)

        if result.get("anomaly"):
            print(f"[🤖 ANOMALY] {result.get('details')}")

            # 2. Ask/apply fix directly from LLM decision
            fix = self.llm.ask_fix(network_state, result.get("details", ""))
            self._apply_fix(fix)
        else:
            print("[🤖 LLM] Nessuna anomalia rilevata.")

    def _build_anomaly_signals(self, network_state: dict, snapshot: dict) -> dict:
        events = snapshot.get("events", [])[:40]
        total_events = len(events)
        dropped = sum(1 for e in events if not e.get("accepted"))
        accepted = total_events - dropped

        latencies = [float(e.get("latency_ms", 0) or 0) for e in events]
        latencies_sorted = sorted(latencies)
        if latencies_sorted:
            p95_idx = int(0.95 * (len(latencies_sorted) - 1))
            latency_p95 = latencies_sorted[p95_idx]
            latency_avg = sum(latencies_sorted) / len(latencies_sorted)
        else:
            latency_p95 = 0.0
            latency_avg = 0.0

        icmp_lat = [float(e.get("latency_ms", 0) or 0) for e in events if str(e.get("proto", "")).upper() == "ICMP"]
        tcp_lat = [float(e.get("latency_ms", 0) or 0) for e in events if str(e.get("proto", "")).upper() == "TCP"]
        udp_lat = [float(e.get("latency_ms", 0) or 0) for e in events if str(e.get("proto", "")).upper() == "UDP"]

        flows = network_state.get("flows", []) or []
        blocked_drop_rules = sum(1 for f in flows if int(f.get("priority", 0) or 0) == 65535)

        num_flows = int(network_state.get("num_flows", 0) or 0)
        flow_growth = num_flows - self._prev_num_flows
        self._prev_num_flows = num_flows

        src_counts = {}
        for e in events:
            src = e.get("src")
            if not src:
                continue
            src_counts[src] = src_counts.get(src, 0) + 1
        max_src_share = (max(src_counts.values()) / total_events) if total_events else 0.0

        return {
            "window_events": total_events,
            "accepted": accepted,
            "dropped": dropped,
            "drop_rate": round((dropped / total_events), 4) if total_events else 0.0,
            "latency_avg_ms": round(latency_avg, 2),
            "latency_p95_ms": round(latency_p95, 2),
            "icmp_count": len(icmp_lat),
            "icmp_avg_ms": round((sum(icmp_lat) / len(icmp_lat)), 2) if icmp_lat else 0.0,
            "tcp_count": len(tcp_lat),
            "tcp_avg_ms": round((sum(tcp_lat) / len(tcp_lat)), 2) if tcp_lat else 0.0,
            "udp_count": len(udp_lat),
            "udp_avg_ms": round((sum(udp_lat) / len(udp_lat)), 2) if udp_lat else 0.0,
            "num_flows": num_flows,
            "flow_growth": flow_growth,
            "blocked_drop_rules": blocked_drop_rules,
            "max_src_share": round(max_src_share, 4),
        }

    @staticmethod
    def _heuristic_anomaly_decision(signals: dict) -> dict:
        reasons = []

        events = int(signals.get("window_events", 0) or 0)
        drop_rate = float(signals.get("drop_rate", 0.0) or 0.0)
        icmp_count = int(signals.get("icmp_count", 0) or 0)
        icmp_avg = float(signals.get("icmp_avg_ms", 0.0) or 0.0)
        p95 = float(signals.get("latency_p95_ms", 0.0) or 0.0)
        flow_growth = int(signals.get("flow_growth", 0) or 0)
        max_src_share = float(signals.get("max_src_share", 0.0) or 0.0)

        if events >= 12 and drop_rate >= 0.20:
            reasons.append(f"drop rate elevato ({drop_rate * 100:.1f}% su {events} eventi)")
        if icmp_count >= 5 and icmp_avg >= 350.0:
            reasons.append(f"latenza ICMP anomala ({icmp_avg:.1f} ms)")
        if events >= 12 and p95 >= 2500.0:
            reasons.append(f"latenza p95 molto alta ({p95:.1f} ms)")
        if flow_growth >= 60 and max_src_share >= 0.75:
            reasons.append(
                f"spike flussi con sorgente dominante (Δflow={flow_growth}, src_share={max_src_share * 100:.1f}%)"
            )

        if reasons:
            return {"anomaly": True, "details": "; ".join(reasons), "source": "heuristic"}
        return {"anomaly": False, "details": "no heuristic trigger", "source": "heuristic"}

    @staticmethod
    def _merge_anomaly_results(llm_result: dict, heuristic_result: dict) -> dict:
        llm_anomaly = bool(llm_result.get("anomaly"))
        heur_anomaly = bool(heuristic_result.get("anomaly"))

        if llm_anomaly and heur_anomaly:
            llm_details = llm_result.get("details", "")
            heur_details = heuristic_result.get("details", "")
            return {
                "anomaly": True,
                "details": f"LLM + Heuristic: {llm_details} | {heur_details}".strip(),
            }

        if llm_anomaly:
            return {
                "anomaly": True,
                "details": llm_result.get("details", "anomalia rilevata da LLM"),
            }

        if heur_anomaly:
            return {
                "anomaly": True,
                "details": f"Heuristic anomaly: {heuristic_result.get('details', '')}".strip(),
            }

        return {
            "anomaly": False,
            "details": llm_result.get("details", "Nessuna anomalia"),
        }

    @staticmethod
    def _normalize_switch_ref(value):
        """Normalize switch references from LLM, e.g. '1' -> 's1'."""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return text
        if text.startswith("s"):
            return text
        if text.isdigit():
            return f"s{text}"
        return text

    def _apply_fix(self, fix: dict):
        """Apply the fix proposed by the LLM."""
        action = fix.get("action")
        host_ref = fix.get("host")
        params = fix.get("params") if isinstance(fix.get("params"), dict) else {}
        reason = fix.get("reason", "")

        if action == "block_host" and host_ref:
            link = self._resolve_host_link(host_ref)
            if link:
                self.ryu.install_drop_rule(
                    dpid=link.get("dpid"),
                    port=link.get("port"),
                    src_mac=link.get("mac"),
                )
                resolved_host = link.get("node1", host_ref)
                print(f"[🔧 FIX] {resolved_host} bloccato (ref={host_ref}) — {reason}")
                return {"success": True}
            else:
                print(f"[⚠️] FIX: host ref '{host_ref}' non trovata in topology.json")
                return {"success": False, "error": f"host ref '{host_ref}' non trovata in topology.json"}

        elif action == "set_link_tc":
            node1 = self._normalize_switch_ref(params.get("node1"))
            node2 = self._normalize_switch_ref(params.get("node2"))
            if not node1 or not node2:
                print("[⚠️] FIX set_link_tc: parametri mancanti (node1/node2)")
                return {"success": False, "error": "parametri mancanti (node1/node2)"}

            result = self.ryu.set_link_tc(
                node1=node1,
                node2=node2,
                bw=params.get("bw"),
                delay=params.get("delay"),
            )
            if result.get("success"):
                self._update_topology_link_tc(node1, node2, params.get("bw"), params.get("delay"))
                print(f"[🔧 FIX] TC aggiornato su {node1}<->{node2} — {reason}")
                return {"success": True}
            else:
                err = result.get("error", "errore sconosciuto")
                print(f"[⚠️] FIX set_link_tc fallita: {err}")
                return {"success": False, "error": err}

        elif action == "add_link":
            node1 = self._normalize_switch_ref(params.get("node1"))
            node2 = self._normalize_switch_ref(params.get("node2"))
            if not node1 or not node2:
                print("[⚠️] FIX add_link: parametri mancanti (node1/node2)")
                return {"success": False, "error": "parametri mancanti (node1/node2)"}

            if not (str(node1).startswith("s") and str(node2).startswith("s")):
                err = "add_link consentito solo tra switch (sX-sY)"
                print(f"[⚠️] FIX add_link fallita: {err}")
                return {"success": False, "error": err}

            result = self.ryu.add_link(
                node1=node1,
                node2=node2,
                bw=params.get("bw"),
                delay=params.get("delay"),
            )
            if result.get("success"):
                self._add_topology_link(node1, node2, params.get("bw"), params.get("delay"))
                print(f"[🔧 FIX] Link aggiunto {node1}<->{node2} — {reason}")
                return {"success": True}
            else:
                err = result.get("error", "errore sconosciuto")
                print(f"[⚠️] FIX add_link fallita: {err}")
                return {"success": False, "error": err}

        elif action == "remove_link":
            node1 = self._normalize_switch_ref(params.get("node1"))
            node2 = self._normalize_switch_ref(params.get("node2"))
            if not node1 or not node2:
                print("[⚠️] FIX remove_link: parametri mancanti (node1/node2)")
                return {"success": False, "error": "parametri mancanti (node1/node2)"}

            if not (str(node1).startswith("s") and str(node2).startswith("s")):
                err = "remove_link consentito solo tra switch (sX-sY)"
                print(f"[⚠️] FIX remove_link fallita: {err}")
                return {"success": False, "error": err}

            result = self.ryu.remove_link(node1=node1, node2=node2)
            if result.get("success"):
                self._remove_topology_link(node1, node2)
                print(f"[🔧 FIX] Link rimosso {node1}<->{node2} — {reason}")
                return {"success": True}
            else:
                err = result.get("error", "errore sconosciuto")
                print(f"[⚠️] FIX remove_link fallita: {err}")
                return {"success": False, "error": err}

        elif action == "none":
            print(f"[🔧 FIX] Nessuna azione necessaria — {reason}")
            return {"success": True}

        else:
            print(f"[⚠️] FIX: azione sconosciuta '{action}'")
            return {"success": False, "error": f"azione sconosciuta '{action}'"}

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _mac_to_host(self, mac: str) -> str:
        for link in self._topo_map.get("links", []):
            if link.get("mac") == mac:
                return link.get("node1", "unknown")
        return "unknown"

    def _resolve_host_link(self, host_ref: str):
        """Resolve LLM host reference (hostname/mac/ip) to topology h-s link."""
        ref = str(host_ref).strip().lower()
        for link in self._topo_map.get("links", []):
            if link.get("type") != "h-s":
                continue
            node1 = str(link.get("node1", "")).lower()
            node2 = str(link.get("node2", "")).lower()
            mac = str(link.get("mac", "")).lower()
            ip = str(link.get("ip", "")).lower()
            if ref in {node1, node2, mac, ip}:
                return link
        return None

    def _load_topology(self) -> dict:
        try:
            with open(TOPOLOGY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"links": []}

    @staticmethod
    def _resolve_path(path_value: str) -> Path:
        p = Path(path_value)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parents[1] / p

    def _process_gui_actions(self):
        path = self._actions_file_path
        if not path.exists():
            return

        try:
            file_size = path.stat().st_size
            if file_size < self._actions_file_position:
                self._actions_file_position = 0

            with open(path, "r", encoding="utf-8") as f:
                f.seek(self._actions_file_position)
                new_lines = f.readlines()
                self._actions_file_position = f.tell()
        except Exception as e:
            print(f"[⚠️] GUI action queue read error: {e}")
            return

        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            request_id = payload.get("request_id")
            if not request_id or request_id in self._processed_action_ids:
                continue

            self._processed_action_ids.add(request_id)
            result = {
                "request_id": request_id,
                "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
                "source": payload.get("source", "gui"),
                "action": payload.get("action"),
                "success": False,
            }

            try:
                exec_result = self._apply_fix(payload)
                if isinstance(exec_result, dict):
                    result["success"] = bool(exec_result.get("success"))
                    if not result["success"]:
                        result["error"] = exec_result.get("error", "action execution failed")
                else:
                    ok = bool(exec_result)
                    result["success"] = ok
                    if not ok:
                        result["error"] = "action execution failed"
            except Exception as e:
                result["error"] = str(e)

            self._append_action_result(result)

    def _append_action_result(self, result: dict):
        try:
            self._actions_results_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._actions_results_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[⚠️] GUI action result write error: {e}")

    def _persist_topology(self):
        try:
            with open(TOPOLOGY_FILE, "w") as f:
                json.dump(self._topo_map, f, indent=4)
        except Exception as e:
            print(f"[⚠️] Persist topology fallita: {e}")

    @staticmethod
    def _same_link(a1: str, a2: str, b1: str, b2: str) -> bool:
        return {str(a1), str(a2)} == {str(b1), str(b2)}

    def _find_link_entry(self, node1: str, node2: str):
        for link in self._topo_map.get("links", []):
            if self._same_link(link.get("node1"), link.get("node2"), node1, node2):
                return link
        return None

    def _update_topology_link_tc(self, node1: str, node2: str, bw=None, delay=None):
        link = self._find_link_entry(node1, node2)
        if not link:
            return
        if bw is not None:
            link["bw"] = bw
        if delay is not None:
            link["delay"] = delay
        self._persist_topology()

    def _add_topology_link(self, node1: str, node2: str, bw=None, delay=None):
        if self._find_link_entry(node1, node2):
            self._update_topology_link_tc(node1, node2, bw=bw, delay=delay)
            return
        link_type = "s-s" if str(node1).startswith("s") and str(node2).startswith("s") else "dynamic"
        new_link = {
            "node1": node1,
            "node2": node2,
            "type": link_type,
        }
        if bw is not None:
            new_link["bw"] = bw
        if delay is not None:
            new_link["delay"] = delay
        self._topo_map.setdefault("links", []).append(new_link)
        self._persist_topology()

    def _remove_topology_link(self, node1: str, node2: str):
        links = self._topo_map.get("links", [])
        filtered = [
            link for link in links
            if not self._same_link(link.get("node1"), link.get("node2"), node1, node2)
        ]
        if len(filtered) != len(links):
            self._topo_map["links"] = filtered
            self._persist_topology()