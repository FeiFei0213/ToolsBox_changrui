"""
widget.py — VGS 日志查看工具

- 后台线程解析，默认跳过 DEBUG（应对 81MB 大文件）
- 级别过滤、关键词搜索（实时）
- 行颜色按级别区分，详情面板显示完整字段
- 自动刷新 vgs.log（追加模式，不全量重载）
- Ctrl+E 快速切换"仅看错误"模式
"""

import json
import os
import re
import time
import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QCheckBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QListWidget, QListWidgetItem,
    QPlainTextEdit, QStatusBar, QFrame, QAbstractItemView,
    QMenu, QMessageBox,
)

from tool_base import ToolBase
from tools.vgs_context import get_vgs_logs_dir, resolve_vgs_relative_path, set_vgs_logs_dir

logger = logging.getLogger(__name__)

_TOOLBOX_DIR       = Path.home() / ".toolbox"
_LOG_VIEWER_SETTINGS = _TOOLBOX_DIR / "log_viewer_settings.json"


def _load_log_dir() -> Path:
    detected = get_vgs_logs_dir(auto_detect=True)
    if detected:
        return detected

    try:
        data = json.loads(_LOG_VIEWER_SETTINGS.read_text(encoding="utf-8"))
        p = Path(data.get("log_dir", ""))
        if p.exists():
            return p
    except Exception:
        pass
    return Path.home()


def _save_log_dir(path: Path) -> None:
    set_vgs_logs_dir(path)
    try:
        _TOOLBOX_DIR.mkdir(parents=True, exist_ok=True)
        _LOG_VIEWER_SETTINGS.write_text(
            json.dumps({"log_dir": str(path)}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"save log_viewer settings: {e}")

_RE_WORKDIR = re.compile(r"'workdir':\s*'([^']+)'")

_LEVEL_BG: dict[str, QColor] = {
    "DEBUG":    QColor("#F5F5F5"),
    "WARNING":  QColor("#FFF8E1"),
    "ERROR":    QColor("#FFEBEE"),
    "CRITICAL": QColor("#B71C1C"),
}
_LEVEL_FG: dict[str, QColor] = {
    "DEBUG":    QColor("#999999"),
    "WARNING":  QColor("#E65100"),
    "ERROR":    QColor("#C62828"),
    "CRITICAL": QColor("#FFFFFF"),
}

_RE_NEW = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) '
    r'\[(\w+)\] ([\w\.]+) (\S+:\d+) \[([^\]]+)\] - (.*)$'
)
_RE_OLD = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] ([\w\.]+) - (.*)$'
)


@dataclass
class LogEntry:
    line_no: int
    dt: str
    level: str
    module: str
    source: str
    thread: str
    message: str
    raw: str
    count: int = 1  # 连续重复次数


def _parse_line(line: str, line_no: int) -> "LogEntry | None":
    m = _RE_NEW.match(line)
    if m:
        dt, level, module, source, thread, message = m.groups()
        return LogEntry(line_no, dt, level, module, source, thread, message, line)
    m = _RE_OLD.match(line)
    if m:
        dt, level, module, message = m.groups()
        return LogEntry(line_no, dt, level, module, "", "", message, line)
    return None


# ─────────────────────────────────────────────────────────────────
# 后台加载线程
# ─────────────────────────────────────────────────────────────────

