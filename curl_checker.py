import subprocess
import os
import time
import re
from typing import List, Dict, Any, Tuple
import ipaddress


def is_ipv6_address(ip_str: str) -> bool:
    """
    Step 1: Discover if the address is IPv4 or IPv6.
    Returns True for IPv6 address, False for IPv4.
    """
    if not ip_str:
        return False
    clean_ip = str(ip_str).strip("[]").strip()
    try:
        return ipaddress.ip_address(clean_ip).version == 6
    except ValueError:
        # Fallback check for IPv6 colons
        return ":" in clean_ip


def execute_single_curl(
    protocol: str, ip: str, port: str, timeout: int = 5
) -> Tuple[str, str, str]:
    """
    Executes a single HTTP/HTTPS curl check against a virtual IP (supports IPv4 and IPv6).
    Returns Tuple[code, command_str, debug_log]:
      - code: '200', '302', 'Timeout', 'ConnRefused', etc.
      - command_str: Exact CLI command executed
      - debug_log: Stdout/stderr details from execution
    """
    # Step 1: Clean and sanitize inputs
    proto_clean = str(protocol).strip().lower()
    clean_ip = str(ip).strip()
    is_v6 = is_ipv6_address(clean_ip)
    raw_ip = clean_ip.strip("[]").strip()
    port_str = str(port).strip()

    # Step 2: Format host string (bracket IPv6 addresses for HTTP/HTTPS URLs)
    if is_v6:
        host_str = f"[{raw_ip}]"
    else:
        host_str = raw_ip

    if (
        not port_str
        or (proto_clean == "http" and port_str == "80")
        or (proto_clean == "https" and port_str == "443")
    ):
        target_url = f"{proto_clean}://{host_str}/"
    else:
        target_url = f"{proto_clean}://{host_str}:{port_str}/"

    # Construct CLI curl command with -6 for IPv6 or -4 for IPv4
    ip_flag = "-6" if is_v6 else "-4"
    cmd = [
        "curl",
        ip_flag,
        "-s",
        "-S",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--retry",
        "1",
        "--retry-delay",
        "1",
        "--retry-connrefused",
        "--connect-timeout",
        "8",
        "-m",
        str(max(timeout + 5, 12)),
        "-k",
        target_url,
    ]
    cmd_str = " ".join(cmd)

    try:
        clean_env = os.environ.copy()
        clean_env.pop("http_proxy", None)
        clean_env.pop("https_proxy", None)
        clean_env.pop("HTTP_PROXY", None)
        clean_env.pop("HTTPS_PROXY", None)
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 8, env=clean_env
        )
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()
        rc = res.returncode

        full_output = f"stdout: '{stdout}' (rc: {rc}) | stderr: '{stderr}'".strip()

        # Extract 3-digit HTTP response code (100-599)
        match = re.search(r"\b([1-5]\d\d)\b", stdout)
        code = "000"
        if match:
            code = match.group(1)

        if code != "000":
            return code, cmd_str, full_output

        stderr_lower = stderr.lower()
        # Explicitly check for URL Format Errors (curl exit code 3 or malformed error messages)
        if (
            rc == 3
            or "url rejected" in stderr_lower
            or "malformed" in stderr_lower
            or "bad/illegal format" in stderr_lower
        ):
            return "FormatError", cmd_str, full_output
        # Prioritize Timeout detection before checking 'failed to connect'
        elif (
            rc == 28
            or "timeout" in stderr_lower
            or "timed out" in stderr_lower
            or "operation timed out" in stderr_lower
        ):
            return "Timeout", cmd_str, full_output
        elif (
            rc == 7 or "connection refused" in stderr_lower or "refused" in stderr_lower
        ):
            return "ConnRefused", cmd_str, full_output
        elif "couldn't connect" in stderr_lower or "failed to connect" in stderr_lower:
            return "ConnRefused", cmd_str, full_output
        elif (
            "ssl" in stderr_lower
            or "certificate" in stderr_lower
            or "handshake" in stderr_lower
        ):
            return "SSLError", cmd_str, full_output
        else:
            return "Error", cmd_str, full_output
    except subprocess.TimeoutExpired:
        return "Timeout", cmd_str, f"Command timed out after {timeout + 8}s"
    except Exception as e:
        return "Error", cmd_str, f"Execution Error: {str(e)}"


def execute_single_netcat(
    protocol: str, ip: str, port: str, timeout: int = 5
) -> Tuple[str, str, str]:
    """
    Executes a netcat (nc) check against a non-HTTP/HTTPS virtual server (TCP or UDP).
    Returns Tuple[code, command_str, debug_log].
    """
    clean_ip = str(ip).strip()
    is_v6 = is_ipv6_address(clean_ip)
    raw_ip = clean_ip.strip("[]").strip()
    port_str = str(port).strip()

    if not port_str:
        return "Error", "nc", "No port specified"

    proto_lower = protocol.lower()
    if proto_lower == "udp":
        cmd = ["nc", "-w", str(timeout), "-vuz", raw_ip, port_str]
    else:  # tcp
        cmd = ["nc", "-w", str(timeout), "-zv", raw_ip, port_str]

    if is_v6:
        cmd.insert(1, "-6")

    cmd_str = " ".join(cmd)

    try:
        clean_env = os.environ.copy()
        clean_env.pop("http_proxy", None)
        clean_env.pop("https_proxy", None)
        clean_env.pop("HTTP_PROXY", None)
        clean_env.pop("HTTPS_PROXY", None)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2, env=clean_env)
        full_output = (res.stdout + "\n" + res.stderr).strip()
        out_lower = full_output.lower()
        log_detail = f"Output: '{full_output}' (rc: {res.returncode})"

        if "succeeded" in out_lower or "open" in out_lower:
            return "Succeeded", cmd_str, log_detail
        elif "refused" in out_lower or "connection refused" in out_lower:
            return "ConnRefused", cmd_str, log_detail
        elif "timed out" in out_lower or "timeout" in out_lower:
            return "Timeout", cmd_str, log_detail
        elif res.returncode == 0:
            return "Succeeded", cmd_str, log_detail
        else:
            return "Closed", cmd_str, log_detail
    except subprocess.TimeoutExpired:
        return "Timeout", cmd_str, f"Netcat timed out after {timeout + 2}s"
    except Exception as e:
        return "Error", cmd_str, f"Netcat error ({str(e)})"


