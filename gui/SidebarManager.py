import streamlit as st
from datetime import datetime


class SidebarManager:
    def __init__(self, topo_data, controller, loader, refresh_sec):
        self.topo_data = topo_data
        self.controller = controller
        self.loader = loader
        self.refresh_sec = refresh_sec

    def host_controls(self):
        if "blocked_hosts" not in st.session_state:
            st.session_state.blocked_hosts = []

        st.sidebar.markdown("---")

        metrics = self.loader.load_metrics()
        if metrics:
            uptime = metrics.get("uptime_s", 0)
            running = metrics.get("running", False)
            status_color = "#00e676" if running else "#ff5252"
            status_label = "● LIVE" if running else "● OFFLINE"
            status_html = (
                f"<div style='color:{status_color}; font-weight:700; font-size:.8rem; "
                f"letter-spacing:1px; text-align:center;'>{status_label} &nbsp;|&nbsp; "
                f"Uptime: {int(uptime)}s</div>"
            )
        else:
            status_html = (
                "<div style='color:#ff9800; font-size:.8rem; text-align:center;'>"
                "⚠ metrics.json not found — start networkGeneration.py</div>"
            )
        st.sidebar.markdown(
            f"<div style='color:#ddeeff; font-size:.72rem; text-align:center;'>"
            f"Updated every {self.refresh_sec}s &nbsp;|&nbsp; {datetime.now().strftime('%H:%M:%S')}"
            f"</div>"
            f"<div style='height:20px'></div>"
            f"{status_html}",
            unsafe_allow_html=True,
        )

        st.sidebar.markdown("---")
        st.sidebar.markdown("<div class='sec-header'>🔒 Host Security</div>", unsafe_allow_html=True)

        target_host = st.sidebar.selectbox("Select Host", self.topo_data["hosts"])
        link_info = next(
            (
                l
                for l in self.topo_data["links"]
                if l.get("type") == "h-s"
                and (l.get("node1") == target_host or l.get("node2") == target_host)
            ),
            None,
        )

        if link_info:
            dpid = link_info.get("dpid")
            port = link_info.get("port")
            mac = link_info.get("mac")
            ip = link_info.get("ip", "—")

            st.sidebar.markdown(
                f"<div style='font-size:.75rem; color:#c8d8f0; font-family:JetBrains Mono;'>"
                f"MAC: {mac}<br>IP: {ip}<br>Switch s{dpid} Port: {port}</div>",
                unsafe_allow_html=True,
            )

            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("🚫 Isolate", width="stretch"):
                    self.controller.enqueue_action(
                        "block_host", params={}, reason="manual_gui", host=target_host
                    )
                    st.session_state.pending_blocked.add(target_host)
                    st.toast(f"🚫 {target_host} isolating...")
                    st.rerun()

            with col2:
                if st.button("✅ Unblock", width="stretch"):
                    self.controller.enqueue_action(
                        "unblock_host", params={}, reason="manual_gui", host=target_host
                    )
                    st.session_state.pending_blocked.discard(target_host)
                    st.toast(f"✅ {target_host} unblocking...")
                    st.rerun()

            if target_host in st.session_state.blocked_hosts:
                st.sidebar.markdown(
                    f"<div class='alert-box'>⚠ {target_host} is currently isolated</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.sidebar.markdown(
                    f"<div class='ok-box'>✔ {target_host} active and reachable</div>",
                    unsafe_allow_html=True,
                )

            blocked_count = len(st.session_state.blocked_hosts)
            if blocked_count > 0:
                if st.sidebar.button(f"🧹 Unblock all ({blocked_count})", width="stretch"):
                    for host in list(st.session_state.blocked_hosts):
                        self.controller.enqueue_action(
                            "unblock_host", params={}, reason="manual_gui", host=host
                        )
                    st.session_state.pending_blocked.clear()
                    st.toast("✅ Unblocking all hosts...")
                    st.rerun()

        self.link_controls()
        return None, None

    def link_controls(self):
        st.sidebar.markdown("---")
        st.sidebar.markdown("<div class='sec-header'>🛠️ Link Management</div>", unsafe_allow_html=True)

        all_nodes = sorted(set(self.topo_data.get("hosts", [])) | set(self.topo_data.get("switches", [])))
        if len(all_nodes) < 2:
            st.sidebar.warning("Insufficient nodes for link operations")
            return

        existing_links = []
        seen_pairs = set()
        for link in self.topo_data.get("links", []):
            n1 = link.get("node1")
            n2 = link.get("node2")
            if not n1 or not n2:
                continue
            pair = tuple(sorted((str(n1), str(n2))))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            existing_links.append(pair)

        switch_nodes = sorted(self.topo_data.get("switches", []))
        existing_switch_links = [
            p for p in existing_links
            if p[0].startswith("s") and p[1].startswith("s")
        ]

        action = st.sidebar.selectbox(
            "Link action",
            ["set_link_tc", "add_link", "remove_link"],
            key="gui_link_action",
        )

        # Clear stale result when the user switches to a different action type
        if st.session_state.get("last_gui_action_type") not in (None, action):
            st.session_state.pop("last_gui_action_id", None)
            st.session_state.pop("last_gui_action_type", None)

        node1 = node2 = None
        params = {}
        _ready = False

        if action == "remove_link":
            if not existing_switch_links:
                st.sidebar.warning("No switch-to-switch links to remove")
            else:
                labels = [f"{a} ↔ {b}" for a, b in existing_switch_links]
                selected = st.sidebar.selectbox("Existing link", labels, key="remove_link_pair")
                node1, node2 = existing_switch_links[labels.index(selected)]
                params = {"node1": node1, "node2": node2}
                _ready = True

        elif action == "set_link_tc":
            if not existing_links:
                st.sidebar.warning("No links available in topology")
            else:
                labels = [f"{a} ↔ {b}" for a, b in existing_links]
                selected = st.sidebar.selectbox("Existing link", labels, key="set_link_tc_pair")
                node1, node2 = existing_links[labels.index(selected)]
                params = {"node1": node1, "node2": node2}
                use_bw = st.sidebar.checkbox("Set bandwidth (Mbps)", value=True, key="set_link_tc_use_bw")
                if use_bw:
                    bw = st.sidebar.number_input("BW Mbps", min_value=1, max_value=10000, value=20, step=1, key="set_link_tc_bw")
                    params["bw"] = float(bw)
                delay = st.sidebar.text_input("Delay", value="3ms", key="set_link_tc_delay")
                if delay.strip():
                    params["delay"] = delay.strip()
                _ready = True

        else:  # add_link
            if len(switch_nodes) < 2:
                st.sidebar.warning("At least two switches required to add an s-s link")
            else:
                existing_sw_set = set(existing_switch_links)
                node1 = st.sidebar.selectbox("Switch 1", switch_nodes, key="add_link_node1")
                node2_choices = [
                    n for n in switch_nodes
                    if n != node1 and tuple(sorted((node1, n))) not in existing_sw_set
                ]
                if not node2_choices:
                    st.sidebar.warning(f"No available switches to link with {node1} — all pairs already exist")
                else:
                    node2 = st.sidebar.selectbox("Switch 2", node2_choices, key="add_link_node2")
                    params = {"node1": node1, "node2": node2}
                    use_bw = st.sidebar.checkbox("Set bandwidth (Mbps)", value=False, key="add_link_use_bw")
                    if use_bw:
                        bw = st.sidebar.number_input("BW Mbps", min_value=1, max_value=10000, value=20, step=1, key="add_link_bw")
                        params["bw"] = float(bw)
                    delay = st.sidebar.text_input("Delay", value="", key="add_link_delay")
                    if delay.strip():
                        params["delay"] = delay.strip()
                    _ready = True

        if not _ready:
            return

        if st.sidebar.button("Submit action", width="stretch", key=f"submit_{action}"):
            try:
                request_id = self.controller.enqueue_action(action=action, params=params, reason="manual_gui")
                st.session_state["last_gui_action_id"] = request_id
                st.session_state["last_gui_action_type"] = action
                st.toast(f"Action queued: {action}")
            except Exception as e:
                st.sidebar.error(f"Failed to submit action: {e}")

        pending_id = st.session_state.get("last_gui_action_id")
        if pending_id:
            result = self.controller.get_action_result(pending_id)
            if result is None:
                st.sidebar.info("Action pending execution...")
            elif result.get("success"):
                st.sidebar.success(f"✅ {result.get('action')} executed")
                st.session_state.pop("last_gui_action_id", None)
                st.session_state.pop("last_gui_action_type", None)
            else:
                err = result.get("error", "unknown error")
                st.sidebar.error(f"❌ {result.get('action')} failed: {err}")
                st.session_state.pop("last_gui_action_id", None)
                st.session_state.pop("last_gui_action_type", None)

