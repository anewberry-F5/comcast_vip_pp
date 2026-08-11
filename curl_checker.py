import subprocess
import requests
import urllib3
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple

import ipaddress
import shutil
import ssl
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LegacyTLSAdapter(HTTPAdapter):
    """
    Custom HTTPAdapter that configures an SSLContext to allow legacy SSL/TLS versions
    and ciphers (SECLEVEL=1) when probing F5 virtual servers with self-signed or legacy certs.
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except Exception:
            pass
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

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

def execute_single_curl(protocol: str, ip: str, port: str, timeout: int = 5, use_curl_cli: bool = False) -> Tuple[str, str, str]:
    """
    Executes a single HTTP/HTTPS curl check against a virtual IP (supports IPv4 and IPv6).
    Returns Tuple[code, command_str, debug_log]:
      - code: '200', '302', 'Timeout', 'ConnRefused', etc.
      - command_str: Exact CLI command or python requests URL executed
      - debug_log: Stdout/stderr details from execution
    """
    # Step 1: Discover if the address is IPv4 or IPv6
    clean_ip = str(ip).strip()
    is_v6 = is_ipv6_address(clean_ip)
    raw_ip = clean_ip.strip("[]").strip()

    # Step 2: Format host string (bracket IPv6 addresses for HTTP/HTTPS URLs)
    if is_v6:
        host_str = f"[{raw_ip}]"
    else:
        host_str = raw_ip

    port_str = str(port).strip()
    if not port_str or (protocol == "http" and port_str == "80") or (protocol == "https" and port_str == "443"):
        target_url = f"{protocol}://{host_str}/"
    else:
        target_url = f"{protocol}://{host_str}:{port_str}/"

    has_curl_cli = bool(shutil.which("curl"))
    if use_curl_cli or has_curl_cli:
        # Construct CLI curl command with -6 for IPv6 or -4 for IPv4
        ip_flag = "-6" if is_v6 else "-4"
        cmd = [
            "curl",
            ip_flag,
            "-s",
            "-S",  # Silent mode but show error on stderr if it fails
            "-o", "/dev/null",
            "-w", "%{http_code}",
            "--connect-timeout", str(timeout),
            "-m", str(timeout + 3),
            "-k",  # Ignore self-signed SSL errors
            target_url
        ]
        cmd_str = " ".join(cmd)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 3)
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()
            
            # Extract 3-digit HTTP response code (100-599)
            match = re.search(r'\b([1-5]\d\d)\b', stdout)
            if match:
                code = match.group(1)
                if code != "000":
                    return code, cmd_str, f"HTTP Code: {code} | stdout: '{stdout}'"

            stderr_lower = stderr.lower()
            log_detail = f"stdout: '{stdout}' | stderr: '{stderr}'"
            if "connection refused" in stderr_lower or "couldn't connect" in stderr_lower or "failed to connect" in stderr_lower:
                return "ConnRefused", cmd_str, log_detail
            elif "timed out" in stderr_lower or "operation timed out" in stderr_lower or "timeout" in stderr_lower:
                return "Timeout", cmd_str, log_detail
            elif "ssl" in stderr_lower or "certificate" in stderr_lower or "handshake" in stderr_lower:
                return "SSLError", cmd_str, log_detail
            else:
                return "Error", cmd_str, log_detail
        except subprocess.TimeoutExpired:
            return "Timeout", cmd_str, f"Command timed out after {timeout + 3}s"
        except Exception:
            # Fall back to requests library if curl CLI fails or is unavailable
            pass

    # Requests library implementation with Legacy TLS support and proxy bypass
    cmd_str = f"python requests.get('{target_url}', verify=False, timeout={timeout})"
    try:
        session = requests.Session()
        session.trust_env = False  # Disable system HTTP_PROXY/HTTPS_PROXY environment variables
        session.mount('https://', LegacyTLSAdapter())
        resp = session.get(
            target_url,
            verify=False,
            timeout=timeout,
            allow_redirects=False,
            headers={"User-Agent": "F5-VIP-Migration-Checker/1.0"}
        )
        return str(resp.status_code), cmd_str, f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return "Timeout", cmd_str, f"Timeout (> {timeout}s)"
    except requests.exceptions.ConnectionError as e:
        return "ConnRefused", cmd_str, f"Connection Refused ({str(e)[:80]})"
    except requests.exceptions.SSLError as e:
        return "SSLError", cmd_str, f"SSL Error ({str(e)[:80]})"
    except requests.exceptions.RequestException as e:
        return "Error", cmd_str, f"Error ({str(e)[:80]})"

def execute_single_netcat(protocol: str, ip: str, port: str, timeout: int = 5) -> Tuple[str, str, str]:
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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
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
    except Exception:
        code, log = execute_socket_probe(proto_lower, raw_ip, int(port_str), is_v6, timeout)
        return code, f"python socket ({proto_lower}://{raw_ip}:{port_str})", log

def execute_socket_probe(protocol: str, raw_ip: str, port: int, is_v6: bool, timeout: int = 5) -> Tuple[str, str]:
    """
    Fallback Python socket probe for TCP/UDP when netcat command line is unavailable.
    """
    import socket
    family = socket.AF_INET6 if is_v6 else socket.AF_INET
    try:
        if protocol == "udp":
            sock = socket.socket(family, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(b"", (raw_ip, port))
            sock.close()
            return "Succeeded", "Socket UDP packet sent"
        else:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((raw_ip, port))
            sock.close()
            return "Succeeded", "Socket TCP connected"
    except socket.timeout:
        return "Timeout", f"Socket timeout (> {timeout}s)"
    except ConnectionRefusedError:
        return "ConnRefused", "Socket connection refused"
    except Exception as e:
        return "Closed", f"Socket error ({str(e)[:80]})"

def execute_single_probe(protocol: str, ip: str, port: str, timeout: int = 5, use_curl_cli: bool = False) -> Tuple[str, str, str]:
    """
    Routes probe to execute_single_curl (for HTTP/HTTPS) or execute_single_netcat (for TCP/UDP).
    """
    proto_lower = str(protocol).lower()
    if proto_lower in ["tcp", "udp"]:
        return execute_single_netcat(proto_lower, ip, port, timeout=timeout)
    else:
        return execute_single_curl(protocol, ip, port, timeout=timeout, use_curl_cli=use_curl_cli)

def probe_vip(vip: Dict[str, Any], runs: int = 3, timeout: int = 5, use_curl_cli: bool = False) -> Dict[str, Any]:
    """
    Runs specified number of probes (default 3) against a single virtual IP.
    Executes HTTP/HTTPS curl checks or TCP/UDP netcat probes based on VIP protocol.
    Stores command executed and detailed probe logs.
    """
    protocol = vip.get("protocol", "http")
    ip = vip.get("ip", "")
    port = str(vip.get("port", ""))
    
    response_codes = []
    run_logs = []
    last_cmd = ""

    for i in range(runs):
        code, cmd_str, log_detail = execute_single_probe(protocol, ip, port, timeout=timeout, use_curl_cli=use_curl_cli)
        response_codes.append(code)
        last_cmd = cmd_str
        run_logs.append(f"Run {i+1}: {code} [{log_detail}]")
        if i < runs - 1:
            time.sleep(0.3)

    result = dict(vip)
    result["curl_codes"] = response_codes
    result["curl_summary"] = ", ".join(response_codes)
    result["run_1"] = response_codes[0] if len(response_codes) > 0 else "-"
    result["run_2"] = response_codes[1] if len(response_codes) > 1 else "-"
    result["run_3"] = response_codes[2] if len(response_codes) > 2 else "-"
    result["executed_command"] = last_cmd
    result["probe_log"] = " | ".join(run_logs)
    return result

def run_curl_checks_concurrently(vips: List[Dict[str, Any]], runs: int = 3, timeout: int = 5, max_workers: int = 10, use_curl_cli: bool = False) -> List[Dict[str, Any]]:
    """
    Runs 3 curl checks against each virtual IP in parallel using ThreadPoolExecutor.
    """
    results = []
    if not vips:
        return results

    with ThreadPoolExecutor(max_workers=min(max_workers, len(vips))) as executor:
        future_map = {
            executor.submit(probe_vip, vip, runs, timeout, use_curl_cli): vip
            for vip in vips
        }
        for future in as_completed(future_map):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                orig_vip = future_map[future]
                err_vip = dict(orig_vip)
                err_vip["curl_codes"] = ["Error"] * runs
                err_vip["curl_summary"] = "Error"
                err_vip["run_1"] = "Error"
                err_vip["run_2"] = "Error"
                err_vip["run_3"] = "Error"
                results.append(err_vip)

    # Sort results by VIP name for clean tabular display
    results.sort(key=lambda x: x.get("name", ""))
    return results
