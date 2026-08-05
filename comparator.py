from typing import List, Dict, Any

def compare_pre_and_post_results(
    pre_results: List[Dict[str, Any]],
    post_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compares Pre-Check and Post-Check curl results for each virtual server.
    """
    post_map = {
        (item.get("name"), item.get("ip"), str(item.get("port")), item.get("protocol")): item
        for item in post_results
    }

    comparison_list = []

    for pre in pre_results:
        key = (pre.get("name"), pre.get("ip"), str(pre.get("port")), pre.get("protocol"))
        post = post_map.get(key)

        pre_summary = pre.get("curl_summary", "")
        pre_codes = pre.get("curl_codes", [])

        if not post:
            # VIP not found in post-check
            status = "❌ MISSING IN POST-CHECK"
            post_summary = "N/A"
            post_codes = []
            status_badge = "🔴 Missing"
        else:
            post_summary = post.get("curl_summary", "")
            post_codes = post.get("curl_codes", [])

            if pre_codes == post_codes:
                status = "✅ MATCH"
                status_badge = "🟢 Match"
            elif any(code in ["Timeout", "ConnRefused", "SSLError", "Error"] for code in post_codes):
                status = "❌ UNREACHABLE / ERROR"
                status_badge = "🔴 Unreachable"
            else:
                status = "⚠️ CHANGED"
                status_badge = "🟡 Response Changed"

        comp_record = {
            "name": pre.get("name"),
            "ip": pre.get("ip"),
            "port": pre.get("port"),
            "protocol": pre.get("protocol"),
            "f5_state": pre.get("state"),
            "pre_curl_summary": pre_summary,
            "pre_run_1": pre.get("run_1"),
            "pre_run_2": pre.get("run_2"),
            "pre_run_3": pre.get("run_3"),
            "post_curl_summary": post_summary,
            "post_run_1": post.get("run_1") if post else "-",
            "post_run_2": post.get("run_2") if post else "-",
            "post_run_3": post.get("run_3") if post else "-",
            "status": status,
            "status_badge": status_badge
        }
        comparison_list.append(comp_record)

    return comparison_list