def execute_single_probe(
    protocol: str, ip: str, port: str, timeout: int = 5
) -> Tuple[str, str, str]:
    """
    Routes probe to execute_single_curl (for HTTP/HTTPS) or execute_single_netcat (for TCP/UDP).
    """
    proto_lower = str(protocol).lower()
    if proto_lower in ["tcp", "udp"]:
        return execute_single_netcat(proto_lower, ip, port, timeout=timeout)
    else:
        return execute_single_curl(protocol, ip, port, timeout=timeout)


def probe_vip(
    vip: Dict[str, Any],
    runs: int = 3,
    timeout: int = 5,
    start_delay: float = 0.0,
) -> Dict[str, Any]:
    """
    Runs specified number of probes (default 3) against a single virtual IP.
    Executes HTTP/HTTPS curl checks or TCP/UDP netcat probes based on VIP protocol.
    Stores command executed and detailed probe logs.
    """
    if start_delay > 0:
        time.sleep(start_delay)

    protocol = vip.get("protocol", "http")
    ip = vip.get("ip", "")
    port = str(vip.get("port", ""))

    response_codes = []
    run_logs = []
    last_cmd = ""

    for i in range(runs):
        code, cmd_str, log_detail = execute_single_probe(
            protocol, ip, port, timeout=timeout
        )
        response_codes.append(code)
        last_cmd = cmd_str
        run_logs.append(f"Run {i+1}: {code} [{log_detail}]")
        if i < runs - 1:
            time.sleep(0.6)

    result = dict(vip)
    result["curl_codes"] = response_codes
    result["curl_summary"] = ", ".join(response_codes)
    result["run_1"] = response_codes[0] if len(response_codes) > 0 else "-"
    result["run_2"] = response_codes[1] if len(response_codes) > 1 else "-"
    result["run_3"] = response_codes[2] if len(response_codes) > 2 else "-"
    result["executed_command"] = last_cmd
    result["probe_log"] = " | ".join(run_logs)
    return result


def run_curl_checks_sequentially(
    vips: List[Dict[str, Any]],
    runs: int = 3,
    timeout: int = 5,
) -> List[Dict[str, Any]]:
    """
    Runs 3 curl/nc checks against each virtual IP sequentially to prevent
    F5 SYN flood rate-limiting and socket queue contention.

    Executes HTTP/HTTPS (curl) virtual servers FIRST, followed by TCP/UDP (netcat)
    virtual servers SECOND, to prevent netcat probe socket contention/rate-limiting
    from affecting HTTP/HTTPS curl probes.

    Results are sorted alphabetically by VIP name for clean tabular display.
    """
    results = []
    if not vips:
        return results

    # Phase 1: Separate HTTP/HTTPS (curl) VIPs from TCP/UDP (netcat) VIPs
    http_vips = [v for v in vips if str(v.get("protocol", "http")).lower() in ["http", "https"]]
    non_http_vips = [v for v in vips if str(v.get("protocol", "http")).lower() not in ["http", "https"]]

    # Execute HTTP/HTTPS curl checks first
    for idx, vip in enumerate(http_vips):
        if idx > 0:
            time.sleep(0.3)
        try:
            res = probe_vip(vip, runs=runs, timeout=timeout, start_delay=0.0)
            results.append(res)
        except Exception as e:
            err_vip = dict(vip)
            err_vip["curl_codes"] = ["Error"] * runs
            err_vip["curl_summary"] = "Error"
            err_vip["run_1"] = "Error"
            err_vip["run_2"] = "Error"
            err_vip["run_3"] = "Error"
            results.append(err_vip)

    # Pause briefly between HTTP/HTTPS phase and TCP/UDP netcat phase if both exist
    if http_vips and non_http_vips:
        time.sleep(1.0)

    # Phase 2: Execute TCP/UDP netcat probes second
    for idx, vip in enumerate(non_http_vips):
        if idx > 0:
            time.sleep(0.5)
        try:
            res = probe_vip(vip, runs=runs, timeout=timeout, start_delay=0.0)
            results.append(res)
        except Exception as e:
            err_vip = dict(vip)
            err_vip["curl_codes"] = ["Error"] * runs
            err_vip["curl_summary"] = "Error"
            err_vip["run_1"] = "Error"
            err_vip["run_2"] = "Error"
            err_vip["run_3"] = "Error"
            results.append(err_vip)

    # Sort results by VIP name for clean tabular display
    results.sort(key=lambda x: x.get("name", ""))
    return results
