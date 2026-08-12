import streamlit as st
import pandas as pd
import time
from f5_client import F5Client
from curl_checker import run_curl_checks_sequentially
from mock_data import get_mock_virtual_servers, simulate_mock_curl_checks
from comparator import compare_pre_and_post_results

# Page configuration
st.set_page_config(
    page_title="F5 BIG-IP VIP Migration Checker",
    page_icon="🔀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for modern aesthetic UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #0F172A;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .status-badge-match {
        color: #15803D;
        background-color: #DCFCE7;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-badge-changed {
        color: #B45309;
        background-color: #FEF3C7;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-badge-error {
        color: #B91C1C;
        background-color: #FEE2E2;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "pre_check_vips" not in st.session_state:
    st.session_state["pre_check_vips"] = None
if "pre_check_results" not in st.session_state:
    st.session_state["pre_check_results"] = None
if "post_check_results" not in st.session_state:
    st.session_state["post_check_results"] = None
if "comparison_results" not in st.session_state:
    st.session_state["comparison_results"] = None

# Header
st.markdown('<div class="main-header">🔀 F5 BIG-IP Virtual IP Migration Verification Tool</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Automated pre and post-migration validation for F5 BIG-IP LTM Virtual Servers</div>', unsafe_allow_html=True)

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ F5 Connection Settings")
    
    mock_mode = st.checkbox("🧪 Demo / Mock Mode", value=False, help="Use simulated F5 virtual servers and curl responses without connecting to real hardware.")
    
    if not mock_mode:
        f5_host = st.text_input("F5 BIG-IP Host / IP", value="", placeholder="e.g. 192.168.1.100 or bigip01.corp")
        f5_user = st.text_input("Username", value="", placeholder="admin")
        f5_pass = st.text_input("Password", type="password", value="")
        f5_port = st.number_input("Management Port", value=443, min_value=1, max_value=65535)
        verify_ssl = st.checkbox("Verify SSL Certificate", value=False)
    else:
        st.info("💡 **Mock Mode Enabled**: Pre and post checks will use simulated virtual server data.")
        f5_host = "mock-f5-bigip.local"
        f5_user = "demo_admin"
        f5_pass = "demo_pass"
        f5_port = 443
        verify_ssl = False

    st.divider()
    st.header("🔍 Probe Settings")
    probe_timeout = st.slider("Curl Timeout (seconds)", min_value=1, max_value=15, value=5)

    st.divider()
    if st.button("🗑️ Reset All Stored Check Data"):
        st.session_state["pre_check_vips"] = None
        st.session_state["pre_check_results"] = None
        st.session_state["post_check_results"] = None
        st.session_state["comparison_results"] = None
        st.rerun()

# Main Tabs
tab_pre, tab_post, tab_comp = st.tabs([
    "1️⃣ Pre-Check Baseline",
    "2️⃣ Post-Check Validation",
    "3️⃣ Comparison & Audit Report"
])

# -----------------------------------------------------------------------------
# TAB 1: PRE-CHECK
# -----------------------------------------------------------------------------
with tab_pre:
    st.subheader("Pre-Migration Baseline Check")
    st.write("Connects to F5 BIG-IP, pulls **active** and **unknown** virtual servers (name, IP, port, http/https protocol), and executes 3 curl requests against each virtual IP.")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_pre_btn = st.button("🚀 Run Pre-Check", type="primary", use_container_width=True)

    if run_pre_btn:
        if not mock_mode and (not f5_host or not f5_user or not f5_pass):
            st.error("❌ Please provide F5 Host, Username, and Password in the sidebar.")
        else:
            with st.spinner("Connecting to F5 BIG-IP & fetching virtual servers..."):
                try:
                    if mock_mode:
                        time.sleep(0.5) # Simulate API latency
                        raw_vips = get_mock_virtual_servers()
                        processed_vips = F5Client.process_virtual_servers(raw_vips)
                        processed_vips = F5Client.filter_mock_vips_by_stats(processed_vips)
                        st.toast("Fetched mock virtual servers successfully!", icon="✅")
                    else:
                        client = F5Client(f5_host, f5_user, f5_pass, port=f5_port, verify_ssl=verify_ssl, timeout=probe_timeout)
                        auth_ok, auth_msg = client.authenticate()
                        if not auth_ok:
                            st.error(f"❌ {auth_msg}")
                            st.stop()
                        
                        raw_vips = client.fetch_virtual_servers()
                        processed_vips = F5Client.process_virtual_servers(raw_vips)
                        with st.spinner("Checking virtual server stats for offline status..."):
                            processed_vips = client.filter_vips_by_stats(processed_vips)
                        st.toast(f"Fetched {len(processed_vips)} active virtual servers from F5.", icon="ℹ️")

                    if not processed_vips:
                        st.warning("⚠️ No active or unknown virtual servers found matching filter criteria.")
                        st.stop()

                    st.success(f"Found **{len(processed_vips)}** active/unknown virtual servers. Now executing 3 curl probes per VIP...")

                    # Run 3 curls per VIP
                    with st.spinner("Running 3 curl requests per virtual server..."):
                        if mock_mode:
                            pre_results = simulate_mock_curl_checks(processed_vips, is_post_check=False)
                        else:
                            pre_results = run_curl_checks_sequentially(
                                processed_vips,
                                runs=3,
                                timeout=probe_timeout
                            )

                    # Store in session state
                    st.session_state["pre_check_vips"] = processed_vips
                    st.session_state["pre_check_results"] = pre_results
                    st.toast("Pre-check baseline complete!", icon="🎉")

                except Exception as e:
                    st.error(f"❌ Error executing pre-check: {str(e)}")

    # Display Pre-Check Results if available
    if st.session_state["pre_check_results"]:
        results = st.session_state["pre_check_results"]
        st.divider()
        st.markdown("### 📊 Pre-Check Baseline Results")

        # Summary Metrics
        m1, m2, m3, m4 = st.columns(4)
        total_vips = len(results)
        http_cnt = sum(1 for x in results if x.get("protocol") == "http")
        https_cnt = sum(1 for x in results if x.get("protocol") == "https")
        active_cnt = sum(1 for x in results if x.get("state") == "active")
        unknown_cnt = sum(1 for x in results if x.get("state") == "unknown")

        m1.metric("Total Active/Unknown VIPs", total_vips)
        m2.metric("HTTP VIPs", http_cnt)
        m3.metric("HTTPS VIPs", https_cnt)
        m4.metric("F5 State Breakdown", f"{active_cnt} Active / {unknown_cnt} Unknown")

        # Table Display
        df_pre = pd.DataFrame(results)
        
        # Format DataFrame columns
        df_display = df_pre[["name", "ip", "port", "protocol", "state", "run_1", "run_2", "run_3", "curl_summary"]].copy()
        df_display.columns = [
            "Virtual Name", "IP Address", "Port", "Protocol", "F5 State", 
            "Run 1 Code", "Run 2 Code", "Run 3 Code", "3-Curl Summary"
        ]

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True
        )

        # Export CSV
        csv_pre = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Pre-Check Results (CSV)",
            data=csv_pre,
            file_name="f5_pre_check_results.csv",
            mime="text/csv"
        )

        # Troubleshooting Log Expander
        with st.expander("🛠️ View Executed Commands & Debug Logs (Troubleshooting)"):
            if "executed_command" in df_pre.columns:
                df_logs = df_pre[["name", "ip", "port", "protocol", "executed_command", "probe_log"]].copy()
                df_logs.columns = ["Virtual Name", "IP Address", "Port", "Protocol", "Command Executed", "Detailed Probe Logs"]
                st.dataframe(df_logs, use_container_width=True, hide_index=True)

                st.divider()
                st.markdown("#### 🔍 Interactive Verbose Log Inspector")
                selected_vip_name = st.selectbox(
                    "Select Virtual Server to inspect full raw stdout/stderr logs:",
                    options=df_pre["name"].tolist(),
                    key="select_pre_vip_log"
                )
                if selected_vip_name:
                    vip_row = df_pre[df_pre["name"] == selected_vip_name].iloc[0]
                    st.markdown(f"**Target URL / Host:** `{vip_row.get('ip')}:{vip_row.get('port')}` ({vip_row.get('protocol')})")
                    st.markdown("**Command Executed:**")
                    st.code(vip_row.get("executed_command", "N/A"), language="bash")
                    
                    raw_log = str(vip_row.get("probe_log", "N/A")).replace(" | Run ", "\n\nRun ")
                    st.markdown("**Full Output & Verbose Trace (stdout, rc, stderr):**")
                    st.code(raw_log, language="text")
            else:
                st.info("No command logs recorded.")

