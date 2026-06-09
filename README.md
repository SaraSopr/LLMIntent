# LLM-Driven SDN Network Slicing

Course project for **Softwarized and Virtualized Mobile Networks** (A.Y. 2025–2026),
M.Sc. in Computer Science — University of Trento.

This project adds an LLM as a **northbound control intelligence layer** on top of a RYU SDN controller.
The model receives compact network state snapshots and decides how to steer traffic and handle anomalies.

## What the system does

The platform runs on Mininet + Open vSwitch + RYU and uses the LLM for three tasks:

- **Slice assignment** (`ask_slice`) for each new flow.
- **Anomaly detection** (`ask_anomaly`) on periodic monitoring windows.
- **Automatic remediation** (`ask_fix`) when anomalies are actionable.

### Network slices

| Slice | Queue | Profile | Typical traffic |
|---|---|---|---|
| Slice 1 | Queue 1 | Low latency / high priority | ICMP, interactive |
| Slice 2 | Queue 2 | High throughput / bulk | TCP, UDP |

## Deployment architecture

The system is split across two machines:

| Component | Host |
|---|---|
| Mininet + OVS + RYU + experiment engine | **Multipass VM** (Ubuntu guest) |
| Streamlit dashboard | **macOS host** |

The project directory is shared via **Multipass mount**. Runtime files written by the experiment (`network/data/`) are read directly by the dashboard on the host without any network transfer.

```
┌─────────────────────────────┐      ┌──────────────────────────────────┐
│        macOS host           │      │        Multipass VM (Ubuntu)     │
│                             │      │                                  │
│  streamlit run gui/         │      │  sudo python3                    │
│    Dashboard.py             │      │    network/networkGeneration.py  │
│         │                   │      │         │                        │
│         │ read              │      │         │ write                  │
│         ▼                   │      │         ▼                        │
│   network/data/  ◄──────────┼──────┼── network/data/                 │
│  (Multipass mount)          │      │  (shared filesystem)             │
│         │                   │      │                                  │
│         │   RYU REST API    │      │                                  │
│         └───────────────────┼─────►│  :8080                          │
└─────────────────────────────┘      └──────────────────────────────────┘
```

## High-level software architecture

```text
LLM (OpenAI Responses API)
       ↑
       ↓
Northbound Python logic (LLMClient)
       ↑
       ↓
RYU REST API (ofctl_rest)
       ↑
       ↓
RYU controller + OpenFlow 1.3
       ↑
       ↓
OVS switches + Mininet hosts
```

## Repository structure

| Path | Role |
|---|---|
| `network/networkGeneration.py` | Main experiment orchestrator |
| `network/networksGenerator.py` | Topology generation + QoS queue setup |
| `network/llmClient.py` | OpenAI client + prompting + parsing + logging |
| `network/networkMonitor.py` | Periodic monitoring, anomaly detection, auto-fix |
| `network/trafficManager.py` | Random traffic generation + LLM-driven slice installation |
| `network/ryuController.py` | RYU REST wrapper |
| `network/metricStore.py` | Thread-safe metrics and persistence |
| `network/templates/*.j2` | Jinja2 prompt templates |
| `gui/Dashboard.py` | Streamlit dashboard entrypoint |
| `gui/SidebarManager.py` | Host security controls (isolate/unblock) |

## Quick start

### 1) Prerequisites

**Multipass VM (Ubuntu guest)**
- Python 3.8+
- Mininet + Open vSwitch
- RYU SDN framework (`pip install ryu`)

**macOS host**
- Python 3.8+
- Multipass
- OpenAI API key

### 2) Mount the project directory into the VM

```bash
# Run on the macOS host — replace <vm-name> with your Multipass VM name
multipass mount /path/to/LLMIntent <vm-name>:/home/ubuntu/LLMIntent
```

This gives the VM write access to `network/data/`, which the dashboard reads directly on the host.

### 3) Install dependencies

**On the VM:**
```bash
pip install openai requests jinja2
```

**On the macOS host:**
```bash
pip install openai requests jinja2 streamlit matplotlib plotly pandas networkx
```

### 4) Configure environment

```bash
cp .env.example .env
```

Key `.env` values:

```env
OPENAI_API_KEY=sk-...
VM_IP=<vm-ip>          # single source of truth — all RYU URLs are derived from this
EXPERIMENT_RUNTIME=120
```

To find the VM IP: `multipass info <vm-name>`. The IP may change on restart — `VM_IP` is the only value you need to update.

Useful optional settings:

- `NUM_SWITCHES`, `NUM_HOSTS`
- `REFRESH_SEC`
- `ADD_URL`, `DEL_URL` (explicit RYU REST endpoints)

### 5) Run the experiment

**On the VM**, from the project root:

```bash
sudo python3 network/networkGeneration.py
```

### 6) Run the dashboard

**On the macOS host**, from the project root:

```bash
streamlit run gui/Dashboard.py
```

## LLM loop behavior

### Slice assignment (per flow)

1. Collect compact flow/state context.
2. Ask the model for `slice: 1|2` with short reason.
3. Install OpenFlow rules with `SET_QUEUE` accordingly.

### Anomaly detection (periodic)

1. Build anomaly signals (drop rate, latency stats, flow growth, etc.).
2. Ask the model for anomaly classification.
3. If anomaly is actionable, request remediation (`block_host` or `none`).
4. Apply fix through RYU REST and log decision metadata.

## Outputs and observability

All runtime files are written to `network/data/` (gitignored):

| File | Content |
|---|---|
| `network/data/metrics.json` | Live traffic metrics read by the dashboard |
| `network/data/topology.json` | Network topology generated at startup |
| `network/data/llm_calls.jsonl` | Full audit log of every LLM call |
| `network/data/gui_actions.jsonl` | Actions queued from the GUI |
| `network/data/gui_actions_results.jsonl` | Execution results of GUI actions |

Dashboard sections:
- topology and host isolation state
- baseline vs LLM comparison
- LLM activity and raw latest call details

## Notes

- Keep secrets only in `.env` (gitignored).
- The VM IP may change on restart — update `RYU_REST_URL`, `ADD_URL`, `DEL_URL` in `.env` with the output of `multipass info <vm-name>`.
- If Mininet is left dirty, run on the VM:

```bash
sudo mn -c
```

## Technologies

- SDN: RYU, OpenFlow 1.3, Open vSwitch
- Emulation: Mininet
- Virtualisation: Multipass (Ubuntu VM on macOS)
- LLM: OpenAI Responses API
- UI: Streamlit
- Prompting: Jinja2 templates

## Author

- Sara Soprana — sara.soprana@studenti.unitn.it