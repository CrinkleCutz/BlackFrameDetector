#!/usr/bin/env python3
import csv
import json
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Tuple, Dict

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtGui import QFont, QPixmap, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# ----------------------------
# Bundled ffmpeg/ffprobe support (PyInstaller)
# ----------------------------

def resolve_tool(name: str) -> str:
    """
    When running as a PyInstaller app, use bundled binaries from:
      <_MEIPASS>/bin/ffmpeg
      <_MEIPASS>/bin/ffprobe
    Otherwise use the system PATH.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "bin" / name
        if candidate.exists():
            return str(candidate)
    return name


def resolve_resource(name: str) -> str:
    """
    Resolve path to bundled resource files (images, etc.).
    When frozen, looks in _MEIPASS; otherwise looks relative to script.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / name
        if candidate.exists():
            return str(candidate)
    # Development: look relative to script location
    script_dir = Path(__file__).parent
    candidate = script_dir / name
    if candidate.exists():
        return str(candidate)
    return name

# ----------------------------
# Data models
# ----------------------------

@dataclass
class BlackFrameHit:
    frame: int
    time_s: Optional[float]
    pblack: Optional[float]
    pts: Optional[int]

@dataclass
class BlackRange:
    start_frame: int
    end_frame: int
    start_time_s: Optional[float]
    end_time_s: Optional[float]
    length_frames: int
    avg_pblack: Optional[float]
    min_pblack: Optional[float]

# Robust-ish parse for blackframe lines. Example:
# [Parsed_blackframe_0 @ ...] frame:23 pblack:100 pts:27600 t:0.920000 type:I last_keyframe:0
BLACKFRAME_LINE_RE = re.compile(
    r"Parsed_blackframe.*?\bframe:(?P<frame>\d+)"
    r"(?:.*?\bpblack:(?P<pblack>\d+(?:\.\d+)?))?"
    r"(?:.*?\bpts:(?P<pts>\d+))?"
    r"(?:.*?\bt:(?P<t>\d+(?:\.\d+)?))?"
)

# ffmpeg -progress key=val lines
PROGRESS_OUT_TIME_MS_RE = re.compile(r"^out_time_ms=(\d+)\s*$")
PROGRESS_END_RE = re.compile(r"^progress=end\s*$")

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mts", ".m2ts",
    ".webm", ".wmv", ".flv", ".ts", ".vob", ".mpg", ".mpeg",
}

# Change 5: Module-level button stylesheet constants
_START_BTN_STYLE = """
    QPushButton {
        background-color: #34c759;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 24px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #2db84e;
    }
    QPushButton:pressed {
        background-color: #28a745;
    }
    QPushButton:disabled {
        background-color: #a8a8a8;
    }
"""

_CANCEL_BTN_STYLE = """
    QPushButton {
        background-color: #ff3b30;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 24px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #e6352b;
    }
    QPushButton:pressed {
        background-color: #cc2f26;
    }
"""

# Change 11: Simplified — no timedelta needed
def seconds_to_hhmmssms(seconds: Optional[float]) -> str:
    if seconds is None:
        return "n/a"
    ms = int(round(seconds * 1000.0))
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    msec = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{msec:03d}"

# ----------------------------
# Range building
# ----------------------------

def build_ranges(hits: List[BlackFrameHit], min_run_frames: int) -> List[BlackRange]:
    if not hits:
        return []

    hits_sorted = sorted(hits, key=lambda h: h.frame)

    ranges: List[BlackRange] = []
    cur = [hits_sorted[0]]

    def finalize(group: List[BlackFrameHit]) -> Optional[BlackRange]:
        if not group:
            return None
        start = group[0]
        end = group[-1]
        length = end.frame - start.frame + 1
        if length < min_run_frames:
            return None

        pvals = [h.pblack for h in group if h.pblack is not None]
        avg_pb = sum(pvals) / len(pvals) if pvals else None
        min_pb = min(pvals) if pvals else None

        return BlackRange(
            start_frame=start.frame,
            end_frame=end.frame,
            start_time_s=start.time_s,
            end_time_s=end.time_s,
            length_frames=length,
            avg_pblack=avg_pb,
            min_pblack=min_pb,
        )

    for h in hits_sorted[1:]:
        prev = cur[-1]
        if h.frame == prev.frame + 1:
            cur.append(h)
        else:
            r = finalize(cur)
            if r:
                ranges.append(r)
            cur = [h]

    r = finalize(cur)
    if r:
        ranges.append(r)

    return ranges

# ----------------------------
# Multi-file helper
# ----------------------------

def collect_video_files(paths: List[str]) -> List[str]:
    """
    Given a list of file/folder paths, recursively scan folders and filter
    by VIDEO_EXTENSIONS. Returns a deduplicated, sorted list of resolved paths.
    """
    seen: set = set()
    result: List[str] = []

    for p in paths:
        path = Path(p)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
                    resolved = str(child.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        result.append(resolved)
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)

    return result

# ----------------------------
# Banner Widget
# ----------------------------

