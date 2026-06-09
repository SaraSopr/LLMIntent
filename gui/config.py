from pathlib import Path
import os


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

VM_IP     = os.getenv("VM_IP", "127.0.0.1")
RYU_PORT  = os.getenv("RYU_REST_PORT", "8080")
BASE_REST = f"http://{VM_IP}:{RYU_PORT}"
ADD_URL   = os.getenv("ADD_URL", f"{BASE_REST}/stats/flowentry/add")
DEL_URL   = os.getenv("DEL_URL", f"{BASE_REST}/stats/flowentry/delete")

# Allinea la versione modulare alla base `try/app_gui_advanced.py`:
# topology.json e metrics.json devono essere risolti nella cartella `try/`.
ROOT_DIR  = Path(__file__).resolve().parents[1]
_DATA_DIR = ROOT_DIR / "network" / "data"

PATH_TOPO    = _DATA_DIR / "topology.json"
PATH_METRICS = _DATA_DIR / "metrics.json"

_LLM_LOG_ENV = os.getenv("LLM_CALLS_LOG_FILE", "network/data/llm_calls.jsonl")
PATH_LLM_CALLS = Path(_LLM_LOG_ENV) if Path(_LLM_LOG_ENV).is_absolute() else ROOT_DIR / _LLM_LOG_ENV
_GUI_ACTIONS_ENV = os.getenv("GUI_ACTIONS_FILE", "network/data/gui_actions.jsonl")
_GUI_ACTIONS_RESULTS_ENV = os.getenv("GUI_ACTIONS_RESULTS_FILE", "network/data/gui_actions_results.jsonl")
PATH_GUI_ACTIONS = Path(_GUI_ACTIONS_ENV) if Path(_GUI_ACTIONS_ENV).is_absolute() else ROOT_DIR / _GUI_ACTIONS_ENV
PATH_GUI_ACTIONS_RESULTS = Path(_GUI_ACTIONS_RESULTS_ENV) if Path(_GUI_ACTIONS_RESULTS_ENV).is_absolute() else ROOT_DIR / _GUI_ACTIONS_RESULTS_ENV

REFRESH_SEC = int(os.getenv("REFRESH_SEC", "1"))
