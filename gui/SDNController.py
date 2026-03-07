import requests
from config import ADD_URL, DEL_URL


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
