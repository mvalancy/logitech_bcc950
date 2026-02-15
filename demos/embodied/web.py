"""Web dashboard for Amy — live video, state, transcript, and position.

Read-only dashboard using only Python stdlib (http.server).  Provides:
- ``/``       — self-contained HTML dashboard (dark theme, CSS Grid)
- ``/video``  — MJPEG stream from the creature's camera
- ``/events`` — SSE stream for state changes, transcripts, position updates

Usage::

    from .web import EventBus, DashboardServer
    bus = EventBus()
    srv = DashboardServer(creature, bus, port=8950)
    srv.start()      # runs in a daemon thread
    bus.publish("state_change", {"state": "IDLE"})
    srv.stop()
"""

from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .creature import Creature


# ---------------------------------------------------------------------------
# EventBus — thread-safe pub/sub
# ---------------------------------------------------------------------------

class EventBus:
    """Simple thread-safe pub/sub for pushing events to SSE clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        """Create and return a new subscriber queue."""
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber queue."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event_type: str, data: dict | None = None) -> None:
        """Push an event to all subscribers (non-blocking, drops if full)."""
        msg = {"type": event_type}
        if data is not None:
            msg["data"] = data
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass


# ---------------------------------------------------------------------------
# HTML dashboard (inline)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Amy — Debug Dashboard</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    background: #0d1117; color: #c9d1d9;
    min-height: 100vh; font-size: 13px;
}
header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 16px;
    border-bottom: 1px solid #21262d;
    background: #161b22;
}
header h1 { font-size: 1rem; font-weight: 600; }
.badges { display: flex; gap: 8px; align-items: center; }
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 10px;
    font-size: 0.72rem; font-weight: 600;
    background: #1c2128;
}
.badge .dot {
    width: 7px; height: 7px; border-radius: 50%;
}

.grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: 1fr auto;
    gap: 1px; background: #21262d;
    height: calc(100vh - 41px);
}
.panel {
    background: #0d1117; padding: 8px;
    overflow: hidden; display: flex; flex-direction: column;
}
.panel h2 {
    font-size: 0.68rem; text-transform: uppercase;
    color: #8b949e; margin-bottom: 6px;
    letter-spacing: 0.06em;
}

/* Video */
.video-panel { position: relative; }
.video-panel img {
    width: 100%; height: auto; max-height: calc(100% - 80px);
    object-fit: contain;
    border-radius: 3px; background: #161b22;
}
#detection-overlay {
    position: absolute; bottom: 80px; left: 6px; right: 6px;
    background: rgba(13,17,23,0.85);
    padding: 3px 8px; border-radius: 3px;
    font-size: 0.7rem; color: #58a6ff;
    pointer-events: none;
}
#yolo-strip {
    display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
    padding: 3px 0;
    font-size: 0.68rem; color: #d29922;
}
#yolo-strip .det-tag {
    background: #1c2128; padding: 1px 6px; border-radius: 8px;
    display: inline-flex; gap: 4px; align-items: center;
}
#yolo-strip .det-conf { color: #484f58; }
#tracking-info {
    font-size: 0.65rem; color: #58a6ff;
    padding: 1px 0;
}

/* Log panels */
.log {
    flex: 1; overflow-y: auto;
    font-size: 0.78rem; line-height: 1.4;
}
.log::-webkit-scrollbar { width: 5px; }
.log::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
.log .entry { padding: 2px 0; border-bottom: 1px solid #161b22; }
.log .ts { color: #484f58; margin-right: 6px; font-size: 0.7rem; }
.log .user { color: #58a6ff; }
.log .amy { color: #d2a8ff; }
.log .event { color: #8b949e; font-style: italic; }
.log .deep { color: #3fb950; }
.log .yolo { color: #d29922; }
.log .friend { color: #f0883e; }
.log .warn { color: #f85149; }
.log .thought { color: #e3b341; font-style: italic; }

/* Auto-chat button */
.auto-btn {
    padding: 3px 10px; border-radius: 10px; border: 1px solid #30363d;
    background: #1c2128; color: #c9d1d9; cursor: pointer;
    font-family: inherit; font-size: 0.72rem; font-weight: 600;
}
.auto-btn.active { background: #f0883e; color: #0d1117; border-color: #f0883e; }
.auto-btn:hover { border-color: #58a6ff; }

/* Context panel */
#context-panel {
    margin-top: 4px;
    padding: 6px 8px;
    background: #161b22; border-radius: 3px;
    font-size: 0.72rem;
    max-height: 220px; overflow-y: auto;
    border: 1px solid #21262d;
}
#context-panel .ctx-label {
    color: #8b949e; font-size: 0.65rem;
    text-transform: uppercase; letter-spacing: 0.05em;
    margin-top: 4px;
}
#context-panel .ctx-label:first-child { margin-top: 0; }
#context-panel .ctx-value { color: #c9d1d9; margin: 2px 0; }
#context-panel .ctx-scene { color: #d29922; }
#context-panel .ctx-deep { color: #3fb950; }
#context-panel .ctx-history { color: #bc8cff; font-size: 0.68rem; }

/* Deep observation */
#deep-obs {
    padding: 4px 8px; margin-top: 4px;
    background: #161b22; border-radius: 3px;
    font-size: 0.72rem; color: #3fb950;
    min-height: 2em;
}

/* Thought panel */
#thought-panel {
    margin-top: 4px;
    padding: 4px 8px;
    background: #161b22; border-radius: 3px;
    font-size: 0.72rem; color: #e3b341;
    max-height: 100px; overflow-y: auto;
    font-style: italic;
}
#thought-panel .thought-entry {
    padding: 1px 0; border-bottom: 1px solid #1c2128;
}
#thought-panel .thought-ts { color: #484f58; margin-right: 4px; font-size: 0.65rem; }

/* Sensorium narrative */
#sensorium-panel {
    margin-top: 4px;
    padding: 4px 8px;
    background: #161b22; border-radius: 3px;
    font-size: 0.68rem; color: #8b949e;
    max-height: 100px; overflow-y: auto;
    white-space: pre-line;
    border: 1px solid #21262d;
}

/* Status bar */
.status-bar {
    grid-column: 1 / -1;
    display: flex; align-items: center; gap: 16px;
    padding: 6px 16px;
    font-size: 0.72rem; color: #8b949e;
    flex-wrap: wrap;
}
.status-bar .item { display: flex; align-items: center; gap: 4px; }
.status-bar .val { color: #c9d1d9; }

/* Position tracks */
.pos-track {
    display: flex; align-items: center; gap: 6px;
}
.pos-track .label { width: 24px; }
.track-svg { width: 120px; height: 16px; }

@media (max-width: 900px) {
    .grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 600px) {
    .grid { grid-template-columns: 1fr; }
    .status-bar { grid-column: 1; }
}
</style>
</head>
<body>
<header>
    <h1>Amy &mdash; Debug Dashboard</h1>
    <div class="badges">
        <span class="badge"><span class="dot" id="state-dot" style="background:#3fb950"></span><span id="state-label">IDLE</span></span>
        <span class="badge"><span class="dot" style="background:#d29922"></span>YOLO <span id="yolo-people">0</span>p</span>
        <span class="badge" id="deep-badge"><span class="dot" style="background:#484f58"></span>Deep</span>
        <span class="badge" id="tracking-badge"><span class="dot" style="background:#484f58"></span>Track</span>
        <span class="badge" id="mood-badge"><span class="dot" style="background:#e3b341"></span>Mood: <span id="mood-label">neutral</span></span>
        <span class="badge" id="thinking-badge"><span class="dot" id="thinking-dot" style="background:#484f58"></span>Think</span>
        <button class="auto-btn" id="auto-btn" onclick="toggleAutoChat()">Auto Chat</button>
    </div>
</header>
<div class="grid">
    <!-- Col 1: Video + YOLO Detections -->
    <div class="panel video-panel">
        <h2>Camera Feed (YOLO overlay)</h2>
        <img id="video" src="/video" alt="Live video">
        <div id="detection-overlay">YOLO: waiting...</div>
        <div id="yolo-strip">Waiting for YOLO...</div>
        <div id="tracking-info">Tracking: none</div>
    </div>
    <!-- Col 2: Transcript + LLM Context -->
    <div class="panel">
        <h2>Conversation</h2>
        <div class="log" id="transcript" style="flex:1"></div>
        <h2 style="margin-top:8px">Deep Observation</h2>
        <div id="deep-obs">Waiting for first deep think...</div>
        <h2 style="margin-top:8px">Inner Thoughts</h2>
        <div id="thought-panel">Waiting for first thought...</div>
        <h2 style="margin-top:8px">Sensorium</h2>
        <div id="sensorium-panel">Waiting for awareness data...</div>
        <h2 style="margin-top:8px">Amy's Mind</h2>
        <div id="context-panel">
            <div class="ctx-label">Scene (YOLO)</div>
            <div class="ctx-value ctx-scene" id="ctx-scene">--</div>
            <div class="ctx-label">Deep Observation</div>
            <div class="ctx-value ctx-deep" id="ctx-deep">--</div>
            <div class="ctx-label">Tracking Target</div>
            <div class="ctx-value" id="ctx-tracking">none</div>
            <div class="ctx-label">Chat History (<span id="ctx-history-len">0</span> msgs)</div>
            <div id="ctx-history"></div>
            <div class="ctx-label">Long-term Memory</div>
            <div class="ctx-value" id="ctx-memory-stats">--</div>
            <div class="ctx-label">Room Understanding</div>
            <div class="ctx-value ctx-deep" id="ctx-room">--</div>
            <div class="ctx-label">Spatial Map</div>
            <div class="ctx-value" id="ctx-spatial" style="font-size:0.65rem;white-space:pre;max-height:80px;overflow-y:auto">--</div>
            <div class="ctx-label">Recent Events</div>
            <div class="ctx-value" id="ctx-events" style="font-size:0.65rem;white-space:pre;max-height:80px;overflow-y:auto">--</div>
        </div>
    </div>
    <!-- Col 3: System Log -->
    <div class="panel">
        <h2>System Log</h2>
        <div class="log" id="syslog"></div>
    </div>
    <!-- Status bar -->
    <div class="status-bar">
        <div class="item">Pan: <div class="pos-track"><svg class="track-svg" viewBox="0 0 120 16">
            <rect x="0" y="6" width="120" height="4" rx="2" fill="#21262d"/>
            <line id="pan-min" x1="0" y1="2" x2="0" y2="14" stroke="#f85149" stroke-width="1.5" visibility="hidden"/>
            <line id="pan-max" x1="120" y1="2" x2="120" y2="14" stroke="#f85149" stroke-width="1.5" visibility="hidden"/>
            <circle id="pan-dot" cx="60" cy="8" r="4" fill="#58a6ff"/>
        </svg></div> <span class="val" id="pan-val">0.0</span></div>
        <div class="item">Tilt: <div class="pos-track"><svg class="track-svg" viewBox="0 0 120 16">
            <rect x="0" y="6" width="120" height="4" rx="2" fill="#21262d"/>
            <line id="tilt-min" x1="0" y1="2" x2="0" y2="14" stroke="#f85149" stroke-width="1.5" visibility="hidden"/>
            <line id="tilt-max" x1="120" y1="2" x2="120" y2="14" stroke="#f85149" stroke-width="1.5" visibility="hidden"/>
            <circle id="tilt-dot" cx="60" cy="8" r="4" fill="#58a6ff"/>
        </svg></div> <span class="val" id="tilt-val">0.0</span></div>
        <div class="item">Zoom: <span class="val" id="zoom-val">100</span></div>
        <div class="item">YOLO: <span class="val" id="yolo-summary">waiting</span></div>
        <div class="item">Uptime: <span class="val" id="uptime">0s</span></div>
    </div>
</div>
<script>
var startTime = Date.now();
setInterval(function() {
    var s = Math.floor((Date.now() - startTime) / 1000);
    var m = Math.floor(s / 60); s = s % 60;
    document.getElementById('uptime').textContent = m + 'm ' + s + 's';
}, 1000);

var STATE_COLORS = { IDLE:'#3fb950', LISTENING:'#d29922', THINKING:'#58a6ff', SPEAKING:'#bc8cff' };

function ts() {
    var d = new Date();
    return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)+':'+('0'+d.getSeconds()).slice(-2);
}

function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function addLog(panel, cls, text) {
    var el = document.getElementById(panel);
    var div = document.createElement('div');
    div.className = 'entry ' + cls;
    div.innerHTML = '<span class="ts">' + ts() + '</span>' + text;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
    while (el.children.length > 300) el.removeChild(el.firstChild);
}

function setState(state) {
    document.getElementById('state-label').textContent = state;
    document.getElementById('state-dot').style.background = STATE_COLORS[state] || '#8b949e';
    addLog('syslog', 'event', 'State: <b>' + state + '</b>');
}

function mapPos(value, min, max, W) {
    if (min === null && max === null) return W / 2;
    var lo = min !== null ? min : (max !== null ? -Math.abs(max)*1.5 : -1);
    var hi = max !== null ? max : (min !== null ? Math.abs(min)*1.5 : 1);
    if (lo === hi) { lo -= 1; hi += 1; }
    var pct = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
    return 4 + pct * (W - 8);
}

function updatePosition(d) {
    var W = 120;
    document.getElementById('pan-dot').setAttribute('cx', mapPos(d.pan, d.pan_min, d.pan_max, W));
    document.getElementById('tilt-dot').setAttribute('cx', mapPos(d.tilt, d.tilt_min, d.tilt_max, W));
    document.getElementById('pan-val').textContent = d.pan.toFixed(1);
    document.getElementById('tilt-val').textContent = d.tilt.toFixed(1);
    document.getElementById('zoom-val').textContent = d.zoom;
    ['pan','tilt'].forEach(function(axis) {
        ['min','max'].forEach(function(lim) {
            var el = document.getElementById(axis+'-'+lim);
            var v = d[axis+'_'+lim];
            if (v !== null) {
                var x = mapPos(v, d[axis+'_min'], d[axis+'_max'], W);
                el.setAttribute('x1', x); el.setAttribute('x2', x);
                el.setAttribute('visibility', 'visible');
            }
        });
    });
}

function updateDetections(d) {
    document.getElementById('detection-overlay').textContent = d.summary;
    document.getElementById('yolo-summary').textContent = d.summary;
    document.getElementById('yolo-people').textContent = d.people;
    var strip = document.getElementById('yolo-strip');
    if (d.boxes && d.boxes.length > 0) {
        var html = '';
        for (var i = 0; i < d.boxes.length; i++) {
            var b = d.boxes[i];
            html += '<span class="det-tag">' + esc(b.label);
            html += ' <span class="det-conf">' + (b.conf * 100).toFixed(0) + '%</span></span>';
        }
        strip.innerHTML = html;
    } else {
        strip.textContent = 'No detections';
    }
}

function toggleAutoChat() {
    fetch('/api/auto-chat', {method:'POST'}).then(function(r){return r.json()}).then(function(d){
        var btn = document.getElementById('auto-btn');
        if (d.auto_chat) { btn.classList.add('active'); btn.textContent = 'Auto Chat ON'; }
        else { btn.classList.remove('active'); btn.textContent = 'Auto Chat'; }
    });
}

var MOOD_COLORS = {
    neutral:'#8b949e', engaged:'#58a6ff', attentive:'#d29922',
    contemplative:'#e3b341', calm:'#3fb950', curious:'#d2a8ff'
};

function addThought(text) {
    var panel = document.getElementById('thought-panel');
    if (panel.textContent === 'Waiting for first thought...') panel.innerHTML = '';
    var div = document.createElement('div');
    div.className = 'thought-entry';
    div.innerHTML = '<span class="thought-ts">' + ts() + '</span>' + esc(text);
    panel.appendChild(div);
    panel.scrollTop = panel.scrollHeight;
    while (panel.children.length > 20) panel.removeChild(panel.firstChild);
    // Pulse the thinking badge
    document.getElementById('thinking-dot').style.background = '#e3b341';
    setTimeout(function() { document.getElementById('thinking-dot').style.background = '#484f58'; }, 2000);
}

function updateContext(d) {
    document.getElementById('ctx-scene').textContent = d.scene || '--';
    document.getElementById('ctx-deep').textContent = d.deep_observation || '--';
    document.getElementById('ctx-tracking').textContent = d.tracking || 'none';
    document.getElementById('ctx-history-len').textContent = d.history_len || 0;
    // Auto-chat button state
    var btn = document.getElementById('auto-btn');
    if (d.auto_chat) { btn.classList.add('active'); btn.textContent = 'Auto Chat ON'; }
    else { btn.classList.remove('active'); btn.textContent = 'Auto Chat'; }
    // Tracking indicator
    var dot = document.getElementById('tracking-badge').querySelector('.dot');
    var info = document.getElementById('tracking-info');
    if (d.tracking && d.tracking !== 'none') {
        dot.style.background = '#58a6ff';
        info.textContent = 'Tracking: ' + d.tracking;
    } else {
        dot.style.background = '#484f58';
        info.textContent = 'Tracking: none';
    }
    // Mood indicator
    if (d.mood) {
        document.getElementById('mood-label').textContent = d.mood;
        var moodDot = document.getElementById('mood-badge').querySelector('.dot');
        moodDot.style.background = MOOD_COLORS[d.mood] || '#8b949e';
    }
    // Thinking suppression indicator
    if (d.thinking_suppressed) {
        document.getElementById('thinking-dot').style.background = '#f85149';
    }
    // Sensorium narrative
    if (d.sensorium_narrative) {
        document.getElementById('sensorium-panel').textContent = d.sensorium_narrative;
    }
    // Chat history preview
    var hist = document.getElementById('ctx-history');
    if (d.history_preview && d.history_preview.length > 0) {
        var hhtml = '';
        for (var i = 0; i < d.history_preview.length; i++) {
            hhtml += '<div class="ctx-history">' + esc(d.history_preview[i]) + '</div>';
        }
        hist.innerHTML = hhtml;
    }
    // Memory data
    if (d.memory) {
        var m = d.memory;
        document.getElementById('ctx-memory-stats').textContent =
            'Session #' + m.session + ' | ' + m.total_observations + ' obs | ' +
            m.total_events + ' events | Uptime: ' + m.uptime_min + 'm';
        document.getElementById('ctx-room').textContent = m.room_summary || 'Not yet explored';
        document.getElementById('ctx-spatial').textContent = m.spatial_summary || 'No spatial data';
        document.getElementById('ctx-events').textContent = m.events || 'No events';
    }
}

// Video feed health monitor — reload if frozen
var videoEl = document.getElementById('video');
var lastVideoError = 0;
videoEl.onerror = function() {
    var now = Date.now();
    if (now - lastVideoError > 3000) {
        lastVideoError = now;
        setTimeout(function() { videoEl.src = '/video?' + Date.now(); }, 1000);
    }
};
// Also reload if image hasn't changed in 10s
setInterval(function() {
    if (!videoEl.complete || videoEl.naturalWidth === 0) {
        videoEl.src = '/video?' + Date.now();
    }
}, 10000);

function connectSSE() {
    var es = new EventSource('/events');
    es.onmessage = function(e) {
        var msg = JSON.parse(e.data);
        var d = msg.data;
        switch(msg.type) {
            case 'state_change':
                setState(d.state); break;
            case 'transcript':
                if (d.speaker === 'user') {
                    addLog('transcript', 'user', '<b>You:</b> ' + esc(d.text));
                } else if (d.speaker === 'friend') {
                    addLog('transcript', 'friend', '<b>Friend:</b> ' + esc(d.text));
                } else {
                    addLog('transcript', 'amy', '<b>Amy:</b> ' + esc(d.text));
                }
                break;
            case 'position_update':
                updatePosition(d); break;
            case 'event':
                var cls = 'event';
                if (d.text.indexOf('[deep]') === 0) cls = 'deep';
                else if (d.text.indexOf('[YOLO') >= 0 || d.text.indexOf('[person') >= 0 || d.text.indexOf('[everyone') >= 0) cls = 'yolo';
                addLog('syslog', cls, esc(d.text));
                if (d.text.indexOf('[deep]:') === 0) {
                    document.getElementById('deep-obs').textContent = d.text.substring(8);
                    document.getElementById('deep-badge').querySelector('.dot').style.background = '#3fb950';
                }
                break;
            case 'thought':
                addThought(d.text);
                addLog('syslog', 'thought', '[think]: ' + esc(d.text));
                break;
            case 'detections':
                updateDetections(d); break;
            case 'context_update':
                updateContext(d); break;
        }
    };
    es.onerror = function() { es.close(); setTimeout(connectSSE, 2000); };
}
connectSSE();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    """Serves the dashboard, MJPEG video, and SSE events."""

    # Suppress per-request log lines
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._serve_html()
        elif self.path == "/video":
            self._serve_mjpeg()
        elif self.path == "/events":
            self._serve_sse()
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/auto-chat":
            creature: Creature = self.server.creature  # type: ignore[attr-defined]
            new_state = creature.toggle_auto_chat()
            body = json.dumps({"auto_chat": new_state}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        body = DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_mjpeg(self) -> None:
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "multipart/x-mixed-replace; boundary=frame",
        )
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        creature: Creature = self.server.creature  # type: ignore[attr-defined]
        last_frame_id: int = -1
        try:
            while True:
                cur_id = creature._frame_buffer.frame_id
                if cur_id != last_frame_id:
                    frame = creature.grab_mjpeg_frame()
                    if frame is not None:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(frame)}\r\n\r\n".encode()
                        )
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                        last_frame_id = cur_id
                time.sleep(0.033)  # ~30 fps
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        bus: EventBus = self.server.event_bus  # type: ignore[attr-defined]
        creature: Creature = self.server.creature  # type: ignore[attr-defined]
        sub = bus.subscribe()

        try:
            # Send initial state
            self._sse_send({
                "type": "state_change",
                "data": {"state": creature._state.value},
            })
            creature._publish_position()

            # Event loop
            while True:
                try:
                    msg = sub.get(timeout=30)
                    self._sse_send(msg)
                except queue.Empty:
                    # Keepalive ping
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            bus.unsubscribe(sub)

    def _sse_send(self, msg: dict) -> None:
        payload = json.dumps(msg)
        self.wfile.write(f"data: {payload}\n\n".encode())
        self.wfile.flush()


# ---------------------------------------------------------------------------
# Dashboard server
# ---------------------------------------------------------------------------

class DashboardServer:
    """Wraps ThreadingHTTPServer in a daemon thread."""

    def __init__(
        self,
        creature: Creature,
        event_bus: EventBus,
        port: int = 8950,
    ) -> None:
        self.creature = creature
        self.event_bus = event_bus
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._httpd = ThreadingHTTPServer(
            ("0.0.0.0", self.port), DashboardHandler
        )
        # Attach references for the handler
        self._httpd.creature = self.creature  # type: ignore[attr-defined]
        self._httpd.event_bus = self.event_bus  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
