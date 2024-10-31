// app.js
const express = require("express");
const axios = require("axios");
const nodemailer = require("nodemailer");
const app = express();
const PORT = 3000;

const INSTANCE_PORTS = [27601, 27602, 27603];
const CHECK_INTERVAL = 60000; // 60 seconds

let syncStatus = {};
INSTANCE_PORTS.forEach((port) => {
    syncStatus[port] = { progress: {}, status: "idle", lastUpdate: null };
});

// Set up nodemailer transporter (fill with your email config)
const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: 'your-email@gmail.com',
        pass: 'your-password'
    }
});

// Helper functions
async function startSync(port) {
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/start`, {
            source: "cluster0",
            destination: "cluster1",
            reversible: true,
            enableUserWriteBlocking: true
        });
        if (response.data.success) {
            syncStatus[port].status = "running";
            monitorSync(port);
            return true;
        }
    } catch (error) {
        console.warn(`Error starting sync on port ${port}:`, error.message);
    }
    return false;
}

async function stopSync(port) {
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/stop`, {});
        if (response.data.success) {
            syncStatus[port].status = "stopped";
            return true;
        }
    } catch (error) {
        console.warn(`Error stopping sync on port ${port}:`, error.message);
    }
    return false;
}

async function checkSyncStatus(port) {
    try {
        const response = await axios.get(`http://localhost:${port}/api/v1/progress`);
        return response.data.progress || {};
    } catch (error) {
        console.warn(`Error checking sync status on port ${port}:`, error.message);
    }
    return null;
}

async function commitSync(port) {
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/commit`, {});
        if (response.data.success) {
            syncStatus[port].status = "committed";
            return true;
        }
    } catch (error) {
        console.warn(`Error committing sync on port ${port}:`, error.message);
    }
    return false;
}

async function reverseSync(port) {
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/reverse`, {});
        if (response.data.success) {
            syncStatus[port].status = "reversed";
            return true;
        }
    } catch (error) {
        console.warn(`Error reversing sync on port ${port}:`, error.message);
    }
    return false;
}

function monitorSync(port) {
    setInterval(async () => {
        if (syncStatus[port].status !== "running") return;

        const progress = await checkSyncStatus(port);
        if (progress) {
            syncStatus[port].progress = progress;
            syncStatus[port].lastUpdate = new Date();

            if (progress.lagTimeSeconds <= 5 && progress.canCommit) {
                await commitSync(port);
            }
        }
    }, CHECK_INTERVAL);
}

// Routes
app.use(express.json());
app.use(express.static("public"));

app.get("/sync_status/:port", (req, res) => {
    const port = parseInt(req.params.port);
    if (syncStatus[port]) {
        res.json(syncStatus[port]);
    } else {
        res.status(404).json({ error: "Port not found" });
    }
});

app.post("/start_sync/:port", async (req, res) => {
    const port = parseInt(req.params.port);
    if (await startSync(port)) {
        res.json({ message: `Sync started on port ${port}`, port });
    } else {
        res.status(500).json({ message: `Failed to start sync on port ${port}` });
    }
});

app.post("/stop_sync/:port", async (req, res) => {
    const port = parseInt(req.params.port);
    if (await stopSync(port)) {
        res.json({ message: `Sync stopped on port ${port}`, port });
    } else {
        res.status(500).json({ message: `Failed to stop sync on port ${port}` });
    }
});

app.post("/commit_sync/:port", async (req, res) => {
    const port = parseInt(req.params.port);
    if (await commitSync(port)) {
        res.json({ message: `Commit completed for port ${port}`, port });
    } else {
        res.status(500).json({ message: `Failed to commit sync on port ${port}` });
    }
});

app.post("/reverse_sync/:port", async (req, res) => {
    const port = parseInt(req.params.port);
    if (await reverseSync(port)) {
        res.json({ message: `Reverse sync started for port ${port}`, port });
    } else {
        res.status(500).json({ message: `Failed to reverse sync on port ${port}` });
    }
});

app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
