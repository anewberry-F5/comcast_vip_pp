# F5 BIG-IP Virtual IP Migration Verification Tool

A Python & Streamlit tool for performing pre-migration baseline audits and post-migration validation checks on F5 BIG-IP LTM Virtual Servers.

---

## 🌟 Key Features

1. **Authentication & Discovery**:
   - Connects to F5 BIG-IP via iControl REST API (`/mgmt/tm/ltm/virtual`).
   - Supports Token Authentication and Basic Authentication.
   - Parses Virtual Server Name, Destination IP Address (IPv4 & IPv6), Port, and Operational State.
   - Detects whether each Virtual Server is **HTTP** or **HTTPS** based on port (e.g., 80 vs 443) and attached SSL profiles (`clientssl`, `serverssl`).

2. **Filtering Rules**:
   - Automatically filters and retains **ONLY** Virtual Servers in **Active** or **Unknown** states (ignoring disabled or offline Virtual Servers).
   - Once active and unknown virtual servers are collected, queries `/mgmt/tm/ltm/virtual/<virtual_server_name>/stats` to inspect `status.availabilityState`. If `"description": "offline"`, the Virtual Server is excluded.

3. **IPv4 & IPv6 Discovery & Probing**:
   - **Step 1**: Discovers whether each Virtual Server IP address is **IPv4** or **IPv6**.
   - **Step 2**: Formats URLs appropriately (brackets IPv6 addresses e.g. `http://[2001:db8::1]:80/`) and executes 3 curl probes using `-6` for IPv6 or `-4` for IPv4.

3. **Pre-Check Baseline Workflow**:
   - Prompts for BIG-IP Host, Username, and Password in the UI.
   - Clicking **Pre-Check** retrieves matching VIPs and executes **3 curl / HTTP requests** against each VIP (`http://<virtual IP>:<port>/` or `https://<virtual IP>:<port>/`).
   - Displays a table showing Virtual Name, IP, Port, Protocol, and response status codes for each of the 3 curl runs.
   - Temporarily stores baseline results in session state and supports CSV export.

4. **Post-Check Validation Workflow**:
   - Clicking **Post-Check** executes the same 3-curl probe series against the virtual IPs (either on the same host or a new post-migration BIG-IP host).
   - Compares Post-Check response codes against Pre-Check response codes.
   - Displays a comparison matrix highlighting **Matches (✅ Passed)**, **Response Code Changes (⚠️ Warning)**, and **Unreachable / Error States (❌ Failed)**.

5. **Demo / Mock Mode**:
   - Includes a built-in mock mode to test and demonstrate the full pre/post check UI workflow offline without requiring an active F5 appliance.

---

## 📁 Repository Structure

- [`app.py`](file:///Users/a.newberry/_code/comcast_vip_pp/app.py): Main Streamlit application interface.
- [`f5_client.py`](file:///Users/a.newberry/_code/comcast_vip_pp/f5_client.py): F5 BIG-IP REST API client module (auth, VIP discovery, state & protocol parsing).
- [`curl_checker.py`](file:///Users/a.newberry/_code/comcast_vip_pp/curl_checker.py): Concurrent 3-curl HTTP probing engine.
- [`comparator.py`](file:///Users/a.newberry/_code/comcast_vip_pp/comparator.py): Pre vs Post comparison and delta analysis module.
- [`mock_data.py`](file:///Users/a.newberry/_code/comcast_vip_pp/mock_data.py): Sample data generator for mock/demo mode.
- [`test_workflow.py`](file:///Users/a.newberry/_code/comcast_vip_pp/test_workflow.py): Automated end-to-end test script.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.12+
- `uv` (recommended) or standard Python `venv` / `pip`

### 2. Install Dependencies
Using `uv`:
```bash
uv add streamlit requests pandas urllib3
```
Or using `pip`:
```bash
pip install streamlit requests pandas urllib3
```

### 3. Launch Streamlit UI
```bash
uv run streamlit run app.py
```
Or with standard python:
```bash
streamlit run app.py
```

### 4. Run via Docker / Docker Compose

Using **Docker Compose**:
```bash
docker compose up -d
```

Or using **Docker**:
```bash
docker build -t comcast-vip-pp .
docker run -d -p 8501:8501 --name comcast_vip_pp comcast-vip-pp
```

Then access the app at `http://localhost:8501`.

---

## 🖥️ How to Use

1. **Configure Connection**:
   - Open the Streamlit web interface in your browser (usually `http://localhost:8501`).
   - Enter your **F5 BIG-IP Host / IP**, **Username**, and **Password** in the sidebar.
   - *(Optional)* Check **Demo / Mock Mode** if you want to test the workflow without connecting to a real BIG-IP.

2. **Run Pre-Check Baseline**:
   - Navigate to the **1️⃣ Pre-Check Baseline** tab.
   - Click **🚀 Run Pre-Check**.
   - Review the metrics, active/unknown VIP list, and 3-curl response codes.
   - Download the pre-check CSV report if needed.

3. **Run Post-Check Validation**:
   - Navigate to the **2️⃣ Post-Check Validation** tab.
   - Click **🔄 Run Post-Check & Compare**.
   - View the comparison results showing match status, changed response codes, and unreachable VIPs.

4. **Audit Report**:
   - Open the **3️⃣ Comparison & Audit Report** tab for detailed run-by-run breakdown and downloadable migration audit logs.
