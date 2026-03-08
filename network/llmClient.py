"""
llmClient.py — LLM Client (OpenAI)
Sends network state + intent to OpenAI Responses API and returns structured decisions.
Logs every call to MetricsStore for GUI display.
"""

import json
import time
import re
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI


def _load_dotenv():
    dotenv_candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    for dotenv_path in dotenv_candidates:
        if not dotenv_path.exists():
            continue
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
SLICE_CACHE_TTL_S = float(os.getenv("SLICE_CACHE_TTL_S", "4"))
FULL_STATE_REFRESH_EVERY = int(os.getenv("LLM_FULL_STATE_REFRESH_EVERY", "0"))
SLICE_RECENT_FLOWS_LIMIT = int(os.getenv("SLICE_RECENT_FLOWS_LIMIT", "3"))
LLM_CALLS_LOG_FILE = os.getenv("LLM_CALLS_LOG_FILE", "network/llm_calls.jsonl")
TOPOLOGY_FILE = os.getenv("TOPOLOGY_FILE", "topology.json")
FIX_DEMO_MODE = os.getenv("FIX_DEMO_MODE", "").strip().lower()

SLICE_DESCRIPTIONS = {
    1: "High-priority slice: low latency, for ICMP and interactive traffic",
    2: "High-throughput slice: bulk transfer, for TCP and UDP traffic",
}

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

_PROMPT_TEMPLATES = {
    "slice_intent": "slice_intent.j2",
    "slice_intent_delta": "slice_intent_delta.j2",
    "anomaly_intent": "anomaly_intent.j2",
    "fix_intent": "fix_intent.j2",
    "query_user": "query_user.j2",
    "system": "system.j2",
}


