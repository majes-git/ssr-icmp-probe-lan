#!/usr/bin/env python3
import argparse
import json
import logging
import threading
import time
import sys

from collections import deque
from flask import Flask, jsonify, request
from pathlib import Path
from ping3 import ping

KEYS = ("transfer", "lan")
CONFIG_PATH = Path("/var/lib/128technology/t128-running.json")
YAML_PATH = Path("/etc/128technology/ssr-icmp-probe-lan.yaml")


def error(*msg):
    print(*msg)
    sys.exit(1)


def info(*msg):
    print(*msg)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ping monitor daemon with REST API"
    )
    parser.add_argument(
        "--destination",
        "-d",
        help="Destination address to ping"
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=1.0,
        help="Ping interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--max-window",
        "-w",
        type=int,
        default=3600,
        help="Max history window in seconds (default: 3600)"
    )
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="REST API bind address (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="REST API port (default: 8000)"
    )
    return parser.parse_args()


def find_destination_from_yaml():
    """
    Reads file in YAML_PATH
    Expected format:
        destination: 1.2.3.4
    """
    if not YAML_PATH.exists():
        return None

    try:
        for line in YAML_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("destination:"):
                _, value = line.split(":", 1)
                return value.strip()
    except Exception:
        pass

    return None


def find_lan_gateway():
    """Look for interfaces named transfer* or lan* and return first gateway."""
    if not CONFIG_PATH.exists():
        return None

    try:
        config = json.load(open(CONFIG_PATH))["datastore"]["config"]
    except FileNotFoundError:
        return None

    try:
        for router in config["authority"]["router"]:
            # TODO: match this asset against asset_id
            for node in router["node"]:
                for dev_if in node["device-interface"]:
                    for net_if in dev_if["network-interface"]:
                        if net_if["name"].startswith(KEYS):
                            for addr in net_if.get("address", []):
                                if "gateway" in addr:
                                    return addr["gateway"]
    except (KeyError, json.JSONDecodeError):
        pass

    return None


def resolve_destination(cli_destination):
    """Resolution priority: CLI > YAML > JSON config"""
    if cli_destination:
        info(f"Using destination from CLI: {cli_destination}")
        return cli_destination

    yaml_dest = find_destination_from_yaml()
    if yaml_dest:
        info(f"Using destination from YAML: {yaml_dest}")
        return yaml_dest

    json_dest = find_lan_gateway()
    if json_dest:
        info(f"Using destination from JSON config: {json_dest}")
        return json_dest

    return None


def create_app():
    return Flask(__name__)


def main():
    args = parse_args()

    destination = resolve_destination(args.destination)
    if not destination:
        error("No destination was given.")

    # Disable access logs
    logging.getLogger('werkzeug').disabled = True

    app = create_app()
    results = deque(maxlen=args.max_window)
    lock = threading.Lock()

    def ping_loop():
        ping_interval = args.interval
        while True:
            try:
                response = ping(destination, timeout=ping_interval)
                success = response is not None
            except Exception:
                success = False

            with lock:
                results.append((time.time(), success))

            time.sleep(ping_interval)

    def packet_loss(last_n_seconds: int) -> float:
        cutoff = time.time() - last_n_seconds
        with lock:
            window = [r for r in results if r[0] >= cutoff]

        if not window:
            return 0.0

        sent = len(window)
        received = sum(1 for _, ok in window if ok)
        return ((sent - received) / sent) * 100.0

    @app.route("/stats")
    def stats():
        window = request.args.get("window", default=5, type=int)
        loss = packet_loss(window)

        return jsonify({
            "destination": destination,
            "window_seconds": window,
            "packet_loss_percent": round(loss, 2),
        })

    t = threading.Thread(target=ping_loop, daemon=True)
    t.start()

    app.run(host=args.bind, port=args.port)


if __name__ == "__main__":
    main()