# Change 6: Cache scaled pixmap
class BannerWidget(QFrame):
    """Header banner that paints logo2.png as a scaled background image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        img_path = resolve_resource("logo2.png")
        self._bg = QPixmap(img_path) if Path(img_path).exists() else QPixmap()
        self._aspect = self._bg.width() / max(self._bg.height(), 1) if not self._bg.isNull() else 4.0
        self._scaled_bg: Optional[QPixmap] = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def resizeEvent(self, event):
        # Set height to show the full image without cropping
        h = max(int(self.width() / self._aspect), 120)
        self.setFixedHeight(h)
        # Cache the scaled pixmap for paintEvent
        if not self._bg.isNull():
            self._scaled_bg = self._bg.scaledToWidth(self.width(), Qt.SmoothTransformation)
        else:
            self._scaled_bg = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)
        # Clip to rounded rectangle
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.setClipPath(path)
        if self._scaled_bg is not None:
            painter.drawPixmap(0, 0, self._scaled_bg)
        else:
            painter.fillRect(self.rect(), QColor(30, 30, 30))
        painter.end()


# ----------------------------
# Main Window
# ----------------------------

class BlackFrameDetectorV2(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Black Frame Detector")
        self.resize(1040, 820)

        # Processes
        self.probe_proc: Optional[QProcess] = None
        self.ffmpeg_proc: Optional[QProcess] = None

        # Parse buffers (line-safe)
        self._stderr_buf = ""
        self._stdout_buf = ""

        # Metadata
        self.video_duration_s: Optional[float] = None
        self.video_fps: Optional[float] = None

        # Run state
        self._running = False
        self._analysis_start_time: Optional[float] = None
        self._queue_start_time: Optional[float] = None
        self._total_video_duration_s: float = 0.0

        # Per-file scratch results
        self.hits: List[BlackFrameHit] = []
        self.ranges: List[BlackRange] = []
        # Change 9: deque for O(1) popleft
        self._pending_hits: deque[BlackFrameHit] = deque()

        # Multi-file queue
        self._file_queue: List[str] = []
        self._current_queue_index: int = 0
        self._queue_active: bool = False
        self.all_hits: Dict[str, List[BlackFrameHit]] = {}
        self.all_ranges: Dict[str, List[BlackRange]] = {}

        # UI batch flush timer
        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(150)
        self.flush_timer.timeout.connect(self._flush_pending_hits)

        self._build_ui()

        # Defaults (macOS + practical black detection for various codecs)
        self.mode_standard.setChecked(True)
        self.threshold_spin.setValue(32)
        self.amount_spin.setValue(98.00)
        self.group_ranges_checkbox.setChecked(True)
        self.min_run_spin.setValue(1)  # detect single black frames by default

        self._sync_mode_presets()
        self._update_range_controls_enabled()

    # ---------------- UI ----------------

    # Change 12: _build_ui split into focused sub-methods
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        root.addWidget(self._build_banner())
        root.addWidget(self._build_file_group())
        root.addWidget(self._build_settings_group())

        # Start row
        start_row = QHBoxLayout()
        start_row.addStretch(1)
        self.start_btn = QPushButton("Start Analysis")
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.start_btn.setStyleSheet(_START_BTN_STYLE)
        self.start_btn.clicked.connect(self.on_start_or_cancel)
        start_row.addWidget(self.start_btn)
        root.addLayout(start_row)

        # Progress
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("Ready")
        self.progress.setStyleSheet("QProgressBar { background-color: #000000; color: white; }")
        self._set_progress_determinate(True)
        root.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #cccccc; font-size: 12px; padding: 4px 0px;")
        root.addWidget(self.status_label)

        tabs, export_row = self._build_results_section()
        root.addWidget(tabs, 1)
        root.addLayout(export_row)

        # Typography
        font = QFont()
        font.setPointSize(13)
        self.setFont(font)

        self.setCentralWidget(central)

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _build_banner(self) -> BannerWidget:
        banner = BannerWidget()
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(24, 28, 24, 18)
        banner_layout.setSpacing(6)
        banner_layout.addStretch(1)

        title_label = QLabel("Black Frame Detector")
        title_font = QFont("Helvetica Neue", 26)
        title_font.setWeight(QFont.Bold)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: white; background: transparent;")
        banner_layout.addWidget(title_label)
        banner_layout.addSpacing(5)

        info_text = QLabel(
            "Analyzes video files to detect black or near-black frames.<br>"
            "Add multiple files or drag-and-drop a folder to batch analyze.<br><br>"
            "<b>Supported Formats:</b> MP4, MOV, MKV, M4V, AVI, MTS, M2TS<br>"
            "<b>Supported Codecs:</b> H.264, H.265/HEVC, ProRes, DNxHD<br>"
            "<b>Resolutions:</b> SD, HD (720p/1080p), UHD (4K)<br><br>"
            "<i>Analysis runs faster than real-time on most content.</i>"
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: white; background: transparent; line-height: 1.5;")
        banner_layout.addWidget(info_text)
        banner_layout.addStretch(1)

        return banner

    def _build_file_group(self) -> QGroupBox:
        file_box = QGroupBox("Video Files")
        file_layout = QVBoxLayout(file_box)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.setStyleSheet("QListWidget { color: white; background-color: #000000; }")
        self.file_list.setMaximumHeight(26)  # single-row default until files added
        file_layout.addWidget(self.file_list)

        file_btn_row = QHBoxLayout()
        self.add_files_btn = QPushButton("Add Files...")
        self.add_folder_btn = QPushButton("Add Folder...")
        self.remove_selected_btn = QPushButton("Remove Selected")
        self.clear_files_btn = QPushButton("Clear All")

        self.add_files_btn.clicked.connect(self.on_browse)
        self.add_folder_btn.clicked.connect(self.on_browse_folder)
        self.remove_selected_btn.clicked.connect(self.on_remove_selected)
        self.clear_files_btn.clicked.connect(self.on_clear_files)

        file_btn_row.addWidget(self.add_files_btn)
        file_btn_row.addWidget(self.add_folder_btn)
        file_btn_row.addStretch(1)
        file_btn_row.addWidget(self.remove_selected_btn)
        file_btn_row.addWidget(self.clear_files_btn)
        file_layout.addLayout(file_btn_row)

        return file_box

    def _build_settings_group(self) -> QGroupBox:
        settings_box = QGroupBox("Detection Settings")
        grid = QGridLayout(settings_box)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        # Mode
        mode_label = QLabel("Detection Mode:")
        self.mode_standard = QRadioButton("Standard")
        self.mode_strict = QRadioButton("Strict")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_standard)
        self.mode_group.addButton(self.mode_strict)
        self.mode_group.buttonToggled.connect(lambda *_: self._sync_mode_presets())

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_standard)
        mode_row.addWidget(self.mode_strict)
        mode_row.addStretch(1)
        mode_hint = QLabel("Standard: catches near-black frames (threshold 32, 98%). Strict: exact black only (threshold 0, 100%).")
        mode_hint.setStyleSheet("color: #6b6b6b;")

        # Threshold
        threshold_label = QLabel("Black Threshold:")
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 50)
        self.threshold_spin.setSingleStep(1)
        threshold_hint = QLabel("0 = exact; 32 is a practical default for most codecs.")
        threshold_hint.setStyleSheet("color: #6b6b6b;")

        # Amount
        amount_label = QLabel("Pixel Blackness (%):")
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(90.0, 100.0)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setSingleStep(0.05)
        self.amount_spin.setSuffix(" %")
        amount_hint = QLabel("Higher is stricter. 98% is practical for most content.")
        amount_hint.setStyleSheet("color: #6b6b6b;")

        # Grouping / ranges
        group_label = QLabel("Output:")
        self.group_ranges_checkbox = QCheckBox("Build consecutive-frame ranges")
        self.group_ranges_checkbox.toggled.connect(self._update_range_controls_enabled)

        min_run_label = QLabel("Min Run Length:")
        self.min_run_spin = QSpinBox()
        self.min_run_spin.setRange(1, 1000)
        self.min_run_spin.setSingleStep(1)
        self.min_run_spin.setSuffix(" frames")
        min_run_hint = QLabel("Use ranges to avoid thousands of single-frame entries; ideal for leaders/tails/slates.")
        min_run_hint.setStyleSheet("color: #6b6b6b;")

        # Layout
        grid.addWidget(mode_label, 0, 0, Qt.AlignRight)
        grid.addLayout(mode_row, 0, 1)
        grid.addWidget(mode_hint, 1, 1, 1, 2)

        grid.addWidget(threshold_label, 2, 0, Qt.AlignRight)
        grid.addWidget(self.threshold_spin, 2, 1, Qt.AlignLeft)
        grid.addWidget(threshold_hint, 3, 1, 1, 2)

        grid.addWidget(amount_label, 4, 0, Qt.AlignRight)
        grid.addWidget(self.amount_spin, 4, 1, Qt.AlignLeft)
        grid.addWidget(amount_hint, 5, 1, 1, 2)

        grid.addWidget(group_label, 6, 0, Qt.AlignRight)
        grid.addWidget(self.group_ranges_checkbox, 6, 1, Qt.AlignLeft)

        grid.addWidget(min_run_label, 7, 0, Qt.AlignRight)
        grid.addWidget(self.min_run_spin, 7, 1, Qt.AlignLeft)
        grid.addWidget(min_run_hint, 8, 1, 1, 2)

        return settings_box

    def _build_results_section(self) -> Tuple[QTabWidget, QHBoxLayout]:
        self.tabs = QTabWidget()
        self.frames_table = QTableWidget(0, 4)
        self.frames_table.setHorizontalHeaderLabels(["File", "Frame Number", "Timestamp", "Blackness %"])
        self.frames_table.horizontalHeader().setStretchLastSection(True)
        self.frames_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.frames_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.frames_table.setAlternatingRowColors(True)
        self.frames_table.setStyleSheet("QTableWidget { background-color: #000000; color: white; } QTableWidget::item:alternate { background-color: #0a0a0a; }")

        self.ranges_table = QTableWidget(0, 7)
        self.ranges_table.setHorizontalHeaderLabels(["File", "Start Frame", "End Frame", "Start Time", "End Time", "Length", "Avg / Min %"])
        self.ranges_table.horizontalHeader().setStretchLastSection(True)
        self.ranges_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ranges_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ranges_table.setAlternatingRowColors(True)
        self.ranges_table.setStyleSheet("QTableWidget { background-color: #000000; color: white; } QTableWidget::item:alternate { background-color: #0a0a0a; }")

        self.tabs.addTab(self.ranges_table, "Ranges")
        self.tabs.addTab(self.frames_table, "Frames")
        self.tabs.setMinimumHeight(210)

        export_row = QHBoxLayout()
        self.export_frames_csv_btn = QPushButton("Export Frames CSV")
        self.export_frames_json_btn = QPushButton("Export Frames JSON")
        self.export_ranges_csv_btn = QPushButton("Export Ranges CSV")
        self.export_ranges_json_btn = QPushButton("Export Ranges JSON")

        self.export_frames_csv_btn.clicked.connect(self.export_frames_csv)
        self.export_frames_json_btn.clicked.connect(self.export_frames_json)
        self.export_ranges_csv_btn.clicked.connect(self.export_ranges_csv)
        self.export_ranges_json_btn.clicked.connect(self.export_ranges_json)

        for b in [self.export_frames_csv_btn, self.export_frames_json_btn, self.export_ranges_csv_btn, self.export_ranges_json_btn]:
            b.setEnabled(False)

        export_row.addWidget(self.export_frames_csv_btn)
        export_row.addWidget(self.export_frames_json_btn)
        export_row.addStretch(1)
        export_row.addWidget(self.export_ranges_csv_btn)
        export_row.addWidget(self.export_ranges_json_btn)

        return self.tabs, export_row

    # Change 2: Removed no-op (setValue(0) when value==0)
    def _set_progress_determinate(self, determinate: bool):
        if determinate:
            self.progress.setRange(0, 1000)
        else:
            # Indeterminate/busy bar
            self.progress.setRange(0, 0)

    def _update_range_controls_enabled(self):
        enabled = self.group_ranges_checkbox.isChecked()
        self.min_run_spin.setEnabled(enabled)

    def _sync_mode_presets(self):
        # Snap to sensible defaults when toggling mode
        if self.mode_strict.isChecked():
            self.threshold_spin.setValue(0)
            self.amount_spin.setValue(100.00)
        else:
            # If user was on strict defaults, restore practical defaults
            if self.threshold_spin.value() == 0 and abs(self.amount_spin.value() - 100.0) < 1e-9:
                self.threshold_spin.setValue(32)
                self.amount_spin.setValue(98.00)

    # ---------------- Drag and Drop ----------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self._running:
            event.ignore()
            return
        urls = event.mimeData().urls()
        raw_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if raw_paths:
            video_paths = collect_video_files(raw_paths)
            if video_paths:
                self._add_files_to_list(video_paths)
            else:
                QMessageBox.information(self, "No Videos Found", "No supported video files were found in the dropped items.")
        event.acceptProposedAction()

    # ---------------- File Management ----------------

    def on_browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.m4v *.avi *.mts *.m2ts *.webm *.wmv *.flv *.ts *.vob *.mpg *.mpeg);;All Files (*.*)",
        )
        if paths:
            video_paths = collect_video_files(paths)
            if video_paths:
                self._add_files_to_list(video_paths)

    def on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Videos", "")
        if folder:
            video_paths = collect_video_files([folder])
            if video_paths:
                self._add_files_to_list(video_paths)
            else:
                QMessageBox.information(self, "No Videos Found", "No supported video files were found in the selected folder.")

    def on_remove_selected(self):
        for item in reversed(self.file_list.selectedItems()):
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
        self._resize_file_list()

    def on_clear_files(self):
        self.file_list.clear()
        self._resize_file_list()

    def _resize_file_list(self):
        """Resize file list to exactly fit its contents, capped at 10 rows."""
        count = self.file_list.count()
        if count == 0:
            self.file_list.setFixedHeight(26)
            return
        row_height = self.file_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 22
        # Show up to 10 rows, add small margin for frame border
        visible_rows = min(count, 10)
        height = visible_rows * row_height + 2 * self.file_list.frameWidth()
        self.file_list.setFixedHeight(height)

    def _add_files_to_list(self, paths: List[str]):
        existing = set()
        for i in range(self.file_list.count()):
            existing.add(self.file_list.item(i).data(Qt.UserRole))

        for p in paths:
            if p in existing:
                continue
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            item.setData(Qt.UserRole, p)
            self.file_list.addItem(item)
            existing.add(p)
        self._resize_file_list()

    # ---------------- Actions ----------------

    def on_start_or_cancel(self):
        if self._running:
            self._cancel()
        else:
            self._start()

    # Change 1: Path(path).exists() instead of os.path.exists(path)
    def _start(self):
        # Build queue from list widget
        queue: List[str] = []
        for i in range(self.file_list.count()):
            path = self.file_list.item(i).data(Qt.UserRole)
            if path and Path(path).exists():
                queue.append(path)

        if not queue:
            QMessageBox.warning(self, "No Files", "Please add at least one valid video file.")
            return

        # Global reset
        self._file_queue = queue
        self._current_queue_index = 0
        self._queue_active = True
        self.all_hits.clear()
        self.all_ranges.clear()
        self.hits.clear()
        self.ranges.clear()
        self._pending_hits.clear()
        self._stderr_buf = ""
        self._stdout_buf = ""

        self.frames_table.setRowCount(0)
        self.ranges_table.setRowCount(0)

        for b in [self.export_frames_csv_btn, self.export_frames_json_btn,
                   self.export_ranges_csv_btn, self.export_ranges_json_btn]:
            b.setEnabled(False)

        self._set_progress_determinate(True)
        self.progress.setValue(0)
        self.progress.setFormat("Ready")
        self.status_label.setText("")

        # Reset list widget item text (remove previous status annotations)
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setText(Path(item.data(Qt.UserRole)).name)
            item.setForeground(QColor("white"))

        self._queue_start_time = time.time()
        self._total_video_duration_s = 0.0
        self._set_running_ui(True)
        self._start_next_file()

    def _start_next_file(self):
        if self._current_queue_index >= len(self._file_queue):
            self._on_all_files_finished()
            return

        path = self._file_queue[self._current_queue_index]
        idx = self._current_queue_index + 1
        total = len(self._file_queue)
        filename = Path(path).name

        # Highlight current file in list widget
        self.file_list.setCurrentRow(self._current_queue_index)

        # Reset per-file scratch
        self.hits.clear()
        self.ranges.clear()
        self._pending_hits.clear()
        self._stderr_buf = ""
        self._stdout_buf = ""
        self.video_duration_s = None
        self.video_fps = None
        self._analysis_start_time = None

        self.progress.setFormat(f"[{idx}/{total}] Probing {filename}...")
        self._run_ffprobe(path)

    def _cancel(self):
        self._queue_active = False
        if self.ffmpeg_proc:
            self.ffmpeg_proc.kill()
        if self.probe_proc:
            self.probe_proc.kill()
        self.flush_timer.stop()
        self._set_running_ui(False)

        completed = self._current_queue_index
        total = len(self._file_queue)
        self.progress.setFormat(f"Cancelled ({completed}/{total} files completed)")

        self._finalize_exports_state()

    # Change 2: Removed duplicate group_ranges_checkbox.setEnabled
    # Change 5: Use _START_BTN_STYLE / _CANCEL_BTN_STYLE constants
    def _set_running_ui(self, running: bool):
        self._running = running
        self.start_btn.setText("Cancel" if running else "Start Analysis")
        self.start_btn.setStyleSheet(_CANCEL_BTN_STYLE if running else _START_BTN_STYLE)

        for w in [
            self.file_list,
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_selected_btn,
            self.clear_files_btn,
            self.mode_standard,
            self.mode_strict,
            self.threshold_spin,
            self.amount_spin,
            self.group_ranges_checkbox,
            self.min_run_spin,
        ]:
            w.setEnabled(not running)

        self.min_run_spin.setEnabled((not running) and self.group_ranges_checkbox.isChecked())

    # ---------------- ffprobe ----------------

    def _run_ffprobe(self, path: str):
        self.probe_proc = QProcess(self)
        self.probe_proc.finished.connect(lambda code, status: self._on_ffprobe_finished(path, code, status))

        args = [
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration:stream=avg_frame_rate,r_frame_rate",
            "-of", "json",
            path,
        ]
        self.probe_proc.start(resolve_tool("ffprobe"), args)

    def _on_ffprobe_finished(self, path: str, exit_code: int, _exit_status):
        if not self.probe_proc:
            return

        out = bytes(self.probe_proc.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        err = bytes(self.probe_proc.readAllStandardError()).decode("utf-8", errors="replace").strip()

        if exit_code != 0 or not out:
            # Change 4: Use consolidated failure helper
            self._record_failure_and_advance(path, "FAILED - probe")
            return

        try:
            data = json.loads(out)
            duration = data.get("format", {}).get("duration", None)
            self.video_duration_s = float(duration) if duration is not None else None
            if self.video_duration_s:
                self._total_video_duration_s += self.video_duration_s

            stream = data["streams"][0]
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/0"
            num, den = rate.split("/")
            self.video_fps = float(num) / float(den) if float(den) != 0 else None
        except Exception:
            # If metadata parse fails, still run analysis but show indeterminate progress
            self.video_duration_s = None
            self.video_fps = None

        self._run_ffmpeg(path)

    # ---------------- ffmpeg ----------------

    def _run_ffmpeg(self, path: str):
        threshold = int(self.threshold_spin.value())
        amount = float(self.amount_spin.value())

        vf = f"format=yuv420p,blackframe=amount={amount}:threshold={threshold}"

        idx = self._current_queue_index + 1
        total = len(self._file_queue)
        filename = Path(path).name

        # Set determinate/indeterminate progress
        if self.video_duration_s and self.video_duration_s > 0:
            self._set_progress_determinate(True)
            self.progress.setValue(0)
        else:
            self._set_progress_determinate(False)

        args = [
            "-hide_banner",
            "-nostats",
            "-nostdin",
            "-loglevel", "info",
            "-i", path,
            "-an", "-sn", "-dn",
            "-vf", vf,
            "-progress", "pipe:1",  # progress key=val on stdout
            "-f", "null", "-",
        ]

        self.ffmpeg_proc = QProcess(self)
        self.ffmpeg_proc.readyReadStandardError.connect(self._on_ffmpeg_stderr_chunk)
        self.ffmpeg_proc.readyReadStandardOutput.connect(self._on_ffmpeg_stdout_chunk)
        self.ffmpeg_proc.finished.connect(lambda code, status: self._on_ffmpeg_finished(path, code, status))

        self.progress.setFormat(f"[{idx}/{total}] Analyzing {filename}..." + (" %p%" if self.video_duration_s else ""))

        self.ffmpeg_proc.start(resolve_tool("ffmpeg"), args)

        if not self.ffmpeg_proc.waitForStarted(3000):
            # Change 4: Use consolidated failure helper
            self._record_failure_and_advance(path, "FAILED - ffmpeg start")
            return

        # Track start time for ETA calculation
        self._analysis_start_time = time.time()

        # Begin UI batching
        self.flush_timer.start()

    def _on_ffmpeg_stdout_chunk(self):
        if not self.ffmpeg_proc:
            return
        chunk = bytes(self.ffmpeg_proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._stdout_buf += chunk

        lines, self._stdout_buf = self._split_complete_lines(self._stdout_buf)
        for line in lines:
            m = PROGRESS_OUT_TIME_MS_RE.match(line)
            if m and self.video_duration_s and self.video_duration_s > 0:
                # Note: despite the name, out_time_ms is actually in microseconds
                out_time_us = int(m.group(1))
                dur_us = int(self.video_duration_s * 1_000_000)
                frac = max(0.0, min(1.0, out_time_us / dur_us))
                self.progress.setValue(int(frac * 1000))

                # Calculate and display ETA
                self._update_progress_eta(frac)
                continue

            if PROGRESS_END_RE.match(line):
                if self.video_duration_s and self.video_duration_s > 0:
                    self.progress.setValue(1000)
                    idx = self._current_queue_index + 1
                    total = len(self._file_queue)
                    # Change 10: derive path from queue instead of _last_path
                    filename = Path(self._file_queue[self._current_queue_index]).name
                    self.progress.setFormat(f"[{idx}/{total}] Finishing {filename}...")

    def _update_progress_eta(self, frac: float):
        """Update progress bar format with ETA countdown."""
        if frac <= 0 or self._analysis_start_time is None:
            return

        elapsed = time.time() - self._analysis_start_time
        if elapsed < 0.5:
            # Not enough data yet for reliable ETA
            return

        idx = self._current_queue_index + 1
        total = len(self._file_queue)
        filename = Path(self._file_queue[self._current_queue_index]).name

        # Estimate total time and remaining time
        estimated_total = elapsed / frac
        remaining = max(0, estimated_total - elapsed)

        # Format remaining time as M:SS
        remaining_min = int(remaining // 60)
        remaining_sec = int(remaining % 60)

        pct = int(frac * 100)
        if remaining_min > 0:
            eta_str = f"{remaining_min}:{remaining_sec:02d} remaining"
        else:
            eta_str = f"{remaining_sec}s remaining"

        self.progress.setFormat(f"[{idx}/{total}] {filename} — {pct}% — {eta_str}")

    # Change 3: Extracted blackframe parsing into a helper
    @staticmethod
    def _parse_blackframe_line(line: str) -> Optional[BlackFrameHit]:
        m = BLACKFRAME_LINE_RE.search(line)
        if not m:
            return None
        frame = int(m.group("frame"))
        pblack = float(m.group("pblack")) if m.group("pblack") else None
        pts = int(m.group("pts")) if m.group("pts") else None
        t = float(m.group("t")) if m.group("t") else None
        return BlackFrameHit(frame=frame, time_s=t, pblack=pblack, pts=pts)

    def _on_ffmpeg_stderr_chunk(self):
        if not self.ffmpeg_proc:
            return
        chunk = bytes(self.ffmpeg_proc.readAllStandardError()).decode("utf-8", errors="replace")
        self._stderr_buf += chunk

        lines, self._stderr_buf = self._split_complete_lines(self._stderr_buf)
        for line in lines:
            hit = self._parse_blackframe_line(line)
            if hit:
                self.hits.append(hit)
                self._pending_hits.append(hit)

    @staticmethod
    def _split_complete_lines(buf: str) -> Tuple[List[str], str]:
        """
        Return (complete_lines, remainder) without losing partial lines.
        """
        if "\n" not in buf:
            return [], buf
        parts = buf.split("\n")
        complete = parts[:-1]
        remainder = parts[-1]
        # Strip CR for Windows-ish line endings
        complete = [line.rstrip("\r") for line in complete if line]
        return complete, remainder

    # Change 9: deque-based flush — O(1) per popleft
    def _flush_pending_hits(self):
        """
        Batch-insert pending hits to avoid UI lock-ups on large result sets.
        """
        if not self._pending_hits:
            return

        batch: List[BlackFrameHit] = []
        for _ in range(min(500, len(self._pending_hits))):
            batch.append(self._pending_hits.popleft())

        # Change 10: derive filename from queue
        filename = Path(self._file_queue[self._current_queue_index]).name

        table = self.frames_table
        table.setUpdatesEnabled(False)
        try:
            start_row = table.rowCount()
            table.setRowCount(start_row + len(batch))
            for i, hit in enumerate(batch):
                row = start_row + i
                table.setItem(row, 0, QTableWidgetItem(filename))
                table.setItem(row, 1, QTableWidgetItem(str(hit.frame)))
                table.setItem(row, 2, QTableWidgetItem(seconds_to_hhmmssms(hit.time_s)))
                pb_str = f"{hit.pblack:.2f}%" if hit.pblack is not None else "n/a"
                table.setItem(row, 3, QTableWidgetItem(pb_str))
        finally:
            table.setUpdatesEnabled(True)

    def _on_ffmpeg_finished(self, path: str, exit_code: int, _exit_status):
        # Stop batch timer and flush any remaining hits
        self.flush_timer.stop()
        self._flush_pending_hits()

        # Change 3: Use _parse_blackframe_line for remaining buffer
        if self._stderr_buf:
            tail_lines = [self._stderr_buf.rstrip("\r")]
            self._stderr_buf = ""
            for line in tail_lines:
                hit = self._parse_blackframe_line(line)
                if hit:
                    self.hits.append(hit)
                    self._pending_hits.append(hit)
            self._flush_pending_hits()

        if exit_code != 0:
            # Change 4: Use consolidated failure helper
            self._record_failure_and_advance(path, "FAILED")
            return

        # Success - sort and store results
        self.hits.sort(key=lambda h: h.frame)

        if self.group_ranges_checkbox.isChecked():
            self.ranges = build_ranges(self.hits, int(self.min_run_spin.value()))
        else:
            self.ranges = []

        # Change 8: Swap references instead of copying
        self.all_hits[path] = self.hits
        self.all_ranges[path] = self.ranges
        self.hits = []
        self.ranges = []

        # Mark item with result count
        item = self.file_list.item(self._current_queue_index)
        count = len(self.all_hits[path])
        if item:
            item.setText(f"{Path(path).name}  [{count} frame{'s' if count != 1 else ''}]")

        # Append per-file status line
        range_count = len(self.all_ranges[path])
        line = f"{Path(path).name} — {count} frame{'s' if count != 1 else ''}"
        if range_count > 0:
            line += f", {range_count} range{'s' if range_count != 1 else ''}"
        self._append_status_line(line)

        self._current_queue_index += 1
        if self._queue_active and self._current_queue_index < len(self._file_queue):
            self._start_next_file()
        else:
            self._on_all_files_finished()

    # Change 4: Consolidated failure-and-advance helper
    def _record_failure_and_advance(self, path: str, label: str):
        self.all_hits[path] = []
        self.all_ranges[path] = []
        self._mark_list_item_failed(self._current_queue_index, label)
        self._append_status_line(f"{Path(path).name} — {label}")
        self._current_queue_index += 1
        if self._queue_active:
            self._start_next_file()

    def _mark_list_item_failed(self, index: int, label: str):
        item = self.file_list.item(index)
        if item:
            path = item.data(Qt.UserRole)
            item.setText(f"{Path(path).name}  [{label}]")
            item.setForeground(QColor("#ff3b30"))

    def _append_status_line(self, line: str):
        current = self.status_label.text()
        if current:
            self.status_label.setText(current + "\n" + line)
        else:
            self.status_label.setText(line)

    # Change 2: Removed redundant setRange after _set_progress_determinate
    def _on_all_files_finished(self):
        self._queue_active = False
        self._set_running_ui(False)

        # Ensure final progress bar state
        self._set_progress_determinate(True)
        self.progress.setValue(1000)

        # Render consolidated tables
        self._render_all_frames_table()
        self._render_all_ranges_table()

        # Summary
        total_files = len(self._file_queue)
        total_frames = sum(len(h) for h in self.all_hits.values())
        total_ranges = sum(len(r) for r in self.all_ranges.values())

        summary = f"Done -- {total_files} file{'s' if total_files != 1 else ''}, {total_frames} frame{'s' if total_frames != 1 else ''}"
        if total_ranges > 0:
            summary += f", {total_ranges} range{'s' if total_ranges != 1 else ''}"
        if self._total_video_duration_s > 0:
            summary += f" | Duration: {seconds_to_hhmmssms(self._total_video_duration_s)}"
        if self._queue_start_time is not None:
            elapsed = time.time() - self._queue_start_time
            summary += f" | Processed in {seconds_to_hhmmssms(elapsed)}"
        self.progress.setFormat(summary)
        self._append_status_line(summary)

        self._finalize_exports_state()

    # Change 7: Direct iteration without intermediate list
    def _render_all_frames_table(self):
        self.frames_table.setRowCount(0)
        total_rows = sum(len(self.all_hits.get(p, [])) for p in self._file_queue)
        if total_rows == 0:
            return

        table = self.frames_table
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(total_rows)
            row = 0
            for path in self._file_queue:
                filename = Path(path).name
                for hit in self.all_hits.get(path, []):
                    table.setItem(row, 0, QTableWidgetItem(filename))
                    table.setItem(row, 1, QTableWidgetItem(str(hit.frame)))
                    table.setItem(row, 2, QTableWidgetItem(seconds_to_hhmmssms(hit.time_s)))
                    pb_str = f"{hit.pblack:.2f}%" if hit.pblack is not None else "n/a"
                    table.setItem(row, 3, QTableWidgetItem(pb_str))
                    row += 1
        finally:
            table.setUpdatesEnabled(True)

    # Change 7: Direct iteration without intermediate list
    def _render_all_ranges_table(self):
        self.ranges_table.setRowCount(0)
        total_rows = sum(len(self.all_ranges.get(p, [])) for p in self._file_queue)
        if total_rows == 0:
            return

        t = self.ranges_table
        t.setUpdatesEnabled(False)
        try:
            t.setRowCount(total_rows)
            row = 0
            for path in self._file_queue:
                filename = Path(path).name
                for r in self.all_ranges.get(path, []):
                    t.setItem(row, 0, QTableWidgetItem(filename))
                    t.setItem(row, 1, QTableWidgetItem(str(r.start_frame)))
                    t.setItem(row, 2, QTableWidgetItem(str(r.end_frame)))
                    t.setItem(row, 3, QTableWidgetItem(seconds_to_hhmmssms(r.start_time_s)))
                    t.setItem(row, 4, QTableWidgetItem(seconds_to_hhmmssms(r.end_time_s)))
                    t.setItem(row, 5, QTableWidgetItem(str(r.length_frames)))
                    if r.avg_pblack is not None and r.min_pblack is not None:
                        s = f"{r.avg_pblack:.2f}% / {r.min_pblack:.2f}%"
                    elif r.min_pblack is not None:
                        s = f"n/a / {r.min_pblack:.2f}%"
                    else:
                        s = "n/a"
                    t.setItem(row, 6, QTableWidgetItem(s))
                    row += 1
        finally:
            t.setUpdatesEnabled(True)

    def _finalize_exports_state(self):
        has_frames = any(len(h) > 0 for h in self.all_hits.values())
        has_ranges = any(len(r) > 0 for r in self.all_ranges.values())
        self.export_frames_csv_btn.setEnabled(has_frames)
        self.export_frames_json_btn.setEnabled(has_frames)
        self.export_ranges_csv_btn.setEnabled(has_ranges)
        self.export_ranges_json_btn.setEnabled(has_ranges)

    # ---------------- Export ----------------

    def export_frames_csv(self):
        has_frames = any(len(h) > 0 for h in self.all_hits.values())
        if not has_frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Frames CSV", "black_frames.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["file", "frame", "time_s", "timestamp", "pblack", "pts"])
            for fpath in self._file_queue:
                filename = Path(fpath).name
                for h in self.all_hits.get(fpath, []):
                    w.writerow([
                        filename,
                        h.frame,
                        h.time_s if h.time_s is not None else "",
                        seconds_to_hhmmssms(h.time_s) if h.time_s is not None else "",
                        f"{h.pblack:.6f}" if h.pblack is not None else "",
                        h.pts if h.pts is not None else "",
                    ])

    def export_frames_json(self):
        has_frames = any(len(h) > 0 for h in self.all_hits.values())
        if not has_frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Frames JSON", "black_frames.json", "JSON (*.json)")
        if not path:
            return
        payload = []
        for fpath in self._file_queue:
            filename = Path(fpath).name
            for h in self.all_hits.get(fpath, []):
                d = asdict(h)
                d["file"] = filename
                d["timestamp"] = seconds_to_hhmmssms(h.time_s) if h.time_s is not None else None
                payload.append(d)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def export_ranges_csv(self):
        has_ranges = any(len(r) > 0 for r in self.all_ranges.values())
        if not has_ranges:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Ranges CSV", "black_ranges.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["file", "start_frame", "end_frame", "start_timestamp", "end_timestamp", "length_frames", "avg_pblack", "min_pblack"])
            for fpath in self._file_queue:
                filename = Path(fpath).name
                for r in self.all_ranges.get(fpath, []):
                    w.writerow([
                        filename,
                        r.start_frame,
                        r.end_frame,
                        seconds_to_hhmmssms(r.start_time_s) if r.start_time_s is not None else "",
                        seconds_to_hhmmssms(r.end_time_s) if r.end_time_s is not None else "",
                        r.length_frames,
                        f"{r.avg_pblack:.6f}" if r.avg_pblack is not None else "",
                        f"{r.min_pblack:.6f}" if r.min_pblack is not None else "",
                    ])

    def export_ranges_json(self):
        has_ranges = any(len(r) > 0 for r in self.all_ranges.values())
        if not has_ranges:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Ranges JSON", "black_ranges.json", "JSON (*.json)")
        if not path:
            return
        payload = []
        for fpath in self._file_queue:
            filename = Path(fpath).name
            for r in self.all_ranges.get(fpath, []):
                d = asdict(r)
                d["file"] = filename
                d["start_timestamp"] = seconds_to_hhmmssms(r.start_time_s) if r.start_time_s is not None else None
                d["end_timestamp"] = seconds_to_hhmmssms(r.end_time_s) if r.end_time_s is not None else None
                payload.append(d)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = BlackFrameDetectorV2()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
