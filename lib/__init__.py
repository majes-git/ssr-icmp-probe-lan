#!/usr/bin/env python3
"""
Shared library for KNI monitoring/state scripts.

Logic:
    1. Collect ALL static-routes using the provided KNI interface
    2. Extract all destination prefixes
    3. Iterate over ALL service-routes
    4. Consider only service-routes where:
         - reachability-detection exists
         - reachability-detection.enabled == true
         - probe section exists
         - at least one probe references a valid icmp-probe-profile
    5. Match service address against collected static-route prefixes
    6. Evaluate corresponding service-path meetsSLA value

If any validation fails, state is DOWN with proper reason.
"""

import argparse
import requests_unixsocket

BASE_URL = "http+unix://%2Fvar%2Frun%2F128technology%2Fspeakeasy.sock"


def parse_args():
    parser = argparse.ArgumentParser()

    # Optional arguments (passed by namespace framework)
    parser.add_argument('--kni-interface',
                        help='Standard argument used by namespace scripts')
    parser.add_argument('--kni-ip',
                        help='Standard argument used by namespace scripts')
    parser.add_argument('--kni-prefix-length',
                        help='Standard argument used by namespace scripts')
    parser.add_argument('--kni-gateway',
                        help='Standard argument used by namespace scripts')
    parser.add_argument('--mac-address',
                        help='Standard argument used by namespace scripts')
    parser.add_argument('--namespace',
                        help='Standard argument used by namespace scripts')

    # Positional arguments (also passed by namespace framework)
    parser.add_argument('kni_interface_pos', nargs='?',
                        help='Standard argument used by namespace scripts')
    parser.add_argument('namespace_pos', nargs='?',
                        help='Standard argument used by namespace scripts')

    return parser.parse_args()


def get_session():
    return requests_unixsocket.Session()


def get_json(session, path):
    url = f"{BASE_URL}{path}"
    response = session.get(url)
    response.raise_for_status()
    return response.json()


def evaluate_kni(session, kni_interface):
    """
    Returns:
        (status_bool, reason_string)
    """

    try:
        running = get_json(session, "/api/v1/config/running")
        stats = get_json(session, "/api/v1/service/servicePaths")
    except Exception as e:
        return False, f"API error: {e}"

    routers = running.get("authority", {}).get("router", [])
    services = running.get("authority", {}).get("service", [])
    service_paths = stats.get("servicePaths", [])

    # ======================================================
    # 1️⃣ Collect ALL static-route prefixes using KNI
    # ======================================================
    destination_prefixes = set()

    for router in routers:
        for routing in router.get("routing", []):
            for static in routing.get("staticRoute", []):
                for nh in static.get("nextHopInterface", []):
                    if nh.get("interface") == kni_interface:
                        prefix = static.get("destinationPrefix")
                        if prefix:
                            destination_prefixes.add(prefix)

    if not destination_prefixes:
        return False, f"No static-route using interface {kni_interface}"

    # ======================================================
    # 2️⃣ Evaluate ALL serviceRoutes
    # ======================================================
    for router in routers:

        # Collect valid ICMP probe profiles for this router
        available_icmp_profiles = {
            p.get("name")
            for p in router.get("icmpProbeProfile", [])
        }

        for sr in router.get("serviceRoute", []):

            rd = sr.get("reachabilityDetection")

            # Must have reachability-detection enabled
            if not rd or not rd.get("enabled"):
                continue

            probes = rd.get("probe")
            if not probes:
                return False, (
                    f"reachability-detection enabled but no icmp-probe-profile "
                    f"configured for service-route {sr.get('name')}"
                )

            # ==================================================
            # 3️⃣ Validate icmp-probe-profile
            # ==================================================
            icmp_profile_valid = False

            for probe in probes:
                icmp_profile = probe.get("icmpProbeProfile")
                if icmp_profile and icmp_profile in available_icmp_profiles:
                    icmp_profile_valid = True
                    break

            if not icmp_profile_valid:
                return False, (
                    f"icmp-probe-profile missing or undefined for "
                    f"service-route {sr.get('name')}"
                )

            service_name = sr.get("serviceName")
            service_route_name = sr.get("name")

            # Find linked service definition
            linked_service = next(
                (s for s in services if s.get("name") == service_name),
                None
            )

            if not linked_service:
                continue

            service_addresses = set(linked_service.get("address", []))

            # Check prefix match
            if not service_addresses.intersection(destination_prefixes):
                continue

            # ==================================================
            # 4️⃣ Evaluate SLA for matching service-route
            # ==================================================
            for sp in service_paths:
                if (
                    sp.get("serviceName") == service_name and
                    sp.get("serviceRouteName") == service_route_name
                ):
                    if sp.get("meetsSLA") == "Yes":
                        return True, (
                            f"icmp-probe successful for service {service_name}"
                        )
                    else:
                        return False, (
                            f"icmp-probe failed for service {service_name}"
                        )

            return False, (
                f"No live service-path found for service {service_name}"
            )

    return False, (
        "No service-route with reachability-detection enabled "
        "matching static-route subnet"
    )
