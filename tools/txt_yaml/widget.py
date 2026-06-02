"""
widget.py — TXT → YAML 转换工具 GUI。

TxtYamlWidget 继承 ToolBase，功能包括：
- 打开 TXT 文件 / 粘贴文本 / 拖拽 TXT 文件到窗口
- 实时预览转换后的 YAML
- 批量转换多个 TXT 文件
- 复制 YAML 到剪贴板 / 另存为文件
- 一键部署到 VGS 配置目录（CollisionDeployPanel）

TXT 格式：每行 x,y，多个轮廓之间用 --- 分隔。
"""
from __future__ import annotations
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from tool_base import ToolBase

# ─────────────────────────────────────────────────────────────────
# Settings helpers
# ─────────────────────────────────────────────────────────────────

_TOOLBOX_DIR    = Path.home() / ".toolbox"
_SETTINGS_FILE  = _TOOLBOX_DIR / "txt_yaml_settings.json"
_LOG_FILE       = _TOOLBOX_DIR / "txt_yaml_replacement_log.json"

# 自动扫描时在各盘符下尝试的相对路径（从最可能到最不可能）
_SCAN_SUBPATHS = [
    "project/code/vgs",
    "projects/code/vgs",
    "code/vgs",
    "dev/vgs",
    "vgs",
    "work/vgs",
    "workspace/vgs",
]


def _auto_detect_vgs_root() -> str | None:
    """扫描各盘符的常见路径，找到含 config/device 目录的 VGS 根目录。"""
    import string
    drives = [f"{d}:" for d in string.ascii_uppercase
              if Path(f"{d}:\\").exists()]
    for drive in drives:
        for sub in _SCAN_SUBPATHS:
            candidate = Path(drive) / sub
            if (candidate / "config" / "device").is_dir():
                return str(candidate)
    return None


def _load_settings() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    try:
        _TOOLBOX_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"save settings: {e}")


def _append_replacement_log(record: dict) -> None:
    try:
        records = json.loads(_LOG_FILE.read_text(encoding="utf-8")) if _LOG_FILE.exists() else []
        records.append(record)
        _LOG_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"write replacement log: {e}")


def _read_replacement_log() -> list:
    try:
        return json.loads(_LOG_FILE.read_text(encoding="utf-8")) if _LOG_FILE.exists() else []
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────
# Collision file scanner
# ─────────────────────────────────────────────────────────────────

def scan_all_molds(vgs_root: str) -> dict:
    """
    扫描所有设备/模具目录，返回：
      { device: { mold_type: { mold_name: Path|None } } }
    Path = collision yaml 路径（文件存在），None = 尚无碰撞文件
    """
    result: dict = {}
    device_root = Path(vgs_root) / "config" / "device"
    if not device_root.exists():
        return result
    for device_dir in sorted(device_root.iterdir()):
        if not device_dir.is_dir():
            continue
        mold_root = device_dir / "mold"
        if not mold_root.exists():
            continue
        for mold_type_dir in sorted(mold_root.iterdir()):
            if not mold_type_dir.is_dir():
                continue
            for mold_name_dir in sorted(mold_type_dir.iterdir()):
                if not mold_name_dir.is_dir():
                    continue
                target = (
                    mold_name_dir
                    / f"{mold_type_dir.name}_collision_{mold_name_dir.name}.yaml"
                )
                d, mt, mn = device_dir.name, mold_type_dir.name, mold_name_dir.name
                result.setdefault(d, {}).setdefault(mt, {})[mn] = (
                    target if target.exists() else None
                )
    return result

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "utf-16")


@dataclass
class ConversionResult:
    source: Path
    target: Path | None
    success: bool
    message: str


def read_text_file(txt_path: str | Path) -> str:
    path = Path(txt_path)
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"无法读取文件编码: {path}") from last_error


