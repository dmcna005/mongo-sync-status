from flask import Flask, render_template, jsonify, request
import requests
import threading
import time
from datetime import datetime

app = Flask(__name__)

# Configuration variables
INSTANCE_PORTS = [27601, 27602]
SYNC_START_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/start"
SYNC_PROGRESS_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/progress"
SYNC_COMMIT_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/commit"
REVERSE_SYNC_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/reverse"
CHECK_INTERVAL = 60  # seconds between status checks
PROGRESS_UPDATE_INTERVAL = 3600  # seconds for hourly progress updates

# Sync status data to share between threads
sync_status = {port: {"progress": {}, "status": "idle", "last_update": None} for port in INSTANCE_PORTS}

# Thread control
thread_lock = threading.Lock()
threads = {}

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
        with thread_lock:
            sync_status[port]["status"] = "running"
        return True
    except Exception as e:
        print(f"Error starting sync for port {port}: {e}")
        return False

# Function to check sync progress
def check_sync_status(port):
    progress_endpoint = SYNC_PROGRESS_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.get(progress_endpoint)
        response.raise_for_status()
        status_data = response.json()
        return status_data.get("progress", {})
    except Exception as e:
        print(f"Error checking sync status for port {port}: {e}")
        return None

# Function to commit sync
def commit_sync(port):
    commit_endpoint = SYNC_COMMIT_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(commit_endpoint, json={})
        response.raise_for_status()
        return response.json().get('success', False)
    except Exception as e:
        print(f"Error committing sync for port {port}: {e}")
        return False

# Function to reverse sync
def reverse_sync(port):
    reverse_sync_endpoint = REVERSE_SYNC_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(reverse_sync_endpoint, json={})
        response.raise_for_status()
        return response.json().get('success', False)
    except Exception as e:
        print(f"Error starting reverse sync for port {port}: {e}")
        return False

# Background thread to update sync status
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
        # Start a monitoring thread
        thread = threading.Thread(target=monitor_sync, args=(port,))
        thread.start()
        threads[port] = thread
        return jsonify({"message": "Sync started", "port": port})
    return jsonify({"message": "Failed to start sync", "port": port}), 500

@app.route("/stop_sync/<int:port>", methods=["POST"])
def stop_sync_endpoint(port):
    with thread_lock:
        sync_status[port]["status"] = "stopped"
    return jsonify({"message": "Sync stopped", "port": port})

@app.route("/reverse_sync/<int:port>", methods=["POST"])
def reverse_sync_endpoint(port):
    if reverse_sync(port):
        return jsonify({"message": "Reverse sync started", "port": port})
    return jsonify({"message": "Failed to start reverse sync", "port": port}), 500

@app.route("/sync_status/<int:port>")
def sync_status_endpoint(port):
    with thread_lock:
        status = sync_status.get(port, {})
    return jsonify(status)

if __name__ == "__main__":
    app.run(debug=True)
