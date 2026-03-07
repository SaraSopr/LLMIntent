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
                "⚠ metrics.json non trovato — avvia networkGeneration2.py</div>",
                unsafe_allow_html=True,
            )

        st.sidebar.markdown("---")
        st.sidebar.markdown("<div class='sec-header'>🔒 Sicurezza Host</div>", unsafe_allow_html=True)

        target_host = st.sidebar.selectbox("Seleziona Host", self.topo_data["hosts"])
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
                if st.button("🚫 Isola", use_container_width=True):
                    resp = self.controller.send_rule("BLOCK", dpid, port, mac)
                    if self._ok_response(resp):
                        if target_host not in st.session_state.blocked_hosts:
                            st.session_state.blocked_hosts.append(target_host)
                        st.toast(f"🚫 {target_host} isolato!")
                        st.rerun()
                    else:
                        st.sidebar.error(self._format_response_error(resp, "Isolamento fallito"))

            with col2:
                if st.button("✅ Sblocca", use_container_width=True):
                    resp = self.controller.send_rule("UNBLOCK", dpid, port, mac)
                    if self._ok_response(resp):
                        if target_host in st.session_state.blocked_hosts:
                            st.session_state.blocked_hosts.remove(target_host)
                        st.toast(f"✅ {target_host} ripristinato!")
                        st.rerun()
                    else:
                        st.sidebar.error(self._format_response_error(resp, "Sblocco fallito"))

            if target_host in st.session_state.blocked_hosts:
                st.sidebar.markdown(
                    f"<div class='alert-box'>⚠ {target_host} è attualmente isolato</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.sidebar.markdown(
                    f"<div class='ok-box'>✔ {target_host} attivo e raggiungibile</div>",
                    unsafe_allow_html=True,
                )

            blocked_count = len(st.session_state.blocked_hosts)
            if blocked_count > 0:
                if st.sidebar.button(f"🧹 Sblocca tutti ({blocked_count})", use_container_width=True):
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
                        st.sidebar.warning(f"⚠ Sblocco parziale. Non ripristinati: {', '.join(failed)}")
                    else:
                        st.toast("✅ Tutti gli host sono stati ripristinati")
                    st.rerun()

        st.sidebar.markdown("---")
        st.sidebar.caption(
            f"Aggiornato ogni {self.refresh_sec}s | {datetime.now().strftime('%H:%M:%S')}"
        )

        return None, None

    @staticmethod
    def _ok_response(resp):
        return resp is not None and 200 <= resp.status_code < 300

    @staticmethod
    def _format_response_error(resp, prefix: str) -> str:
        if resp is None:
            return f"{prefix}: controller non raggiungibile"
        body = (resp.text or "").strip().replace("\n", " ")
        if len(body) > 140:
            body = body[:140] + "..."
        return f"{prefix}: HTTP {resp.status_code}" + (f" — {body}" if body else "")
