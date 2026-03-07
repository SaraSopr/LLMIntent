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

## High-level architecture

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

- Python **3.8+**
- Mininet + Open vSwitch
- RYU SDN framework
- OpenAI API key
- (Optional) Vagrant/VirtualBox if running in a VM

### 2) Install dependencies

```bash
pip install openai requests jinja2 streamlit matplotlib plotly pandas networkx
```

### 3) Configure environment

```bash
cp .env.example .env
```

Minimum `.env` values:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
RYU_REST_URL=http://127.0.0.1:8080
GUI_VM_IP=192.168.64.8
EXPERIMENT_RUNTIME=120
```

Useful optional settings:

- `NUM_SWITCHES`, `NUM_HOSTS`
- `REFRESH_SEC`
- `LLM_CALLS_LOG_FILE`
- `ADD_URL`, `DEL_URL` (explicit GUI endpoints)

### 4) Run the experiment

From project root:

```bash
sudo python3 network/networkGeneration.py
```

### 5) Run the dashboard

In a separate terminal:

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

- Runtime metrics: `network/metrics.json`
- Model-call audit log: `network/llm_calls.jsonl`
- Dashboard sections:
  - topology and host isolation state
  - baseline vs LLM comparison
  - LLM activity and raw latest call details

## Notes

- Keep secrets only in `.env`.
- `.env` and `.idea/` are git-ignored.
- If Mininet is left dirty, run:

```bash
sudo mn -c
```

## Technologies

- SDN: RYU, OpenFlow 1.3, Open vSwitch
- Emulation: Mininet
- LLM: OpenAI Responses API
- UI: Streamlit
- Prompting: Jinja2 templates

## Author

- Sara Soprana — sara.soprana@studenti.unitn.it