# -----------------------------------------------------------------------------
# TAB 2: POST-CHECK
# -----------------------------------------------------------------------------
with tab_post:
    st.subheader("Post-Migration Validation Check")
    st.write("Executes the same 3 curl requests against the virtual IPs after migration and compares response status codes against the pre-check baseline.")

    if not st.session_state["pre_check_results"]:
        st.info("ℹ️ Please run the **Pre-Check Baseline** first before performing a Post-Check.")
    else:
        st.success(f"Loaded **{len(st.session_state['pre_check_results'])}** virtual servers from Pre-Check baseline.")

        # Post-check execution host option
        with st.expander("⚙️ Post-Check Target Host Settings (Optional)", expanded=False):
            st.write("If you migrated to a new BIG-IP appliance with different management IP or credentials, specify them below:")
            post_host = st.text_input("Post-Check BIG-IP Host / IP (Leave blank to use pre-check host)", value="")
            post_user = st.text_input("Post-Check Username", value="")
            post_pass = st.text_input("Post-Check Password", type="password", value="")

        run_post_btn = st.button("🔄 Run Post-Check & Compare", type="primary", use_container_width=True)

        if run_post_btn:
            target_vips = st.session_state["pre_check_vips"]

            with st.spinner("Running post-check 3-curl probes..."):
                try:
                    if mock_mode:
                        time.sleep(0.5)
                        post_results = simulate_mock_curl_checks(target_vips, is_post_check=True)
                    else:
                        # If a post-check host was specified, optionally re-fetch VIPs from new BIG-IP
                        if post_host and post_user and post_pass:
                            client = F5Client(post_host, post_user, post_pass, port=f5_port, verify_ssl=verify_ssl, timeout=probe_timeout)
                            auth_ok, auth_msg = client.authenticate()
                            if not auth_ok:
                                st.error(f"❌ Post-Check Authentication Failed: {auth_msg}")
                                st.stop()
                            raw_post = client.fetch_virtual_servers()
                            post_target_vips = F5Client.process_virtual_servers(raw_post)
                            with st.spinner("Checking post-check virtual server stats for offline status..."):
                                post_target_vips = client.filter_vips_by_stats(post_target_vips)
                        else:
                            post_target_vips = target_vips

                        post_results = run_curl_checks_sequentially(
                            post_target_vips,
                            runs=3,
                            timeout=probe_timeout
                        )

                    # Store post results & compute comparison
                    st.session_state["post_check_results"] = post_results
                    comparison = compare_pre_and_post_results(
                        st.session_state["pre_check_results"],
                        post_results
                    )
                    st.session_state["comparison_results"] = comparison
                    st.toast("Post-check complete and comparison generated!", icon="🎉")

                except Exception as e:
                    st.error(f"❌ Error during post-check: {str(e)}")

        # Display Post-Check Results if available
        if st.session_state["comparison_results"]:
            comp = st.session_state["comparison_results"]
            st.divider()
            st.markdown("### 🔄 Post-Check Comparison Results")

            # Summary Metrics
            c1, c2, m3, m4 = st.columns(4)
            tot = len(comp)
            matches = sum(1 for x in comp if "MATCH" in x.get("status", ""))
            changed = sum(1 for x in comp if "CHANGED" in x.get("status", ""))
            failed = sum(1 for x in comp if "UNREACHABLE" in x.get("status", "") or "MISSING" in x.get("status", ""))

            c1.metric("Total VIPs Validated", tot)
            c2.metric("Matches (Passed)", matches, delta=f"{matches}/{tot}")
            m3.metric("Response Code Changed", changed, delta=f"-{changed}" if changed else "0", delta_color="off")
            m4.metric("Unreachable / Missing", failed, delta=f"-{failed}" if failed else "0", delta_color="inverse")

            # Comparison Table
            df_comp = pd.DataFrame(comp)
            df_comp_disp = df_comp[[
                "name", "ip", "port", "protocol",
                "pre_curl_summary", "post_curl_summary", "status"
            ]].copy()
            df_comp_disp.columns = [
                "Virtual Name", "IP Address", "Port", "Protocol",
                "Pre-Check Curls", "Post-Check Curls", "Comparison Status"
            ]

            st.dataframe(
                df_comp_disp,
                use_container_width=True,
                hide_index=True
            )

            # Export Comparison CSV
            csv_comp = df_comp_disp.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Pre vs Post Comparison Report (CSV)",
                data=csv_comp,
                file_name="f5_vip_migration_comparison_report.csv",
                mime="text/csv"
            )

            # Troubleshooting Log Expander
            with st.expander("🛠️ View Executed Commands & Debug Logs (Troubleshooting)"):
                if st.session_state["post_check_results"]:
                    df_post = pd.DataFrame(st.session_state["post_check_results"])
                    if "executed_command" in df_post.columns:
                        df_post_logs = df_post[["name", "ip", "port", "protocol", "executed_command", "probe_log"]].copy()
                        df_post_logs.columns = ["Virtual Name", "IP Address", "Port", "Protocol", "Command Executed", "Detailed Probe Logs"]
                        st.dataframe(df_post_logs, use_container_width=True, hide_index=True)

                        st.divider()
                        st.markdown("#### 🔍 Interactive Verbose Log Inspector")
                        selected_post_vip_name = st.selectbox(
                            "Select Virtual Server to inspect full raw stdout/stderr logs:",
                            options=df_post["name"].tolist(),
                            key="select_post_vip_log"
                        )
                        if selected_post_vip_name:
                            post_vip_row = df_post[df_post["name"] == selected_post_vip_name].iloc[0]
                            st.markdown(f"**Target URL / Host:** `{post_vip_row.get('ip')}:{post_vip_row.get('port')}` ({post_vip_row.get('protocol')})")
                            st.markdown("**Command Executed:**")
                            st.code(post_vip_row.get("executed_command", "N/A"), language="bash")
                            
                            post_raw_log = str(post_vip_row.get("probe_log", "N/A")).replace(" | Run ", "\n\nRun ")
                            st.markdown("**Full Output & Verbose Trace (stdout, rc, stderr):**")
                            st.code(post_raw_log, language="text")

