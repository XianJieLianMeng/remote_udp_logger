#!/usr/bin/env python3
import argparse
import html
import json
import queue
import socket
import sys
import threading
from pathlib import Path

from udp_log_env import ensure_supported_python

ensure_supported_python("udp_log_gui")

try:
    from PySide6.QtCore import QTimer, Qt
except ImportError:
    raise SystemExit(
        "udp_log_gui requires PySide6. Install it with:\n"
        "  python -m pip install -r requirements.txt\n"
        "or use the prebuilt XbellUdpLogViewer package (no Python needed)."
    )
from PySide6.QtGui import QIntValidator, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from udp_log_journal import UdpLogJournal
from udp_log_record import (
    UdpLogRecord,
    format_udp_log_record,
    format_udp_log_record_jsonl,
    parse_udp_log_line,
)
from udp_log_sequence import UdpLogSequenceTracker


CONFIG_FILE_NAME = "udp_log_gui_config.json"
MAX_DISPLAY_LOG_LINES = 4000
SOCKET_TIMEOUT_SEC = 0.5
PROJECT_DEFAULT_DEVICE_TARGET = "255.255.255.255:8001"

LEVEL_COLORS = {
    "E": "#ff7676",
    "W": "#ffc46b",
    "I": "#dbe6ff",
    "D": "#9fb3dd",
    "V": "#7f92bf",
}
GAP_COLOR = "#c792ea"

# QTextBlock user states used for error navigation.
BLOCK_STATE_ERROR = 1
BLOCK_STATE_WARNING = 2
BLOCK_STATE_GAP = 3

STATUS_STYLES = {
    "idle": "background: #2a3450; color: #b9c7e6;",
    "listening": "background: #17402c; color: #8dffb3;",
    "paused": "background: #4d3d18; color: #ffd27d;",
    "stopped": "background: #4a2531; color: #ff9f9f;",
}


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def detect_local_ipv4s() -> tuple[str, list[str]]:
    ips: list[str] = []
    preferred_ip = ""

    def add_ip(ip: str) -> None:
        if not ip or ip.startswith("127.") or ip == "0.0.0.0":
            return
        if ip not in ips:
            ips.append(ip)

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        preferred_ip = probe.getsockname()[0]
        add_ip(preferred_ip)
    except OSError:
        preferred_ip = ""
    finally:
        try:
            probe.close()
        except Exception:
            pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM):
            add_ip(info[4][0])
    except OSError:
        pass

    try:
        _host_name, _aliases, host_ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in host_ips:
            add_ip(ip)
    except OSError:
        pass

    if not preferred_ip and ips:
        preferred_ip = ips[0]

    return preferred_ip, ips


class UdpReceiver:
    def __init__(self, host: str, port: int, line_queue: queue.Queue[tuple[str, str]]) -> None:
        self.host = host
        self.port = port
        self.line_queue = line_queue
        self.stop_event = threading.Event()
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is not None:
            return

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(SOCKET_TIMEOUT_SEC)
        try:
            self.sock.bind((self.host, self.port))
        except OSError as exc:
            self.sock.close()
            self.sock = None
            detail = f"Failed to bind UDP {self.host}:{self.port}\n{exc}"
            if getattr(exc, "winerror", None) == 10048:
                detail += "\n\nHint: another log tool is already using this UDP port."
            raise RuntimeError(detail) from exc

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="udp-log-receiver", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        if self.thread is not None:
            self.thread.join(timeout=1.5)
        self.thread = None
        self.sock = None

    def _run(self) -> None:
        assert self.sock is not None
        while not self.stop_event.is_set():
            try:
                payload, addr = self.sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                if self.stop_event.is_set():
                    break
                continue

            text = payload.decode("utf-8", errors="replace")
            if not text.endswith("\n"):
                text += "\n"
            self.line_queue.put((text, f"{addr[0]}:{addr[1]}"))


