#!/usr/bin/env python3
import argparse
import json
import queue
import socket
import sys
import threading
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from udp_log_env import ensure_supported_python

ensure_supported_python("udp_log_web_viewer")

from udp_log_journal import UdpLogJournal
from udp_log_record import format_udp_log_record, parse_udp_log_line
from udp_log_sequence import UdpLogSequenceTracker


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xbell Wireless Log Viewer</title>
  <style>
    :root {
      --bg: #0b1020;
      --panel: #131a2e;
      --line: #1e2742;
      --text: #dbe6ff;
      --muted: #8ea2d0;
      --accent: #5cc8ff;
      --accent-2: #8dffb3;
      --danger: #ff8f8f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(92, 200, 255, 0.14), transparent 28%),
        radial-gradient(circle at top right, rgba(141, 255, 179, 0.08), transparent 24%),
        var(--bg);
      color: var(--text);
      font: 14px/1.5 Consolas, "SFMono-Regular", Menlo, Monaco, monospace;
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
      margin-bottom: 16px;
    }
    .title {
      font-size: 28px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .subtitle {
      color: var(--muted);
      margin-top: 4px;
    }
    .status-card {
      background: rgba(19, 26, 46, 0.9);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      min-width: 260px;
      backdrop-filter: blur(8px);
    }
    .status-row {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 6px;
    }
    .status-row:last-child { margin-bottom: 0; }
    .label { color: var(--muted); }
    .value { color: var(--text); }
    .toolbar {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .toolbar input {
      min-width: 260px;
      flex: 1;
      background: rgba(19, 26, 46, 0.9);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      outline: none;
    }
    .toolbar select {
      background: rgba(19, 26, 46, 0.9);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      outline: none;
    }
    .toolbar button {
      background: linear-gradient(135deg, var(--accent), #6ea8ff);
      color: #05101e;
      border: 0;
      border-radius: 12px;
      padding: 10px 16px;
      font-weight: 700;
      cursor: pointer;
    }
    .toolbar button.secondary {
      background: rgba(19, 26, 46, 0.9);
      color: var(--text);
      border: 1px solid var(--line);
    }
    .log-panel {
      background: rgba(19, 26, 46, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }
    .log-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
      margin-right: 8px;
      background: var(--danger);
      box-shadow: 0 0 12px rgba(255, 143, 143, 0.45);
    }
    .dot.connected {
      background: var(--accent-2);
      box-shadow: 0 0 12px rgba(141, 255, 179, 0.45);
    }
    #log {
      margin: 0;
      padding: 16px;
      min-height: 65vh;
      max-height: 65vh;
      overflow: auto;
      word-break: break-word;
    }
    #log .line { white-space: pre-wrap; }
    #log .lv-E { color: #ff7676; font-weight: 700; }
    #log .lv-W { color: #ffc46b; }
    #log .lv-I { color: var(--text); }
    #log .lv-D { color: #9fb3dd; }
    #log .lv-V { color: #7f92bf; }
    #log .lv-gap { color: #c792ea; font-style: italic; }
    .count-e { color: #ff7676; font-weight: 700; }
    .count-w { color: #ffc46b; font-weight: 700; }
    .count-gap { color: #c792ea; font-weight: 700; }
    .toolbar button.paused {
      background: linear-gradient(135deg, #ffd27d, #ffb45c);
      color: #241a05;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 800px) {
      .hero {
        grid-template-columns: 1fr;
      }
      .status-card {
        min-width: 0;
      }
      #log {
        min-height: 70vh;
        max-height: 70vh;
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <div class="title">Wireless Log Viewer</div>
        <div class="subtitle">设备通过 UDP 推送日志，这个页面负责在本机浏览器里实时展示。</div>
      </div>
      <div class="status-card">
        <div class="status-row"><span class="label">UDP 监听</span><span class="value" id="udpTarget">-</span></div>
        <div class="status-row"><span class="label">页面状态</span><span class="value"><span class="dot" id="dot"></span><span id="connText">连接中</span></span></div>
        <div class="status-row"><span class="label">最近来源</span><span class="value" id="source">-</span></div>
        <div class="status-row"><span class="label">显示 / 缓存</span><span class="value" id="lineStats">0 / 0</span></div>
        <div class="status-row">
          <span class="label">计数</span>
          <span class="value">
            <span class="count-e">E <span id="errCount">0</span></span>
            &nbsp;<span class="count-w">W <span id="warnCount">0</span></span>
            &nbsp;<span class="count-gap">丢包 <span id="gapCount">0</span></span>
          </span>
        </div>
      </div>
    </div>

    <div class="toolbar">
      <input id="filter" type="text" placeholder="关键字：正文 / 来源 / IMEI / 源码文件">
      <select id="levelFilter">
        <option value="">全部级别</option>
        <option value="E">E</option>
        <option value="W">W</option>
        <option value="I">I</option>
        <option value="D">D</option>
        <option value="V">V</option>
      </select>
      <select id="deviceFilter">
        <option value="">全部设备</option>
      </select>
      <input id="featureFilter" type="text" placeholder="feature，例如 device_msg.eval">
      <button id="pauseBtn">暂停显示</button>
      <button id="toggleBtn" class="secondary">暂停自动滚动</button>
      <button id="clearBtn" class="secondary">清空页面</button>
      <button id="exportBtn" class="secondary">导出日志</button>
      <button id="exportJsonBtn" class="secondary">导出 JSONL</button>
    </div>

    <div class="log-panel">
      <div class="log-header">
        <div>实时日志</div>
        <div class="hint">如果这里一直没内容，先确认设备和电脑在同一局域网，并且设备已经连上 Wi-Fi。</div>
      </div>
      <div id="log"></div>
    </div>
  </div>

  <script>
    const logEl = document.getElementById("log");
    const filterEl = document.getElementById("filter");
    const levelFilterEl = document.getElementById("levelFilter");
    const deviceFilterEl = document.getElementById("deviceFilter");
    const featureFilterEl = document.getElementById("featureFilter");
    const dotEl = document.getElementById("dot");
    const connTextEl = document.getElementById("connText");
    const sourceEl = document.getElementById("source");
    const udpTargetEl = document.getElementById("udpTarget");
    const clearBtn = document.getElementById("clearBtn");
    const exportBtn = document.getElementById("exportBtn");
    const exportJsonBtn = document.getElementById("exportJsonBtn");
    const toggleBtn = document.getElementById("toggleBtn");

    const pauseBtn = document.getElementById("pauseBtn");
    const lineStatsEl = document.getElementById("lineStats");
    const errCountEl = document.getElementById("errCount");
    const warnCountEl = document.getElementById("warnCount");
    const gapCountEl = document.getElementById("gapCount");

    const MAX_LINES = 2000;
    const state = {
      lines: [],
      autoScroll: true,
      paused: false,
      udpTarget: "",
      shown: 0,
      errors: 0,
      warnings: 0,
      gaps: 0,
    };

    function isGap(record) {
      return (record.feature || "") === "udp.seq";
    }

    const knownDevices = new Set();

    function registerDevice(record) {
      const imei = record.imei || "";
      if (!imei || imei === "-" || knownDevices.has(imei)) return;
      knownDevices.add(imei);
      const option = document.createElement("option");
      option.value = imei;
      option.textContent = imei;
      deviceFilterEl.appendChild(option);
    }

    function escapeHtml(value) {
      return (value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function levelClass(record) {
      if (isGap(record)) return "lv-gap";
      const level = record.level || "I";
      return "EWIDV".includes(level) ? "lv-" + level : "lv-I";
    }

    function lineHtml(record) {
      return '<div class="line ' + levelClass(record) + '">'
        + escapeHtml((record.line || "").trimEnd())
        + "</div>";
    }

    function passesFilters(record) {
      const keyword = filterEl.value.trim().toLowerCase();
      const level = levelFilterEl.value;
      const device = deviceFilterEl.value;
      const feature = featureFilterEl.value.trim().toLowerCase();
      if (device && record.imei !== device) return false;
      if (level && record.level !== level) return false;
      if (feature && !(record.feature || "").toLowerCase().includes(feature)) return false;
      if (!keyword) return true;
      return [
        record.line,
        record.source,
        record.imei,
        record.feature,
        record.script,
      ].some((value) => (value || "").toLowerCase().includes(keyword));
    }

    function countRecord(record) {
      if (isGap(record)) { state.gaps += 1; return; }
      if (record.level === "E") state.errors += 1;
      else if (record.level === "W") state.warnings += 1;
    }

    function updateStats() {
      lineStatsEl.textContent = state.shown + " / " + state.lines.length;
      errCountEl.textContent = state.errors;
      warnCountEl.textContent = state.warnings;
      gapCountEl.textContent = state.gaps;
    }

    function render() {
      const output = state.lines.filter(passesFilters);
      logEl.innerHTML = output.map(lineHtml).join("");
      state.shown = output.length;
      updateStats();
      if (state.autoScroll) {
        logEl.scrollTop = logEl.scrollHeight;
      }
    }

    function appendRecord(record) {
      if (!passesFilters(record)) {
        updateStats();
        return;
      }
      logEl.insertAdjacentHTML("beforeend", lineHtml(record));
      while (logEl.childElementCount > MAX_LINES) {
        logEl.firstElementChild.remove();
      }
      state.shown = Math.min(state.shown + 1, MAX_LINES);
      updateStats();
      if (state.autoScroll) {
        logEl.scrollTop = logEl.scrollHeight;
      }
    }

    function setConnected(connected) {
      dotEl.classList.toggle("connected", connected);
      connTextEl.textContent = state.paused
        ? "已暂停（仍在接收与落盘）"
        : connected ? "已连接" : "连接中断";
    }

    async function loadHistory() {
      const response = await fetch("/history");
      const data = await response.json();
      state.lines = data.records || [];
      state.errors = 0;
      state.warnings = 0;
      state.gaps = 0;
      state.lines.forEach(countRecord);
      state.lines.forEach(registerDevice);
      state.udpTarget = data.udp_target || "";
      udpTargetEl.textContent = state.udpTarget || "-";
      render();
    }

    filterEl.addEventListener("input", render);
    levelFilterEl.addEventListener("change", render);
    deviceFilterEl.addEventListener("change", render);
    featureFilterEl.addEventListener("input", render);
    pauseBtn.addEventListener("click", () => {
      state.paused = !state.paused;
      pauseBtn.textContent = state.paused ? "恢复显示" : "暂停显示";
      pauseBtn.classList.toggle("paused", state.paused);
      setConnected(dotEl.classList.contains("connected"));
      if (!state.paused) {
        render();
      }
    });
    clearBtn.addEventListener("click", () => {
      state.lines = [];
      state.errors = 0;
      state.warnings = 0;
      state.gaps = 0;
      render();
    });
    function exportQuery() {
      const device = deviceFilterEl.value;
      return device ? "?imei=" + encodeURIComponent(device) : "";
    }
    exportBtn.addEventListener("click", async () => {
      await downloadFile("/download" + exportQuery(), "udp_logs.log");
    });
    exportJsonBtn.addEventListener("click", async () => {
      await downloadFile("/download-jsonl" + exportQuery(), "udp_logs.jsonl");
    });
    async function downloadFile(path, fallbackName) {
      try {
        const response = await fetch(path);
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        const blob = await response.blob();
        const disposition = response.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="([^"]+)"/);
        const filename = match ? match[1] : fallbackName;
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        alert("导出失败: " + err);
      }
    }
    toggleBtn.addEventListener("click", () => {
      state.autoScroll = !state.autoScroll;
      toggleBtn.textContent = state.autoScroll ? "暂停自动滚动" : "恢复自动滚动";
      render();
    });

    loadHistory().catch((err) => {
      state.lines.push({line: "加载历史日志失败: " + err + "\\n"});
      render();
    });

    const source = new EventSource("/events");
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.source) {
        sourceEl.textContent = payload.source;
      }
      if (payload.line) {
        state.lines.push(payload);
        if (state.lines.length > MAX_LINES) {
          state.lines.splice(0, state.lines.length - MAX_LINES);
        }
        countRecord(payload);
        registerDevice(payload);
        if (state.paused) {
          updateStats();
        } else {
          appendRecord(payload);
        }
      }
    };
  </script>
</body>
</html>
"""


class LogHub:
    def __init__(self, max_lines: int = 2000) -> None:
        self._lines = deque(maxlen=max_lines)
        self._subscribers = []
        self._lock = threading.Lock()
        self._last_source = "-"
        self._journal = UdpLogJournal("udp_web_session")
        self._jsonl_journal = UdpLogJournal("udp_web_session", suffix=".jsonl")
        self._sequence_tracker = UdpLogSequenceTracker()

    def publish(self, line: str, source: str) -> None:
        record = parse_udp_log_line(line, source)
        payload = self._build_payload(record, format_udp_log_record(record, include_source=True))
        gap = self._sequence_tracker.observe(record)
        gap_payload = None
        if gap is not None:
            gap_record = parse_udp_log_line(gap.to_line(), "local")
            gap_payload = self._build_payload(gap_record, gap_record.text)
        with self._lock:
            self._lines.append(payload)
            if gap_payload is not None:
                self._lines.append(gap_payload)
            self._last_source = source
            subscribers = list(self._subscribers)
        self._journal.append(payload["line"])
        self._jsonl_journal.append(self._payload_to_jsonl_line(payload))
        if gap_payload is not None:
            self._journal.append(gap_payload["line"])
            self._jsonl_journal.append(self._payload_to_jsonl_line(gap_payload))
        for subscriber in subscribers:
            subscriber.put(payload)
            if gap_payload is not None:
                subscriber.put(gap_payload)

    def _build_payload(self, record, line: str) -> dict:
        return {
            "line": line,
            "source": record.source,
            "imei": record.imei,
            "sequence": record.sequence,
            "level": record.level,
            "timestamp": record.timestamp,
            "script": record.script,
            "feature": record.feature,
            "message": record.message,
            "text": record.text.rstrip("\r\n"),
        }

    def history(self):
        with self._lock:
            return list(self._lines), self._last_source

    def export_text(self, imei: str = "") -> str:
        text = self._journal.read_text()
        if not text:
            with self._lock:
                text = "".join(record["line"] for record in self._lines)
        if not imei:
            return text
        # Session lines carry an "[imei=<id> source=...]" prefix; sequence-gap
        # notices embed "imei=<id> " in their body. Both stay in the export.
        marker = f"imei={imei} "
        return "".join(
            line + "\n" for line in text.splitlines() if marker in line
        )

    def export_filename(self, imei: str = "") -> str:
        name = self._journal.path.name
        return f"{imei}_{name}" if imei else name

    def export_jsonl_text(self, imei: str = "") -> str:
        text = self._jsonl_journal.read_text()
        if not text:
            with self._lock:
                text = "".join(self._payload_to_jsonl_line(record) for record in self._lines)
        if not imei:
            return text
        kept: list[str] = []
        for line in text.splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("imei") == imei or f"imei={imei} " in str(record.get("text", "")):
                kept.append(line + "\n")
        return "".join(kept)

    def _payload_to_jsonl_line(self, record: dict) -> str:
        jsonl_fields = (
            "source",
            "imei",
            "sequence",
            "level",
            "timestamp",
            "script",
            "feature",
            "message",
            "text",
        )
        return (
            json.dumps(
                {field: record.get(field) for field in jsonl_fields},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

    def export_jsonl_filename(self, imei: str = "") -> str:
        name = self._jsonl_journal.path.name
        return f"{imei}_{name}" if imei else name

    def subscribe(self) -> queue.Queue:
        subscriber = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def close(self) -> None:
        self._journal.close()
        self._jsonl_journal.close()


def make_handler(log_hub: LogHub, udp_target: str):
    class LogViewerHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_GET(self):
            parsed = urlparse(self.path)
            imei = (parse_qs(parsed.query).get("imei") or [""])[0]
            if parsed.path == "/":
                self._send_html()
                return
            if parsed.path == "/history":
                self._send_history()
                return
            if parsed.path == "/download":
                self._send_download(imei)
                return
            if parsed.path == "/download-jsonl":
                self._send_jsonl_download(imei)
                return
            if parsed.path == "/events":
                self._stream_events()
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        def _send_html(self):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_history(self):
            records, last_source = log_hub.history()
            payload = json.dumps(
                {
                    "records": records,
                    "lines": [record["line"] for record in records],
                    "last_source": last_source,
                    "udp_target": udp_target,
                }
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_download(self, imei: str = ""):
            body = log_hub.export_text(imei).encode("utf-8")
            filename = log_hub.export_filename(imei)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_jsonl_download(self, imei: str = ""):
            body = log_hub.export_jsonl_text(imei).encode("utf-8")
            filename = log_hub.export_jsonl_filename(imei)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            subscriber = log_hub.subscribe()
            try:
                while True:
                    try:
                        payload = subscriber.get(timeout=10)
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        continue

                    message = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
                    self.wfile.write(message)
                    self.wfile.flush()
            except OSError:
                # Browser closed/refreshed the SSE connection (on Windows this
                # raises ConnectionAbortedError, WinError 10053). Normal churn,
                # not an error worth a traceback.
                pass
            finally:
                log_hub.unsubscribe(subscriber)

    return LogViewerHandler


def udp_receiver(log_hub: LogHub, sock: socket.socket) -> None:
    while True:
        payload, addr = sock.recvfrom(4096)
        text = payload.decode("utf-8", errors="replace")
        if not text.endswith("\n"):
            text += "\n"
        log_hub.publish(text, f"{addr[0]}:{addr[1]}")


def open_udp_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        sock.close()
        message = f"Failed to bind UDP receiver on {host}:{port}: {exc}"
        if getattr(exc, "winerror", None) == 10048:
            message += "\nHint: another log receiver is already using this UDP port. Close udp_log_receiver.py first."
        raise RuntimeError(message) from exc
    return sock


def open_http_server(host: str, preferred_port: int, handler_factory) -> tuple[ThreadingHTTPServer, int]:
    candidate_ports = [preferred_port]
    if preferred_port == 18065:
        candidate_ports.extend([28065, 38065, 48065, 0])

    last_error = None
    for port in candidate_ports:
        try:
            server = ThreadingHTTPServer((host, port), handler_factory)
            actual_port = server.server_address[1]
            return server, actual_port
        except OSError as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Failed to bind HTTP server on {host}:{preferred_port}: {last_error}") from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a browser-based UDP log viewer.")
    parser.add_argument("--udp-host", default="0.0.0.0", help="UDP bind host, default: 0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=8001, help="UDP bind port, default: 8001")
    parser.add_argument("--http-host", default="127.0.0.1", help="HTTP bind host, default: 127.0.0.1")
    parser.add_argument("--http-port", type=int, default=18065, help="HTTP bind port, default: 18065")
    parser.add_argument("--open-browser", action="store_true", help="Open the viewer automatically in your default browser")
    args = parser.parse_args()

    udp_target = f"{args.udp_host}:{args.udp_port}"
    log_hub = LogHub()
    udp_socket = open_udp_socket(args.udp_host, args.udp_port)

    receiver_thread = threading.Thread(
        target=udp_receiver,
        args=(log_hub, udp_socket),
        name="udp-log-receiver",
        daemon=True,
    )
    receiver_thread.start()

    server, actual_http_port = open_http_server(
        args.http_host, args.http_port, make_handler(log_hub, udp_target)
    )
    viewer_url = f"http://{args.http_host}:{actual_http_port}"
    print(f"UDP receiver listening on udp://{udp_target}", flush=True)
    print(f"Open {viewer_url} in your browser", flush=True)
    if args.http_port != actual_http_port:
        print(
            f"Requested HTTP port {args.http_port} was unavailable, switched to {actual_http_port}.",
            flush=True,
        )
    if args.open_browser:
        webbrowser.open(viewer_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()
        udp_socket.close()
        log_hub.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
