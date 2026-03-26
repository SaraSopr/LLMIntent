#!/usr/bin/python3
"""
NetworksGenerator — Mininet topology builder with extended JSON metadata.
Generates topology.json consumed by the GUI and the SDN experiment engine.

Slices:
  Queue 1 → High-priority slice (ICMP, interactive) — min 8 Mbps
  Queue 2 → Low-priority slice  (TCP/UDP bulk)      — min 2 Mbps
"""

import json
import random
import subprocess
from mininet.topo import Topo

SLICE_CONFIG = {
    1: {"min_rate": "8000000",  "max_rate": "10000000", "label": "high-priority"},
    2: {"min_rate": "2000000",  "max_rate": "10000000", "label": "low-priority"},
}


class NetworksGenerator(Topo):
    def __init__(self, num_switches=3, num_hosts=5, *args, **params):
        self.num_switches = num_switches
        self.num_hosts    = num_hosts
        self.topo_data    = {
            "hosts":    [],
            "switches": [],
            "links":    [],
            "slices":   SLICE_CONFIG,
            "meta": {
                "num_switches": num_switches,
                "num_hosts":    num_hosts,
            }
        }
        self.switch_ports = {f"s{i + 1}": 1 for i in range(num_switches)}
        super(NetworksGenerator, self).__init__(*args, **params)

    def build(self):
        # ── Switches ──────────────────────────────────────────────────────
        for i in range(1, self.num_switches + 1):
            s_name = f"s{i}"
            self.addSwitch(s_name)
            self.topo_data["switches"].append(s_name)

        # ── Hosts ─────────────────────────────────────────────────────────
        for i in range(1, self.num_hosts + 1):
            h_name   = f"h{i}"
            mac_addr = "00:00:00:00:00:{:02x}".format(i)
            ip_addr  = f"10.0.0.{i}/8"
            self.addHost(h_name, mac=mac_addr, ip=ip_addr)
            self.topo_data["hosts"].append(h_name)

        # ── Switch ↔ Switch links (linear chain) ──────────────────────────
        for i in range(1, self.num_switches):
            s1, s2 = f"s{i}", f"s{i + 1}"
            p1, p2 = self.switch_ports[s1], self.switch_ports[s2]

            self.addLink(s1, s2, port1=p1, port2=p2,
                         bw=100, delay="2ms", loss=0)
            self.topo_data["links"].append({
                "node1": s1, "node2": s2, "type": "s-s",
                "s1_port": p1, "s2_port": p2,
                "bw": 100, "delay": "2ms",
            })
            self.switch_ports[s1] += 1
            self.switch_ports[s2] += 1

        # ── Host ↔ Switch links ───────────────────────────────────────────
        switches = [f"s{i + 1}" for i in range(self.num_switches)]
        for idx, h in enumerate(self.topo_data["hosts"]):
            target_s = random.choice(switches)
            s_port   = self.switch_ports[target_s]
            mac_addr = "00:00:00:00:00:{:02x}".format(idx + 1)
            ip_addr  = f"10.0.0.{idx + 1}"

            self.addLink(h, target_s, port1=0, port2=s_port,
                         bw=10, delay="5ms", loss=0)
            self.topo_data["links"].append({
                "node1": h, "node2": target_s, "type": "h-s",
                "dpid": int(target_s[1:]),
                "port": s_port,
                "mac":  mac_addr,
                "ip":   ip_addr,
                "bw":   10, "delay": "5ms",
            })
            self.switch_ports[target_s] += 1

        # ── Persist ───────────────────────────────────────────────────────
        with open("topology.json", "w") as f:
            json.dump(self.topo_data, f, indent=4)
        print("✅ topology.json generated with MAC, IP, ports and link metadata.")

    # ── QoS SETUP (called after net.start()) ──────────────────────────────

    def setup_queues(self, net):
        """
        Configure OVS QoS queues on every switch port.
        Must be called AFTER net.start().

        Queue 0 → default (unclassified traffic)
        Queue 1 → high-priority slice (min 8 Mbps)
        Queue 2 → low-priority  slice (min 2 Mbps)
        """
        print("[📶] Configuring QoS queues on switches...")
        for sw in net.switches:
            for intf in sw.intfNames():
                if intf == "lo":
                    continue
                self._configure_port_queues(intf)
        print("[✅] QoS queues configured.")

    def _configure_port_queues(self, intf: str):
        """Apply OVS QoS + queues to a single interface."""
        try:
            # 1. Create QoS on the port
            subprocess.run([
                "ovs-vsctl", "set", "port", intf,
                "qos=@newqos",
                "--", "--id=@newqos", "create", "qos",
                "type=linux-htb",
                "other-config:max-rate=10000000",
                "queues:0=@q0", "queues:1=@q1", "queues:2=@q2",
                "--", "--id=@q0", "create", "queue",
                "other-config:min-rate=1000000",
                "other-config:max-rate=10000000",
                "--", "--id=@q1", "create", "queue",
                f"other-config:min-rate={SLICE_CONFIG[1]['min_rate']}",
                f"other-config:max-rate={SLICE_CONFIG[1]['max_rate']}",
                "--", "--id=@q2", "create", "queue",
                f"other-config:min-rate={SLICE_CONFIG[2]['min_rate']}",
                f"other-config:max-rate={SLICE_CONFIG[2]['max_rate']}",
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"[⚠️] QoS setup failed on {intf}: {e.stderr.decode()[:100]}")

    @staticmethod
    def cleanup_queues():
        """Remove all OVS QoS configurations (called in _stop_all)."""
        print("[🧹] Cleaning up QoS queues...")
        subprocess.run(["ovs-vsctl", "--all", "destroy", "qos"],
                       capture_output=True)
        subprocess.run(["ovs-vsctl", "--all", "destroy", "queue"],
                       capture_output=True)
        print("[✅] QoS queues removed.")