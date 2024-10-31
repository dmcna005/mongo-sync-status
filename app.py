from flask import Flask, render_template, jsonify, request
import requests
import threading
import time
from datetime import datetime
import logging

app = Flask(__name__)

# Configuration variables
INSTANCE_PORTS = [27601, 27602]
SYNC_PROGRESS_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/progress"
SYNC_COMMIT_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/commit"
REVERSE_SYNC_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/reverse"
CHECK_INTERVAL = 60  # seconds between status checks

# Sync status data to share between threads
sync_status = {port: {"progress": {}, "status": "idle", "last_update": None} for port in INSTANCE_PORTS}

# Thread control
thread_lock = threading.Lock()
threads = {}

# Configure logging to write to a file
logging.basicConfig(filename='sync_manager.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Function to check sync progress
def check_sync_status(port):
    progress_endpoint = SYNC_PROGRESS_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.get(progress_endpoint)
        response.raise_for_status()
        status_data = response.json()
        logging.info(f"Sync status for port {port}: {status_data}")  # Log response data
        return status_data.get("progress", {})
    except Exception as e:
        logging.error(f"Error checking sync status for port {port}: {e}")  # Log error
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
        logging.error(f"Error committing sync for port {port}: {e}")
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
        logging.error(f"Error starting reverse sync for port {port}: {e}")
        return False

# Background thread to monitor existing or started syncs
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

# Function to initialize monitoring for already running processes
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

# Routes
@app.route("/")
def index():
    return render_template("index.html", instance_ports=INSTANCE_PORTS)

@app.route("/check_sync/<int:port>")
def check_sync_endpoint(port):
    # Fetch and return current sync status without starting a new sync
    progress = check_sync_status(port)
    if progress:
        with thread_lock:
            sync_status[port]["progress"] = progress
            sync_status[port]["status"] = "running" if progress.get("state") == "RUNNING" else "idle"
    return jsonify(sync_status.get(port, {}))

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
initialize_monitoring()

if __name__ == "__main__":
    app.run(debug=True)
