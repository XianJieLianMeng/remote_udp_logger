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
DEFAULT_LANGUAGE = "zh"

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
    "idle": "background: #232b3f; color: #8b9bc0;",
    "listening": "background: #17402c; color: #8dffb3;",
    "paused": "background: #4d3d18; color: #ffd27d;",
    "stopped": "background: #4a2531; color: #ff9f9f;",
}

# User-facing text catalog. Keep every visible string here so the UI stays
# translatable; do not hard-code labels inside widget-building code.
TEXTS = {
    "zh": {
        "app_title": "Xbell 无线日志查看器",
        "status_idle": "空闲 · 配置接收参数后点击开始",
        "status_listening": "正在监听 udp://{url}",
        "status_paused": "已暂停显示 · 仍在接收与落盘",
        "status_stopped": "已停止",
        "btn_start": "开始接收",
        "btn_stop": "停止接收",
        "btn_pause": "暂停显示",
        "btn_resume": "恢复显示",
        "tip_pause": "冻结界面显示；日志仍在接收并写入会话文件",
        "btn_export": "导出日志",
        "btn_clear": "清空",
        "btn_prev_error": "上一错误",
        "btn_next_error": "下一错误",
        "tip_prev_error": "跳到上一条错误行（Shift+F3）",
        "tip_next_error": "跳到下一条错误行（F3）",
        "settings": "接收设置",
        "lbl_udp_host": "UDP 监听地址",
        "lbl_udp_port": "UDP 端口",
        "btn_refresh_ip": "刷新本机 IP",
        "hint_receiver": "监听地址保持 0.0.0.0 即可接收；设备端目标是给固件日志配置复制用的地址。",
        "net_local": "本机 IPv4：{ips}",
        "net_none": "未检测到",
        "net_detected": "检测到的电脑目标：{target}",
        "lbl_device_target": "设备端目标",
        "btn_use_detected": "使用检测到的 IP",
        "btn_use_default": "使用项目默认",
        "btn_copy_target": "复制目标",
        "ph_filter": "过滤：正文 / 来源 / IMEI / feature / 源码文件",
        "level_all": "全部级别",
        "level_E": "E · 错误",
        "level_W": "W · 警告",
        "level_I": "I · 信息",
        "level_D": "D · 调试",
        "level_V": "V · 详细",
        "ph_feature": "feature",
        "devices_all": "全部设备",
        "chk_show_source": "显示来源",
        "chk_auto_scroll": "自动滚动",
        "stats": "显示 {shown} / 缓存 {buffered}",
        "stats_gaps": "丢包",
        "sb_latest_source": "最新来源：{source}",
        "sb_session": "会话文件：{path}",
        "msg_invalid_port_title": "端口无效",
        "msg_invalid_port": "UDP 端口无效：{port}",
        "msg_start_failed_title": "启动失败",
        "msg_use_failed_title": "无法使用",
        "msg_use_failed": "暂时没有检测到可用的电脑 IP 目标。",
        "msg_copy_failed_title": "复制失败",
        "msg_copy_failed": "设备端目标为空。",
        "msg_copied_title": "已复制",
        "msg_copied": "已复制设备端目标：\n{value}",
        "msg_export_failed_title": "保存失败",
        "msg_exported_title": "导出完成",
        "msg_exported": "日志已导出到：\n{path}",
        "export_dialog_title": "导出日志",
        "no_errors_below": "光标下方没有错误行",
        "no_errors_above": "光标上方没有错误行",
    },
    "en": {
        "app_title": "Xbell Wireless Log Viewer",
        "status_idle": "Idle · configure the receiver, then press Start",
        "status_listening": "Listening on udp://{url}",
        "status_paused": "View paused · still receiving and journaling",
        "status_stopped": "Stopped",
        "btn_start": "Start",
        "btn_stop": "Stop",
        "btn_pause": "Pause View",
        "btn_resume": "Resume View",
        "tip_pause": "Freeze the on-screen view; logs keep being received and journaled",
        "btn_export": "Export Logs",
        "btn_clear": "Clear",
        "btn_prev_error": "Prev Error",
        "btn_next_error": "Next Error",
        "tip_prev_error": "Jump to the previous error line (Shift+F3)",
        "tip_next_error": "Jump to the next error line (F3)",
        "settings": "Receiver Settings",
        "lbl_udp_host": "UDP Host",
        "lbl_udp_port": "UDP Port",
        "btn_refresh_ip": "Refresh IP",
        "hint_receiver": "Keep UDP Host = 0.0.0.0 for receiving. Device Target is the copy-friendly value for the device-side log setting.",
        "net_local": "Local IPv4: {ips}",
        "net_none": "not detected",
        "net_detected": "Detected PC target: {target}",
        "lbl_device_target": "Device Target",
        "btn_use_detected": "Use Detected IP",
        "btn_use_default": "Use Project Default",
        "btn_copy_target": "Copy Target",
        "ph_filter": "Filter text, source, IMEI, feature, or source file",
        "level_all": "All Levels",
        "level_E": "E · error",
        "level_W": "W · warning",
        "level_I": "I · info",
        "level_D": "D · debug",
        "level_V": "V · verbose",
        "ph_feature": "Feature",
        "devices_all": "All Devices",
        "chk_show_source": "Show Source",
        "chk_auto_scroll": "Auto Scroll",
        "stats": "Shown {shown} / Buffered {buffered}",
        "stats_gaps": "Gaps",
        "sb_latest_source": "Latest source: {source}",
        "sb_session": "Session file: {path}",
        "msg_invalid_port_title": "Invalid Port",
        "msg_invalid_port": "UDP port is invalid: {port}",
        "msg_start_failed_title": "Start Failed",
        "msg_use_failed_title": "Use Failed",
        "msg_use_failed": "No valid detected IP target is available yet.",
        "msg_copy_failed_title": "Copy Failed",
        "msg_copy_failed": "Device target is empty.",
        "msg_copied_title": "Copied",
        "msg_copied": "Copied device target:\n{value}",
        "msg_export_failed_title": "Save Failed",
        "msg_exported_title": "Exported",
        "msg_exported": "Logs exported to:\n{path}",
        "export_dialog_title": "Export Logs",
        "no_errors_below": "No error lines below the cursor",
        "no_errors_above": "No error lines above the cursor",
    },
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
        self.language = DEFAULT_LANGUAGE
        self.error_count = 0
        self.warning_count = 0
        self.gap_count = 0
        self.shown_count = 0
        self.status_kind = "idle"
        self.listen_url = ""
        self.latest_source = "-"
        self.journal = UdpLogJournal("udp_gui_session")
        self.jsonl_journal = UdpLogJournal("udp_gui_session", suffix=".jsonl")
        self.sequence_tracker = UdpLogSequenceTracker()

        self.resize(1180, 780)
        self.setMinimumSize(980, 640)

        self._build_ui()
        self._load_config()
        if initial_udp_host:
            self.udp_host_edit.setText(initial_udp_host)
        if initial_udp_port is not None:
            self.udp_port_edit.setText(str(initial_udp_port))

        self._connect_signals()
        self._apply_texts()
        self.refresh_network_info()

        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(100)
        self.queue_timer.timeout.connect(self._drain_queue)
        self.queue_timer.start()

        if auto_start:
            self.toggle_receiver()

    def tr_text(self, key: str, **kwargs) -> str:
        catalog = TEXTS.get(self.language, TEXTS[DEFAULT_LANGUAGE])
        template = catalog.get(key) or TEXTS[DEFAULT_LANGUAGE].get(key, key)
        return template.format(**kwargs) if kwargs else template

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # One dominant blue-gray hue family; strong color is reserved for the
        # status pill, the primary action, and log levels.
        self.setStyleSheet(
            """
            QMainWindow { background: #0e1320; }
            QLabel { color: #e2e9f8; font-size: 13px; }
            QFrame#card { background: #151b2c; border: 1px solid #222b40; border-radius: 10px; }
            QLineEdit {
                background: #0d1424;
                border: 1px solid #2a3245;
                border-radius: 6px;
                color: #e2e9f8;
                padding: 6px 9px;
                selection-background-color: #3a6ea5;
            }
            QLineEdit:focus { border: 1px solid #57a8e8; }
            QComboBox {
                background: #0d1424;
                border: 1px solid #2a3245;
                border-radius: 6px;
                color: #e2e9f8;
                padding: 5px 9px;
            }
            QComboBox:focus { border: 1px solid #57a8e8; }
            QComboBox QAbstractItemView {
                background: #151b2c;
                color: #e2e9f8;
                selection-background-color: #3a6ea5;
            }
            QPushButton {
                background: #1d2537;
                border: 1px solid #2e3850;
                border-radius: 6px;
                color: #c9d6f2;
                padding: 7px 14px;
            }
            QPushButton:hover { background: #263149; }
            QPushButton:pressed { background: #161d2c; }
            QPushButton#primary {
                background: #2f5fa8;
                border: 1px solid #4179cc;
                color: #f0f6ff;
                font-weight: 600;
            }
            QPushButton#primary:hover { background: #386fc0; }
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
                color: #8b9bc0;
                font-weight: 600;
                padding: 4px;
            }
            QToolButton:hover { color: #c9d6f2; }
            QCheckBox { color: #c9d6f2; spacing: 6px; font-size: 13px; }
            QPlainTextEdit {
                background: #0a0f1b;
                border: 1px solid #222b40;
                border-radius: 10px;
                color: #dbe6ff;
                padding: 10px;
                selection-background-color: #3a6ea5;
                font-family: Consolas, "Courier New", monospace;
                font-size: 10.5pt;
            }
            QStatusBar { color: #8b9bc0; font-size: 12px; }
            QStatusBar QLabel { color: #8b9bc0; font-size: 12px; }
            """
        )

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 6)
        root.setSpacing(8)
        self.setCentralWidget(central)

        # -- Header: title + status pill + stats + language ----------------
        header = QHBoxLayout()
        header.setSpacing(12)
        root.addLayout(header)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(self.title_label)

        self.status_label = QLabel()
        header.addWidget(self.status_label)
        header.addStretch(1)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #8b9bc0; font-size: 12px;")
        header.addWidget(self.stats_label)

        self.language_combo = QComboBox()
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.setFixedWidth(96)
        header.addWidget(self.language_combo)

        # -- Action toolbar ----------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(8)
        root.addLayout(actions)

        self.start_stop_button = QPushButton()
        self.start_stop_button.setObjectName("primary")
        self.start_stop_button.setMinimumWidth(112)
        actions.addWidget(self.start_stop_button)

        self.pause_button = QPushButton()
        self.pause_button.setObjectName("pause")
        self.pause_button.setCheckable(True)
        actions.addWidget(self.pause_button)

        self.save_button = QPushButton()
        self.clear_button = QPushButton()
        self.prev_error_button = QPushButton()
        self.next_error_button = QPushButton()
        actions.addWidget(self.save_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.prev_error_button)
        actions.addWidget(self.next_error_button)
        actions.addStretch(1)

        self.settings_toggle = QToolButton()
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

        self.udp_host_label = QLabel()
        grid.addWidget(self.udp_host_label, 0, 0)
        self.udp_host_edit = QLineEdit("0.0.0.0")
        self.udp_host_edit.setMinimumWidth(150)
        grid.addWidget(self.udp_host_edit, 1, 0)

        self.udp_port_label = QLabel()
        grid.addWidget(self.udp_port_label, 0, 1)
        self.udp_port_edit = QLineEdit("8001")
        self.udp_port_edit.setValidator(QIntValidator(1, 65535, self))
        self.udp_port_edit.setMaximumWidth(110)
        grid.addWidget(self.udp_port_edit, 1, 1)

        self.refresh_button = QPushButton()
        grid.addWidget(self.refresh_button, 1, 2)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #8b9bc0; font-size: 12px;")
        self.hint_label.setWordWrap(True)
        grid.addWidget(self.hint_label, 2, 0, 1, 6)

        self.network_info_label = QLabel()
        self.network_info_label.setStyleSheet("color: #8b9bc0; font-size: 12px;")
        grid.addWidget(self.network_info_label, 3, 0, 1, 6)

        self.device_target_label = QLabel()
        grid.addWidget(self.device_target_label, 4, 0)
        self.device_target_edit = QLineEdit(PROJECT_DEFAULT_DEVICE_TARGET)
        self.device_target_edit.setMinimumWidth(240)
        grid.addWidget(self.device_target_edit, 5, 0, 1, 2)

        self.use_detected_button = QPushButton()
        self.use_default_button = QPushButton()
        self.copy_target_button = QPushButton()
        grid.addWidget(self.use_detected_button, 5, 2)
        grid.addWidget(self.use_default_button, 5, 3)
        grid.addWidget(self.copy_target_button, 5, 4)

        for column in range(6):
            grid.setColumnStretch(column, 1 if column == 5 else 0)

        # -- Filter toolbar ------------------------------------------------
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        root.addLayout(toolbar)

        self.filter_edit = QLineEdit()
        self.filter_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar.addWidget(self.filter_edit)

        self.level_combo = QComboBox()
        self.level_combo.setMinimumWidth(120)
        toolbar.addWidget(self.level_combo)

        self.feature_edit = QLineEdit()
        self.feature_edit.setMinimumWidth(130)
        toolbar.addWidget(self.feature_edit)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        toolbar.addWidget(self.device_combo)

        self.show_source_check = QCheckBox()
        self.show_source_check.setChecked(True)
        toolbar.addWidget(self.show_source_check)

        self.auto_scroll_check = QCheckBox()
        self.auto_scroll_check.setChecked(True)
        toolbar.addWidget(self.auto_scroll_check)

        # -- Log view -------------------------------------------------------
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_DISPLAY_LOG_LINES)
        root.addWidget(self.text, 1)

        # -- Status bar -----------------------------------------------------
        self.source_label = QLabel()
        self.statusBar().addWidget(self.source_label)
        self.session_label = QLabel()
        self.statusBar().addPermanentWidget(self.session_label)

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
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
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
    # Language
    # ------------------------------------------------------------------
    def _on_language_changed(self) -> None:
        language = str(self.language_combo.currentData() or DEFAULT_LANGUAGE)
        if language == self.language:
            return
        self.language = language
        self._apply_texts()
        self._save_config()

    def _apply_texts(self) -> None:
        self.setWindowTitle(self.tr_text("app_title"))
        self.title_label.setText(self.tr_text("app_title"))
        self.pause_button.setToolTip(self.tr_text("tip_pause"))
        self.pause_button.setText(
            self.tr_text("btn_resume") if self.paused else self.tr_text("btn_pause")
        )
        self.start_stop_button.setText(
            self.tr_text("btn_stop") if self.running else self.tr_text("btn_start")
        )
        self.save_button.setText(self.tr_text("btn_export"))
        self.clear_button.setText(self.tr_text("btn_clear"))
        self.prev_error_button.setText(self.tr_text("btn_prev_error"))
        self.prev_error_button.setToolTip(self.tr_text("tip_prev_error"))
        self.next_error_button.setText(self.tr_text("btn_next_error"))
        self.next_error_button.setToolTip(self.tr_text("tip_next_error"))
        self.settings_toggle.setText(self.tr_text("settings"))
        self.udp_host_label.setText(self.tr_text("lbl_udp_host"))
        self.udp_port_label.setText(self.tr_text("lbl_udp_port"))
        self.refresh_button.setText(self.tr_text("btn_refresh_ip"))
        self.hint_label.setText(self.tr_text("hint_receiver"))
        self.device_target_label.setText(self.tr_text("lbl_device_target"))
        self.use_detected_button.setText(self.tr_text("btn_use_detected"))
        self.use_default_button.setText(self.tr_text("btn_use_default"))
        self.copy_target_button.setText(self.tr_text("btn_copy_target"))
        self.filter_edit.setPlaceholderText(self.tr_text("ph_filter"))
        self.feature_edit.setPlaceholderText(self.tr_text("ph_feature"))
        self.show_source_check.setText(self.tr_text("chk_show_source"))
        self.auto_scroll_check.setText(self.tr_text("chk_auto_scroll"))

        self._rebuild_level_combo()
        self._refresh_device_combo()
        self._render_status()
        self._update_stats()
        self._update_status_bar()
        self._update_network_label()

    def _rebuild_level_combo(self) -> None:
        current = str(self.level_combo.currentData() or "")
        self.level_combo.blockSignals(True)
        self.level_combo.clear()
        self.level_combo.addItem(self.tr_text("level_all"), "")
        for level in ("E", "W", "I", "D", "V"):
            self.level_combo.addItem(self.tr_text(f"level_{level}"), level)
        index = self.level_combo.findData(current)
        self.level_combo.setCurrentIndex(index if index >= 0 else 0)
        self.level_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        payload = {}
        if self.config_path.exists():
            try:
                payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}

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
        language = str(payload.get("language", DEFAULT_LANGUAGE))
        self.language = language if language in TEXTS else DEFAULT_LANGUAGE
        index = self.language_combo.findData(self.language)
        if index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)

    def _save_config(self) -> None:
        payload = {
            "udp_host": self.udp_host_edit.text().strip(),
            "udp_port": self.udp_port_edit.text().strip(),
            "device_target": self.device_target_edit.text().strip(),
            "auto_scroll": self.auto_scroll_check.isChecked(),
            "show_source": self.show_source_check.isChecked(),
            "language": self.language,
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
            QMessageBox.critical(
                self,
                self.tr_text("msg_invalid_port_title"),
                self.tr_text("msg_invalid_port", port=port_text),
            )
            return

        try:
            self.receiver = UdpReceiver(host, port, self.line_queue)
            self.receiver.start()
        except RuntimeError as exc:
            self.receiver = None
            QMessageBox.critical(self, self.tr_text("msg_start_failed_title"), str(exc))
            return

        self.running = True
        self.listen_url = f"{host}:{port}"
        self._set_status("listening")
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
            self._set_status("stopped")
            self.settings_toggle.setChecked(True)

    def _set_start_button_running(self, running: bool) -> None:
        self.start_stop_button.setText(
            self.tr_text("btn_stop") if running else self.tr_text("btn_start")
        )
        self.start_stop_button.setProperty("running", "true" if running else "false")
        style = self.start_stop_button.style()
        style.unpolish(self.start_stop_button)
        style.polish(self.start_stop_button)

    def _on_pause_toggled(self, paused: bool) -> None:
        self.paused = paused
        self.pause_button.setText(
            self.tr_text("btn_resume") if paused else self.tr_text("btn_pause")
        )
        if paused:
            if self.running:
                self._set_status("paused")
        else:
            self.render()
            if self.running:
                self._set_status("listening")

    def _on_settings_toggled(self, expanded: bool) -> None:
        self.settings_card.setVisible(expanded)
        self.settings_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _set_status(self, kind: str) -> None:
        self.status_kind = kind
        self._render_status()

    def _render_status(self) -> None:
        if self.status_kind == "listening":
            message = self.tr_text("status_listening", url=self.listen_url)
        elif self.status_kind == "paused":
            message = self.tr_text("status_paused")
        elif self.status_kind == "stopped":
            message = self.tr_text("status_stopped")
        else:
            message = self.tr_text("status_idle")
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"{STATUS_STYLES.get(self.status_kind, STATUS_STYLES['idle'])} "
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
            self.tr_text("export_dialog_title"),
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
            QMessageBox.critical(self, self.tr_text("msg_export_failed_title"), str(exc))
            return
        QMessageBox.information(
            self,
            self.tr_text("msg_exported_title"),
            self.tr_text("msg_exported", path=output_path),
        )

    def refresh_network_info(self) -> None:
        preferred_ip, ips = detect_local_ipv4s()
        self.detected_ips = ips
        port_text = self.udp_port_edit.text().strip()
        try:
            port = int(port_text)
        except ValueError:
            port = None

        if preferred_ip and port is not None:
            self.detected_target_value = f"{preferred_ip}:{port}"
        else:
            self.detected_target_value = ""
        self._update_network_label()

    def _update_network_label(self) -> None:
        ips = getattr(self, "detected_ips", [])
        parts = [
            self.tr_text("net_local", ips=", ".join(ips) if ips else self.tr_text("net_none"))
        ]
        if self.detected_target_value:
            parts.append(self.tr_text("net_detected", target=self.detected_target_value))
        self.network_info_label.setText("    ".join(parts))

    def use_detected_target(self) -> None:
        if not self.detected_target_value:
            QMessageBox.warning(
                self, self.tr_text("msg_use_failed_title"), self.tr_text("msg_use_failed")
            )
            return
        self.device_target_edit.setText(self.detected_target_value)
        self._save_config()

    def use_project_default_target(self) -> None:
        self.device_target_edit.setText(PROJECT_DEFAULT_DEVICE_TARGET)
        self._save_config()

    def copy_device_target(self) -> None:
        value = self.device_target_edit.text().strip()
        if not value:
            QMessageBox.warning(
                self, self.tr_text("msg_copy_failed_title"), self.tr_text("msg_copy_failed")
            )
            return
        self._save_config()
        QApplication.clipboard().setText(value)
        QMessageBox.information(
            self, self.tr_text("msg_copied_title"), self.tr_text("msg_copied", value=value)
        )

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
            self.latest_source = source

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
        self._update_status_bar()

    def _refresh_device_combo(self) -> None:
        current_imei = self.device_combo.currentData() or ""
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem(self.tr_text("devices_all"), "")
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
        key = "no_errors_below" if forward else "no_errors_above"
        self.statusBar().showMessage(self.tr_text(key), 3000)

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
        summary = self.tr_text("stats", shown=self.shown_count, buffered=len(self.records))
        self.stats_label.setText(
            f"{summary}"
            f'    <span style="color: {LEVEL_COLORS["E"]};">E {self.error_count}</span>'
            f'    <span style="color: {LEVEL_COLORS["W"]};">W {self.warning_count}</span>'
            f'    <span style="color: {GAP_COLOR};">{self.tr_text("stats_gaps")} {self.gap_count}</span>'
        )

    def _update_status_bar(self) -> None:
        self.source_label.setText(self.tr_text("sb_latest_source", source=self.latest_source))
        self.session_label.setText(self.tr_text("sb_session", path=self.journal.path))

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
