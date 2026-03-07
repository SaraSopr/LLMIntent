             ChatGPT
                ↑
                ↓
     Northbound Python Script
                ↑
                ↓
         REST API (ofctl_rest)
                ↑
                ↓
         Ryu Controller
                ↑
                ↓
            Switch
                ↑
                ↓
             Hosts

# LLM-Driven SDN Network Slicing

Project for the **Softwarized and Virtualized Mobile Networks** course (A.Y. 2025–2026).  
Master's degree in Computer Science — University of Trento.

This project integrates a **Large Language Model (LLM)** into the decision process of a Software Defined Network, acting as a **northbound intelligence layer** over a RYU SDN controller. The LLM receives the current network state and operator intents, then autonomously implements changes on the network through OpenFlow rules.

---

## Project Overview

The system implements an **LLM-driven network slicing architecture** over an emulated SDN infrastructure using Mininet and RYU.

The LLM is responsible for three autonomous decisions:

- **Slice assignment** — For each new traffic flow, the LLM decides which network slice to use based on the protocol and current network state.
- **Anomaly detection** — Periodically, the LLM analyses network metrics (drop rates, traffic patterns) and detects anomalies.
- **Automatic remediation** — When an anomaly is detected, the LLM proposes and implements a fix (e.g. blocking a misbehaving host) via RYU REST API.

### Network Slices

| Slice | Queue | Profile | Traffic |
|-------|-------|---------|---------|
| Slice 1 | Queue 1 | High-priority / Low-latency | ICMP, interactive |
| Slice 2 | Queue 2 | High-throughput / Bulk | TCP, UDP |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              NORTHBOUND LAYER               │
│                                             │
│   LLMClient (OpenAI Responses API)         │
│   ├── ask_slice()    → slice assignment     │
│   ├── ask_anomaly()  → anomaly detection    │
│   └── ask_fix()      → automatic remediation│
└───────────────────┬─────────────────────────┘
                    │ REST
┌───────────────────▼─────────────────────────┐
│              CONTROL PLANE                  │
│                                             │
│   RYU SDN Controller                        │
│   ├── simple_switch_13  (L2 learning)       │
│   └── ofctl_rest        (REST API)          │
└───────────────────┬─────────────────────────┘
                    │ OpenFlow 1.3
┌───────────────────▼─────────────────────────┐
│               DATA PLANE                    │
│                                             │
│   Mininet + Open vSwitch                    │
│   ├── 3 switches (linear topology)          │
│   ├── 5 hosts                               │
│   └── QoS queues (HTB) per port             │
└─────────────────────────────────────────────┘
```

### Module Structure

| File | Responsibility |
|------|----------------|
| `networkGeneration2.py` | Orchestrator — Mininet setup, thread management |
| `networksGenerator.py` | Topology builder + OVS QoS queue configuration |
| `llmClient.py` | LLM northbound interface (OpenAI Responses API) |
| `network/templates/*.j2` | Jinja2 prompt templates (slice, anomaly, fix, system/user) |
| `ryuController.py` | RYU REST API wrapper |
| `trafficManager.py` | Traffic generation + LLM slice assignment |
| `networkMonitor.py` | Drop detection + LLM anomaly detection + auto-fix |
| `metricStore.py` | Thread-safe metrics store → `metrics.json` |

---

## Getting Started

### Prerequisites

- **Vagrant** + **VirtualBox** (or ComNetsEmu VM)
- **Python 3.8+**
- **Mininet** + **Open vSwitch**
- **RYU SDN Framework**
- **Ollama** (macOS/Linux, for local LLM) — [ollama.com](https://ollama.com)
- An **OpenAI API key** — [platform.openai.com](https://platform.openai.com)

### Setup Instructions

**1. Start the VM**
```bash
vagrant up
vagrant ssh
```

**2. Install Python dependencies (inside the VM)**
```bash
pip install openai requests jinja2
```

**3. Start Ollama on the host machine (macOS)**

If using Ollama as LLM provider, run on the **Mac host**:
```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

> The VM reaches the Mac host at `192.168.64.1:11434`.  
> To verify: `curl http://192.168.64.1:11434/api/tags`

**4. Configure environment variables (.env)**

Create a local `.env` file from the example:
```bash
cp .env.example .env
```

Then set at least:
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
RYU_REST_URL=http://127.0.0.1:8080
GUI_VM_IP=192.168.64.8
EXPERIMENT_RUNTIME=120
```

Useful optional variables:
- `NUM_SWITCHES`, `NUM_HOSTS` (topology size)
- `REFRESH_SEC` (dashboard refresh rate)
- `METRICS_FILE` (metrics output file)

**5. Run the experiment**
```bash
cd /path/to/project
sudo python3 networkGeneration.py
```

**6. Launch the GUI** (in a separate terminal)
```bash
streamlit run app_gui_advanced.py
```

---

## LLM Decision Loop

### Slice Assignment (every flow)
```
new TCP flow h1 → h2
→ LLM: "TCP is bulk transfer → Slice 2 (high-throughput)"
→ RYU installs flow with SET_QUEUE:2
→ log: [📡] TCP: h1→h2 | ✅ ACCEPTED | 1389ms | 🔵 Slice 2
```

### Anomaly Detection + Remediation (every 30s)
```
LLM analyses node_stats from RYU
→ "High drop rate at h4 (3 drops) — unusual pattern"
→ ask_fix(): "block_host: h4"
→ RYU installs drop rule priority:65535 on h4
→ log: [🔧 FIX] h4 blocked — High drop rate detected
```

---

## Supported LLM Providers

| Provider | Model | Notes |
|----------|-------|-------|
| `openai` | `gpt-5-mini` | Recommended — typed outputs + robust JSON handling |
| `groq` | `groq/compound` | Legacy compatibility via fallback env vars |
| `ollama` | `ministral-3:8b` | Legacy/local alternative |

To switch provider, edit `networkGeneration2.py`:
```python
# Groq (recommended)
exp = SDNExperiment(provider="groq", api_key="gsk_...")

# Ollama (local)
exp = SDNExperiment(provider="ollama")

# OpenAI
exp = SDNExperiment(provider="openai", api_key="sk-...")
```

---

## Notes

- Keep secrets only in `.env` (never hardcode API keys in Python files).
- `.env` is ignored by git; use `.env.example` as template.

- If Mininet fails to terminate correctly, run `sudo mn -c` to clean up.
- The first LLM call may take longer as the model loads into memory.
- QoS queues are configured using OVS HTB (Hierarchical Token Bucket) with:
  - Queue 1: min 8 Mbps, max 10 Mbps
  - Queue 2: min 2 Mbps, max 10 Mbps

---

## Authors

| Sara Soprana | sara.soprana@studenti.unitn.it |
|----------|--------------------------------|

---

## Used Technologies

- **SDN**: RYU Controller, OpenFlow 1.3, Open vSwitch
- **Network Emulation**: Mininet
- **LLM**: OpenAI Responses API (`gpt-5-mini` default), legacy Groq fallback
- **QoS**: OVS HTB queuing, SET_QUEUE OpenFlow action
- **GUI**: Streamlit