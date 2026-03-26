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

        # st.sidebar.markdown(
        #     """
        #     <div style='text-align:center; padding: 16px 0 8px 0;'>
        #       <span style='font-size:2rem'>🌐</span><br>
        #       <span style='font-family:Rajdhani; font-size:1.3rem; font-weight:700; color:#4dd8ff;
        #                    letter-spacing:2px;'>SDN PRO CONTROLLER</span><br>
        #       <span style='font-size:.7rem; color:#3d6fe8; letter-spacing:1px;'>REAL-TIME NETWORK DASHBOARD</span>
        #     </div>
        #     """,
        #     unsafe_allow_html=True,
        # )

        st.sidebar.markdown("---")

        metrics = self.loader.load_metrics()
        if metrics:
            uptime = metrics.get("uptime_s", 0)
            running = metrics.get("running", False)
            status_color = "#00e676" if running else "#ff5252"
            status_label = "● LIVE" if running else "● OFFLINE"
            st.sidebar.markdown(
                f"<div style='color:{status_color}; font-weight:700; font-size:.8rem; "
                f"letter-spacing:1px; text-align:center;'>{status_label} &nbsp;|&nbsp; "
                f"Uptime: {int(uptime)}s</div>",
                unsafe_allow_html=True,
            )
        else:
            st.sidebar.markdown(
                "<div style='color:#ff9800; font-size:.8rem; text-align:center;'>"
                "⚠ metrics.json not found — start networkGeneration.py</div>",
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
                f"<div style='font-size:.75rem; color:#6a8aac; font-family:JetBrains Mono;'>"
                f"MAC: {mac}<br>IP: {ip}<br>Switch s{dpid} Port: {port}</div>",
                unsafe_allow_html=True,
            )

            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("🚫 Isolate", use_container_width=True):
                    resp = self.controller.send_rule("BLOCK", dpid, port, mac)
                    if self._ok_response(resp):
                        if target_host not in st.session_state.blocked_hosts:
                            st.session_state.blocked_hosts.append(target_host)
                        st.toast(f"🚫 {target_host} isolated!")
                        st.rerun()
                    else:
                        st.sidebar.error(self._format_response_error(resp, "Isolation failed"))

            with col2:
                if st.button("✅ Unblock", use_container_width=True):
                    resp = self.controller.send_rule("UNBLOCK", dpid, port, mac)
                    if self._ok_response(resp):
                        if target_host in st.session_state.blocked_hosts:
                            st.session_state.blocked_hosts.remove(target_host)
                        st.toast(f"✅ {target_host} restored!")
                        st.rerun()
                    else:
                        st.sidebar.error(self._format_response_error(resp, "Unblock failed"))

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
                if st.sidebar.button(f"🧹 Unblock all ({blocked_count})", use_container_width=True):
                    failed = []
                    for host in list(st.session_state.blocked_hosts):
                        host_link = next(
                            (
                                l for l in self.topo_data["links"]
                                if l.get("type") == "h-s"
                                and (l.get("node1") == host or l.get("node2") == host)
                            ),
                            None,
                        )
                        if not host_link:
                            failed.append(host)
                            continue

                        resp = self.controller.send_rule(
                            "UNBLOCK",
                            host_link.get("dpid"),
                            host_link.get("port"),
                            host_link.get("mac"),
                        )
                        if not self._ok_response(resp):
                            failed.append(host)

                    st.session_state.blocked_hosts = failed
                    if failed:
                        st.sidebar.warning(f"⚠ Partial unblock. Not restored: {', '.join(failed)}")
                    else:
                        st.toast("✅ All hosts have been restored")
                    st.rerun()

        st.sidebar.markdown("---")
        st.sidebar.caption(
            f"Updated every {self.refresh_sec}s | {datetime.now().strftime('%H:%M:%S')}"
        )

        self.link_controls()

        return None, None

    def link_controls(self):
        st.sidebar.markdown("---")
        st.sidebar.markdown("<div class='sec-header'>🛠️ Link Management</div>", unsafe_allow_html=True)

        all_nodes = sorted(set(self.topo_data.get("hosts", [])) | set(self.topo_data.get("switches", [])))
        if len(all_nodes) < 2:
            st.sidebar.caption("Insufficient nodes for link operations")
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

        if action in {"set_link_tc", "remove_link"}:
            selectable = existing_switch_links if action == "remove_link" else existing_links
            if not selectable:
                st.sidebar.warning("No links available in topology")
                return
            labels = [f"{a} ↔ {b}" for a, b in selectable]
            selected_label = st.sidebar.selectbox("Existing link", labels, key=f"{action}_pair")
            idx = labels.index(selected_label)
            node1, node2 = selectable[idx]
        else:
            if len(switch_nodes) < 2:
                st.sidebar.warning("At least two switches required to add an s-s link")
                return
            c1, c2 = st.sidebar.columns(2)
            with c1:
                node1 = st.selectbox("Switch 1", switch_nodes, key=f"{action}_node1")
            with c2:
                node2_choices = [n for n in switch_nodes if n != node1]
                node2 = st.selectbox("Switch 2", node2_choices, key=f"{action}_node2")

        params = {"node1": node1, "node2": node2}

        if action in {"set_link_tc", "add_link"}:
            use_bw = st.sidebar.checkbox("Set bandwidth (Mbps)", value=(action == "set_link_tc"), key=f"{action}_use_bw")
            if use_bw:
                bw = st.sidebar.number_input("BW Mbps", min_value=1, max_value=10000, value=20, step=1, key=f"{action}_bw")
                params["bw"] = float(bw)

            delay = st.sidebar.text_input("Delay (e.g. 3ms)", value="" if action == "add_link" else "3ms", key=f"{action}_delay")
            if delay.strip():
                params["delay"] = delay.strip()

        if st.sidebar.button("Submit action", use_container_width=True, key=f"submit_{action}"):
            try:
                request_id = self.controller.enqueue_action(action=action, params=params, reason="manual_gui")
                st.session_state["last_gui_action_id"] = request_id
                st.toast(f"Action queued: {action}")
            except Exception as e:
                st.sidebar.error(f"Failed to submit action: {e}")

        pending_id = st.session_state.get("last_gui_action_id")
        if pending_id:
            result = self.controller.get_action_result(pending_id)
            if not result:
                st.sidebar.info("Action pending execution...")
            else:
                if result.get("success"):
                    st.sidebar.success(f"✅ {result.get('action')} executed")
                else:
                    err = result.get("error", "unknown error")
                    st.sidebar.error(f"❌ {result.get('action')} failed: {err}")

    @staticmethod
    def _ok_response(resp):
        return resp is not None and 200 <= resp.status_code < 300

    @staticmethod
    def _format_response_error(resp, prefix: str) -> str:
        if resp is None:
            return f"{prefix}: controller unreachable"
        body = (resp.text or "").strip().replace("\n", " ")
        if len(body) > 140:
            body = body[:140] + "..."
        return f"{prefix}: HTTP {resp.status_code}" + (f" — {body}" if body else "")
