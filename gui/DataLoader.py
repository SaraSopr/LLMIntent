import json, os
from config import PATH_TOPO, PATH_METRICS

class DataLoader:
    def __init__(self, topo_path=PATH_TOPO, metrics_path=PATH_METRICS):
        self.topo_path = topo_path
        self.metrics_path = metrics_path

    def load_topology(self):
        """Reads the topology file."""
        if os.path.exists(self.topo_path):
            with open(self.topo_path) as f:
                return json.load(f)
        return None

    def load_metrics(self):
        if os.path.exists(self.metrics_path):
            try:
                with open(self.metrics_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return None
