import random
from typing import List, Dict, Any

MOCK_VIRTUAL_SERVERS = [
    {
        "name": "/Common/vs_portal_web_80",
        "fullPath": "/Common/vs_portal_web_80",
        "destination": "/Common/192.168.10.10:80",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "available", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}, {"name": "tcp"}]}
    },
    {
        "name": "/Common/vs_portal_secure_443",
        "fullPath": "/Common/vs_portal_secure_443",
        "destination": "/Common/192.168.10.10:443",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "available", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}, {"name": "clientssl"}, {"name": "tcp"}]}
    },
    {
        "name": "/Common/vs_api_gateway_8443",
        "fullPath": "/Common/vs_api_gateway_8443",
        "destination": "/Common/10.0.50.25:8443",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "unknown", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}, {"name": "serverssl"}, {"name": "clientssl"}]}
    },
    {
        "name": "/Common/vs_auth_service_8080",
        "fullPath": "/Common/vs_auth_service_8080",
        "destination": "/Common/10.0.50.30:8080",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "available", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}]}
    },
    {
        "name": "/Common/vs_legacy_crm_80",
        "fullPath": "/Common/vs_legacy_crm_80",
        "destination": "/Common/172.16.2.100:80",
        "enabled": False,
        "disabled": True,
        "status": {"availabilityState": "disabled", "enabledState": "disabled"},
        "profilesReference": {"items": [{"name": "http"}]}
    },
    {
        "name": "/Common/vs_partner_portal_443",
        "fullPath": "/Common/vs_partner_portal_443",
        "destination": "/Common/172.16.5.15:443",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "unknown", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}, {"name": "clientssl"}]}
    },
    {
        "name": "/Common/vs_internal_dns_53",
        "fullPath": "/Common/vs_internal_dns_53",
        "destination": "/Common/10.0.1.53:53",
        "enabled": False,
        "disabled": True,
        "status": {"availabilityState": "offline", "enabledState": "disabled"},
        "profilesReference": {"items": [{"name": "udp"}]}
    },
    {
        "name": "/Common/vs_offline_app_8080",
        "fullPath": "/Common/vs_offline_app_8080",
        "destination": "/Common/10.0.99.99:8080",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "offline", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}]}
    },
    {
        "name": "/Common/vs_offline_via_stats_80",
        "fullPath": "/Common/vs_offline_via_stats_80",
        "destination": "/Common/10.0.88.88:80",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "unknown", "enabledState": "enabled"},
        "stats": {
            "entries": {
                "https://localhost/mgmt/tm/ltm/virtual/~Common~vs_offline_via_stats_80/stats": {
                    "nestedStats": {
                        "entries": {
                            "status.availabilityState": {"description": "offline"}
                        }
                    }
                }
            }
        },
        "profilesReference": {"items": [{"name": "http"}]}
    },
    {
        "name": "/Common/vs_ipv6_portal_443",
        "fullPath": "/Common/vs_ipv6_portal_443",
        "destination": "/Common/2001:db8::1.443",
        "enabled": True,
        "disabled": False,
        "status": {"availabilityState": "available", "enabledState": "enabled"},
        "profilesReference": {"items": [{"name": "http"}, {"name": "clientssl"}]}
    }
]

def get_mock_virtual_servers() -> List[Dict[str, Any]]:
    return MOCK_VIRTUAL_SERVERS

def simulate_mock_curl_checks(vips: List[Dict[str, Any]], is_post_check: bool = False) -> List[Dict[str, Any]]:
    """
    Simulates curl response codes for mock VIPs during pre or post check.
    """
    results = []
    for vip in vips:
        res = dict(vip)
        name = vip.get("name", "")
        
        if not is_post_check:
            # Pre-check baseline response codes
            if "secure" in name or "portal" in name:
                codes = ["200", "200", "200"]
            elif "api" in name:
                codes = ["401", "401", "401"]
            elif "partner" in name:
                codes = ["302", "302", "302"]
            else:
                codes = ["200", "200", "200"]
        else:
            # Post-check response codes (with 1 simulated change for demonstration)
            if "partner" in name:
                # Simulate a minor delta or timeout on post check for demo comparison
                codes = ["302", "302", "302"]
            elif "api" in name:
                codes = ["401", "401", "401"]
            elif "secure" in name:
                codes = ["200", "200", "200"]
            else:
                codes = ["200", "200", "200"]

        res["curl_codes"] = codes
        res["curl_summary"] = ", ".join(codes)
        res["run_1"] = codes[0]
        res["run_2"] = codes[1]
        res["run_3"] = codes[2]
        results.append(res)
    
    results.sort(key=lambda x: x.get("name", ""))
    return results