# -----------------------------------------------------------------------------
# TAB 3: FULL COMPARISON & AUDIT REPORT
# -----------------------------------------------------------------------------
with tab_comp:
    st.subheader("Detailed Migration Comparison & Audit Report")
    st.write("Side-by-side comparison matrix showing pre-check vs post-check response codes per curl run.")

    if not st.session_state["comparison_results"]:
        st.info("ℹ️ Comparison data will appear here after both **Pre-Check** and **Post-Check** have been executed.")
    else:
        comp_data = st.session_state["comparison_results"]
        df_audit = pd.DataFrame(comp_data)

        # Filter option
        status_filter = st.selectbox(
            "Filter by Status",
            options=["All Statuses", "Matches Only (Passed)", "Changed / Differing Codes", "Unreachable / Errors"]
        )

        if status_filter == "Matches Only (Passed)":
            df_audit = df_audit[df_audit["status"].str.contains("MATCH", na=False)]
        elif status_filter == "Changed / Differing Codes":
            df_audit = df_audit[df_audit["status"].str.contains("CHANGED", na=False)]
        elif status_filter == "Unreachable / Errors":
            df_audit = df_audit[df_audit["status"].str.contains("UNREACHABLE|MISSING", na=False)]

        df_audit_disp = df_audit[[
            "name", "ip", "port", "protocol", "f5_state",
            "pre_run_1", "pre_run_2", "pre_run_3",
            "post_run_1", "post_run_2", "post_run_3",
            "status"
        ]].copy()

        df_audit_disp.columns = [
            "Virtual Name", "IP Address", "Port", "Protocol", "F5 State",
            "Pre Run 1", "Pre Run 2", "Pre Run 3",
            "Post Run 1", "Post Run 2", "Post Run 3",
            "Validation Status"
        ]

        st.dataframe(df_audit_disp, use_container_width=True, hide_index=True)

        csv_audit = df_audit_disp.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Full Audit Log (CSV)",
            data=csv_audit,
            file_name="f5_vip_full_audit_log.csv",
            mime="text/csv"
        )
