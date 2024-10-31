from flask import Flask, render_template, jsonify, request
import requests
import threading
import time
from datetime import datetime
import logging

app = Flask(__name__)

# Configuration variables
INSTANCE_PORTS = [27601, 27602]
SYNC_START_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/start"
SYNC_PROGRESS_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/progress"
SYNC_COMMIT_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/commit"
REVERSE_SYNC_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/reverse"
SYNC_STOP_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/stop"  # Endpoint to stop sync

CHECK_INTERVAL = 60  # seconds between status checks

# Sync status data to share between threads
sync_status = {port: {"progress": {}, "status": "idle", "last_update": None} for port in INSTANCE_PORTS}

# Thread control
thread_lock = threading.Lock()
threads = {}

# Configure logging to log only debug and warning messages
logging.basicConfig(filename='sync_manager.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Function to start sync process
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
        else:
            logging.warning(f"Failed to start sync on port {port}. Response: {response.json()}")
            return False
    except Exception as e:
        logging.warning(f"Error starting sync for port {port}: {e}")
        return False

# Function to stop sync process
def stop_sync(port):
    stop_endpoint = SYNC_STOP_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(stop_endpoint, json={})
        response.raise_for_status()
        if response.json().get("success", False):
            with thread_lock:
                sync_status[port]["status"] = "stopped"
            return True
        return False
    except Exception as e:
        logging.warning(f"Error stopping sync for port {port}: {e}")
        return False

# Function to check sync progress
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

# Function to commit sync
def commit_sync(port):
    commit_endpoint = SYNC_COMMIT_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(commit_endpoint, json={})
        response.raise_for_status()
        if response.json().get('success', False):
            return True
        return False
    except Exception as e:
        logging.warning(f"Error committing sync for port {port}: {e}")
        return False

# Function to reverse sync
def reverse_sync(port):
    reverse_sync_endpoint = REVERSE_SYNC_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(reverse_sync_endpoint, json={})
        response.raise_for_status()
        if response.json().get('success', False):
            return True
        return False
    except Exception as e:
        logging.warning(f"Error starting reverse sync for port {port}: {e}")
        return False

# Background thread to monitor sync
def monitor_sync(port):
    while True:
        with thread_lock:
            if sync_status[port]["status"] != "running":
                break

        progress = check_sync_status(port)
        if progress:
            with thread_lock:
                sync_status[port]["progress"] = progress
                sync_status[port]["last_update"] = datetime.now()

            if progress.get("lagTimeSeconds") == 0 and progress.get("canCommit", False):
                if commit_sync(port):
                    with thread_lock:
                        sync_status[port]["status"] = "committed"
                break

        time.sleep(CHECK_INTERVAL)

# Routes
@app.route("/")
def index():
    return render_template("index.html", instance_ports=INSTANCE_PORTS)

@app.route("/start_sync/<int:port>", methods=["POST"])
def start_sync_endpoint(port):
    if start_sync(port):
        thread = threading.Thread(target=monitor_sync, args=(port,))
        thread.start()
        threads[port] = thread
        return jsonify({"message": f"Sync started on port {port}", "port": port})
    return jsonify({"message": f"Failed to start sync on port {port}", "port": port}), 500

@app.route("/stop_sync/<int:port>", methods=["POST"])
def stop_sync_endpoint(port):
    if stop_sync(port):
        with thread_lock:
            sync_status[port]["status"] = "stopped"
        return jsonify({"message": f"Sync stopped on port {port}", "port": port})
    return jsonify({"message": f"Failed to stop sync on port {port}", "port": port}), 500

@app.route("/commit_sync/<int:port>", methods=["POST"])
def commit_sync_endpoint(port):
    if commit_sync(port):
        with thread_lock:
            sync_status[port]["status"] = "committed"
        return jsonify({"message": f"Sync committed on port {port}", "port": port})
    return jsonify({"message": f"Failed to commit sync on port {port}", "port": port}), 500

@app.route("/reverse_sync/<int:port>", methods=["POST"])
def reverse_sync_endpoint(port):
    if reverse_sync(port):
        with thread_lock:
            sync_status[port]["status"] = "reverse-running"
        return jsonify({"message": f"Reverse sync started on port {port}", "port": port})
    return jsonify({"message": f"Failed to start reverse sync on port {port}", "port": port}), 500

@app.route("/sync_status/<int:port>")
def sync_status_endpoint(port):
    with thread_lock:
        status = sync_status.get(port, {})
    return jsonify(status)

# Initialize monitoring for any running sync processes
def initialize_monitoring():
    for port in INSTANCE_PORTS:
        progress = check_sync_status(port)
        if progress and progress.get("state") == "RUNNING":
            with thread_lock:
                sync_status[port]["status"] = "running"
                sync_status[port]["progress"] = progress
            thread = threading.Thread(target=monitor_sync, args=(port,))
            thread.start()
            threads[port] = thread

initialize_monitoring()

if __name__ == "__main__":
    app.run(debug=True)
