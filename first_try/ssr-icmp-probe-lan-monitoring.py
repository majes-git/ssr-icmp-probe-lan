#!/usr/bin/env python3

import requests

URL = "http://localhost:8000/stats"
THRESHOLD = 30.0  # percent

def check_status():
    try:
        response = requests.get(URL, timeout=5)
        response.raise_for_status()

        data = response.json()
        packet_loss = float(data.get("packet_loss_percent"))

        if packet_loss < THRESHOLD:
            print("UP")
        else:
            print("DOWN")

    except Exception:
        # Any failure means DOWN
        print("DOWN")

if __name__ == "__main__":
    check_status()
