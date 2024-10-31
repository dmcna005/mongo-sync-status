from flask import Flask, render_template, jsonify
import requests
import threading
import time
from datetime import datetime
import logging

app = Flask(__name__)

INSTANCE_PORTS = [27601, 27602, 27603]
SYNC_START_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/start"
SYNC_PROGRESS_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/progress"
SYNC_COMMIT_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/commit"
REVERSE_SYNC_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/reverse"
SYNC_STOP_ENDPOINT_TEMPLATE = "http://localhost:{}/api/v1/stop"

CHECK_INTERVAL = 5  # seconds between status checks

# Shared sync status data
sync_status = {port: {"progress": {}, "status": "idle", "last_update": None, "monitor_thread": None} for port in INSTANCE_PORTS}

# Lock for thread-safe updates
thread_lock = threading.Lock()

logging.basicConfig(filename='sync_manager.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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

def stop_sync(port):
    stop_endpoint = SYNC_STOP_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(stop_endpoint, json={})
        response.raise_for_status()
        if response.json().get("success", False):
            with thread_lock:
                sync_status[port]["status"] = "stopped"
            return True
    except Exception as e:
        logging.warning(f"Error stopping sync for port {port}: {e}")
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

def commit_sync(port):
    commit_endpoint = SYNC_COMMIT_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(commit_endpoint, json={})
        response.raise_for_status()
        if response.json().get('success', False):
            with thread_lock:
                sync_status[port]["status"] = "committed"
            return True
    except Exception as e:
        logging.warning(f"Error committing sync for port {port}: {e}")
    return False

def reverse_sync(port):
    reverse_sync_endpoint = REVERSE_SYNC_ENDPOINT_TEMPLATE.format(port)
    try:
        response = requests.post(reverse_sync_endpoint, json={})
        response.raise_for_status()
        if response.json().get('success', False):
            with thread_lock:
                sync_status[port]["status"] = "reversed"
            return True
    except Exception as e:
        logging.warning(f"Error starting reverse sync for port {port}: {e}")
    return False

def monitor_sync(port):
    while True:
        with thread_lock:
            if sync_status[port]["status"] not in ["running"]:
                break  # Exit the loop if the status is not "running"

        progress = check_sync_status(port)
        if progress:
            with thread_lock:
                sync_status[port]["progress"] = progress
                sync_status[port]["last_update"] = datetime.now()

            # Check if we can commit
            if progress.get("lagTimeSeconds", 0) <= 5 and progress.get("canCommit", False):
                if commit_sync(port):
                    with thread_lock:
                        sync_status[port]["status"] = "committed"
                break  # Exit the loop after committing

        time.sleep(CHECK_INTERVAL)

@app.route("/")
def index():
    return render_template("index.html", instance_ports=INSTANCE_PORTS)

@app.route("/start_sync/<int:port>", methods=["POST"])
def start_sync_endpoint(port):
    if port in sync_status and sync_status[port]["status"] == "idle":
        if start_sync(port):
            thread = threading.Thread(target=monitor_sync, args=(port,))
            thread.start()
            with thread_lock:
                sync_status[port]["monitor_thread"] = thread
            return jsonify({"message": f"Sync started on port {port}", "port": port})
    return jsonify({"message": f"Failed to start sync on port {port} or already running", "port": port}), 500

@app.route("/stop_sync/<int:port>", methods=["POST"])
def stop_sync_endpoint(port):
    if stop_sync(port):
        with thread_lock:
            sync_status[port]["status"] = "stopped"
            if sync_status[port]["monitor_thread"] is not None:
                # Optionally, you could join the thread if you want to wait for it to finish
                sync_status[port]["monitor_thread"] = None
        return jsonify({"message": f"Sync stopped on port {port}", "port": port})
    return jsonify({"message": f"Failed to stop sync on port {port}", "port": port}), 500

@app.route("/commit_sync/<int:port>", methods=["POST"])
def commit_sync_endpoint(port):
    if commit_sync(port):
        return jsonify({"message": f"Commit completed for port {port}", "port": port})
    return jsonify({"message": f"Failed to commit sync on port {port}", "port": port}), 500

@app.route("/reverse_sync/<int:port>", methods=["POST"])
def reverse_sync_endpoint(port):
    if reverse_sync(port):
        return jsonify({"message": f"Reverse sync started for port {port}", "port": port})
    return jsonify({"message": f"Failed to reverse sync on port {port}", "port": port}), 500

@app.route("/sync_status/<int:port>")
def sync_status_route(port):
    with thread_lock:
        status = sync_status.get(port)
        if status is None:
            return jsonify({"error": "Invalid port"}), 404
        return jsonify(status)

if __name__ == "__main__":
    app.run(debug=True)
