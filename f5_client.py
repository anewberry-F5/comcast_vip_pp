import urllib3
import requests
import re
from typing import List, Dict, Any, Tuple

# Suppress insecure HTTPS warnings when connecting to BIG-IP with self-signed SSL certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class F5Client:
    """
    Client for communicating with F5 BIG-IP iControl REST API.
    """
    def __init__(self, host: str, username: str, password: str, port: int = 443, verify_ssl: bool = False, timeout: int = 10):
        # Format host URL properly
        clean_host = host.strip().replace("https://", "").replace("http://", "").strip("/")
        self.host = clean_host
        self.port = port
        self.base_url = f"https://{clean_host}:{port}"
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.auth_token = None

    def authenticate(self) -> Tuple[bool, str]:
        """
        Authenticate against F5 BIG-IP REST API to acquire a token or test Basic Auth.
        """
        login_url = f"{self.base_url}/mgmt/shared/authn/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "loginProviderName": "tmos"
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            resp = requests.post(
                login_url,
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token", {}).get("token")
                if token:
                    self.auth_token = token
                    return True, "Successfully authenticated via F5 Token Auth."
            
            # If token auth is not supported or returns 404/400, test basic auth on /mgmt/tm/ltm/virtual
            test_url = f"{self.base_url}/mgmt/tm/ltm/virtual?$top=1"
            test_resp = requests.get(
                test_url,
                auth=(self.username, self.password),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            if test_resp.status_code == 200:
                return True, "Successfully authenticated via Basic Auth."
            else:
                return False, f"Authentication failed (HTTP {test_resp.status_code}): {test_resp.text[:200]}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Connection error connecting to F5 BIG-IP at {self.host}: {str(e)}"

    def get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["X-F5-Auth-Token"] = self.auth_token
        return headers

    def fetch_virtual_servers(self) -> List[Dict[str, Any]]:
        """
        Fetch virtual servers from BIG-IP iControl REST API.
        """
        url = f"{self.base_url}/mgmt/tm/ltm/virtual?expandSubcollections=true"
        headers = self.get_headers()
        
        kwargs = {
            "headers": headers,
            "verify": self.verify_ssl,
            "timeout": self.timeout
        }
        if not self.auth_token:
            kwargs["auth"] = (self.username, self.password)

        resp = requests.get(url, **kwargs)
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch virtual servers from BIG-IP (HTTP {resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        raw_items = data.get("items", [])
        return raw_items

    @staticmethod
    def parse_destination(destination_str: str) -> Tuple[str, str]:
        """
        Parse destination string from F5 API format into IP and Port (supports IPv4 and IPv6).
        Examples:
        - '/Common/192.168.10.50:80' -> ('192.168.10.50', '80')
        - '/Common/10.0.0.1%1:443' -> ('10.0.0.1', '443')
        - '/Common/2001:db8::1.80' -> ('2001:db8::1', '80')
        - '/Common/[2001:db8::1]:80' -> ('2001:db8::1', '80')
        - '10.1.1.1:8080' -> ('10.1.1.1', '8080')
        """
        if not destination_str:
            return "", ""
        
        # Remove partition prefix e.g., /Common/
        clean_dest = destination_str.split("/")[-1].strip()
        
        # Strip route domain suffix like %1
        if "%" in clean_dest:
            clean_dest = re.sub(r'%\d+', '', clean_dest)

        # Case 1: Bracketed IPv6 format e.g. [2001:db8::1]:80
        if clean_dest.startswith("["):
            match = re.match(r'^\[([^\]]+)\](?::(\d+))?$', clean_dest)
            if match:
                return match.group(1), match.group(2) or ""

        # Case 2: Dot notation for IPv6 with port e.g. 2001:db8::1.80
        if ":" in clean_dest and "." in clean_dest:
            parts = clean_dest.rsplit(".", 1)
            if parts[1].isdigit():
                return parts[0], parts[1]

        # Case 3: Standard colon notation (e.g. 192.168.10.50:80 or 2001:db8::1:80)
        if ":" in clean_dest:
            parts = clean_dest.rsplit(":", 1)
            if parts[1].isdigit():
                return parts[0], parts[1]
            return clean_dest, ""

        return clean_dest, ""

    @classmethod
    def process_virtual_servers(cls, raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses raw F5 virtual server JSON data into clean virtual server records.
        Filters for ONLY active and unknown virtual servers.
        """
        processed_vips = []

        for item in raw_items:
            name = item.get("name") or item.get("fullPath", "Unknown_VS")
            full_path = item.get("fullPath", name)
            dest_str = item.get("destination", "")
            ip, port = cls.parse_destination(dest_str)

            # Extract top-level flags and status fields
            disabled = item.get("disabled", False)
            enabled = item.get("enabled", True)
            
            status_obj = item.get("status", {})
            if isinstance(status_obj, dict):
                avail_state = str(item.get("availabilityState") or status_obj.get("availabilityState", "")).lower()
                enabled_state = str(item.get("enabledState") or status_obj.get("enabledState", "")).lower()
            else:
                avail_state = str(item.get("availabilityState", "")).lower()
                enabled_state = str(item.get("enabledState", "")).lower()

            # Explicitly disregard virtuals that are disabled or offline
            if disabled or not enabled:
                continue
            if "disabled" in enabled_state or "offline" in avail_state or "disabled" in avail_state or avail_state in ["offline", "disabled", "red"]:
                continue

            # Classify remaining virtuals: retain ONLY 'active' or 'unknown'
            if avail_state in ["available", "green"]:
                norm_state = "active"
            elif avail_state in ["unknown", "blue"]:
                norm_state = "unknown"
            elif not avail_state:
                # Default for enabled virtuals with unpopulated availability state
                norm_state = "unknown"
            else:
                # Disregard any other availability states that are neither active nor unknown
                continue

            # Determine if VIP is HTTP or HTTPS
            # Check profiles attached
            profiles = []
            prof_ref = item.get("profilesReference", {})
            if isinstance(prof_ref, dict):
                p_items = prof_ref.get("items", [])
                for p in p_items:
                    if isinstance(p, dict):
                        profiles.append(p.get("name", "").lower())

            has_ssl_profile = any("ssl" in p or "clientssl" in p for p in profiles)
            has_http_profile = any("http" in p for p in profiles)

            # Protocol detection logic
            if port == "443" or port == "8443" or port == "4433" or has_ssl_profile:
                protocol = "https"
            else:
                protocol = "http"

            processed_vips.append({
                "name": name,
                "full_path": full_path,
                "ip": ip,
                "port": port,
                "protocol": protocol,
                "state": norm_state,
                "destination_raw": dest_str,
                "profiles": profiles,
                "raw_stats": item.get("stats", {})
            })

        return processed_vips

    @staticmethod
    def format_f5_name_for_url(name_or_path: str) -> str:
        """
        Formats a virtual server name or full path for iControl REST URL parameters.
        F5 iControl REST uses tilde (~) in place of forward slash (/).
        Examples:
        - '/Common/vs_portal_web_80' -> '~Common~vs_portal_web_80'
        - 'vs_portal_web_80' -> '~Common~vs_portal_web_80'
        - '~Common~vs_portal_web_80' -> '~Common~vs_portal_web_80'
        """
        if not name_or_path:
            return ""
        clean = name_or_path.strip()
        if clean.startswith("/"):
            return clean.replace("/", "~")
        elif not clean.startswith("~"):
            return f"~Common~{clean}"
        return clean

    def get_virtual_server_stats(self, virtual_name_or_path: str) -> Dict[str, Any]:
        """
        Fetch stats for a single virtual server from /mgmt/tm/ltm/virtual/<virtual_server_name>/stats
        """
        formatted_name = self.format_f5_name_for_url(virtual_name_or_path)
        url = f"{self.base_url}/mgmt/tm/ltm/virtual/{formatted_name}/stats"
        headers = self.get_headers()
        
        kwargs = {
            "headers": headers,
            "verify": self.verify_ssl,
            "timeout": self.timeout
        }
        if not self.auth_token:
            kwargs["auth"] = (self.username, self.password)

        try:
            resp = requests.get(url, **kwargs)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        return {}

    @staticmethod
    def extract_availability_from_stats(stats_json: Dict[str, Any]) -> str:
        """
        Parses status.availabilityState description from F5 stats response.
        Example stats structure:
        {
          "entries": {
            "https://localhost/mgmt/tm/ltm/virtual/~Common~vs_name/stats": {
              "nestedStats": {
                "entries": {
                  "status.availabilityState": {
                    "description": "offline"
                  }
                }
              }
            }
          }
        }
        """
        if not isinstance(stats_json, dict):
            return ""

        entries = stats_json.get("entries", {})
        if isinstance(entries, dict):
            for key, val in entries.items():
                if isinstance(val, dict):
                    nested = val.get("nestedStats", {}).get("entries", {})
                    if isinstance(nested, dict):
                        avail_obj = nested.get("status.availabilityState", {})
                        if isinstance(avail_obj, dict):
                            desc = avail_obj.get("description") or avail_obj.get("value", "")
                            if desc:
                                return str(desc).strip().lower()

        direct_avail = stats_json.get("status.availabilityState", {})
        if isinstance(direct_avail, dict):
            desc = direct_avail.get("description") or direct_avail.get("value", "")
            if desc:
                return str(desc).strip().lower()
        elif isinstance(direct_avail, str):
            return direct_avail.strip().lower()

        return ""

    def filter_vips_by_stats(self, vips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Queries /mgmt/tm/ltm/virtual/<virtual_server_name>/stats for each virtual server.
        If status.availabilityState has description: "offline", do NOT include that virtual server.
        """
        filtered = []
        for vip in vips:
            full_path = vip.get("full_path") or vip.get("name", "")
            
            stats_data = {}
            if hasattr(self, "base_url") and self.base_url:
                stats_data = self.get_virtual_server_stats(full_path)
            
            if not stats_data and "raw_stats" in vip:
                stats_data = vip["raw_stats"]

            avail_desc = self.extract_availability_from_stats(stats_data)
            
            # Disregard if stats explicitly report availability description as "offline"
            if avail_desc == "offline":
                continue

            filtered.append(vip)

        return filtered

    @classmethod
    def filter_mock_vips_by_stats(cls, vips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters mock virtual servers based on embedded raw_stats data.
        """
        filtered = []
        for vip in vips:
            stats_data = vip.get("raw_stats", {})
            avail_desc = cls.extract_availability_from_stats(stats_data)
            if avail_desc == "offline":
                continue
            filtered.append(vip)
        return filtered