class LLMClient:
    """Northbound LLM interface via OpenAI Responses API."""

    def __init__(self, api_key: str = OPENAI_KEY, model: str = OPENAI_MODEL, metrics=None):
        self.model   = model
        self.api_key = api_key
        self.client  = OpenAI(api_key=api_key) if api_key else None
        self.metrics = metrics  # MetricsStore reference for logging
        self.slice_cache_ttl_s = SLICE_CACHE_TTL_S
        self.full_state_refresh_every = max(0, FULL_STATE_REFRESH_EVERY)
        self.slice_recent_flows_limit = max(1, SLICE_RECENT_FLOWS_LIMIT)
        self._slice_cache = {}
        self._state_for_delta = None
        self._slice_queries = 0
        self._last_response_id = {
            "slice": None,
            "anomaly": None,
            "fix": None,
        }
        self.fix_demo_mode = FIX_DEMO_MODE
        self._fix_demo_cycle_idx = 0
        self.calls_log_file = self._resolve_calls_log_file(LLM_CALLS_LOG_FILE)

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    def ask_slice(self, src: str, dst: str, protocol: str, network_state: dict) -> dict:
        """
        Advanced LLM-based slice selection based on network conditions.
        """
        compact_state = self._compact_state_for_slice(network_state)
        cache_key = self._slice_cache_key(src, dst, protocol, compact_state)
        cached = self._slice_cache.get(cache_key)
        now = time.time()
        if cached and now - cached["ts"] <= self.slice_cache_ttl_s:
            result = cached["result"]
        else:
            self._slice_queries += 1
            mode, baseline_json, state_json = self._state_payload_for_slice(compact_state)
            intent_template = "slice_intent" if mode == "full" else "slice_intent_delta"
            intent = self._render_prompt(
                intent_template,
                src=src,
                dst=dst,
                protocol=protocol,
            )
            result = self._query(
                intent,
                query_kind="slice",
                mode=mode,
                baseline_json=baseline_json,
                state_json=state_json,
            )
            self._slice_cache[cache_key] = {"ts": now, "result": result}

        fallback_reason = result.get("reason", "")
        if fallback_reason in {"LLM unavailable", "Parse error"}:
            result = self._baseline_slice_decision(protocol, fallback_reason)

        slice_id = int(result.get("slice", 2))
        reason = result.get("reason", "No reason")

        print(f"[🤖 SLICE-LLM] {src}→{dst} → slice={slice_id} | {reason}")

        self._log("slice", f"{protocol} {src}->{dst}", result)

        return {
            "slice": slice_id,
            "reason": reason
        }

    def ask_anomaly(self, network_state: dict) -> dict:
        intent = self._render_prompt("anomaly_intent")
        compact_state = self._compact_state(network_state)
        result = self._query(
            intent,
            query_kind="anomaly",
            mode="full",
            baseline_json="",
            state_json=self._json_dumps(compact_state),
        )
        print(f"[🤖 ANOMALY] {result}")

        self._log("anomaly", "network state analysis", result)
        return {
            "anomaly": result.get("anomaly", False),
            "details": result.get("details", "No details."),
        }

    def ask_fix(self, network_state: dict, anomaly_details: str) -> dict:
        guided_details = self._apply_fix_demo_guidance(anomaly_details)
        intent = self._render_prompt("fix_intent", anomaly_details=guided_details)
        compact_state = self._compact_state(network_state)
        result = self._query(
            intent,
            query_kind="fix",
            mode="full",
            baseline_json="",
            state_json=self._json_dumps(compact_state),
        )
        if isinstance(result, dict):
            result["fix_source"] = "llm_direct"
        print(f"[🤖 FIX] {result}")

        self._log("fix", anomaly_details[:80], result)
        return result

    def _apply_fix_demo_guidance(self, anomaly_details: str) -> str:
        """
        Optional demo steering for fast scenario coverage.
        Enabled only when FIX_DEMO_MODE is set.
        Values: set_link_tc | add_link | remove_link | cycle
        """
        mode = self.fix_demo_mode
        if not mode:
            return anomaly_details

        forced_action = mode
        if mode == "cycle":
            sequence = ["set_link_tc", "add_link", "remove_link"]
            forced_action = sequence[self._fix_demo_cycle_idx % len(sequence)]
            self._fix_demo_cycle_idx += 1

        if forced_action not in {"set_link_tc", "add_link", "remove_link"}:
            return anomaly_details

        topo_summary, _ = self._topology_summary_for_slice()
        switches = topo_summary.get("switches", []) if isinstance(topo_summary, dict) else []
        switch_links = topo_summary.get("switch_links", []) if isinstance(topo_summary, dict) else []

        chosen = ("s1", "s2")
        if len(switches) >= 2:
            chosen = (switches[0], switches[1])
        if switch_links:
            first = switch_links[0]
            chosen = (str(first.get("a", chosen[0])), str(first.get("b", chosen[1])))

        s1, s2 = chosen

        if forced_action == "set_link_tc":
            hint = (
                f"\n\n[DEMO_MODE] For this run, you MUST return action 'set_link_tc' "
                f"with params {{\"node1\":\"{s1}\",\"node2\":\"{s2}\",\"bw\":20,\"delay\":\"3ms\"}}."
            )
        elif forced_action == "add_link":
            hint = (
                f"\n\n[DEMO_MODE] For this run, you MUST return action 'add_link' "
                f"with params {{\"node1\":\"{s1}\",\"node2\":\"{s2}\",\"bw\":50,\"delay\":\"2ms\"}}."
            )
        else:
            hint = (
                f"\n\n[DEMO_MODE] For this run, you MUST return action 'remove_link' "
                f"with params {{\"node1\":\"{s1}\",\"node2\":\"{s2}\"}}."
            )

        return anomaly_details + hint

    # ── PRIVATE ───────────────────────────────────────────────────────────────

    def _query(self, intent: str, query_kind: str,
               mode: str, baseline_json: str, state_json: str) -> dict:
        prompt = self._build_prompt(intent, mode, baseline_json, state_json)
        raw    = self._call_openai(prompt, query_kind=query_kind)
        parsed = self._parse_response(raw)
        if parsed.get("reason") == "Parse error":
            forced = self._request_final_json_after_reasoning(
                query_kind=query_kind,
                response_id=self._last_response_id.get(query_kind),
                force_json=True,
            )
            if forced:
                reparsed = self._parse_response(forced)
                if reparsed.get("reason") != "Parse error":
                    return reparsed
        return parsed

    def _build_prompt(self, intent: str, mode: str,
                      baseline_json: str, state_json: str) -> str:
        return self._render_prompt(
            "query_user",
            mode=mode,
            baseline_json=baseline_json,
            state_json=state_json,
            intent=intent,
        )

    @staticmethod
    def _json_dumps(data: dict) -> str:
        return json.dumps(data, separators=(",", ":"), sort_keys=True)

    def _compact_state(self, network_state: dict) -> dict:
        flows = network_state.get("flows", [])
        recent_flows = sorted(flows, key=lambda f: f.get("duration_sec", 999))[:5]
        anomaly_signals = network_state.get("anomaly_signals", {})
        if not isinstance(anomaly_signals, dict):
            anomaly_signals = {}
        return {
            "num_switches": network_state.get("num_switches", "?"),
            "num_flows":    network_state.get("num_flows", 0),
            "node_stats":   network_state.get("node_stats", {}),
            "anomaly_signals": anomaly_signals,
            "recent_flows": [
                {
                    "src":     f.get("match", {}).get("eth_src") or f.get("match", {}).get("dl_src"),
                    "dst":     f.get("match", {}).get("eth_dst") or f.get("match", {}).get("dl_dst"),
                    "action":  f.get("actions"),
                    "packets": f.get("packet_count", 0),
                    "dpid":    f.get("dpid"),
                }
                for f in recent_flows
            ],
        }

    def _compact_state_for_slice(self, network_state: dict) -> dict:
        flows = network_state.get("flows", [])
        recent_flows = sorted(flows, key=lambda f: f.get("duration_sec", 999))[:self.slice_recent_flows_limit]

        def queue_from_actions(actions):
            if not isinstance(actions, list):
                return 0
            for action in actions:
                if isinstance(action, dict) and action.get("type") == "SET_QUEUE":
                    return int(action.get("queue_id", 0) or 0)
                if isinstance(action, str):
                    match = re.search(r"SET_QUEUE\s*[:=]\s*(\d+)", action, re.IGNORECASE)
                    if match:
                        return int(match.group(1))
            return 0

        node_stats = network_state.get("node_stats", {}) or {}
        node_stats_compact = {
            node: {
                "tx": int(stats.get("tx", 0)),
                "rx": int(stats.get("rx", 0)),
                "d": int(stats.get("drops", 0)),
                "p": int(stats.get("packets", 0)),
            }
            for node, stats in node_stats.items()
        }

        q1_flows = 0
        q2_flows = 0
        q1_packets = 0
        q2_packets = 0
        for flow in flows:
            queue_id = queue_from_actions(flow.get("actions"))
            packets = int(flow.get("packet_count", 0) or 0)
            if queue_id == 1:
                q1_flows += 1
                q1_packets += packets
            elif queue_id == 2:
                q2_flows += 1
                q2_packets += packets

        total_drops = sum(int(stats.get("d", 0) or 0) for stats in node_stats_compact.values())

        topo_summary, topo_sig = self._topology_summary_for_slice()

        return {
            "ns": network_state.get("num_switches", "?"),
            "nf": network_state.get("num_flows", 0),
            "n": node_stats_compact,
            "topo_sig": topo_sig,
            "topo": topo_summary,
            "sp": {
                "q1_flows": q1_flows,
                "q2_flows": q2_flows,
                "q1_packets": q1_packets,
                "q2_packets": q2_packets,
                "total_drops": total_drops,
            },
            "rf": [
                {
                    "s": f.get("match", {}).get("eth_src") or f.get("match", {}).get("dl_src"),
                    "d": f.get("match", {}).get("eth_dst") or f.get("match", {}).get("dl_dst"),
                    "q": queue_from_actions(f.get("actions")),
                    "p": f.get("packet_count", 0),
                    "sw": f.get("dpid"),
                }
                for f in recent_flows
            ],
        }

    def _state_payload_for_slice(self, compact_state: dict):
        prev = self._state_for_delta or {}
        topo_changed = compact_state.get("topo_sig") != prev.get("topo_sig")

        if topo_changed:
            # Force a fresh full-context turn on topology updates.
            # This avoids reusing stale conversational memory for slice decisions.
            self._last_response_id["slice"] = None

        periodic_refresh_due = (
            self.full_state_refresh_every > 0
            and self._slice_queries > 0
            and self._slice_queries % self.full_state_refresh_every == 0
        )
        should_send_full = (
            self._state_for_delta is None
            or topo_changed
            or periodic_refresh_due
            or not self._last_response_id.get("slice")
        )
        if should_send_full:
            self._state_for_delta = compact_state
            return "full", "", self._json_dumps(compact_state)

        delta = {}

        if compact_state.get("ns") != prev.get("ns"):
            delta["ns"] = compact_state.get("ns")

        if compact_state.get("topo_sig") != prev.get("topo_sig"):
            delta["topo_changed"] = True
            delta["topo_sig"] = compact_state.get("topo_sig")
            delta["topo"] = compact_state.get("topo", {})

        prev_sp = prev.get("sp", {}) if isinstance(prev.get("sp"), dict) else {}
        curr_sp = compact_state.get("sp", {}) if isinstance(compact_state.get("sp"), dict) else {}
        if curr_sp != prev_sp:
            delta["sp"] = curr_sp

        prev_nf = int(prev.get("nf", 0) or 0)
        curr_nf = int(compact_state.get("nf", 0) or 0)
        if curr_nf != prev_nf:
            delta["nf"] = curr_nf
            delta["nf_delta"] = curr_nf - prev_nf

        prev_nodes = prev.get("n", {}) if isinstance(prev.get("n"), dict) else {}
        curr_nodes = compact_state.get("n", {}) if isinstance(compact_state.get("n"), dict) else {}
        node_delta = {}
        for node in sorted(set(prev_nodes.keys()) | set(curr_nodes.keys())):
            old_stats = prev_nodes.get(node, {})
            new_stats = curr_nodes.get(node, {})
            ds = {}
            for key in ("tx", "rx", "d", "p"):
                old_v = int(old_stats.get(key, 0) or 0)
                new_v = int(new_stats.get(key, 0) or 0)
                if new_v != old_v:
                    ds[key] = new_v - old_v
            if ds:
                node_delta[node] = ds
        if node_delta:
            delta["n_delta"] = node_delta

        prev_rf = prev.get("rf", []) if isinstance(prev.get("rf"), list) else []
        curr_rf = compact_state.get("rf", []) if isinstance(compact_state.get("rf"), list) else []
        prev_rf_keys = {
            (f.get("s"), f.get("d"), f.get("q"), f.get("sw"), f.get("p"))
            for f in prev_rf
            if isinstance(f, dict)
        }
        rf_add = [
            f for f in curr_rf
            if isinstance(f, dict)
            and (f.get("s"), f.get("d"), f.get("q"), f.get("sw"), f.get("p")) not in prev_rf_keys
        ]
        if rf_add:
            delta["rf_add"] = rf_add

        if not delta:
            delta = {"keep": True}

        self._state_for_delta = compact_state
        return "delta", "", self._json_dumps(delta)

    @staticmethod
    def _slice_cache_key(src: str, dst: str, protocol: str, compact_state: dict) -> str:
        seed = {
            "src": src,
            "dst": dst,
            "protocol": protocol,
            "num_flows": compact_state.get("nf"),
            "node_stats": compact_state.get("n"),
            "slice_pressure": compact_state.get("sp"),
            "recent_flows": compact_state.get("rf"),
            "topo_sig": compact_state.get("topo_sig"),
        }
        raw = json.dumps(seed, separators=(",", ":"), sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _topology_file_path() -> Path:
        root = Path(__file__).resolve().parents[1]

        env_path = Path(TOPOLOGY_FILE)
        if not env_path.is_absolute():
            env_path = root / env_path

        candidates = [
            env_path,
            root / "network" / "topology.json",
            root / "topology.json",
        ]

        # pick existing file with best topology richness
        best_path = candidates[0]
        best_score = -1
        for candidate in candidates:
            score = LLMClient._topology_quality_score(candidate)
            if score > best_score:
                best_score = score
                best_path = candidate

        return best_path

    @staticmethod
    def _topology_quality_score(path: Path) -> int:
        if not path.exists():
            return -1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            switches = data.get("switches", [])
            hosts = data.get("hosts", [])
            links = data.get("links", [])
            hs_links = [l for l in links if isinstance(l, dict) and l.get("type") == "h-s"]
            ss_links = [l for l in links if isinstance(l, dict) and l.get("type") == "s-s"]
            return len(switches) * 100 + len(hosts) * 50 + len(hs_links) * 20 + len(ss_links) * 10 + len(links)
        except Exception:
            return -1

    def _topology_summary_for_slice(self):
        """
        Build a compact topology summary and signature for slice decisions.
        Signature changes force the LLM to re-evaluate routing assumptions.
        """
        path = self._topology_file_path()
        try:
            if not path.exists():
                return {"switches": [], "switch_links": [], "host_uplinks": {}}, "missing"

            topo = json.loads(path.read_text(encoding="utf-8"))
            switches = sorted([str(s) for s in topo.get("switches", [])])

            switch_links = []
            host_uplinks = {}
            for link in topo.get("links", []):
                n1 = str(link.get("node1", ""))
                n2 = str(link.get("node2", ""))
                ltype = str(link.get("type", ""))

                if ltype == "s-s" and n1 and n2:
                    pair = sorted([n1, n2])
                    switch_links.append({
                        "a": pair[0],
                        "b": pair[1],
                        "bw": link.get("bw"),
                        "delay": link.get("delay"),
                    })

                if ltype == "h-s":
                    host = n1 if n1.startswith("h") else n2 if n2.startswith("h") else None
                    sw = n1 if n1.startswith("s") else n2 if n2.startswith("s") else None
                    if host and sw:
                        host_uplinks[host] = sw

            switch_links = sorted(
                switch_links,
                key=lambda x: (x.get("a", ""), x.get("b", ""))
            )
            host_uplinks = {k: host_uplinks[k] for k in sorted(host_uplinks.keys())}

            summary = {
                "switches": switches,
                "switch_links": switch_links,
                "host_uplinks": host_uplinks,
            }
            sig_raw = json.dumps(summary, separators=(",", ":"), sort_keys=True)
            sig = hashlib.sha1(sig_raw.encode("utf-8")).hexdigest()[:12]
            return summary, sig
        except Exception:
            return {"switches": [], "switch_links": [], "host_uplinks": {}}, "error"

    @staticmethod
    def _render_prompt(template_name: str, **context) -> str:
        template = _JINJA_ENV.get_template(_PROMPT_TEMPLATES[template_name])
        return template.render(**context).strip()

    def _call_openai(self, prompt: str, query_kind: str) -> str:
        if not self.client:
            print("[⚠️] OPENAI_API_KEY non configurata. Imposta la variabile in .env")
            self._append_model_call_log({
                "query_kind": query_kind,
                "status": "no_client",
                "prompt": prompt,
                "response": "",
                "error": "OPENAI_API_KEY not configured",
            })
            return ""

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"[🤖] OpenAI Responses → {self.model}")
                previous_response_id = self._last_response_id.get(query_kind)
                kwargs = {}
                use_memory = bool(previous_response_id and attempt == 1)
                if use_memory:
                    kwargs["previous_response_id"] = previous_response_id

                response = self.client.responses.create(
                    model=self.model,
                    instructions=self._render_prompt("system"),
                    input=[{
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }],
                    max_output_tokens=160,
                    **kwargs,
                )
                if getattr(response, "id", None):
                    self._last_response_id[query_kind] = response.id

                raw_text = self._extract_response_text(response)
                if raw_text:
                    self._append_model_call_log({
                        "query_kind": query_kind,
                        "status": "success",
                        "attempt": attempt,
                        "response_id": getattr(response, "id", None),
                        "model": self.model,
                        "prompt": prompt,
                        "response": raw_text,
                    })
                    return raw_text

                self._append_model_call_log({
                    "query_kind": query_kind,
                    "status": "empty_output",
                    "attempt": attempt,
                    "response_id": getattr(response, "id", None),
                    "model": self.model,
                    "prompt": prompt,
                    "response": "",
                    "output_types": self._summarize_response_output_types(response),
                })

                finalized = self._request_final_json_after_reasoning(
                    query_kind=query_kind,
                    response_id=getattr(response, "id", None),
                    force_json=False,
                )
                if finalized:
                    return finalized

                if use_memory and attempt < max_attempts:
                    self._last_response_id[query_kind] = None
                    continue
                return ""
            except Exception as e:
                msg = str(e)
                is_rate_limited = "rate_limit" in msg.lower() or "429" in msg
                if is_rate_limited and attempt < max_attempts:
                    wait_s = self._extract_retry_seconds(msg)
                    print(f"[⏳] OpenAI rate limit, retry tra {wait_s:.2f}s...")
                    self._append_model_call_log({
                        "query_kind": query_kind,
                        "status": "rate_limit_retry",
                        "attempt": attempt,
                        "model": self.model,
                        "prompt": prompt,
                        "response": "",
                        "error": msg,
                        "retry_in_s": round(wait_s, 3),
                    })
                    time.sleep(wait_s)
                    continue
                print(f"[⚠️] OpenAI error: {type(e).__name__}: {e}")
                self._append_model_call_log({
                    "query_kind": query_kind,
                    "status": "error",
                    "attempt": attempt,
                    "model": self.model,
                    "prompt": prompt,
                    "response": "",
                    "error": f"{type(e).__name__}: {e}",
                })
                return ""
        return ""

    @staticmethod
    def _extract_response_text(response) -> str:
        direct = getattr(response, "output_text", None)
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        chunks = []
        for item in getattr(response, "output", []) or []:
            item_type = getattr(item, "type", None)
            if item_type != "message":
                continue
            for content_item in getattr(item, "content", []) or []:
                text = getattr(content_item, "text", None)
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
                    continue
                maybe_value = getattr(content_item, "value", None)
                if isinstance(maybe_value, str) and maybe_value.strip():
                    chunks.append(maybe_value.strip())

        if chunks:
            return "\n".join(chunks).strip()

        try:
            payload = response.model_dump() if hasattr(response, "model_dump") else None
            if payload:
                extracted = LLMClient._extract_first_text_from_payload(payload)
                if extracted:
                    return extracted
        except Exception:
            pass

        return ""

    @staticmethod
    def _extract_first_text_from_payload(payload) -> str:
        if isinstance(payload, dict):
            for key in ("text", "output_text", "value"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                extracted = LLMClient._extract_first_text_from_payload(value)
                if extracted:
                    return extracted
        elif isinstance(payload, list):
            for value in payload:
                extracted = LLMClient._extract_first_text_from_payload(value)
                if extracted:
                    return extracted
        return ""

    @staticmethod
    def _summarize_response_output_types(response):
        summary = []
        for item in getattr(response, "output", []) or []:
            summary.append(getattr(item, "type", "unknown"))
        return summary

    def _request_final_json_after_reasoning(self, query_kind: str, response_id: Optional[str], force_json: bool = False) -> str:
        if not response_id:
            return ""
        try:
            followup_text = (
                "Return ONLY a valid JSON object that matches the requested schema. "
                "No explanation, no markdown, no extra text."
                if force_json else
                "Provide the final answer now as valid JSON only."
            )
            follow_up = self.client.responses.create(
                model=self.model,
                previous_response_id=response_id,
                input=[{
                    "role": "user",
                    "content": [{"type": "input_text", "text": followup_text}],
                }],
                max_output_tokens=160,
            )

            if getattr(follow_up, "id", None):
                self._last_response_id[query_kind] = follow_up.id

            text = self._extract_response_text(follow_up)
            self._append_model_call_log({
                "query_kind": query_kind,
                "status": "followup_after_reasoning",
                "attempt": "followup",
                "response_id": getattr(follow_up, "id", None),
                "model": self.model,
                "prompt": followup_text,
                "response": text,
                "output_types": self._summarize_response_output_types(follow_up),
            })
            return text
        except Exception as e:
            self._append_model_call_log({
                "query_kind": query_kind,
                "status": "followup_error",
                "attempt": "followup",
                "model": self.model,
                "prompt": "Return ONLY valid JSON",
                "response": "",
                "error": f"{type(e).__name__}: {e}",
            })
            return ""

    @staticmethod
    def _baseline_slice_decision(protocol: str, fallback_reason: str) -> dict:
        proto = str(protocol or "").upper()
        slice_id = 1 if proto == "ICMP" else 2
        reason = (
            f"Baseline fallback ({fallback_reason}): "
            + ("ICMP -> Slice 1 (low-latency)." if slice_id == 1 else "TCP/UDP -> Slice 2 (high-throughput).")
        )
        return {"slice": slice_id, "reason": reason}

    @staticmethod
    def _resolve_calls_log_file(path_value: str) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[1] / path

    def _append_model_call_log(self, payload: dict):
        entry = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "log_type": "llm_model_call",
            **payload,
        }
        try:
            self.calls_log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.calls_log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @staticmethod
    def _extract_retry_seconds(error_message: str) -> float:
        match = re.search(r"try again in\s*([0-9]+(?:\.[0-9]+)?)s", error_message.lower())
        if match:
            return max(1.0, float(match.group(1)) + 0.2)
        return 2.0

    def _parse_response(self, raw: str) -> dict:
        if not raw:
            return {"slice": 2, "anomaly": False, "reason": "LLM unavailable"}
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
        print(f"[⚠️] LLM response non parsabile: {raw[:200]}")
        return {"slice": 2, "anomaly": False, "reason": "Parse error"}

    def _log(self, call_type: str, prompt_summary: str, response: dict):
        """Log the LLM call to MetricsStore if available."""
        if self.metrics:
            self.metrics.add_llm_log(call_type, prompt_summary, response)