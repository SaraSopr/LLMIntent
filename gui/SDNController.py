import requests
import json
from datetime import datetime
from uuid import uuid4
from config import ADD_URL, DEL_URL, PATH_GUI_ACTIONS, PATH_GUI_ACTIONS_RESULTS


class SDNController:
    def __init__(self, add_url=ADD_URL, del_url=DEL_URL):
        self.add_url = add_url
        self.del_url = del_url

    @staticmethod
    def _normalize_dpid(dpid):
        if isinstance(dpid, str) and dpid.lower().startswith("s"):
            return int(dpid[1:])
        return int(dpid)

    @staticmethod
    def _build_payload(dpid, port, mac_addr, src_field="eth_src"):
        match = {src_field: mac_addr}
        if port is not None:
            match["in_port"] = int(port)
        return {
            "dpid": int(dpid),
            "priority": 65535,
            "match": match,
            "actions": [],
        }

    @staticmethod
    def _post(url, payload):
        return requests.post(url, json=payload, timeout=2)

    def send_rule(self, action, dpid, port, mac_addr):
        dpid = self._normalize_dpid(dpid)

        try:
            if action == "BLOCK":
                payload = self._build_payload(dpid, None, mac_addr, src_field="eth_src")
                resp = self._post(self.add_url, payload)
                if 200 <= resp.status_code < 300:
                    return resp
                payload_alt = self._build_payload(dpid, None, mac_addr, src_field="dl_src")
                return self._post(self.add_url, payload_alt)

            payload = self._build_payload(dpid, None, mac_addr, src_field="eth_src")
            delete_strict = self.del_url.replace("/delete", "/delete_strict")
            resp = self._post(delete_strict, payload)
            if 200 <= resp.status_code < 300:
                return resp
            resp = self._post(self.del_url, payload)
            if 200 <= resp.status_code < 300:
                return resp

            payload_alt = self._build_payload(dpid, None, mac_addr, src_field="dl_src")
            resp = self._post(delete_strict, payload_alt)
            if 200 <= resp.status_code < 300:
                return resp
            return self._post(self.del_url, payload_alt)
        except Exception:
            return None

    @staticmethod
    def enqueue_action(action: str, params: dict, reason: str = "manual_gui") -> str:
        request_id = str(uuid4())
        payload = {
            "request_id": request_id,
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "source": "gui",
            "action": action,
            "host": None,
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
