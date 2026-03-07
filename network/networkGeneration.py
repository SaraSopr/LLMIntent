"""
networkGeneration.py — SDN Experiment Engine

Architecture:
  MetricsStore     — thread-safe metrics & JSON persistence
  RyuController    — RYU REST API wrapper
  LLMClient        — Ollama/Groq/OpenAI northbound interface
  TrafficManager   — traffic generation + LLM-driven slice assignment
  NetworkMonitor   — drop detection + LLM anomaly detection
  SDNExperiment    — orchestrator (Mininet setup, thread management)

Slices:
  Slice 1 (Queue 1) — High-priority: low latency (ICMP, interactive)
  Slice 2 (Queue 2) — High-throughput: bulk transfer (TCP, UDP)
"""

import os
import time
import subprocess
import threading
from pathlib import Path

from mininet.net   import Mininet
from mininet.node  import OVSKernelSwitch, RemoteController
from mininet.link  import TCLink
from mininet.clean import cleanup

from metricStore        import MetricsStore
from ryuController      import RyuController
from llmClient          import LLMClient
from trafficManager     import TrafficManager
from networkMonitor     import NetworkMonitor
from networksGenerator  import NetworksGenerator


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

# ── CONFIG ────────────────────────────────────────────────────────────────────
METRICS_FILE = os.getenv("METRICS_FILE", "metrics.json")
LLM_CALLS_LOG_FILE = os.getenv("LLM_CALLS_LOG_FILE", "network/llm_calls.jsonl")
DEFAULT_RUNTIME = int(os.getenv("EXPERIMENT_RUNTIME", "120"))
DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_NUM_SWITCHES = int(os.getenv("NUM_SWITCHES", "3"))
DEFAULT_NUM_HOSTS = int(os.getenv("NUM_HOSTS", "5"))

class SDNExperiment:
    """
    Orchestrates the full SDN experiment:
    - Cleans up stale processes
    - Starts RYU controller
    - Builds and starts the Mininet network
    - Configures QoS queues for network slicing
    - Launches traffic, monitoring, and metrics threads
    """

    def __init__(self, runtime: int = DEFAULT_RUNTIME,
                 api_key: str = DEFAULT_API_KEY,
                 model: str = ''):
        self.runtime      = runtime
        self.net          = None
        self.stop_event   = threading.Event()
        self.num_switches = 0

        # Core components
        self.metrics = MetricsStore()
        self.ryu     = RyuController()
        self.llm     = LLMClient(api_key=api_key, metrics=self.metrics)

    # ── SETUP ─────────────────────────────────────────────────────────────────

    def _kill_old_processes(self):
        print("[🧹] Pulizia preventiva...")
        os.system("sudo pkill -9 iperf 2>/dev/null")
        os.system("sudo pkill -9 ping  2>/dev/null")
        os.system("sudo pkill -9 nc    2>/dev/null")
        os.system("sudo pkill -9 ryu-manager 2>/dev/null")
        cleanup()
        time.sleep(2)

    def _start_ryu(self) -> subprocess.Popen:
        print("[⚡] Avvio Controller RYU...")
        return subprocess.Popen(
            ["ryu-manager", "ryu.app.simple_switch_13", "ryu.app.ofctl_rest"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _metrics_persist_loop(self):
        while not self.stop_event.is_set():
            self.metrics.persist(METRICS_FILE)
            time.sleep(1)

    @staticmethod
    def _reset_llm_calls_log():
        path = Path(LLM_CALLS_LOG_FILE)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
            print(f"[🧾] LLM calls log azzerato: {path}")
        except Exception as e:
            print(f"[⚠️] Impossibile azzerare LLM calls log: {e}")

    # ── RUN ───────────────────────────────────────────────────────────────────

    def run(self, topo_obj):
        self.num_switches = topo_obj.num_switches
        self._kill_old_processes()
        self._reset_llm_calls_log()

        ryu_proc = self._start_ryu()
        time.sleep(3)

        print("[🌐] Costruzione rete Mininet...")
        self.net = Mininet(
            topo=topo_obj,
            switch=OVSKernelSwitch,
            controller=RemoteController("c0", ip="127.0.0.1", port=6633),
            link=TCLink,
            autoSetMacs=True,
        )
        self.net.start()

        # ── QoS queue setup (after net.start()) ───────────────────────────
        topo_obj.setup_queues(self.net)

        self.stop_event.clear()

        # Instantiate workers
        traffic_mgr = TrafficManager(
            net=self.net,
            metrics=self.metrics,
            ryu=self.ryu,
            llm=self.llm,
            stop_event=self.stop_event,
            num_switches=self.num_switches,
        )
        monitor = NetworkMonitor(
            metrics=self.metrics,
            ryu=self.ryu,
            llm=self.llm,
            stop_event=self.stop_event,
            num_switches=self.num_switches,
        )

        # Launch threads
        for name, fn in [
            ("traffic", traffic_mgr.generate_random_traffic),
            ("monitor", monitor.monitor_blocked_traffic),
            ("persist", self._metrics_persist_loop),
        ]:
            t = threading.Thread(target=fn, name=name, daemon=True)
            t.start()

        print(
            f"[⏱️] Rete attiva per {self.runtime}s — "
            "Avvia la GUI con: streamlit run app_gui_advanced.py"
        )
        try:
            time.sleep(self.runtime)
        except KeyboardInterrupt:
            print("\n[!] Stop manuale.")
        finally:
            self._stop_all(ryu_proc, topo_obj)

    # ── TEARDOWN ──────────────────────────────────────────────────────────────

    def _stop_all(self, ryu_proc: subprocess.Popen, topo_obj):
        print("[🧹] Spegnimento in corso...")
        self.metrics.running = False
        self.metrics.persist(METRICS_FILE)
        self.stop_event.set()
        ryu_proc.terminate()
        os.system("sudo pkill -9 iperf ping nc 2>/dev/null")
        if self.net:
            self.net.stop()  # ← prima Mininet
        NetworksGenerator.cleanup_queues()  # ← poi OVS queues
        cleanup()
        print("✅ VM pulita.")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    topo_obj = NetworksGenerator(num_switches=DEFAULT_NUM_SWITCHES, num_hosts=DEFAULT_NUM_HOSTS)
    exp      = SDNExperiment(
        runtime=DEFAULT_RUNTIME
    )
    exp.run(topo_obj)