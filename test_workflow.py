from f5_client import F5Client
from mock_data import get_mock_virtual_servers, simulate_mock_curl_checks
from curl_checker import run_curl_checks_concurrently, is_ipv6_address, execute_single_curl
from comparator import compare_pre_and_post_results

def test_ipv6_discovery():
    print("0. Testing IPv4 vs IPv6 discovery & parsing...")
    assert not is_ipv6_address("192.168.1.1"), "192.168.1.1 must be detected as IPv4"
    assert not is_ipv6_address("10.0.50.25"), "10.0.50.25 must be detected as IPv4"
    assert is_ipv6_address("2001:db8::1"), "2001:db8::1 must be detected as IPv6"
    assert is_ipv6_address("[2001:db8::1]"), "[2001:db8::1] must be detected as IPv6"
    assert is_ipv6_address("fe80::1ff:fe23:4567:890a"), "fe80::... must be detected as IPv6"

    # Test F5 destination parser with IPv4 and IPv6 formats
    ip4, port4 = F5Client.parse_destination("/Common/192.168.10.50:80")
    assert ip4 == "192.168.10.50" and port4 == "80"

    ip6_dot, port6_dot = F5Client.parse_destination("/Common/2001:db8::1.443")
    assert ip6_dot == "2001:db8::1" and port6_dot == "443"

    ip6_bracket, port6_bracket = F5Client.parse_destination("/Common/[2001:db8::1]:8443")
    assert ip6_bracket == "2001:db8::1" and port6_bracket == "8443"

    print(" - IPv4 vs IPv6 Discovery & Destination Parsing tests passed!")

def test_full_pipeline():
    print("1. Testing mock virtual server processing...")
    raw_vips = get_mock_virtual_servers()
    processed = F5Client.process_virtual_servers(raw_vips)
    
    print(f"Processed {len(processed)} active/unknown VIPs out of {len(raw_vips)} raw VIPs before stats check.")

    print("\n1b. Testing stats endpoint availability filtering...")
    filtered_vips = F5Client.filter_mock_vips_by_stats(processed)
    print(f"Retained {len(filtered_vips)} VIPs after stats check.")
    for p in filtered_vips:
        print(f" - {p['name']} | IP: {p['ip']} | Port: {p['port']} | Protocol: {p['protocol']} | State: {p['state']}")
        assert p['state'] in ['active', 'unknown'], "Filtered VIP state must be active or unknown"
        assert p['protocol'] in ['http', 'https', 'tcp', 'udp'], "Protocol must be http, https, tcp, or udp"

    processed_names = [p['name'] for p in filtered_vips]
    assert "/Common/vs_legacy_crm_80" not in processed_names, "Disabled VIP must be excluded"
    assert "/Common/vs_internal_dns_53" not in processed_names, "Offline VIP must be excluded"
    assert "/Common/vs_offline_app_8080" not in processed_names, "Offline VIP must be excluded"
    assert "/Common/vs_offline_via_stats_80" not in processed_names, "VIP with stats offline description must be excluded"

    processed = filtered_vips

    print("\n2. Testing Pre-Check simulated curl checks...")
    pre_results = simulate_mock_curl_checks(processed, is_post_check=False)
    assert len(pre_results) == len(processed)
    for r in pre_results:
        print(f" - {r['name']}: {r['curl_summary']}")
        assert len(r['curl_codes']) == 3, "Must have exactly 3 curl response codes"

    print("\n3. Testing Post-Check simulated curl checks...")
    post_results = simulate_mock_curl_checks(processed, is_post_check=True)
    assert len(post_results) == len(processed)

    print("\n4. Testing Comparison calculation...")
    comparison = compare_pre_and_post_results(pre_results, post_results)
    assert len(comparison) == len(processed)
    for c in comparison:
        print(f" - {c['name']} | Pre: {c['pre_curl_summary']} | Post: {c['post_curl_summary']} | Status: {c['status']}")

    print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_ipv6_discovery()
    test_full_pipeline()
