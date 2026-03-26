"""
metricStore.py — Thread-safe metrics store for the SDN experiment.
Written to metrics.json for the GUI to consume.
"""

import json
import time
import threading
from collections import deque

METRICS_FILE  = "metrics.json"
MAX_EVENTS    = 200
MAX_LLM_LOGS  = 50


class MetricsStore:
    """Thread-safe store that the GUI reads via metrics.json."""

    def __init__(self):
        self._lock      = threading.Lock()
        self.events     = deque(maxlen=MAX_EVENTS)
        self.node_stats = {}
        self.flow_table = []
        self.llm_logs   = deque(maxlen=MAX_LLM_LOGS)  # LLM calls log
        self.start_time = time.time()
        self.running    = True

    def add_event(self, src: str, dst: str, protocol: str,
                  accepted: bool, latency_ms: float = 0.0,
                  slice_id: int = 0, reason: str = ""):
        with self._lock:
            ts = round(time.time() - self.start_time, 2)
            event = {
                "ts":         ts,
                "src":        src,
                "dst":        dst,
                "proto":      protocol,
                "accepted":   accepted,
                "latency_ms": round(latency_ms, 2),
                "slice":      slice_id,
                "reason":     reason,
            }
            self.events.appendleft(event)

            for node in (src, dst):
                if node not in self.node_stats:
                    self.node_stats[node] = {"tx": 0, "rx": 0, "drops": 0, "packets": 0}

            self.node_stats[src]["tx"]      += 1
            self.node_stats[dst]["rx"]      += 1
            self.node_stats[src]["packets"] += 1
            self.node_stats[dst]["packets"] += 1
            if not accepted:
                self.node_stats[src]["drops"] += 1

    def add_llm_log(self, call_type: str, prompt_summary: str, response: dict):
        """
        Log an LLM call with its response.
        call_type: 'slice' | 'anomaly' | 'fix'
        """
        with self._lock:
            ts = round(time.time() - self.start_time, 2)
            self.llm_logs.appendleft({
                "ts":       ts,
                "type":     call_type,
                "prompt":   prompt_summary,
                "response": response,
            })

    def update_flows(self, flows: list):
        with self._lock:
            self.flow_table = flows

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running":    self.running,
                "uptime_s":   round(time.time() - self.start_time, 1),
                "events":     list(self.events),
                "node_stats": dict(self.node_stats),
                "flow_table": list(self.flow_table),
                "llm_logs":   list(self.llm_logs),
                "ts_updated": time.time(),
            }

    def persist(self, filepath: str = METRICS_FILE):
        snap = self.snapshot()
        try:
            with open(filepath, "w") as f:
                json.dump(snap, f, indent=4)
        except Exception as e:
            print(f"[⚠️] Error writing metrics: {e}")