class LogLoader(QThread):
    chunk_ready = Signal(list)        # list[LogEntry]，每 500 条 emit 一次
    finished    = Signal(int, float)  # (total_lines_read, elapsed_sec)

    def __init__(self, path: Path, levels: set, parent=None):
        super().__init__(parent)
        self._path   = path
        self._levels = levels
        self._stop   = False

    def stop(self):
        self._stop = True

    def run(self):
        t0    = time.monotonic()
        chunk: list = []
        total = 0
        last_entry: "LogEntry | None" = None
        last_key: tuple | None        = None

        def _flush(entry: "LogEntry"):
            chunk.append(entry)
            if len(chunk) >= 500:
                self.chunk_ready.emit(chunk[:])
                chunk.clear()

        try:
            with open(self._path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    if self._stop:
                        break
                    total += 1
                    entry = _parse_line(raw.rstrip("\n\r"), total)
                    if entry is None or entry.level not in self._levels:
                        continue

                    key = (entry.level, entry.module, entry.message)
                    if key == last_key and last_entry is not None:
                        last_entry.count += 1
                    else:
                        if last_entry is not None:
                            _flush(last_entry)
                        last_entry = entry
                        last_key   = key

        except Exception as e:
            logger.error(f"LogLoader: {e}")

        if last_entry is not None:
            _flush(last_entry)
        if chunk:
            self.chunk_ready.emit(chunk)
        self.finished.emit(total, time.monotonic() - t0)


# ─────────────────────────────────────────────────────────────────
# 主 Widget
# ─────────────────────────────────────────────────────────────────

class LogViewerWidget(ToolBase):
    tool_name        = "日志查看器"
    tool_description = "查看 VGS 运行日志，支持级别过滤和关键词搜索"
    tool_icon        = "📋"

    def init_ui(self):
        self.resize(1400, 820)

        self._entries: list[LogEntry]   = []
        self._current_file: Path | None = None
        self._last_size: int            = 0
        self._loader: LogLoader | None  = None
        self._error_mode_saved: dict | None = None  # Ctrl+E 保存的级别状态

        # 加载保存的日志目录，不存在则提示用户选择
        self._log_dir: Path = _load_log_dir()
        if not self._log_dir.exists():
            self._log_dir = self._ask_log_dir() or self._log_dir

        self._auto_timer = QTimer()
        self._auto_timer.setInterval(3000)
        self._auto_timer.timeout.connect(self._check_auto_refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        # ── 主区：左侧文件列表 + 右侧内容 ────────────────────────
        main_sp = QSplitter(Qt.Orientation.Horizontal)
        main_sp.setHandleWidth(1)

        self._file_list = QListWidget()
        self._file_list.setMaximumWidth(210)
        self._file_list.setMinimumWidth(140)
        self._file_list.setStyleSheet(
            "QListWidget { font-size:12px; border:none; border-right:1px solid #ccc; }"
        )
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        main_sp.addWidget(self._file_list)

        # 右侧：上方表格 + 下方详情
        right_sp = QSplitter(Qt.Orientation.Vertical)
        right_sp.setHandleWidth(3)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["时间", "级别", "模块", "消息"])
        hh = self._table.horizontalHeader()
        for col, mode in enumerate([
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Stretch,
        ]):
            hh.setSectionResizeMode(col, mode)
        self._table.setColumnWidth(0, 152)
        self._table.setColumnWidth(1, 72)
        self._table.setColumnWidth(2, 220)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.setFont(QFont("Consolas", 9))
        self._table.currentItemChanged.connect(
            lambda curr, _prev: self._on_row_selected(curr.row() if curr else -1)
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        right_sp.addWidget(self._table)

        # 详情区：find bar + 只读文本框
        detail_area = QWidget()
        da_lay = QVBoxLayout(detail_area)
        da_lay.setContentsMargins(0, 0, 0, 0)
        da_lay.setSpacing(0)

        self._find_bar = QWidget()
        self._find_bar.setStyleSheet(
            "QWidget { background:#FFFDE7; border-top:1px solid #FBC02D; }"
            "QPushButton { padding:1px 6px; }"
        )
        fb = QHBoxLayout(self._find_bar)
        fb.setContentsMargins(6, 2, 6, 2)
        fb.setSpacing(4)
        fb.addWidget(QLabel("查找:"))
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("在详情中查找…")
        self._find_input.setFixedWidth(220)
        self._find_prev_btn = QPushButton("↑")
        self._find_next_btn = QPushButton("↓")
        self._find_close_btn = QPushButton("✕")
        for b in (self._find_prev_btn, self._find_next_btn, self._find_close_btn):
            b.setFixedWidth(26)
        fb.addWidget(self._find_input)
        fb.addWidget(self._find_prev_btn)
        fb.addWidget(self._find_next_btn)
        fb.addStretch()
        fb.addWidget(self._find_close_btn)
        self._find_bar.setVisible(False)
        da_lay.addWidget(self._find_bar)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFont(QFont("Consolas", 9))
        self._detail.setMaximumHeight(160)
        self._detail.setMinimumHeight(80)
        self._detail.setPlaceholderText("点击日志行查看详情…")
        da_lay.addWidget(self._detail, 1)

        right_sp.addWidget(detail_area)
        right_sp.setSizes([640, 140])

        main_sp.addWidget(right_sp)
        main_sp.setSizes([175, 1100])
        main_sp.setStretchFactor(0, 0)
        main_sp.setStretchFactor(1, 1)
        root.addWidget(main_sp, 1)

        # ── 状态栏 ────────────────────────────────────────────────
        self._statusbar = QStatusBar()
        self._statusbar.setStyleSheet("font-size:12px;")
        root.addWidget(self._statusbar)
        self._statusbar.showMessage("就绪")

        # ── 信号连接 ──────────────────────────────────────────────
        self._search_edit.textChanged.connect(self._apply_filter)
        self._clear_btn.clicked.connect(lambda: self._search_edit.clear())
        self._time_from.textChanged.connect(self._apply_filter)
        self._time_to.textChanged.connect(self._apply_filter)
        self._find_input.textChanged.connect(self._find_in_detail)
        self._find_input.returnPressed.connect(self._find_next_in_detail)
        self._find_next_btn.clicked.connect(self._find_next_in_detail)
        self._find_prev_btn.clicked.connect(self._find_prev_in_detail)
        self._find_close_btn.clicked.connect(lambda: self._find_bar.setVisible(False))

        # ── 快捷键 ────────────────────────────────────────────────
        QShortcut(QKeySequence("Ctrl+R"), self, self._reload)
        QShortcut(QKeySequence("Ctrl+F"), self, self._show_find_bar)
        QShortcut(QKeySequence("Ctrl+E"), self, self._toggle_error_mode)

        self._populate_file_list()

    # ── 工具栏 ────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet(
            "QWidget { background:#f0f0f0; border-bottom:1px solid #ccc; }"
            "QPushButton { padding:3px 10px; }"
            "QPushButton:checked { background:#1976D2; color:white; border-radius:4px; }"
        )
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setToolTip("Ctrl+R")
        refresh_btn.clicked.connect(self._reload)
        lay.addWidget(refresh_btn)

        self._auto_btn = QPushButton("自动刷新")
        self._auto_btn.setCheckable(True)
        self._auto_btn.setToolTip("每 3 秒检查当前日志是否有新内容（仅当前日志可用）")
        self._auto_btn.toggled.connect(self._toggle_auto_refresh)
        lay.addWidget(self._auto_btn)

        lay.addWidget(self._vline())
        lay.addWidget(QLabel("级别:"))

        self._level_checks: dict[str, QCheckBox] = {}
        for lv, checked in [("DEBUG", False), ("INFO", True), ("WARNING", True), ("ERROR", True)]:
            cb = QCheckBox(lv)
            cb.setChecked(checked)
            cb.toggled.connect(lambda _chk, level=lv: self._on_level_toggled(level))
            self._level_checks[lv] = cb
            lay.addWidget(cb)

        lay.addWidget(self._vline())
        lay.addWidget(QLabel("🔍"))

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("关键词过滤 (Ctrl+F)")
        self._search_edit.setFixedWidth(230)
        self._search_edit.setClearButtonEnabled(True)
        lay.addWidget(self._search_edit)

        self._clear_btn = QPushButton("✕")
        self._clear_btn.setFixedWidth(28)
        self._clear_btn.setToolTip("清空关键词")
        lay.addWidget(self._clear_btn)

        lay.addWidget(self._vline())

        self._error_btn = QPushButton("仅看错误")
        self._error_btn.setCheckable(True)
        self._error_btn.setToolTip("Ctrl+E — 仅显示 WARNING/ERROR，再按恢复")
        self._error_btn.toggled.connect(self._set_error_mode)
        lay.addWidget(self._error_btn)

        lay.addWidget(self._vline())
        lay.addWidget(QLabel("时间:"))

        self._time_from = QLineEdit()
        self._time_from.setPlaceholderText("HH:MM:SS")
        self._time_from.setFixedWidth(72)
        self._time_from.setToolTip("起始时间（含）")
        lay.addWidget(self._time_from)

        lay.addWidget(QLabel("~"))

        self._time_to = QLineEdit()
        self._time_to.setPlaceholderText("HH:MM:SS")
        self._time_to.setFixedWidth(72)
        self._time_to.setToolTip("结束时间（含）")
        lay.addWidget(self._time_to)

        time_clear_btn = QPushButton("清")
        time_clear_btn.setFixedWidth(30)
        time_clear_btn.setToolTip("清空时间段")
        time_clear_btn.clicked.connect(lambda: (self._time_from.clear(), self._time_to.clear()))
        lay.addWidget(time_clear_btn)

        lay.addWidget(self._vline())

        change_dir_btn = QPushButton("切换目录")
        change_dir_btn.setToolTip("选择日志目录")
        change_dir_btn.clicked.connect(self._change_log_dir)
        lay.addWidget(change_dir_btn)

        lay.addStretch()
        return tb

    @staticmethod
    def _vline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # ── 文件列表 ──────────────────────────────────────────────────

    def _ask_log_dir(self) -> Path | None:
        from PySide6.QtWidgets import QFileDialog
        start = str(self._log_dir) if self._log_dir.exists() else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "选择 VGS 日志目录", start)
        if chosen:
            p = Path(chosen)
            _save_log_dir(p)
            return p
        return None

    def _change_log_dir(self):
        p = self._ask_log_dir()
        if p:
            self._log_dir = p
            self._populate_file_list()

    def _populate_file_list(self):
        self._file_list.clear()
        if not self._log_dir.exists():
            self._statusbar.showMessage(f"日志目录不存在: {self._log_dir}，请点击 [切换目录]")
            return
        files = sorted(
            self._log_dir.glob("vgs.log*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files:
            label = "📄 当前日志" if p.name == "vgs.log" else p.name.replace("vgs.log.", "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, p)
            size_kb = p.stat().st_size / 1024
            size_str = f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"
            item.setToolTip(f"{p}\n{size_str}")
            self._file_list.addItem(item)
        if self._file_list.count() > 0:
            self._file_list.setCurrentRow(0)

    def _on_file_selected(self, current: QListWidgetItem, _prev):
        if current is None:
            return
        self._load_file(current.data(Qt.ItemDataRole.UserRole))

    # ── 加载 ──────────────────────────────────────────────────────

    def _checked_levels(self) -> set:
        return {lv for lv, cb in self._level_checks.items() if cb.isChecked()}

    def _on_level_toggled(self, _level: str):
        if self._current_file:
            self._load_file(self._current_file)

    def _load_file(self, path: Path):
        if not path or not path.exists():
            return
        if self._loader and self._loader.isRunning():
            self._loader.stop()
            self._loader.wait(400)

        self._entries.clear()
        self._table.setRowCount(0)
        self._detail.clear()
        self._current_file = path
        self._last_size = path.stat().st_size

        is_current = (path.name == "vgs.log")
        self._auto_btn.setEnabled(is_current)
        if not is_current:
            self._auto_timer.stop()
            self._auto_btn.blockSignals(True)
            self._auto_btn.setChecked(False)
            self._auto_btn.blockSignals(False)

        levels  = self._checked_levels()
        size_mb = path.stat().st_size / 1024 / 1024
        self._statusbar.showMessage(f"加载中: {path.name}  {size_mb:.1f} MB …")

        self._loader = LogLoader(path, levels)
        self._loader.chunk_ready.connect(self._on_chunk)
        self._loader.finished.connect(self._on_load_finished)
        self._loader.start()

    def _on_chunk(self, chunk: list):
        kw = self._search_edit.text().strip().lower()
        self._entries.extend(chunk)
        self._table.setUpdatesEnabled(False)
        for entry in chunk:
            if not kw or kw in entry.message.lower() or kw in entry.module.lower():
                self._append_row(entry)
        self._table.setUpdatesEnabled(True)
        if self._table.rowCount() > 0:
            self._table.scrollToBottom()

    def _on_load_finished(self, total_lines: int, elapsed: float):
        n_shown   = self._table.rowCount()
        n_stored  = len(self._entries)
        size_mb   = self._current_file.stat().st_size / 1024 / 1024 if self._current_file else 0
        self._statusbar.showMessage(
            f"显示 {n_shown:,}  /  存储 {n_stored:,} 条  │  "
            f"原始 {total_lines:,} 行  │  {size_mb:.1f} MB  │  耗时 {elapsed:.1f}s"
        )

    # ── 表格 ──────────────────────────────────────────────────────

    def _append_row(self, entry: LogEntry):
        row = self._table.rowCount()
        self._table.insertRow(row)
        bg  = _LEVEL_BG.get(entry.level)
        fg  = _LEVEL_FG.get(entry.level)
        msg = entry.message if entry.count == 1 else f"{entry.message}  ×{entry.count}"
        for col, text in enumerate([entry.dt, entry.level, entry.module, msg]):
            item = QTableWidgetItem(text)
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, entry)
            if bg:
                item.setBackground(bg)
            if fg:
                item.setForeground(fg)
            self._table.setItem(row, col, item)

    def _apply_filter(self):
        kw        = self._search_edit.text().strip().lower()
        t_from    = self._time_from.text().strip()
        t_to      = self._time_to.text().strip()
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        for entry in self._entries:
            if kw and kw not in entry.message.lower() and kw not in entry.module.lower():
                continue
            et = entry.dt[11:]  # "HH:MM:SS"
            if t_from and et < t_from:
                continue
            if t_to and et > t_to:
                continue
            self._append_row(entry)
        self._table.setUpdatesEnabled(True)
        n = self._table.rowCount()
        extras = []
        if kw:
            extras.append(f"关键词: {kw}")
        if t_from or t_to:
            extras.append(f"时间: {t_from or '00:00:00'} ~ {t_to or '23:59:59'}")
        self._statusbar.showMessage(
            f"显示 {n:,} / {len(self._entries):,} 条"
            + (f"  │  {',  '.join(extras)}" if extras else "")
        )

    def _on_row_selected(self, row: int):
        if row < 0:
            return
        item = self._table.item(row, 0)
        if not item:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, LogEntry):
            return
        self._detail.setPlainText(
            f"原始:   {entry.raw}\n\n"
            f"时间:   {entry.dt}\n"
            f"级别:   {entry.level}\n"
            f"模块:   {entry.module}\n"
            f"来源:   {entry.source or '—'}\n"
            f"线程:   {entry.thread or '—'}\n"
            f"消息:   {entry.message}"
        )

    # ── 详情面板查找 ──────────────────────────────────────────────

    def _show_find_bar(self):
        self._find_bar.setVisible(True)
        self._find_input.setFocus()
        self._find_input.selectAll()

    def _find_in_detail(self):
        from PySide6.QtGui import QTextCursor
        text = self._find_input.text()
        if not text:
            cursor = self._detail.textCursor()
            cursor.clearSelection()
            self._detail.setTextCursor(cursor)
            return
        self._detail.moveCursor(QTextCursor.MoveOperation.Start)
        self._detail.find(text)

    def _find_next_in_detail(self):
        text = self._find_input.text()
        if not text:
            return
        found = self._detail.find(text)
        if not found:
            from PySide6.QtGui import QTextCursor
            self._detail.moveCursor(QTextCursor.MoveOperation.Start)
            self._detail.find(text)

    def _find_prev_in_detail(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtGui import QTextDocument
        text = self._find_input.text()
        if not text:
            return
        found = self._detail.find(text, QTextDocument.FindFlag.FindBackward)
        if not found:
            self._detail.moveCursor(QTextCursor.MoveOperation.End)
            self._detail.find(text, QTextDocument.FindFlag.FindBackward)

    # ── 右键菜单 ──────────────────────────────────────────────────

    def _on_table_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._table.item(row, 0)
        if not item:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, LogEntry):
            return
        menu = QMenu(self)
        open_act = menu.addAction("📂 打开输出文件夹")
        if menu.exec(self._table.viewport().mapToGlobal(pos)) == open_act:
            self._open_output_folder(entry)

    def _find_workdir(self, up_to_line_no: int) -> "str | None":
        """从日志文件中向上查找最近一次 folder_creator 输出的 workdir。"""
        if not self._current_file:
            return None
        result = None
        try:
            with open(self._current_file, "r", encoding="utf-8", errors="replace") as f:
                for i, raw in enumerate(f, 1):
                    if i > up_to_line_no:
                        break
                    if "workdir" in raw:
                        m = _RE_WORKDIR.search(raw)
                        if m:
                            result = m.group(1)
        except Exception as e:
            logger.warning(f"find workdir: {e}")
        return result

    def _open_output_folder(self, entry: LogEntry):
        workdir_raw = self._find_workdir(entry.line_no)
        if not workdir_raw:
            QMessageBox.warning(
                self, "未找到路径",
                "未能从日志中找到对应的输出文件夹。\n"
                "该功能依赖 DEBUG 级别的 folder_creator 输出行，\n"
                "请确认日志中存在该步骤的记录。"
            )
            return
        # 规范化：./output\\M7\\D01 → output\M7\D01
        path_str = workdir_raw.replace('\\\\', '\\').replace('/', '\\')
        if path_str.startswith('.\\'):
            path_str = path_str[2:]
        full_path = resolve_vgs_relative_path(path_str)
        if full_path is None:
            QMessageBox.warning(
                self, "未设置 VGS 路径",
                "无法定位 VGS 根目录，请先选择 VGS 日志目录。"
            )
            return
        if not full_path.exists():
            QMessageBox.warning(self, "文件夹不存在", f"路径不存在:\n{full_path}")
            return
        os.startfile(str(full_path))

    # ── 操作 ──────────────────────────────────────────────────────

    def _reload(self):
        if self._current_file:
            self._load_file(self._current_file)

    def _toggle_auto_refresh(self, on: bool):
        if on:
            self._auto_timer.start()
        else:
            self._auto_timer.stop()

    def _check_auto_refresh(self):
        if not self._current_file or not self._current_file.exists():
            return
        new_size = self._current_file.stat().st_size
        if new_size <= self._last_size:
            return
        levels = self._checked_levels()
        kw     = self._search_edit.text().strip().lower()
        try:
            with open(self._current_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._last_size)
                new_entries: list[LogEntry] = []
                tail = self._entries[-1] if self._entries else None
                tail_key = (tail.level, tail.module, tail.message) if tail else None
                for raw in f:
                    entry = _parse_line(raw.rstrip("\n\r"), 0)
                    if not entry or entry.level not in levels:
                        continue
                    key = (entry.level, entry.module, entry.message)
                    if key == tail_key and tail is not None:
                        tail.count += 1
                        # 更新表格最后一行的消息列
                        last_row = self._table.rowCount() - 1
                        if last_row >= 0:
                            item = self._table.item(last_row, 3)
                            if item:
                                item.setText(f"{tail.message}  ×{tail.count}")
                    else:
                        new_entries.append(entry)
                        tail     = entry
                        tail_key = key
            self._last_size = new_size
            if new_entries:
                self._entries.extend(new_entries)
                self._table.setUpdatesEnabled(False)
                for entry in new_entries:
                    if not kw or kw in entry.message.lower() or kw in entry.module.lower():
                        self._append_row(entry)
                self._table.setUpdatesEnabled(True)
                self._table.scrollToBottom()
                self._statusbar.showMessage(
                    f"+{len(new_entries)} 条新日志  │  共 {len(self._entries):,} 条"
                )
        except Exception as e:
            logger.warning(f"auto-refresh: {e}")

    def _toggle_error_mode(self):
        self._error_btn.setChecked(not self._error_btn.isChecked())

    def _set_error_mode(self, on: bool):
        if on:
            self._error_mode_saved = {lv: cb.isChecked() for lv, cb in self._level_checks.items()}
            for lv, cb in self._level_checks.items():
                cb.blockSignals(True)
                cb.setChecked(lv in ("WARNING", "ERROR"))
                cb.blockSignals(False)
        else:
            if self._error_mode_saved:
                for lv, cb in self._level_checks.items():
                    cb.blockSignals(True)
                    cb.setChecked(self._error_mode_saved.get(lv, False))
                    cb.blockSignals(False)
                self._error_mode_saved = None
        if self._current_file:
            self._load_file(self._current_file)
