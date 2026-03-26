# Demo Checklist — LLMIntent

This guide validates the **intent-based fix actions** (`set_link_tc`, `add_link`, `remove_link`) with verifiable evidence.

## 1) Setup

1. Start the SDN experiment:
   - `sudo python3 network/networkGeneration.py`
2. Start the dashboard:
   - `streamlit run gui/Dashboard.py`
3. Verify observability files:
   - `network/llm_calls.jsonl`
   - `network/gui_actions_results.jsonl`
   - `network/metrics.json`

## 2) What we are validating

In the prompt `network/templates/fix_intent.j2`, the model can propose:
- `set_link_tc`
- `add_link` (switch-to-switch only)
- `remove_link` (switch-to-switch only)

With JSON schema:
- `action`, `host`, `params`, `reason`

## 3) Scenario A — set_link_tc

### Goal
Verify that the LLM proposes `set_link_tc` with valid parameters when it detects congestion or latency degradation.

### Steps
1. Let traffic run until an anomaly appears in the monitor/dashboard.
2. Check the latest `query_kind: "fix"` entry in `network/llm_calls.jsonl`.
3. Verify the JSON contains:
   - `"action": "set_link_tc"`
   - `params.node1`, `params.node2`
   - at least one of `params.bw` or `params.delay`
4. Verify runtime application (`[🔧 FIX] TC updated ...`).

### Screenshot evidence
- Row in `llm_calls.jsonl` with fix `set_link_tc`
- Runtime application log

## 4) Scenario B — add_link (switch-to-switch)

### Goal
Verify proposal and execution of a new link between switches.

### Steps
1. Induce a degraded path scenario or need for an alternative route.
2. Wait for the LLM fix.
3. Verify in `network/llm_calls.jsonl`:
   - `"action": "add_link"`
   - `params.node1`, `params.node2` both of type `sX`
4. Verify execution and topology update (`network/topology.json`).

### Screenshot evidence
- JSON fix `add_link`
- Extract from `network/topology.json` with new s-s link

## 5) Scenario C — remove_link (switch-to-switch)

### Goal
Verify proposal and execution of link removal between switches.

### Steps
1. After adding a link or in an overload scenario, wait for a removal proposal.
2. Verify in `network/llm_calls.jsonl`:
   - `"action": "remove_link"`
   - `params.node1`, `params.node2` both `sX`
3. Verify execution and removal from `network/topology.json`.

### Screenshot evidence
- JSON fix `remove_link`
- Updated topology without the link

## 6) Dashboard-side validation (executor)

The **Link Management** sidebar tests the backend executor (not the LLM decision):
- Manual submissions of `set_link_tc` / `add_link` / `remove_link`
- Result in `network/gui_actions_results.jsonl`

Use it to verify action application robustness, independently from model decision quality.

## 7) Pass criteria

For each scenario:
1. `fix` JSON conforming to the schema
2. Parameters consistent with prompt constraints
3. Action actually applied by the northbound layer
4. Evidence persisted to logs/files

## 8) Useful quick commands

- Latest LLM fixes:
  - `grep '"query_kind": "fix"' network/llm_calls.jsonl | tail -n 5`
- Latest GUI action results:
  - `tail -n 10 network/gui_actions_results.jsonl`
- Runtime metrics state:
  - `cat network/metrics.json`
