import json
from datetime import datetime
from uuid import uuid4
from config import PATH_GUI_ACTIONS, PATH_GUI_ACTIONS_RESULTS


class SDNController:
    @staticmethod
    def enqueue_action(action: str, params: dict, reason: str = "manual_gui", host: str = None) -> str:
        request_id = str(uuid4())
        payload = {
            "request_id": request_id,
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "source": "gui",
            "action": action,
            "host": host,
            "params": params or {},
            "reason": reason,
        }
        PATH_GUI_ACTIONS.parent.mkdir(parents=True, exist_ok=True)
        with open(PATH_GUI_ACTIONS, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return request_id

    @staticmethod
    def get_action_result(request_id: str):
        if not PATH_GUI_ACTIONS_RESULTS.exists():
            return None
        try:
            with open(PATH_GUI_ACTIONS_RESULTS, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("request_id") == request_id:
                    return item
        except Exception:
            return None
        return None
