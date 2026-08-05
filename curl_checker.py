import subprocess
import requests
import urllib3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def execute_single_curl(protocol: str, ip: str, port: str, timeout: int = 5, use_curl_cli: bool = False) -> str:
    """
    Executes a single HTTP/HTTPS curl check against a virtual IP.
    Returns HTTP response status code (e.g. '200', '302', '404', '500') or error reason (e.g. 'Timeout', 'ConnRefused').
    """
    if not port or (protocol == "http" and port == "80") or (protocol == "https" and port == "443"):
        target_url = f"{protocol}://{ip}/"
    else:
        target_url = f"{protocol}://{ip}:{port}/"

    if use_curl_cli:
        # Construct CLI curl command: curl -v -s -o /dev/null -w "%{http_code}" --connect-timeout <timeout> -k <url>
        cmd = [
            "curl",
            "-v",
            "-s",
            "-o", "/dev/null",
            "-w", "%{http_code}",
            "--connect-timeout", str(timeout),
            "-k",  # Ignore self-signed SSL errors
            target_url
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
            stdout = res.stdout.strip()
            if stdout and stdout.isdigit() and stdout != "000":
                return stdout
            elif "Connection refused" in res.stderr:
                return "ConnRefused"
            elif "Timed out" in res.stderr or "Operation timed out" in res.stderr:
                return "Timeout"
            else:
                return "Error"
        except subprocess.TimeoutExpired:
            return "Timeout"
        except Exception:
            # Fall back to requests library if curl CLI fails or is unavailable
            pass

    # Requests library implementation
    try:
        resp = requests.get(
            target_url,
            verify=False,
            timeout=timeout,
            allow_redirects=False,
            headers={"User-Agent": "F5-VIP-Migration-Checker/1.0"}
        )
        return str(resp.status_code)
    except requests.exceptions.Timeout:
        return "Timeout"
    except requests.exceptions.ConnectionError:
        return "ConnRefused"
    except requests.exceptions.SSLError:
        return "SSLError"
    except requests.exceptions.RequestException as e:
        return "Error"

def probe_vip(vip: Dict[str, Any], runs: int = 3, timeout: int = 5, use_curl_cli: bool = False) -> Dict[str, Any]:
    """
    Runs specified number of curls (default 3) against a single virtual IP.
    """
    protocol = vip.get("protocol", "http")
    ip = vip.get("ip", "")
    port = str(vip.get("port", ""))
    
    response_codes = []
    for _ in range(runs):
        code = execute_single_curl(protocol, ip, port, timeout=timeout, use_curl_cli=use_curl_cli)
        response_codes.append(code)
        # Brief delay between runs
        time.sleep(0.1)

    result = dict(vip)
    result["curl_codes"] = response_codes
    result["curl_summary"] = ", ".join(response_codes)
    result["run_1"] = response_codes[0] if len(response_codes) > 0 else "-"
    result["run_2"] = response_codes[1] if len(response_codes) > 1 else "-"
    result["run_3"] = response_codes[2] if len(response_codes) > 2 else "-"
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
