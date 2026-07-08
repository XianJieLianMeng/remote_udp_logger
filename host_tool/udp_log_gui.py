#!/usr/bin/env python3
import argparse
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
from PySide6.QtGui import QIntValidator, QTextCursor
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

        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(100)
        self.queue_timer.timeout.connect(self._drain_queue)
        self.queue_timer.start()

        if auto_start:
            self.start_receiver()

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
            QPushButton {
                background: #263759;
                border: 1px solid #3a4d73;
                border-radius: 6px;
                color: #e4ecff;
                padding: 8px 12px;
            }
            QPushButton:hover { background: #304568; }
            QPushButton:pressed { background: #1c2a46; }
            QCheckBox { color: #e4ecff; spacing: 8px; }
            QPlainTextEdit {
                background: #121a30;
                border: 1px solid #263759;
                border-radius: 8px;
                color: #dbe6ff;
                padding: 10px;
                selection-background-color: #4267d5;
                font-family: Consolas, "Courier New", monospace;
                font-size: 11pt;
            }
            """
        )

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        self.setCentralWidget(central)

        title = QLabel("Xbell Wireless Log Viewer")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        root.addWidget(title)

        subtitle = QLabel(
            "Battery-powered device logs over UDP. Configure host/port here, then click Start."
        )
        subtitle.setStyleSheet("color: #b9c7e6;")
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        root.addWidget(card)

        config_title = QLabel("Receiver Settings")
        config_title.setStyleSheet("font-weight: 700;")
        grid.addWidget(config_title, 0, 0, 1, 2)

        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(self.status_label, 0, 2, 1, 5)

        grid.addWidget(QLabel("UDP Host"), 1, 0)
        self.udp_host_edit = QLineEdit("0.0.0.0")
        self.udp_host_edit.setMinimumWidth(150)
        grid.addWidget(self.udp_host_edit, 2, 0)

        grid.addWidget(QLabel("UDP Port"), 1, 1)
        self.udp_port_edit = QLineEdit("8001")
        self.udp_port_edit.setValidator(QIntValidator(1, 65535, self))
        self.udp_port_edit.setMaximumWidth(110)
        grid.addWidget(self.udp_port_edit, 2, 1)

        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.save_button = QPushButton("Export Logs")
        self.clear_button = QPushButton("Clear")
        self.refresh_button = QPushButton("Refresh IP")
        grid.addWidget(self.start_button, 2, 2)
        grid.addWidget(self.stop_button, 2, 3)
        grid.addWidget(self.save_button, 2, 4)
        grid.addWidget(self.clear_button, 2, 5)
        grid.addWidget(self.refresh_button, 2, 6)

        hint = QLabel(
            "Tip: keep UDP Host = 0.0.0.0 for receiving. Device Target is a copy-friendly value for the device-side log setting."
        )
        hint.setStyleSheet("color: #b9c7e6;")
        grid.addWidget(hint, 3, 0, 1, 7)

        self.local_ips_label = QLabel("Local IPv4: detecting...")
        self.preferred_ip_label = QLabel("Preferred IP: -")
        self.detected_target_label = QLabel("Detected PC target: -")
        grid.addWidget(self.local_ips_label, 4, 0, 1, 7)
        grid.addWidget(self.preferred_ip_label, 5, 0, 1, 7)
        grid.addWidget(self.detected_target_label, 6, 0, 1, 7)

        grid.addWidget(QLabel("Device Target"), 7, 0)
        self.device_target_edit = QLineEdit(PROJECT_DEFAULT_DEVICE_TARGET)
        self.device_target_edit.setMinimumWidth(260)
        grid.addWidget(self.device_target_edit, 8, 0, 1, 2)

        self.use_detected_button = QPushButton("Use Detected IP")
        self.use_default_button = QPushButton("Use Project Default")
        self.copy_target_button = QPushButton("Copy Device Target")
        grid.addWidget(self.use_detected_button, 8, 2)
        grid.addWidget(self.use_default_button, 8, 3, 1, 2)
        grid.addWidget(self.copy_target_button, 8, 5, 1, 2)

        default_label = QLabel(f"Project default example: {PROJECT_DEFAULT_DEVICE_TARGET}")
        default_label.setStyleSheet("color: #b9c7e6;")
        grid.addWidget(default_label, 9, 0, 1, 7)

        for column in range(7):
            grid.setColumnStretch(column, 1 if column in (0, 2, 3, 4, 5, 6) else 0)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        root.addLayout(toolbar)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter text, source, IMEI, feature, or source file")
        self.filter_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar.addWidget(self.filter_edit)

        self.level_combo = QComboBox()
        self.level_combo.addItem("All Levels", "")
        for level in ("E", "W", "I", "D", "V"):
            self.level_combo.addItem(level, level)
        self.level_combo.setMinimumWidth(110)
        toolbar.addWidget(self.level_combo)

        self.feature_edit = QLineEdit()
        self.feature_edit.setPlaceholderText("Feature")
        self.feature_edit.setMinimumWidth(160)
        toolbar.addWidget(self.feature_edit)

        self.device_combo = QComboBox()
        self.device_combo.addItem("All Devices", "")
        self.device_combo.setMinimumWidth(250)
        toolbar.addWidget(self.device_combo)

        self.show_source_check = QCheckBox("Show Source")
        self.show_source_check.setChecked(True)
        toolbar.addWidget(self.show_source_check)

        self.auto_scroll_check = QCheckBox("Auto Scroll")
        self.auto_scroll_check.setChecked(True)
        toolbar.addWidget(self.auto_scroll_check)

        self.source_label = QLabel("Latest source: -")
        toolbar.addWidget(self.source_label)

        self.count_label = QLabel("Lines: 0")
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        toolbar.addWidget(self.count_label)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        root.addWidget(self.text, 1)

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self.start_receiver)
        self.stop_button.clicked.connect(self.stop_receiver)
        self.save_button.clicked.connect(self.save_logs)
        self.clear_button.clicked.connect(self.clear_logs)
        self.refresh_button.clicked.connect(self.refresh_network_info)
        self.use_detected_button.clicked.connect(self.use_detected_target)
        self.use_default_button.clicked.connect(self.use_project_default_target)
        self.copy_target_button.clicked.connect(self.copy_device_target)
        self.filter_edit.textChanged.connect(self.render)
        self.feature_edit.textChanged.connect(self.render)
        self.level_combo.currentIndexChanged.connect(self.render)
        self.udp_port_edit.textChanged.connect(self.refresh_network_info)
        self.device_combo.currentIndexChanged.connect(self.render)
        self.show_source_check.stateChanged.connect(self.render)

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

    def start_receiver(self) -> None:
        if self.running:
            QMessageBox.information(self, "Already Running", "The UDP receiver is already running.")
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
        self.status_label.setText(f"Listening on udp://{host}:{port}")
        self._save_config()

    def stop_receiver(self) -> None:
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None
        self.running = False
        self.status_label.setText("Stopped")

    def clear_logs(self) -> None:
        self.records.clear()
        self.devices.clear()
        self.sequence_tracker = UdpLogSequenceTracker()
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
        if ips:
            self.local_ips_label.setText(f"Local IPv4: {', '.join(ips)}")
        else:
            self.local_ips_label.setText("Local IPv4: not detected")

        display_ip = preferred_ip if preferred_ip else "-"
        self.preferred_ip_label.setText(f"Preferred IP: {display_ip}")

        port_text = self.udp_port_edit.text().strip()
        try:
            port = int(port_text)
        except ValueError:
            port = None

        if preferred_ip and port is not None:
            self.detected_target_value = f"{preferred_ip}:{port}"
            self.detected_target_label.setText(f"Detected PC target: {self.detected_target_value}")
        elif preferred_ip:
            self.detected_target_value = ""
            self.detected_target_label.setText(f"Detected PC target: {preferred_ip}:<invalid-port>")
        else:
            self.detected_target_value = ""
            self.detected_target_label.setText("Detected PC target: unavailable")

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
        updated = False
        while True:
            try:
                line, source = self.line_queue.get_nowait()
            except queue.Empty:
                break
            record = parse_udp_log_line(line, source)
            self.records.append(record)
            self.journal.append(self._format_record(record, include_source=True))
            self.jsonl_journal.append(format_udp_log_record_jsonl(record))
            gap = self.sequence_tracker.observe(record)
            if gap is not None:
                gap_record = parse_udp_log_line(gap.to_line(), "local")
                self.records.append(gap_record)
                self.journal.append(gap_record.text)
                self.jsonl_journal.append(format_udp_log_record_jsonl(gap_record))
            if record.imei != "-":
                self.devices[record.imei] = source
                self._refresh_device_combo()
            if len(self.records) > MAX_DISPLAY_LOG_LINES:
                self.records = self.records[-MAX_DISPLAY_LOG_LINES:]
            self.source_label.setText(f"Latest source: {source}")
            updated = True

        if updated:
            self.render()

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

    def render(self) -> None:
        keyword = self.filter_edit.text().strip().lower()
        feature_keyword = self.feature_edit.text().strip().lower()
        selected_level = str(self.level_combo.currentData() or "")
        selected_imei = self._selected_device_imei()
        display_records = self.records
        if selected_imei:
            display_records = [record for record in display_records if record.imei == selected_imei]
        if selected_level:
            display_records = [record for record in display_records if record.level == selected_level]
        if feature_keyword:
            display_records = [
                record for record in display_records
                if feature_keyword in record.feature.lower()
            ]
        if keyword:
            display_records = [
                record for record in display_records
                if keyword in record.text.lower()
                or keyword in record.source.lower()
                or keyword in record.imei.lower()
                or keyword in record.feature.lower()
                or keyword in record.script.lower()
            ]

        include_source = self.show_source_check.isChecked()
        self.text.setPlainText(
            "".join(self._format_record(record, include_source) for record in display_records)
        )
        self.count_label.setText(f"Lines: {len(display_records)}")
        if self.auto_scroll_check.isChecked():
            self.text.moveCursor(QTextCursor.End)

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