class UdpLogGui(QMainWindow):
    def __init__(
        self,
        initial_udp_host: str | None = None,
        initial_udp_port: int | None = None,
        auto_start: bool = False,
    ) -> None:
        super().__init__()

        self.app_dir = get_app_dir()
        self.config_path = self.app_dir / CONFIG_FILE_NAME
        self.records: list[UdpLogRecord] = []
        self.devices: dict[str, str] = {}
        self.line_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.receiver: UdpReceiver | None = None
        self.detected_target_value = ""
        self.running = False
        self.paused = False
        self.error_count = 0
        self.warning_count = 0
        self.gap_count = 0
        self.shown_count = 0
        self.journal = UdpLogJournal("udp_gui_session")
        self.jsonl_journal = UdpLogJournal("udp_gui_session", suffix=".jsonl")
        self.sequence_tracker = UdpLogSequenceTracker()

        self.setWindowTitle("Xbell Wireless Log Viewer")
        self.resize(1180, 780)
        self.setMinimumSize(980, 640)

        self._build_ui()
        self._load_config()
        if initial_udp_host:
            self.udp_host_edit.setText(initial_udp_host)
        if initial_udp_port is not None:
            self.udp_port_edit.setText(str(initial_udp_port))

        self._connect_signals()
        self.refresh_network_info()
        self._set_status("idle", "Idle - configure receiver, then press Start")

        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(100)
        self.queue_timer.timeout.connect(self._drain_queue)
        self.queue_timer.start()

        if auto_start:
            self.toggle_receiver()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #0f1526; }
            QLabel { color: #e4ecff; }
            QFrame#card { background: #141d33; border-radius: 8px; }
            QLineEdit {
                background: #0f172a;
                border: 1px solid #30405f;
                border-radius: 6px;
                color: #e4ecff;
                padding: 7px 9px;
                selection-background-color: #4267d5;
            }
            QComboBox {
                background: #0f172a;
                border: 1px solid #30405f;
                border-radius: 6px;
                color: #e4ecff;
                padding: 6px 9px;
            }
            QComboBox QAbstractItemView {
                background: #141d33;
                color: #e4ecff;
                selection-background-color: #4267d5;
            }
            QPushButton {
                background: #263759;
                border: 1px solid #3a4d73;
                border-radius: 6px;
                color: #e4ecff;
                padding: 8px 14px;
            }
            QPushButton:hover { background: #304568; }
            QPushButton:pressed { background: #1c2a46; }
            QPushButton#primary {
                background: #2f6b46;
                border: 1px solid #3f8f5e;
                font-weight: 700;
            }
            QPushButton#primary:hover { background: #38804f; }
            QPushButton#primary[running="true"] {
                background: #6b3040;
                border: 1px solid #8f4054;
            }
            QPushButton#primary[running="true"]:hover { background: #7d3a4c; }
            QPushButton#pause:checked {
                background: #4d3d18;
                border: 1px solid #806524;
                color: #ffd27d;
            }
            QToolButton {
                background: transparent;
                border: none;
                color: #b9c7e6;
                font-weight: 700;
                padding: 4px;
            }
            QCheckBox { color: #e4ecff; spacing: 8px; }
            QPlainTextEdit {
                background: #0b1020;
                border: 1px solid #263759;
                border-radius: 8px;
                color: #dbe6ff;
                padding: 10px;
                selection-background-color: #4267d5;
                font-family: Consolas, "Courier New", monospace;
                font-size: 10.5pt;
            }
            QStatusBar { color: #8ea2d0; }
            """
        )

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 8)
        root.setSpacing(10)
        self.setCentralWidget(central)

        # -- Header: title + status pill + counters ----------------------
        header = QHBoxLayout()
        header.setSpacing(12)
        root.addLayout(header)

        title = QLabel("Xbell Wireless Log Viewer")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        header.addWidget(title)

        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet(
            f"{STATUS_STYLES['idle']} border-radius: 10px; padding: 4px 12px; font-weight: 600;"
        )
        header.addWidget(self.status_label)
        header.addStretch(1)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #b9c7e6; font-size: 12px;")
        header.addWidget(self.stats_label)

        # -- Action toolbar ----------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(8)
        root.addLayout(actions)

        self.start_stop_button = QPushButton("▶  Start")
        self.start_stop_button.setObjectName("primary")
        self.start_stop_button.setMinimumWidth(120)
        actions.addWidget(self.start_stop_button)

        self.pause_button = QPushButton("⏸  Pause View")
        self.pause_button.setObjectName("pause")
        self.pause_button.setCheckable(True)
        self.pause_button.setToolTip(
            "Freeze the on-screen view. Logs keep being received and written to the session file."
        )
        actions.addWidget(self.pause_button)

        self.save_button = QPushButton("Export Logs")
        self.clear_button = QPushButton("Clear")
        actions.addWidget(self.save_button)
        actions.addWidget(self.clear_button)

        self.prev_error_button = QPushButton("⬆ Prev Error")
        self.prev_error_button.setToolTip("Jump to the previous error line (Shift+F3)")
        self.next_error_button = QPushButton("⬇ Next Error")
        self.next_error_button.setToolTip("Jump to the next error line (F3)")
        actions.addWidget(self.prev_error_button)
        actions.addWidget(self.next_error_button)
        actions.addStretch(1)

        self.settings_toggle = QToolButton()
        self.settings_toggle.setText("Receiver Settings")
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setChecked(True)
        self.settings_toggle.setArrowType(Qt.DownArrow)
        self.settings_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        actions.addWidget(self.settings_toggle)

        # -- Collapsible settings card ------------------------------------
        self.settings_card = QFrame()
        self.settings_card.setObjectName("card")
        grid = QGridLayout(self.settings_card)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        root.addWidget(self.settings_card)

        grid.addWidget(QLabel("UDP Host"), 0, 0)
        self.udp_host_edit = QLineEdit("0.0.0.0")
        self.udp_host_edit.setMinimumWidth(150)
        grid.addWidget(self.udp_host_edit, 1, 0)

        grid.addWidget(QLabel("UDP Port"), 0, 1)
        self.udp_port_edit = QLineEdit("8001")
        self.udp_port_edit.setValidator(QIntValidator(1, 65535, self))
        self.udp_port_edit.setMaximumWidth(110)
        grid.addWidget(self.udp_port_edit, 1, 1)

        self.refresh_button = QPushButton("Refresh IP")
        grid.addWidget(self.refresh_button, 1, 2)

        hint = QLabel(
            "Keep UDP Host = 0.0.0.0 for receiving. Device Target is the copy-friendly value "
            "for the device-side log setting."
        )
        hint.setStyleSheet("color: #8ea2d0; font-size: 12px;")
        grid.addWidget(hint, 2, 0, 1, 6)

        self.network_info_label = QLabel("Local IPv4: detecting...")
        self.network_info_label.setStyleSheet("color: #b9c7e6; font-size: 12px;")
        grid.addWidget(self.network_info_label, 3, 0, 1, 6)

        grid.addWidget(QLabel("Device Target"), 4, 0)
        self.device_target_edit = QLineEdit(PROJECT_DEFAULT_DEVICE_TARGET)
        self.device_target_edit.setMinimumWidth(240)
        grid.addWidget(self.device_target_edit, 5, 0, 1, 2)

        self.use_detected_button = QPushButton("Use Detected IP")
        self.use_default_button = QPushButton("Use Project Default")
        self.copy_target_button = QPushButton("Copy Device Target")
        grid.addWidget(self.use_detected_button, 5, 2)
        grid.addWidget(self.use_default_button, 5, 3)
        grid.addWidget(self.copy_target_button, 5, 4)

        for column in range(6):
            grid.setColumnStretch(column, 1 if column == 5 else 0)

        # -- Filter toolbar ------------------------------------------------
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        root.addLayout(toolbar)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter text, source, IMEI, feature, or source file")
        self.filter_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar.addWidget(self.filter_edit)

        self.level_combo = QComboBox()
        self.level_combo.addItem("All Levels", "")
        self.level_combo.addItem("E - error", "E")
        self.level_combo.addItem("W - warning", "W")
        self.level_combo.addItem("I - info", "I")
        self.level_combo.addItem("D - debug", "D")
        self.level_combo.addItem("V - verbose", "V")
        self.level_combo.setMinimumWidth(120)
        toolbar.addWidget(self.level_combo)

        self.feature_edit = QLineEdit()
        self.feature_edit.setPlaceholderText("Feature")
        self.feature_edit.setMinimumWidth(140)
        toolbar.addWidget(self.feature_edit)

        self.device_combo = QComboBox()
        self.device_combo.addItem("All Devices", "")
        self.device_combo.setMinimumWidth(220)
        toolbar.addWidget(self.device_combo)

        self.show_source_check = QCheckBox("Show Source")
        self.show_source_check.setChecked(True)
        toolbar.addWidget(self.show_source_check)

        self.auto_scroll_check = QCheckBox("Auto Scroll")
        self.auto_scroll_check.setChecked(True)
        toolbar.addWidget(self.auto_scroll_check)

        # -- Log view -------------------------------------------------------
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_DISPLAY_LOG_LINES)
        root.addWidget(self.text, 1)

        # -- Status bar -----------------------------------------------------
        self.source_label = QLabel("Latest source: -")
        self.statusBar().addWidget(self.source_label)
        self.session_label = QLabel(f"Session file: {self.journal.path}")
        self.statusBar().addPermanentWidget(self.session_label)

        self._update_stats()

    def _connect_signals(self) -> None:
        self.start_stop_button.clicked.connect(self.toggle_receiver)
        self.pause_button.toggled.connect(self._on_pause_toggled)
        self.save_button.clicked.connect(self.save_logs)
        self.clear_button.clicked.connect(self.clear_logs)
        self.refresh_button.clicked.connect(self.refresh_network_info)
        self.use_detected_button.clicked.connect(self.use_detected_target)
        self.use_default_button.clicked.connect(self.use_project_default_target)
        self.copy_target_button.clicked.connect(self.copy_device_target)
        self.settings_toggle.toggled.connect(self._on_settings_toggled)
        self.prev_error_button.clicked.connect(lambda: self._jump_to_error(forward=False))
        self.next_error_button.clicked.connect(lambda: self._jump_to_error(forward=True))
        QShortcut(QKeySequence("F3"), self, activated=lambda: self._jump_to_error(forward=True))
        QShortcut(
            QKeySequence("Shift+F3"), self, activated=lambda: self._jump_to_error(forward=False)
        )
        self.filter_edit.textChanged.connect(self.render)
        self.feature_edit.textChanged.connect(self.render)
        self.level_combo.currentIndexChanged.connect(self.render)
        self.udp_port_edit.textChanged.connect(self.refresh_network_info)
        self.device_combo.currentIndexChanged.connect(self.render)
        self.show_source_check.stateChanged.connect(self.render)

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        if not self.config_path.exists():
            return

        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self.udp_host_edit.setText(str(payload.get("udp_host", self.udp_host_edit.text())))
        self.udp_port_edit.setText(str(payload.get("udp_port", self.udp_port_edit.text())))
        self.device_target_edit.setText(
            str(payload.get("device_target", self.device_target_edit.text()))
        )
        self.auto_scroll_check.setChecked(
            bool(payload.get("auto_scroll", self.auto_scroll_check.isChecked()))
        )
        self.show_source_check.setChecked(
            bool(payload.get("show_source", self.show_source_check.isChecked()))
        )

    def _save_config(self) -> None:
        payload = {
            "udp_host": self.udp_host_edit.text().strip(),
            "udp_port": self.udp_port_edit.text().strip(),
            "device_target": self.device_target_edit.text().strip(),
            "auto_scroll": self.auto_scroll_check.isChecked(),
            "show_source": self.show_source_check.isChecked(),
        }
        try:
            self.config_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Receiver control
    # ------------------------------------------------------------------
    def toggle_receiver(self) -> None:
        if self.running:
            self.stop_receiver()
        else:
            self.start_receiver()

    def start_receiver(self) -> None:
        if self.running:
            return

        host = self.udp_host_edit.text().strip() or "0.0.0.0"
        port_text = self.udp_port_edit.text().strip()
        try:
            port = int(port_text)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            QMessageBox.critical(self, "Invalid Port", f"UDP port is invalid: {port_text}")
            return

        try:
            self.receiver = UdpReceiver(host, port, self.line_queue)
            self.receiver.start()
        except RuntimeError as exc:
            self.receiver = None
            QMessageBox.critical(self, "Start Failed", str(exc))
            return

        self.running = True
        self._set_status("listening", f"Listening on udp://{host}:{port}")
        self._set_start_button_running(True)
        self.settings_toggle.setChecked(False)
        self._save_config()

    def stop_receiver(self) -> None:
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None
        was_running = self.running
        self.running = False
        self._set_start_button_running(False)
        if was_running:
            self._set_status("stopped", "Stopped")
            self.settings_toggle.setChecked(True)

    def _set_start_button_running(self, running: bool) -> None:
        self.start_stop_button.setText("■  Stop" if running else "▶  Start")
        self.start_stop_button.setProperty("running", "true" if running else "false")
        style = self.start_stop_button.style()
        style.unpolish(self.start_stop_button)
        style.polish(self.start_stop_button)

    def _on_pause_toggled(self, paused: bool) -> None:
        self.paused = paused
        self.pause_button.setText("▶  Resume View" if paused else "⏸  Pause View")
        if paused:
            if self.running:
                self._set_status("paused", "View paused - still receiving and journaling")
        else:
            self.render()
            if self.running:
                host = self.udp_host_edit.text().strip() or "0.0.0.0"
                port = self.udp_port_edit.text().strip()
                self._set_status("listening", f"Listening on udp://{host}:{port}")

    def _on_settings_toggled(self, expanded: bool) -> None:
        self.settings_card.setVisible(expanded)
        self.settings_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _set_status(self, kind: str, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"{STATUS_STYLES.get(kind, STATUS_STYLES['idle'])} "
            "border-radius: 10px; padding: 4px 12px; font-weight: 600; font-size: 12px;"
        )

    # ------------------------------------------------------------------
    # Log intake and rendering
    # ------------------------------------------------------------------
    def clear_logs(self) -> None:
        self.records.clear()
        self.devices.clear()
        self.sequence_tracker = UdpLogSequenceTracker()
        self.error_count = 0
        self.warning_count = 0
        self.gap_count = 0
        self._refresh_device_combo()
        self.render()

    def save_logs(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            self.journal.path.name,
            "Log Files (*.log);;JSON Lines (*.jsonl);;Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            output_path = Path(path)
            wants_jsonl = path.lower().endswith(".jsonl") or "json lines" in selected_filter.lower()
            if wants_jsonl:
                if output_path.suffix.lower() != ".jsonl":
                    output_path = output_path.with_suffix(".jsonl")
                text = self.jsonl_journal.read_text()
                if not text and self.records:
                    text = "".join(format_udp_log_record_jsonl(record) for record in self.records)
            else:
                text = self.journal.read_text()
                if not text and self.records:
                    text = "".join(
                        self._format_record(record, include_source=True) for record in self.records
                    )
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Logs exported to:\n{output_path}")

    def refresh_network_info(self) -> None:
        preferred_ip, ips = detect_local_ipv4s()
        port_text = self.udp_port_edit.text().strip()
        try:
            port = int(port_text)
        except ValueError:
            port = None

        if preferred_ip and port is not None:
            self.detected_target_value = f"{preferred_ip}:{port}"
        else:
            self.detected_target_value = ""

        parts = []
        parts.append(f"Local IPv4: {', '.join(ips) if ips else 'not detected'}")
        if self.detected_target_value:
            parts.append(f"Detected PC target: {self.detected_target_value}")
        self.network_info_label.setText("    ".join(parts))

    def use_detected_target(self) -> None:
        if not self.detected_target_value:
            QMessageBox.warning(self, "Use Failed", "No valid detected IP target is available yet.")
            return
        self.device_target_edit.setText(self.detected_target_value)
        self._save_config()

    def use_project_default_target(self) -> None:
        self.device_target_edit.setText(PROJECT_DEFAULT_DEVICE_TARGET)
        self._save_config()

    def copy_device_target(self) -> None:
        value = self.device_target_edit.text().strip()
        if not value:
            QMessageBox.warning(self, "Copy Failed", "Device target is empty.")
            return
        self._save_config()
        QApplication.clipboard().setText(value)
        QMessageBox.information(self, "Copied", f"Copied device target:\n{value}")

    def _drain_queue(self) -> None:
        appended: list[UdpLogRecord] = []
        while True:
            try:
                line, source = self.line_queue.get_nowait()
            except queue.Empty:
                break
            record = parse_udp_log_line(line, source)
            self.records.append(record)
            appended.append(record)
            self.journal.append(self._format_record(record, include_source=True))
            self.jsonl_journal.append(format_udp_log_record_jsonl(record))
            if record.level == "E":
                self.error_count += 1
            elif record.level == "W":
                self.warning_count += 1
            gap = self.sequence_tracker.observe(record)
            if gap is not None:
                gap_record = parse_udp_log_line(gap.to_line(), "local")
                self.records.append(gap_record)
                appended.append(gap_record)
                self.journal.append(gap_record.text)
                self.jsonl_journal.append(format_udp_log_record_jsonl(gap_record))
                self.gap_count += 1
            if record.imei != "-":
                self.devices[record.imei] = source
                self._refresh_device_combo()
            self.source_label.setText(f"Latest source: {source}")

        if not appended:
            return

        if len(self.records) > MAX_DISPLAY_LOG_LINES:
            self.records = self.records[-MAX_DISPLAY_LOG_LINES:]

        if not self.paused:
            include_source = self.show_source_check.isChecked()
            shown = 0
            for record in appended:
                if self._record_passes_filters(record):
                    self._append_record_block(record, include_source)
                    shown += 1
            if shown:
                self.shown_count += shown
                if self.auto_scroll_check.isChecked():
                    self.text.moveCursor(QTextCursor.End)
        self._update_stats()

    def _refresh_device_combo(self) -> None:
        current_imei = self.device_combo.currentData() or ""
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("All Devices", "")
        for imei in sorted(self.devices):
            source = self.devices[imei]
            self.device_combo.addItem(f"{imei} @ {source}", imei)
        index = self.device_combo.findData(current_imei)
        self.device_combo.setCurrentIndex(index if index >= 0 else 0)
        self.device_combo.blockSignals(False)

    def _selected_device_imei(self) -> str:
        value = self.device_combo.currentData()
        return str(value) if value else ""

    def _format_record(self, record: UdpLogRecord, include_source: bool) -> str:
        return format_udp_log_record(record, include_source=include_source)

    def _record_passes_filters(self, record: UdpLogRecord) -> bool:
        selected_imei = self._selected_device_imei()
        if selected_imei and record.imei != selected_imei:
            return False
        selected_level = str(self.level_combo.currentData() or "")
        if selected_level and record.level != selected_level:
            return False
        feature_keyword = self.feature_edit.text().strip().lower()
        if feature_keyword and feature_keyword not in record.feature.lower():
            return False
        keyword = self.filter_edit.text().strip().lower()
        if keyword and not (
            keyword in record.text.lower()
            or keyword in record.source.lower()
            or keyword in record.imei.lower()
            or keyword in record.feature.lower()
            or keyword in record.script.lower()
        ):
            return False
        return True

    def _record_to_html(self, record: UdpLogRecord, include_source: bool) -> str:
        line = self._format_record(record, include_source).rstrip("\n")
        escaped = html.escape(line)
        if record.feature == "udp.seq":
            return f'<span style="color: {GAP_COLOR}; font-style: italic;">{escaped}</span>'
        color = LEVEL_COLORS.get(record.level, LEVEL_COLORS["I"])
        weight = " font-weight: 700;" if record.level == "E" else ""
        return f'<span style="color: {color};{weight}">{escaped}</span>'

    def _record_block_state(self, record: UdpLogRecord) -> int:
        if record.feature == "udp.seq":
            return BLOCK_STATE_GAP
        if record.level == "E":
            return BLOCK_STATE_ERROR
        if record.level == "W":
            return BLOCK_STATE_WARNING
        return 0

    def _append_record_block(self, record: UdpLogRecord, include_source: bool) -> None:
        self.text.appendHtml(self._record_to_html(record, include_source))
        self.text.document().lastBlock().setUserState(self._record_block_state(record))

    def _jump_to_error(self, forward: bool) -> None:
        block = self.text.textCursor().block()
        block = block.next() if forward else block.previous()
        while block.isValid():
            if block.userState() == BLOCK_STATE_ERROR:
                cursor = self.text.textCursor()
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                self.auto_scroll_check.setChecked(False)
                self.text.setTextCursor(cursor)
                self.text.centerCursor()
                return
            block = block.next() if forward else block.previous()
        direction = "below" if forward else "above"
        self.statusBar().showMessage(f"No error lines {direction} the cursor", 3000)

    def render(self) -> None:
        include_source = self.show_source_check.isChecked()
        display_records = [r for r in self.records if self._record_passes_filters(r)]

        self.text.setUpdatesEnabled(False)
        self.text.clear()
        for record in display_records:
            self._append_record_block(record, include_source)
        self.text.setUpdatesEnabled(True)

        self.shown_count = len(display_records)
        if self.auto_scroll_check.isChecked():
            self.text.moveCursor(QTextCursor.End)
        self._update_stats()

    def _update_stats(self) -> None:
        self.stats_label.setText(
            f"Shown {self.shown_count} / Buffered {len(self.records)}"
            f'    <span style="color: {LEVEL_COLORS["E"]};">E {self.error_count}</span>'
            f'    <span style="color: {LEVEL_COLORS["W"]};">W {self.warning_count}</span>'
            f'    <span style="color: {GAP_COLOR};">Gaps {self.gap_count}</span>'
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_config()
        self.stop_receiver()
        self.journal.close()
        self.jsonl_journal.close()
        event.accept()


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop UDP log viewer")
    parser.add_argument("--udp-host", default=None, help="Initial UDP bind host")
    parser.add_argument("--udp-port", type=int, default=None, help="Initial UDP bind port")
    parser.add_argument("--auto-start", action="store_true", help="Start receiving immediately")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    viewer = UdpLogGui(
        initial_udp_host=args.udp_host,
        initial_udp_port=args.udp_port,
        auto_start=args.auto_start,
    )
    viewer.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
