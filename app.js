import express from 'express';
import axios from 'axios';
import { Server as SocketIOServer } from 'socket.io';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;
const INSTANCE_PORTS = [27601, 27602, 27603];

const syncStatus = {
    27601: { status: 'idle', progress: {} },
    27602: { status: 'idle', progress: {} },
    27603: { status: 'idle', progress: {} },
};

const server = http.createServer(app);
const io = new SocketIOServer(server);

// Serve static files from the "public" directory
app.use(express.static(path.join(__dirname, 'public')));

// Endpoint to start sync
app.post('/start_sync/:port', async (req, res) => {
    const port = req.params.port;
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/start`, {
            source: 'cluster0',
            destination: 'cluster1',
            reversible: true,
            enableUserWriteBlocking: true,
        });
        syncStatus[port].status = 'running';
        io.emit('syncStatusUpdate', { port, status: 'running' });
        res.json({ message: `Sync started on port ${port}` });
    } catch (error) {
        res.status(500).json({ message: `Failed to start sync on port ${port}` });
    }
});

// Endpoint to stop sync
app.post('/stop_sync/:port', async (req, res) => {
    const port = req.params.port;
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/stop`);
        syncStatus[port].status = 'stopped';
        io.emit('syncStatusUpdate', { port, status: 'stopped' });
        res.json({ message: `Sync stopped on port ${port}` });
    } catch (error) {
        res.status(500).json({ message: `Failed to stop sync on port ${port}` });
    }
});

// Endpoint to commit sync
app.post('/commit_sync/:port', async (req, res) => {
    const port = req.params.port;
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/commit`);
        syncStatus[port].status = 'committed';
        io.emit('syncStatusUpdate', { port, status: 'committed' });
        res.json({ message: `Commit completed on port ${port}` });
    } catch (error) {
        res.status(500).json({ message: `Failed to commit sync on port ${port}` });
    }
});

// Endpoint to reverse sync
app.post('/reverse_sync/:port', async (req, res) => {
    const port = req.params.port;
    try {
        const response = await axios.post(`http://localhost:${port}/api/v1/reverse`);
        syncStatus[port].status = 'reversing';
        io.emit('syncStatusUpdate', { port, status: 'reversing' });
        res.json({ message: `Reverse sync started on port ${port}` });
    } catch (error) {
        res.status(500).json({ message: `Failed to reverse sync on port ${port}` });
    }
});

// Endpoint to check sync status
app.get('/sync_status/:port', async (req, res) => {
    const port = req.params.port;
    try {
        const response = await axios.get(`http://localhost:${port}/api/v1/progress`);
        syncStatus[port].progress = response.data.progress;
        io.emit('syncStatusUpdate', { port, progress: response.data.progress });
        res.json(response.data);
    } catch (error) {
        res.status(500).json({ message: `Could not get status for port ${port}` });
    }
});

server.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});
