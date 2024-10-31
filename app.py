from flask import Flask, render_template, jsonify, request
import requests
import threading
import time
from datetime import datetime
import logging

app = Flask(__name__)

INSTANCE_PORTS = [27601, 27602]
SYNC_START_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/start"
SYNC_PROGRESS_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/progress"
SYNC_COMMIT_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/commit"
REVERSE_SYNC_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/reverse"
SYNC_STOP_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/stop"

CHECK_INTERVAL = 60  # seconds between status checks

sync_status = {port: {"progress": {}, "status": "idle", "last_update": None} for port in INSTANCE_PORTS}

thread_lock = threading.Lock()
threads = {}

# Configure logging to show only DEBUG and WARNING messages
logging.basicConfig(
    filename='sync_manager.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger().setLevel(logging.WARNING)  # Exclude INFO level

def start_sync(port):
    payload = {
        "source": "cluster0",
        "destination": "cluster1",
        "reversible": True,
        "enableUserWriteBlocking": True
    }
    start_endpoint = SYNC_START_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(start_endpoint, json=payload)
        response.raise_for_status()
        if response.json().get("success", False):
            with thread_lock:
                sync_status[port]["status"] = "running"
            return True
    except Exception as e:
        logging.warning(f"Error starting sync for port {port}: {e}")
    return False

def check_sync_status(port):
    progress_endpoint = SYNC_PROGRESS_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.get(progress_endpoint)
        response.raise_for_status()
        status_data = response.json()
        logging.debug(f"Sync status for port {port}: {status_data}")
        return status_data.get("progress", {})
    except Exception as e:
        logging.warning(f"Error checking sync status for port {port}: {e}")
    return None

@app.route("/sync_status/<int:port>")
def sync_status_endpoint(port):
    with thread_lock:
        status = sync_status.get(port, {})
    return jsonify(status)

# Other route and function definitions remain unchanged
