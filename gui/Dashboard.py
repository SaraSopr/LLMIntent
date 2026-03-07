import time
import json
from datetime import datetime
from collections import defaultdict

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from DataLoader import DataLoader
from SDNController import SDNController
from SidebarManager import SidebarManager
from Visualizer import Visualizer
from config import REFRESH_SEC, PATH_LLM_CALLS


class Dashboard:
    @staticmethod
    def apply_styles():
        st.markdown("""
        <style>
          .stApp { background: #0a0e1a; }
                    .compare-btn-wrap { margin: 2px 0 12px 0; }
                    .compare-btn-wrap button {
                        min-height: 52px;
                        font-size: 1rem;
                        font-weight: 700;
                        color: #ffffff !important;
                        border: 1px solid #2a4f7f !important;
                        background: linear-gradient(135deg, #0d1b2a 0%, #132743 100%) !important;
                        box-shadow: 0 4px 24px rgba(77,216,255,0.08);
                    }
          .metric-card {
            background: linear-gradient(135deg, #0d1b2a 0%, #1a2744 100%);
            border: 1px solid #1e3a5f;
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 12px;
            box-shadow: 0 4px 24px rgba(0,100,255,0.08);
          }
          .metric-val {
            font-size: 2.4rem;
            font-weight: 700;
            color: #4dd8ff;
            line-height: 1;
          }
          .metric-lbl {
            font-size: 0.78rem;
            color: #6a8aac;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-top: 4px;
          }
          .sec-header {
            font-size: 1.1rem; font-weight: 700; color: #4dd8ff; text-transform: uppercase;
            letter-spacing: 2px; border-bottom: 1px solid #1e3a5f; padding-bottom: 8px; margin-bottom: 16px;
          }
          .badge-ok  { background:#0d3b26; color:#00e676; border:1px solid #00e676;
                       border-radius:4px; padding:1px 8px; font-size:.7rem; font-weight:700; }
          .badge-err { background:#3b0d0d; color:#ff5252; border:1px solid #ff5252;
                       border-radius:4px; padding:1px 8px; font-size:.7rem; font-weight:700; }
          .badge-proto { background:#0d1f3b; color:#82b1ff; border:1px solid #3d6fe8;
                         border-radius:4px; padding:1px 8px; font-size:.7rem; font-weight:700; }
          .evt-row {
            display:flex; align-items:center; gap:10px;
            padding: 7px 10px; border-radius:8px; margin-bottom:4px;
            background: rgba(30,58,95,0.25);
            border-left: 3px solid transparent;
            font-size:.88rem;
          }
          .evt-row.ok  { border-left-color:#00e676; }
          .evt-row.err { border-left-color:#ff5252; }
          .evt-ts { color:#3d6fe8; font-size:.72rem; min-width:52px; }
          .alert-box {
            background: rgba(255,82,82,0.08); border:1px solid #ff5252;
            border-radius:8px; padding:12px 16px; margin-top:8px; color:#ff8080; font-size:.85rem;
          }
          .ok-box {
            background: rgba(0,230,118,0.07); border:1px solid #00e676;
            border-radius:8px; padding:12px 16px; margin-top:8px; color:#69f0ae; font-size:.85rem;
          }
                    .cmp-wrap {
                        margin-bottom: 10px;
                    }
                    .cmp-head {
                        display:flex;
                        justify-content:space-between;
                        align-items:center;
                        font-size:.78rem;
                        color:#9bb3d1;
                        margin-bottom:6px;
                        letter-spacing:.5px;
                    }
                    .cmp-track {
                        width:100%;
                        height:10px;
                        border-radius:999px;
                        border:1px solid #1e3a5f;
                        background:rgba(18,35,62,.7);
                        overflow:hidden;
                        margin-bottom:14px;
                    }
                    .cmp-fill {
                        height:100%;
                        background: linear-gradient(90deg, #00e676 0%, #4dd8ff 100%);
                    }
                    .cmp-panel {
                        border:1px solid #1e3a5f;
                        border-radius:12px;
                        background:linear-gradient(135deg, rgba(13,27,42,.95) 0%, rgba(24,39,68,.9) 100%);
                        padding:12px;
                        min-height:178px;
                        box-shadow: 0 4px 18px rgba(0,100,255,.08);
                    }
                    .cmp-panel.cmp-llm { border-left:3px solid #4dd8ff; }
                    .cmp-panel.cmp-base { border-left:3px solid #ff9800; }
                    .cmp-title {
                        font-size:.8rem;
                        font-weight:700;
                        text-transform:uppercase;
                        letter-spacing:1.3px;
                        margin-bottom:10px;
                    }
                    .cmp-llm .cmp-title { color:#4dd8ff; }
                    .cmp-base .cmp-title { color:#ffb74d; }
                    .cmp-grid {
                        display:grid;
                        grid-template-columns:repeat(2, minmax(0, 1fr));
                        gap:8px;
                    }
                    .cmp-card {
                        border:1px solid rgba(61,111,232,.2);
                        border-radius:10px;
                        background:rgba(10,20,36,.66);
                        padding:10px;
                    }
                    .cmp-val {
                        font-size:1.35rem;
                        font-weight:700;
                        line-height:1.1;
                        color:#d8e7ff;
                    }
                    .cmp-lbl {
                        font-size:.66rem;
                        color:#8fa7c6;
                        text-transform:uppercase;
                        letter-spacing:1px;
                        margin-top:2px;
                    }
          [data-testid="stSidebar"] { background: #080c18 !important; border-right: 1px solid #1e3a5f; }
          
        .host-table {
        
            width: 100%;
            border-collapse: collapse;
            font-size: .8rem;
            background-color: rgba(20,25,40,.6);
            border-radius: 8px;
            overflow: hidden;
        
        }
        
        .host-table th {
        
            text-align: left;
            padding: 8px;
            background-color: rgba(61,111,232,.15);
            color: #3d6fe8;
            font-weight: 600;
        
        }
        
        .host-table td {
        
            padding: 6px 8px;
            border-top: 1px solid rgba(255,255,255,.05);
            color: #aac;
        
        }
        
        .host-table tr.ok:hover {
        
            background-color: rgba(61,232,122,.08);
        
        }
        
        .host-table tr.err:hover {
        
            background-color: rgba(232,61,61,.08);
        
        }
        </style>
        """, unsafe_allow_html=True)

    def __init__(self):
        self.loader = DataLoader()
        self.controller = SDNController()
        self.vis = Visualizer()

    @staticmethod
    def proto_pie(events):
        counts = defaultdict(int)
        for e in events:
            counts[e["proto"]] += 1
        if not counts:
            return None
        fig = go.Figure(
            go.Pie(
                labels=list(counts.keys()),
                values=list(counts.values()),
                hole=0.55,
                marker=dict(
                    colors=["#4dd8ff", "#ff9800", "#69f0ae"],
                    line=dict(color="#0a0e1a", width=2),
                ),
                textinfo="label+percent",
                textfont_color="white",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=220,
        )
        return fig

    @staticmethod
    def throughput_timeline(events):
        if len(events) < 2:
            return None
        df = pd.DataFrame(events)
        df["ts_bin"] = (df["ts"] // 5) * 5
        grp = df.groupby(["ts_bin", "proto"]).size().reset_index(name="count")
        fig = px.bar(
            grp,
            x="ts_bin",
            y="count",
            color="proto",
            color_discrete_map={"TCP": "#4dd8ff", "UDP": "#ff9800", "ICMP": "#69f0ae"},
            barmode="stack",
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(color="#6a8aac", title="Tempo (s)", gridcolor="#1a2744"),
            yaxis=dict(color="#6a8aac", title="Pacchetti", gridcolor="#1a2744"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font_color="white"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=220,
        )
        return fig

    @staticmethod
    def latency_chart(events):
        if len(events) < 3:
            return None
        df = pd.DataFrame(events).head(50)[::-1]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=df["latency_ms"],
                mode="lines+markers",
                line=dict(color="#ff9800", width=2),
                marker=dict(color="#4dd8ff", size=5),
                fill="tozeroy",
                fillcolor="rgba(77,216,255,0.06)",
                name="Latency ms",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(color="#6a8aac", title="Tempo (s)", gridcolor="#1a2744"),
            yaxis=dict(color="#6a8aac", title="ms", gridcolor="#1a2744"),
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=200,
        )
        return fig

    @staticmethod
    def node_stats_chart(node_stats):
        if not node_stats:
            return None
        nodes = list(node_stats.keys())
        tx_vals = [node_stats[n]["tx"] for n in nodes]
        rx_vals = [node_stats[n]["rx"] for n in nodes]
        dr_vals = [node_stats[n]["drops"] for n in nodes]

        fig = go.Figure()
        for name, vals, color in [
            ("TX", tx_vals, "#4dd8ff"),
            ("RX", rx_vals, "#69f0ae"),
            ("Drops", dr_vals, "#ff5252"),
        ]:
            fig.add_trace(go.Bar(name=name, x=nodes, y=vals, marker_color=color))

        fig.update_layout(
            barmode="group",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(color="#6a8aac", gridcolor="#1a2744"),
            yaxis=dict(color="#6a8aac", gridcolor="#1a2744"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font_color="white"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=240,
        )
        return fig

    @staticmethod
    def render_kpi_cards(total_pkts, accepted, dropped, acc_rate, avg_lat):
        k1, k2, k3, k4, k5 = st.columns(5)
        for col, val, lbl in [
            (k1, total_pkts, "FLUSSI TOTALI"),
            (k2, accepted, "ACCETTATI"),
            (k3, dropped, "BLOCCATI"),
            (k4, f"{acc_rate}%", "ACCEPTANCE RATE"),
            (k5, f"{avg_lat} ms", "LATENZA MEDIA"),
        ]:
            col.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-val'>{val}</div>"
                f"<div class='metric-lbl'>{lbl}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    @staticmethod
    def render_baseline_vs_llm_kpis(events):
        if not events:
            st.caption("Nessun dato disponibile per il confronto Baseline vs LLM")
            return

        valid_events = [
            e for e in events
            if e.get("proto") in {"ICMP", "TCP", "UDP"} and e.get("slice") in {1, 2}
        ]
        if not valid_events:
            st.caption("Eventi non sufficienti per il confronto Baseline vs LLM")
            return

        total = len(valid_events)
        llm_s1 = sum(1 for e in valid_events if e.get("slice") == 1)
        llm_s2 = total - llm_s1

        baseline_s1 = sum(1 for e in valid_events if e.get("proto") == "ICMP")
        baseline_s2 = total - baseline_s1

        agree = sum(
            1 for e in valid_events
            if (1 if e.get("proto") == "ICMP" else 2) == e.get("slice")
        )
        disagree = total - agree

        llm_acc = sum(1 for e in valid_events if e.get("accepted"))
        llm_acc_rate = round((llm_acc / total) * 100, 1) if total else 0
        agree_rate = round((agree / total) * 100, 1) if total else 0
        disagree_rate = (disagree / total) * 100 if total else 0

        st.markdown(
            f"""
            <div class='cmp-wrap'>
                <div class='cmp-head'>
                    <span>Accordo LLM vs Baseline</span>
                    <span>{agree_rate}%</span>
                </div>
                <div class='cmp-track'>
                    <div class='cmp-fill' style='width:{agree_rate}%;'></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown(
                f"""
                <div class='cmp-panel cmp-llm'>
                    <div class='cmp-title'>Intent-Based (LLM)</div>
                    <div class='cmp-grid'>
                        <div class='cmp-card'><div class='cmp-val'>{total}</div><div class='cmp-lbl'>Flussi (LLM)</div></div>
                        <div class='cmp-card'><div class='cmp-val'>{round((llm_s1 / total) * 100, 1)}%</div><div class='cmp-lbl'>Slice 1</div></div>
                        <div class='cmp-card'><div class='cmp-val'>{round((llm_s2 / total) * 100, 1)}%</div><div class='cmp-lbl'>Slice 2</div></div>
                        <div class='cmp-card'><div class='cmp-val'>{llm_acc_rate}%</div><div class='cmp-lbl'>Acceptance Rate</div></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_r:
            st.markdown(
                f"""
                <div class='cmp-panel cmp-base'>
                    <div class='cmp-title'>Baseline (Regole Statiche)</div>
                    <div class='cmp-grid'>
                        <div class='cmp-card'><div class='cmp-val'>{total}</div><div class='cmp-lbl'>Flussi (Baseline)</div></div>
                        <div class='cmp-card'><div class='cmp-val'>{round((baseline_s1 / total) * 100, 1)}%</div><div class='cmp-lbl'>Slice 1 (ICMP)</div></div>
                        <div class='cmp-card'><div class='cmp-val'>{round((baseline_s2 / total) * 100, 1)}%</div><div class='cmp-lbl'>Slice 2 (TCP/UDP)</div></div>
                        <div class='cmp-card'><div class='cmp-val'>{disagree} ({disagree_rate:.1f}%)</div><div class='cmp-lbl'>Disaccordi con LLM</div></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption("Baseline usata nel confronto: ICMP → Slice 1, TCP/UDP → Slice 2")

    @staticmethod
    def render_live_event_feed(events):
        st.markdown("<div class='sec-header'>Live Event Feed</div>", unsafe_allow_html=True)
        if events:
            rows_html = ""
            for e in events[:30]:
                cls = "ok" if e.get("accepted") else "err"
                verdict_badge = (
                    "<span class='badge-ok'>ACK</span>"
                    if e.get("accepted")
                    else "<span class='badge-err'>DROP</span>"
                )
                proto_badge = f"<span class='badge-proto'>{e.get('proto', '?')}</span>"
                rows_html += (
                    f"<div class='evt-row {cls}'>"
                    f"  <span class='evt-ts'>{e.get('ts', 0):.1f}s</span>"
                    f"  {proto_badge}"
                    f"  <span style='color:#aac;'>{e.get('src', '?')}</span>"
                    f"  <span style='color:#446;'>→</span>"
                    f"  <span style='color:#aac;'>{e.get('dst', '?')}</span>"
                    f"  {verdict_badge}"
                    f"  <span style='color:#3d6fe8; font-size:.7rem;'>{e.get('latency_ms', 0):.0f}ms</span>"
                    f"</div>"
                )
            st.markdown(rows_html, unsafe_allow_html=True)
        else:
            st.markdown(
                "<div style='color:#3d6fe8; text-align:center; margin-top:60px; font-size:.9rem;'>"
                "⏳ In attesa di traffico...<br><small>Avvia networkGeneration2.py</small></div>",
                unsafe_allow_html=True,
            )

    @staticmethod
    def render_block_causes(events, blocked_hosts):
        st.markdown("<div class='sec-header'>Cause blocco</div>", unsafe_allow_html=True)

        dropped_events = [e for e in events if not e.get("accepted")]
        if not dropped_events:
            st.markdown(
                "<div style='color:#3d6fe8; text-align:center; margin-top:20px;'>"
                "✓ Nessun blocco rilevato negli ultimi eventi"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        causes = {
            "Host isolato": 0,
            "Timeout probe": 0,
            "LLM fallback": 0,
        }

        for e in dropped_events:
            src = e.get("src", "")
            dst = e.get("dst", "")
            reason = str(e.get("reason", ""))
            latency = float(e.get("latency_ms", 0) or 0)

            if src in blocked_hosts or dst in blocked_hosts:
                causes["Host isolato"] += 1
            elif "LLM unavailable" in reason or "Parse error" in reason:
                causes["LLM fallback"] += 1
            elif latency >= 3000:
                causes["Timeout probe"] += 1

        c1, c2, c3 = st.columns(3)
        for col, label in [
            (c1, "Host isolato"),
            (c2, "Timeout probe"),
            (c3, "LLM fallback"),
        ]:
            col.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-val'>{causes[label]}</div>"
                f"<div class='metric-lbl'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    @staticmethod
    def render_host_stats(node_stats, topo_data):

        st.markdown("<div class='sec-header'>Dettaglio Statistiche Host</div>", unsafe_allow_html=True)

        if node_stats:

            table_html = (
                "<table class='host-table'>"
                "<thead>"
                "<tr>"
                "<th>Host</th>"
                "<th>IP</th>"
                "<th>MAC</th>"
                "<th>Switch</th>"
                "<th>TX</th>"
                "<th>RX</th>"
                "<th>DROP</th>"
                "<th>TOT</th>"
                "<th>STATO</th>"
                "</tr>"
                "</thead>"
                "<tbody>"
            )

            for node, s in node_stats.items():
                link_info = next(
                    (l for l in topo_data["links"]
                     if l.get("type") == "h-s"
                     and (l.get("node1") == node or l.get("node2") == node)),
                    None,
                )

                ip = link_info.get("ip", "—") if link_info else "—"
                mac = link_info.get("mac", "—") if link_info else "—"
                switch = f"s{link_info.get('dpid', '?')}" if link_info else "—"

                blocked = node in st.session_state.blocked_hosts

                stato = (
                    "<span class='badge-err'>ISOLATO</span>"
                    if blocked else
                    "<span class='badge-ok'>ATTIVO</span>"
                )

                row_class = "err" if blocked else "ok"

                table_html += (
                    f"<tr class='{row_class}'>"
                    f"<td><span class='badge-proto'>{node}</span></td>"
                    f"<td>{ip}</td>"
                    f"<td>{mac}</td>"
                    f"<td>{switch}</td>"
                    f"<td><span class='badge-proto'>{s['tx']}</span></td>"
                    f"<td><span class='badge-proto'>{s['rx']}</span></td>"
                    f"<td><span class='badge-err'>{s['drops']}</span></td>"
                    f"<td>{s['packets']}</td>"
                    f"<td>{stato}</td>"
                    f"</tr>"
                )

            table_html += "</tbody></table>"

            st.markdown(table_html, unsafe_allow_html=True)

        else:

            st.markdown(
                "<div style='color:#3d6fe8; text-align:center; margin-top:40px;'>"
                "⏳ Nessuna statistica host disponibile"
                "</div>",
                unsafe_allow_html=True,
            )

    @staticmethod
    def render_flow_table(node_stats, topo_data, flow_table):
        st.markdown("<div class='sec-header'>Flow Table</div>", unsafe_allow_html=True)

        if flow_table:

            table_html = (
                "<table class='host-table'>"
                "<thead>"
                "<tr>"
                "<th>SW</th>"
                "<th>Priority</th>"
                "<th>In</th>"
                "<th>Src MAC</th>"
                "<th>Dst MAC</th>"
                "<th>Action</th>"
                "<th>Pkts</th>"
                "<th>Bytes</th>"
                "<th>Age</th>"
                "</tr>"
                "</thead>"
                "<tbody>"
            )

            for f in flow_table[:20]:
                match = f.get("match", {})
                actions = f.get("actions", [])

                action_str = (
                    actions[0].get("type", "DROP")
                    if actions and isinstance(actions[0], dict)
                    else (str(actions[0]) if actions else "DROP")
                )

                is_drop = action_str.upper() == "DROP"

                row_class = "err" if is_drop else "ok"

                action_badge = (
                    "<span class='badge-err'>DROP</span>"
                    if is_drop else
                    f"<span class='badge-ok'>{action_str}</span>"
                )

                table_html += (
                    f"<tr class='{row_class}'>"

                    f"<td><span class='badge-proto'>s{f.get('dpid', '?')}</span></td>"

                    f"<td><span class='badge-proto'>{f.get('priority', '?')}</span></td>"

                    f"<td>{match.get('in_port', '—')}</td>"

                    f"<td style='font-size:.75rem'>{str(match.get('eth_src') or match.get('dl_src') or '—')[:17]}</td>"

                    f"<td style='font-size:.75rem'>{str(match.get('eth_dst') or match.get('dl_dst') or '—')[:17]}</td>"

                    f"<td>{action_badge}</td>"

                    f"<td><span class='badge-proto'>{f.get('packet_count', 0)}</span></td>"

                    f"<td>{f.get('byte_count', 0)}</td>"

                    f"<td>{f.get('duration_sec', '?')}s</td>"

                    f"</tr>"
                )

            table_html += "</tbody></table>"

            st.markdown(table_html, unsafe_allow_html=True)

        else:

            st.markdown(
                "<div style='color:#3d6fe8; text-align:center; margin-top:40px;'>"
                "Nessun flow installato"
                "</div>",
                unsafe_allow_html=True,
            )

            # ── AGGIUNGI QUESTI METODI ALLA CLASSE Dashboard ──────────────────────────────

    @staticmethod
    def render_llm_activity(llm_logs: list):
        """Render LLM call log with slice, anomaly and fix decisions."""
        st.markdown("<div class='sec-header'>🤖 LLM Activity Log</div>", unsafe_allow_html=True)

        if not llm_logs:
            st.markdown(
                "<div style='color:#3d6fe8; text-align:center; margin-top:20px;'>"
                "⏳ Nessuna chiamata LLM ancora...</div>",
                unsafe_allow_html=True,
            )
            return

        TYPE_CONFIG = {
            "slice": {"icon": "🔀", "color": "#4dd8ff", "label": "SLICE"},
            "anomaly": {"icon": "🔍", "color": "#ff9800", "label": "ANOMALY"},
            "fix": {"icon": "🔧", "color": "#ff5252", "label": "FIX"},
        }

        rows_html = ""
        for log in llm_logs[:20]:
            cfg = TYPE_CONFIG.get(log.get("type", "slice"), TYPE_CONFIG["slice"])
            response = log.get("response", {})
            ts = log.get("ts", 0)
            prompt = log.get("prompt", "")

            # Build response summary based on type
            if log.get("type") == "slice":
                slice_id = response.get("slice", "?")
                slice_color = "#4dd8ff" if slice_id == 1 else "#ff9800"
                slice_label = "Slice 1 🔴" if slice_id == 1 else "Slice 2 🔵"
                resp_html = (
                    f"<span style='color:{slice_color}; font-weight:700;'>{slice_label}</span> "
                    f"<span style='color:#6a8aac; font-size:.75rem;'>— {response.get('reason', '')}</span>"
                )
            elif log.get("type") == "anomaly":
                anomaly = response.get("anomaly", False)
                color = "#ff5252" if anomaly else "#69f0ae"
                label = "⚠ ANOMALY DETECTED" if anomaly else "✓ Normal"
                resp_html = (
                    f"<span style='color:{color}; font-weight:700;'>{label}</span> "
                    f"<span style='color:#6a8aac; font-size:.75rem;'>— {response.get('details', '')}</span>"
                )
            else:  # fix
                action = response.get("action", "none")
                host = response.get("host", "")
                color = "#ff5252" if action == "block_host" else "#69f0ae"
                label = f"🚫 BLOCK {host}" if action == "block_host" else "✓ No action"
                resp_html = (
                    f"<span style='color:{color}; font-weight:700;'>{label}</span> "
                    f"<span style='color:#6a8aac; font-size:.75rem;'>— {response.get('reason', '')}</span>"
                )

            rows_html += f"""
                        <div style='display:flex; align-items:flex-start; gap:10px; padding:8px 10px;
                                    border-radius:8px; margin-bottom:4px;
                                    background:rgba(30,58,95,0.2);
                                    border-left:3px solid {cfg["color"]};'>
                            <span style='color:{cfg["color"]}; font-size:.7rem; min-width:52px;'>{ts:.1f}s</span>
                            <span style='background:{cfg["color"]}22; color:{cfg["color"]};
                                         border:1px solid {cfg["color"]}; border-radius:4px;
                                         padding:1px 6px; font-size:.65rem; font-weight:700; min-width:52px;
                                         text-align:center;'>{cfg["label"]}</span>
                            <span style='color:#aac; font-size:.78rem; min-width:140px;'>{prompt[:40]}</span>
                            <span style='flex:1;'>{resp_html}</span>
                        </div>
                        """

        st.markdown(rows_html, unsafe_allow_html=True)

    @staticmethod
    def render_slice_distribution(events: list):
        """Render pie chart of Slice 1 vs Slice 2 distribution."""
        slice_counts = {1: 0, 2: 0}
        for e in events:
            s = e.get("slice", 0)
            if s in slice_counts:
                slice_counts[s] += 1

        if not any(slice_counts.values()):
            return None

        fig = go.Figure(
            go.Pie(
                labels=["Slice 1 (Low-latency)", "Slice 2 (High-throughput)"],
                values=[slice_counts[1], slice_counts[2]],
                hole=0.55,
                marker=dict(
                    colors=["#ff5252", "#4dd8ff"],
                    line=dict(color="#0a0e1a", width=2),
                ),
                textinfo="label+percent",
                textfont_color="white",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=220,
        )
        return fig

    @staticmethod
    def render_llm_raw_calls(log_path):
        st.markdown("<div class='sec-header'>🧾 LLM Raw Calls</div>", unsafe_allow_html=True)

        if not log_path.exists():
            st.caption(f"Nessun file log trovato: {log_path}")
            return

        entries = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            st.error(f"Errore lettura log modello: {e}")
            return

        if not entries:
            st.caption("File log vuoto")
            return

        last = entries[-1]
        prompt = last.get("prompt", "")
        response = last.get("response", "")
        if isinstance(response, (dict, list)):
            response = json.dumps(response, ensure_ascii=False, indent=2)
        else:
            response = str(response)

        st.markdown("**Prompt**")
        st.code(prompt, language="text")
        st.markdown("**Response**")
        st.code(response, language="text")

    @staticmethod
    def _infer_blocked_hosts_from_flows(topo_data, flow_table):
        if not topo_data or not flow_table:
            return []

        mac_to_host = {}
        for link in topo_data.get("links", []):
            if link.get("type") != "h-s":
                continue
            host = link.get("node1")
            mac = str(link.get("mac", "")).lower()
            if host and mac:
                mac_to_host[mac] = host

        blocked = set()
        for flow in flow_table:
            if int(flow.get("priority", 0) or 0) != 65535:
                continue
            match = flow.get("match", {}) or {}
            src_mac = str(match.get("eth_src") or match.get("dl_src") or "").lower()
            host = mac_to_host.get(src_mac)
            if host:
                blocked.add(host)

        return sorted(blocked)

    def run(self):
        st.set_page_config(
            page_title="SDN Pro Controller",
            page_icon="🌐",
            layout="wide",
            initial_sidebar_state="expanded",
        )

        self.apply_styles()

        topo_data = self.loader.load_topology()
        if not topo_data:
            st.error("⚠ topology.json non trovato. Avvia prima **networkGeneration2.py**.")
            st.stop()

        metrics_data = self.loader.load_metrics()

        if "blocked_hosts" not in st.session_state:
            st.session_state.blocked_hosts = []

        flow_table = (metrics_data or {}).get("flow_table", [])
        inferred_blocked = self._infer_blocked_hosts_from_flows(topo_data, flow_table)
        st.session_state.blocked_hosts = sorted(
            set(st.session_state.blocked_hosts) | set(inferred_blocked)
        )

        sidebar = SidebarManager(topo_data, self.controller, self.loader, REFRESH_SEC)
        sidebar.host_controls()

        st.markdown(
            "<h1 style='font-size:2rem; font-weight:700; color:#4dd8ff; text-transform:uppercase; "
            "letter-spacing:2px; border-bottom:1px solid #1e3a5f; padding-bottom:8px; margin-bottom:4px;'>"
            "🌐 SDN Network Controller</h1><br>",
            unsafe_allow_html=True,
        )

        events = (metrics_data or {}).get("events", [])
        node_stats = (metrics_data or {}).get("node_stats", {})
        flow_table = (metrics_data or {}).get("flow_table", [])

        total_pkts = len(events)
        accepted = sum(1 for e in events if e.get("accepted"))
        dropped = total_pkts - accepted
        acc_rate = round(accepted / total_pkts * 100, 1) if total_pkts else 0
        avg_lat = round(sum(e.get("latency_ms", 0) for e in events) / max(1, total_pkts), 1)

        self.render_baseline_vs_llm_kpis(events)

        st.markdown("---")
        col_topo, col_events = st.columns([3, 2])

        with col_topo:
            st.markdown("<div class='sec-header'>Topologia di Rete</div>", unsafe_allow_html=True)
            G = self.vis.build_graph(topo_data)

            active_pkts = [(e["src"], e["dst"]) for e in events[:3]] if events else []
            fig = self.vis.draw_topology(G, st.session_state.blocked_hosts, None, active_pkts)
            st.pyplot(fig, width='stretch')
            plt.close(fig)

        with col_events:
            self.render_live_event_feed(events)

        self.render_block_causes(events, st.session_state.blocked_hosts)

        st.markdown("---")
        col_pie, col_tl, col_lat = st.columns(3)

        with col_pie:
            st.markdown("<div class='sec-header'>Distribuzione Protocolli</div>", unsafe_allow_html=True)
            fig_p = self.proto_pie(events)
            if fig_p:
                st.plotly_chart(fig_p, key="pie", config={"displayModeBar": False})
            else:
                st.caption("Nessun dato disponibile")

        with col_tl:
            st.markdown("<div class='sec-header'>Throughput nel Tempo</div>", unsafe_allow_html=True)
            fig_t = self.throughput_timeline(events)
            if fig_t:
                st.plotly_chart(fig_t, key="timeline", config={"displayModeBar": False})
            else:
                st.caption("Nessun dato disponibile")

        with col_lat:
            st.markdown("<div class='sec-header'>Latenza (ms)</div>", unsafe_allow_html=True)
            fig_l = self.latency_chart(events)
            if fig_l:
                st.plotly_chart(fig_l, key="latency", config={"displayModeBar": False})
            else:
                st.caption("Nessun dato disponibile")

        st.markdown("---")

        st.markdown("<div class='sec-header'>Statistiche per Nodo (TX / RX / Drops)</div>", unsafe_allow_html=True)

        fig_n = self.node_stats_chart(node_stats)
        if fig_n:
            st.plotly_chart(fig_n, key="nodestats", config={"displayModeBar": False})
        else:
            st.caption("Nessun dato disponibile")

        self.render_flow_table(node_stats, topo_data, flow_table)

        # ── LLM SECTION ───────────────────────────────────────────────────────────
        st.markdown("---")
        llm_logs = (metrics_data or {}).get("llm_logs", [])
        tab_llm_summary, tab_llm_raw = st.tabs(["LLM Activity", "LLM Raw Calls"])

        with tab_llm_summary:
            self.render_llm_activity(llm_logs)

            st.markdown("<div class='sec-header'>📊 Slice Distribution</div>", unsafe_allow_html=True)
            fig_slice = self.render_slice_distribution(events)
            if fig_slice:
                st.plotly_chart(fig_slice, key="slice_dist", config={"displayModeBar": False})
            else:
                st.caption("Nessun dato slice disponibile")

        with tab_llm_raw:
            self.render_llm_raw_calls(PATH_LLM_CALLS)

        if node_stats:
            st.markdown("---")
            self.render_host_stats(node_stats, topo_data)

        st.markdown(
            f"<div style='text-align:right; color:#1e3a5f; font-size:.7rem; margin-top:24px;'>"
            f"Auto-refresh ogni {REFRESH_SEC}s · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
            unsafe_allow_html=True,
        )
        time.sleep(REFRESH_SEC)
        st.rerun()


if __name__ == "__main__":
    Dashboard().run()