def parse_txt_content(content: str) -> list[list[tuple[str, str]]]:
    blocks = [block.strip() for block in content.strip().split("---") if block.strip()]
    if not blocks:
        raise ValueError("未找到有效数据块，请确认文件内容以 --- 分隔。")

    contours: list[list[tuple[str, str]]] = []
    for block_index, block in enumerate(blocks, start=1):
        points: list[tuple[str, str]] = []
        for line_index, raw_line in enumerate(block.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(
                    f"第 {block_index} 个轮廓第 {line_index} 行格式错误，应为 x,y，实际内容: {raw_line}"
                )
            points.append((parts[0], parts[1]))
        if not points:
            raise ValueError(f"第 {block_index} 个轮廓没有有效坐标。")
        contours.append(points)

    return contours


def convert_text(content: str) -> str:
    contours = parse_txt_content(content)
    lines_out: list[str] = []
    for idx, points in enumerate(contours, start=1):
        lines_out.append(f"contour{idx}:")
        for x, y in points:
            lines_out.append(f"  - [{x}, {y}]")
    return "\n".join(lines_out) + "\n"


def convert_file(txt_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(txt_path)
    if source.suffix.lower() != ".txt":
        raise ValueError(f"只支持 .txt 文件: {source}")
    yaml_content = convert_text(read_text_file(source))
    target = Path(output_path) if output_path else source.with_suffix(".yaml")
    target.write_text(yaml_content, encoding="utf-8")
    return target


def batch_convert(paths: Iterable[str | Path]) -> list[ConversionResult]:
    results: list[ConversionResult] = []
    for path in paths:
        source = Path(path)
        try:
            target = convert_file(source)
            results.append(ConversionResult(source, target, True, f"已生成: {target}"))
        except Exception as exc:
            results.append(ConversionResult(source, None, False, str(exc)))
    return results


# ─────────────────────────────────────────────────────────────────
# CollisionDeployPanel
# ─────────────────────────────────────────────────────────────────

class CollisionDeployPanel(QWidget):
    """
    部署面板：三级下拉（设备/款/模具）选目标，一键替换 VGS 配置目录中的
    collision YAML 文件。支持替换单个设备或同款同模具的全部设备。
    """

    def __init__(self, get_yaml_text: Callable[[], str], parent=None):
        super().__init__(parent)
        self._get_yaml_text = get_yaml_text
        self._targets: dict = {}   # device → mold_type → mold_name → Path
        self._build()
        self._load_and_scan()

    # ── UI ────────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        group = QGroupBox("部署到配置文件")
        gl = QVBoxLayout(group)
        gl.setSpacing(8)

        # 行1：VGS 路径
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("VGS 路径:"))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("VGS 根目录（含 config/device 的上级目录）")
        path_row.addWidget(self._path_edit, 1)
        browse_btn = QPushButton("浏览")
        browse_btn.setFixedWidth(52)
        browse_btn.clicked.connect(self._browse_vgs_root)
        path_row.addWidget(browse_btn)
        auto_btn = QPushButton("自动查找")
        auto_btn.setFixedWidth(72)
        auto_btn.setToolTip("自动扫描各盘符的常见路径")
        auto_btn.clicked.connect(self._auto_find)
        path_row.addWidget(auto_btn)
        rescan_btn = QPushButton("重新扫描")
        rescan_btn.clicked.connect(self._load_and_scan)
        path_row.addWidget(rescan_btn)
        gl.addLayout(path_row)

        # 行2：三级下拉
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("设备:"))
        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(80)
        sel_row.addWidget(self._device_combo)
        sel_row.addSpacing(16)
        sel_row.addWidget(QLabel("款:"))
        self._mold_type_combo = QComboBox()
        self._mold_type_combo.setMinimumWidth(70)
        sel_row.addWidget(self._mold_type_combo)
        sel_row.addSpacing(16)
        sel_row.addWidget(QLabel("模具:"))
        self._mold_name_combo = QComboBox()
        self._mold_name_combo.setMinimumWidth(200)
        sel_row.addWidget(self._mold_name_combo)
        sel_row.addStretch()
        gl.addLayout(sel_row)

        # 行3：目标路径预览
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标:"))
        self._target_label = QLabel("—")
        self._target_label.setStyleSheet("color:#555; font-size:11px;")
        self._target_label.setWordWrap(True)
        self._target_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        target_row.addWidget(self._target_label, 1)
        gl.addLayout(target_row)

        # 行4：操作按钮
        btn_row = QHBoxLayout()
        self._deploy_one_btn = QPushButton("替换选中设备")
        self._deploy_one_btn.setStyleSheet(
            "QPushButton { background:#1976D2; color:white; padding:5px 16px;"
            " border-radius:4px; } QPushButton:disabled { background:#aaa; }"
        )
        self._deploy_one_btn.setEnabled(False)
        self._deploy_one_btn.clicked.connect(self._deploy_one)
        btn_row.addWidget(self._deploy_one_btn)

        self._create_btn = QPushButton("新增碰撞区域文件")
        self._create_btn.setStyleSheet(
            "QPushButton { background:#E65100; color:white; padding:5px 16px;"
            " border-radius:4px; } QPushButton:disabled { background:#aaa; }"
        )
        self._create_btn.setEnabled(False)
        self._create_btn.setToolTip("为当前选中的模具新建 collision yaml 文件")
        self._create_btn.clicked.connect(self._create_new_collision)
        btn_row.addWidget(self._create_btn)

        log_btn = QPushButton("查看替换记录")
        log_btn.clicked.connect(self._show_log)
        btn_row.addWidget(log_btn)

        btn_row.addStretch()
        gl.addLayout(btn_row)

        # 行5：状态
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size:11px; color:#555;")
        gl.addWidget(self._status_label)

        outer.addWidget(group)

        # 信号连接
        self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        self._mold_type_combo.currentIndexChanged.connect(self._on_mold_type_changed)
        self._mold_name_combo.currentIndexChanged.connect(self._on_mold_name_changed)

    # ── 扫描 / 初始化 ─────────────────────────────────────────────

    def _load_and_scan(self):
        settings = _load_settings()
        vgs_root = settings.get("vgs_root", "")

        # 已保存的路径不再存在时清空，重新自动检测
        if vgs_root and not Path(vgs_root).is_dir():
            vgs_root = ""

        if not vgs_root:
            detected = _auto_detect_vgs_root()
            if detected:
                vgs_root = detected
                settings["vgs_root"] = vgs_root
                _save_settings(settings)

        self._path_edit.setText(vgs_root)

        self._targets = scan_all_molds(vgs_root)

        total = sum(
            1 for d in self._targets.values()
            for mt in d.values()
            for p in mt.values() if p is not None
        )
        missing = sum(
            1 for d in self._targets.values()
            for mt in d.values()
            for p in mt.values() if p is None
        )

        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        if self._targets:
            for dev in self._targets:
                self._device_combo.addItem(dev, dev)
            tip = f"已扫描 {total} 个碰撞文件"
            if missing:
                tip += f"，{missing} 个模具尚无碰撞文件"
            self._status_label.setText(tip)
        else:
            self._status_label.setText("未找到任何模具目录，请确认 VGS 路径是否正确")
        self._device_combo.blockSignals(False)

        self._on_device_changed()

    def _browse_vgs_root(self):
        start = self._path_edit.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "选择 VGS 项目根目录", start
        )
        if not path:
            return
        self._path_edit.setText(path)
        settings = _load_settings()
        settings["vgs_root"] = path
        _save_settings(settings)
        self._load_and_scan()

    def _auto_find(self):
        self._status_label.setText("正在扫描，请稍候…")
        self.repaint()
        found = _auto_detect_vgs_root()
        if found:
            self._path_edit.setText(found)
            settings = _load_settings()
            settings["vgs_root"] = found
            _save_settings(settings)
            self._load_and_scan()
        else:
            self._status_label.setText("未自动找到 VGS 目录，请点击浏览手动选择")
            QMessageBox.information(
                self, "未找到",
                "自动扫描未找到 VGS 根目录。\n请点击「浏览」手动选择包含 config/device 的项目目录。"
            )

    # ── 级联更新 ──────────────────────────────────────────────────

    def _on_device_changed(self):
        device = self._device_combo.currentData()
        self._mold_type_combo.blockSignals(True)
        self._mold_type_combo.clear()
        if device and device in self._targets:
            for mt in self._targets[device]:
                self._mold_type_combo.addItem(mt, mt)
        self._mold_type_combo.blockSignals(False)
        self._on_mold_type_changed()

    def _on_mold_type_changed(self):
        device = self._device_combo.currentData()
        mold_type = self._mold_type_combo.currentData()
        self._mold_name_combo.blockSignals(True)
        self._mold_name_combo.clear()
        if device and mold_type and device in self._targets:
            molds = self._targets[device].get(mold_type, {})
            for mn, path in molds.items():
                label = mn if path else f"{mn}  （无碰撞文件）"
                self._mold_name_combo.addItem(label, mn)
        self._mold_name_combo.blockSignals(False)
        self._on_mold_name_changed()

    def _on_mold_name_changed(self):
        path = self._current_target_path()
        if path is not None:
            self._target_label.setText(str(path))
        else:
            device    = self._device_combo.currentData()
            mold_type = self._mold_type_combo.currentData()
            mold_name = self._mold_name_combo.currentData()
            if device and mold_type and mold_name:
                vgs_root = self._path_edit.text().strip() or _DEFAULT_VGS_ROOT
                suggested = (
                    Path(vgs_root) / "config" / "device" / device
                    / "mold" / mold_type / mold_name
                    / f"{mold_type}_collision_{mold_name}.yaml"
                )
                self._target_label.setText(f"（待创建）{suggested}")
            else:
                self._target_label.setText("—")
        self.refresh_buttons()

    def _current_target_path(self) -> Path | None:
        device    = self._device_combo.currentData()
        mold_type = self._mold_type_combo.currentData()
        mold_name = self._mold_name_combo.currentData()
        if not (device and mold_type and mold_name):
            return None
        return self._targets.get(device, {}).get(mold_type, {}).get(mold_name)

    # ── 按钮激活 ──────────────────────────────────────────────────

    def refresh_buttons(self):
        has_yaml = bool(self._get_yaml_text())
        has_file = self._current_target_path() is not None
        no_file  = self._current_mold_dir_path() is not None and not has_file
        self._deploy_one_btn.setEnabled(has_yaml and has_file)
        self._create_btn.setEnabled(has_yaml and no_file)

    def _current_mold_dir_path(self) -> "Path | None":
        device    = self._device_combo.currentData()
        mold_type = self._mold_type_combo.currentData()
        mold_name = self._mold_name_combo.currentData()
        if not (device and mold_type and mold_name):
            return None
        vgs_root = self._path_edit.text().strip() or _DEFAULT_VGS_ROOT
        return (
            Path(vgs_root) / "config" / "device"
            / device / "mold" / mold_type / mold_name
        )

    # ── 部署 ──────────────────────────────────────────────────────

    def _deploy(self, paths: list[Path]) -> None:
        yaml_text = self._get_yaml_text()
        if not yaml_text:
            QMessageBox.warning(self, "无内容", "请先转换 TXT 内容再部署。")
            return

        files_text = "\n".join(f"  {p}" for p in paths)
        reply = QMessageBox.question(
            self, "确认替换",
            f"即将替换以下 {len(paths)} 个文件（原文件自动备份，带时间戳）：\n\n{files_text}\n\n确认继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        device    = self._device_combo.currentData()
        mold_type = self._mold_type_combo.currentData()
        mold_name = self._mold_name_combo.currentData()

        success, failed = [], []
        for p in paths:
            bak = p.with_name(f"{p.stem}_{ts}.yaml.bak")
            try:
                if p.exists():
                    shutil.copy2(p, bak)
                p.write_text(yaml_text, encoding="utf-8")
                success.append(p)
                _append_replacement_log({
                    "time":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "device":    device or "",
                    "mold_type": mold_type or "",
                    "mold_name": mold_name or "",
                    "file":      str(p),
                    "backup":    str(bak),
                })
            except Exception as exc:
                if bak.exists():
                    try:
                        shutil.copy2(bak, p)
                    except Exception:
                        pass
                failed.append((p, exc))
                logger.error(f"deploy {p}: {exc}")

        if failed:
            msg = "\n".join(f"{p}: {e}" for p, e in failed)
            QMessageBox.critical(self, "部分失败", f"以下文件替换失败：\n{msg}")
        if success:
            self._status_label.setText(
                f"已替换 {len(success)} 个文件（备份: {ts}）"
            )

    def _deploy_one(self):
        path = self._current_target_path()
        if path:
            self._deploy([path])

    def _create_new_collision(self):
        from PySide6.QtWidgets import QInputDialog
        device    = self._device_combo.currentData()
        mold_type = self._mold_type_combo.currentData()
        mold_name = self._mold_name_combo.currentData()
        yaml_text = self._get_yaml_text()
        if not (device and mold_type and mold_name and yaml_text):
            return

        dir_path       = self._current_mold_dir_path()
        suggested_name = f"{mold_type}_collision_{mold_name}.yaml"

        # 警告
        msg = (
            "⚠  新增碰撞区域文件请联系视觉工作人员！\n\n"
            "确认已获得视觉工作人员授权后，点击 OK 继续。\n\n"
            f"建议文件名：{suggested_name}\n"
            f"保存目录：{dir_path}"
        )
        reply = QMessageBox.warning(
            self, "新增碰撞区域文件", msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return

        filename, ok = QInputDialog.getText(
            self, "确认文件名", "文件名（可修改）：", text=suggested_name
        )
        if not ok or not filename.strip():
            return
        filename = filename.strip()
        if not filename.endswith(".yaml"):
            filename += ".yaml"

        save_path = dir_path / filename
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            save_path.write_text(yaml_text, encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return

        self._status_label.setText(f"已创建: {save_path}")
        QMessageBox.information(self, "创建成功", f"碰撞区域文件已创建:\n{save_path}")
        self._load_and_scan()

    def _show_log(self):
        from PySide6.QtWidgets import QDialog, QTextEdit, QDialogButtonBox
        records = _read_replacement_log()
        dlg = QDialog(self)
        dlg.setWindowTitle("替换记录")
        dlg.resize(860, 480)
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFontFamily("Consolas")
        if not records:
            txt.setPlainText("暂无替换记录。")
        else:
            lines = []
            for r in reversed(records):  # 最新的在最上面
                lines.append(
                    f"[{r.get('time','')}]  "
                    f"{r.get('device','')} / {r.get('mold_type','')} / {r.get('mold_name','')}\n"
                    f"  文件: {r.get('file','')}\n"
                    f"  备份: {r.get('backup','')}\n"
                )
            txt.setPlainText("\n".join(lines))
        lay.addWidget(txt, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec()


# ─────────────────────────────────────────────────────────────────

class DropTextEdit(QPlainTextEdit):
    filesDropped = Signal(list)

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText(placeholder)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls if url.isLocalFile()]
        txt_files = [path for path in files if path.lower().endswith(".txt")]
        if txt_files:
            self.filesDropped.emit(txt_files)
            event.acceptProposedAction()
            return
        if event.mimeData().hasText():
            self.insertPlainText(event.mimeData().text())
            event.acceptProposedAction()
            return
        event.ignore()


class TxtYamlWidget(ToolBase):
    tool_name = "替换碰撞区域文件（txt转yaml）"
    tool_description = "将安全区域坐标 TXT 转为 YAML，并部署/新增到 VGS 碰撞配置"
    tool_icon = "📄"

    def init_ui(self):
        self.current_txt_path: Path | None = None
        self.current_yaml_text = ""

        self.resize(1100, 920)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        intro = QLabel("支持打开 TXT、直接粘贴内容、拖拽 TXT 文件到窗口，以及批量转换。")
        intro.setWordWrap(True)
        main_layout.addWidget(intro)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        main_layout.addLayout(button_row)

        self.open_button = QPushButton("打开 TXT")
        self.convert_button = QPushButton("转换预览")
        self.save_button = QPushButton("另存 YAML")
        self.copy_button = QPushButton("复制 YAML")
        self.batch_button = QPushButton("批量转换 TXT")
        self.clear_button = QPushButton("清空")

        for button in (
            self.open_button, self.convert_button, self.save_button,
            self.copy_button, self.batch_button, self.clear_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)

        editors_row = QHBoxLayout()
        editors_row.setSpacing(12)
        main_layout.addLayout(editors_row, 1)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()
        editors_row.addLayout(left_panel, 1)
        editors_row.addLayout(right_panel, 1)

        left_panel.addWidget(QLabel("TXT 输入"))
        right_panel.addWidget(QLabel("YAML 预览"))

        self.input_edit = DropTextEdit(
            "把安全区域 TXT 内容粘贴到这里，或把 .txt 文件拖进来。多文件拖入会自动批量转换。"
        )
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText('点击"转换预览"后，这里会显示 YAML。')
        self.input_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_panel.addWidget(self.input_edit, 1)
        right_panel.addWidget(self.output_edit, 1)

        tips = QLabel("TXT 格式要求: 每行一个坐标，格式为 x,y；不同轮廓之间用 --- 分隔。")
        tips.setWordWrap(True)
        main_layout.addWidget(tips)

        self._deploy_panel = CollisionDeployPanel(lambda: self.current_yaml_text)
        main_layout.addWidget(self._deploy_panel)

        self.status = QStatusBar()
        main_layout.addWidget(self.status)
        self.set_status("就绪")

        self.open_button.clicked.connect(self.open_txt_file)
        self.convert_button.clicked.connect(self.convert_current_text)
        self.save_button.clicked.connect(self.save_yaml_file)
        self.copy_button.clicked.connect(self.copy_yaml)
        self.batch_button.clicked.connect(self.batch_convert_dialog)
        self.clear_button.clicked.connect(self.clear_all)
        self.input_edit.filesDropped.connect(self.handle_dropped_files)

    def set_status(self, text: str) -> None:
        self.status.showMessage(text)

    def handle_dropped_files(self, file_paths: list[str]) -> None:
        if len(file_paths) == 1:
            self.load_txt_file(Path(file_paths[0]))
            return
        self.run_batch_convert([Path(path) for path in file_paths])

    def open_txt_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 TXT 文件", str(Path.cwd()), "Text Files (*.txt)",
        )
        if not file_path:
            return
        self.load_txt_file(Path(file_path))

    def load_txt_file(self, path: Path) -> None:
        try:
            content = read_text_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", str(exc))
            self.set_status(f"打开失败: {path}")
            return
        self.current_txt_path = path
        self.input_edit.setPlainText(content)
        self.set_status(f"已加载: {path}")
        self.convert_current_text()

    def convert_current_text(self) -> None:
        content = self.input_edit.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "提示", "请先打开 TXT 文件或粘贴内容。")
            self.set_status("等待输入 TXT 内容")
            return
        try:
            self.current_yaml_text = convert_text(content)
        except Exception as exc:
            self.output_edit.clear()
            self.current_yaml_text = ""
            QMessageBox.critical(self, "转换失败", str(exc))
            self.set_status("转换失败")
            return
        self.output_edit.setPlainText(self.current_yaml_text)
        contour_count = self.current_yaml_text.count("contour")
        self.set_status(f"转换成功，共 {contour_count} 个轮廓")
        self._deploy_panel.refresh_buttons()

    def save_yaml_file(self) -> None:
        if not self.current_yaml_text:
            self.convert_current_text()
        if not self.current_yaml_text:
            return
        default_path = (
            self.current_txt_path.with_suffix(".yaml")
            if self.current_txt_path
            else Path.cwd() / "safe_area.yaml"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存 YAML 文件", str(default_path), "YAML Files (*.yaml *.yml)",
        )
        if not file_path:
            return
        target = Path(file_path)
        try:
            target.write_text(self.current_yaml_text, encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            self.set_status(f"保存失败: {target}")
            return
        self.set_status(f"已保存: {target}")
        QMessageBox.information(self, "保存成功", f"YAML 已保存到:\n{target}")

    def copy_yaml(self) -> None:
        if not self.current_yaml_text:
            self.convert_current_text()
        if not self.current_yaml_text:
            return
        QGuiApplication.clipboard().setText(self.current_yaml_text)
        self.set_status("YAML 已复制到剪贴板")

    def batch_convert_dialog(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择一个或多个 TXT 文件", str(Path.cwd()), "Text Files (*.txt)",
        )
        if not file_paths:
            return
        self.run_batch_convert([Path(path) for path in file_paths])

    def run_batch_convert(self, paths: list[Path]) -> None:
        results = batch_convert(paths)
        success_items = [item for item in results if item.success]
        failed_items = [item for item in results if not item.success]

        lines = [f"成功 {len(success_items)} 个，失败 {len(failed_items)} 个。"]
        for item in success_items[:10]:
            lines.append(f"成功: {item.target}")
        for item in failed_items[:10]:
            lines.append(f"失败: {item.source} -> {item.message}")
        if len(results) > 10:
            lines.append("结果较多，完整信息请查看同目录输出文件。")

        self.set_status(f"批量转换完成: {len(success_items)}/{len(results)} 成功")
        box = QMessageBox(self)
        box.setWindowTitle("批量转换结果")
        box.setIcon(
            QMessageBox.Icon.Information if not failed_items else QMessageBox.Icon.Warning
        )
        box.setText("\n".join(lines))
        box.exec()

    def clear_all(self) -> None:
        self.current_txt_path = None
        self.current_yaml_text = ""
        self.input_edit.clear()
        self.output_edit.clear()
        self.set_status("已清空")
        self._deploy_panel.refresh_buttons()
