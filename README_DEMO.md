# Demo Checklist — LLMIntent

Questa guida valida la parte **intent-based fix actions** (`set_link_tc`, `add_link`, `remove_link`) con evidenze verificabili.

## 1) Setup

1. Avvia esperimento SDN:
   - `sudo python3 network/networkGeneration.py`
2. Avvia dashboard:
   - `streamlit run gui/Dashboard.py`
3. Verifica file di osservabilità:
   - `network/llm_calls.jsonl`
   - `network/gui_actions_results.jsonl`
   - `network/metrics.json`

## 2) Cosa stiamo validando

Nel prompt `network/templates/fix_intent.j2`, il modello può proporre:
- `set_link_tc`
- `add_link` (solo switch-switch)
- `remove_link` (solo switch-switch)

Con schema JSON:
- `action`, `host`, `params`, `reason`

## 3) Scenario A — set_link_tc

### Obiettivo
Verificare che l’LLM proponga `set_link_tc` con parametri validi quando vede congestione/latenza.

### Passi
1. Lascia girare traffico finché compare anomalia in monitor/dashboard.
2. Controlla l’ultima entry `query_kind: "fix"` in `network/llm_calls.jsonl`.
3. Verifica che il JSON abbia:
   - `"action": "set_link_tc"`
   - `params.node1`, `params.node2`
   - almeno uno tra `params.bw` o `params.delay`
4. Verifica applicazione in runtime (`[🔧 FIX] TC aggiornato ...`).

### Evidenza da screenshot
- Riga in `llm_calls.jsonl` con fix `set_link_tc`
- Log runtime di applicazione

## 4) Scenario B — add_link (switch-switch)

### Obiettivo
Verificare proposta ed esecuzione di un nuovo link tra switch.

### Passi
1. Induci scenario di path degradato / necessità percorso alternativo.
2. Attendi fix LLM.
3. Verifica in `network/llm_calls.jsonl`:
   - `"action": "add_link"`
   - `params.node1`, `params.node2` entrambi tipo `sX`
4. Verifica esecuzione e aggiornamento topologia (`network/topology.json`).

### Evidenza da screenshot
- JSON fix `add_link`
- Estratto `network/topology.json` con nuovo link s-s

## 5) Scenario C — remove_link (switch-switch)

### Obiettivo
Verificare proposta ed esecuzione di rimozione link tra switch.

### Passi
1. Dopo aggiunta link o scenario di overload, attendi proposta di rimozione.
2. Verifica in `network/llm_calls.jsonl`:
   - `"action": "remove_link"`
   - `params.node1`, `params.node2` entrambi `sX`
3. Verifica esecuzione e rimozione dal `network/topology.json`.

### Evidenza da screenshot
- JSON fix `remove_link`
- Topologia aggiornata senza il link

## 6) Validazione lato dashboard (executor)

La sidebar **Gestione Link** testa l’esecutore backend (non la decisione LLM):
- invii manuali di `set_link_tc` / `add_link` / `remove_link`
- esito in `network/gui_actions_results.jsonl`

Usala per verificare robustezza dell’applicazione action, separatamente dalla qualità della decisione del modello.

## 7) Criteri di superamento

Per ciascuno scenario:
1. JSON `fix` conforme allo schema
2. Parametri coerenti con vincoli del prompt
3. Azione realmente applicata dal northbound
4. Evidenza persistita su log/file

## 8) Comandi rapidi utili

- Ultime fix LLM:
  - `grep '"query_kind": "fix"' network/llm_calls.jsonl | tail -n 5`
- Ultimi risultati azioni GUI:
  - `tail -n 10 network/gui_actions_results.jsonl`
- Stato metriche runtime:
  - `cat network/metrics.json`
