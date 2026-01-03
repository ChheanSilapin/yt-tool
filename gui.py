"""
YouTube Shorts Tool - PyQt6 GUI
Two tabs: Shorts Downloader + Subtitle Generator
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from main import get_shorts_list, download_short

# Consistent font
FONT_FAMILY = "Cascadia Code"


# ==================== DOWNLOAD WORKER ====================

class DownloadWorker(QThread):
    """Background worker with parallel downloads (4 concurrent)."""
    
    progress = pyqtSignal(int, int, float)
    status = pyqtSignal(str)
    finished_download = pyqtSignal(int, int)
    error = pyqtSignal(str)
    
    MAX_WORKERS = 4
    
    def __init__(self, channel_url: str, output_dir: Path, include_id: bool = True):
        super().__init__()
        self.channel_url = channel_url
        self.output_dir = output_dir
        self.include_id = include_id
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
    
    def run(self):
        try:
            self.status.emit("Fetching Shorts list...")
            shorts_list = get_shorts_list(self.channel_url)
            
            if not shorts_list:
                self.error.emit("No Shorts found on this channel")
                return
            
            total = len(shorts_list)
            self.status.emit(f"Found {total} shorts. Starting parallel download...")
            
            metadata_list = []
            completed = 0
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                future_to_short = {
                    executor.submit(download_short, short['url'], self.output_dir, self.include_id): short
                    for short in shorts_list
                }
                
                for future in as_completed(future_to_short):
                    if self._is_cancelled:
                        executor.shutdown(wait=False, cancel_futures=True)
                        self.status.emit("Download cancelled")
                        break
                    
                    short = future_to_short[future]
                    completed += 1
                    
                    elapsed = time.time() - start_time
                    speed_mbps = (completed * 2.0) / elapsed if elapsed > 0 else 0.0
                    
                    self.progress.emit(completed, total, speed_mbps)
                    
                    try:
                        metadata = future.result()
                        if metadata:
                            metadata_list.append(metadata)
                            self.status.emit(f'Downloaded: {metadata.get("title", "")[:30]}...')
                    except Exception:
                        self.status.emit(f'Failed: {short["title"][:30]}...')
            
            self.finished_download.emit(len(metadata_list), total)
            
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")


# ==================== SUBTITLE WORKER ====================

class SubtitleWorker(QThread):
    """Background worker for subtitle generation."""
    
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished = pyqtSignal(int, int)
    error = pyqtSignal(str)
    
    def __init__(self, input_paths: list, output_dir: Path):
        super().__init__()
        self.input_paths = input_paths
        self.output_dir = output_dir
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
    
    def run(self):
        try:
            from subtitle_service import process_single_video
            
            total = len(self.input_paths)
            success = 0
            
            for i, input_path in enumerate(self.input_paths, 1):
                if self._is_cancelled:
                    self.status.emit("Processing cancelled")
                    break
                
                self.progress.emit(i, total)
                self.status.emit(f"Processing: {input_path.name}")
                
                output_path = self.output_dir / f"{input_path.stem}_subtitled{input_path.suffix}"
                
                if process_single_video(input_path, output_path):
                    success += 1
                    self.status.emit(f"Completed: {output_path.name}")
                else:
                    self.status.emit(f"Failed: {input_path.name}")
            
            self.finished.emit(success, total)
            
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")


def get_timestamp():
    return datetime.now().strftime("[%H:%M:%S]")


# ==================== DOWNLOAD TAB ====================

class DownloadTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.output_path = str(Path.home() / "Downloads" / "YouTube_Shorts")
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Channel URL
        layout.addWidget(self._label("Channel URL"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/@channelname/shorts")
        self.url_input.setFont(QFont(FONT_FAMILY, 10))
        self.url_input.setMinimumHeight(32)
        layout.addWidget(self.url_input)
        
        # Save Location
        layout.addWidget(self._label("Save Location"))
        save_row = QHBoxLayout()
        self.path_input = QLineEdit(self.output_path)
        self.path_input.setFont(QFont(FONT_FAMILY, 10))
        self.path_input.setMinimumHeight(32)
        self.path_input.setReadOnly(True)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setMinimumHeight(32)
        self.browse_btn.setFixedWidth(70)
        self.browse_btn.clicked.connect(self.browse_folder)
        save_row.addWidget(self.path_input, 1)
        save_row.addWidget(self.browse_btn)
        layout.addLayout(save_row)
        
        # Options
        self.include_id_checkbox = QCheckBox("Include video ID in filename")
        self.include_id_checkbox.setFont(QFont(FONT_FAMILY, 9))
        self.include_id_checkbox.setChecked(False)
        self.include_id_checkbox.setStyleSheet("color:#9CA3AF;")
        layout.addWidget(self.include_id_checkbox)
        
        # Buttons
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Start Download")
        self.download_btn.setFont(QFont(FONT_FAMILY, 10))
        self.download_btn.setMinimumHeight(32)
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setObjectName("action_btn")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFont(QFont(FONT_FAMILY, 10))
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setObjectName("cancel_btn")
        
        btn_row.addWidget(self.download_btn, 1)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)
        
        # Activity Log Header
        log_header = QHBoxLayout()
        log_label = QLabel("Activity Log")
        log_label.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
        log_label.setStyleSheet("color:#D1D5DB;")
        
        self.progress_label = QLabel("0/0")
        self.progress_label.setFont(QFont(FONT_FAMILY, 9))
        self.progress_label.setStyleSheet("color:#9CA3AF;background:#1F2937;padding:3px 8px;border-radius:4px;")
        
        self.speed_label = QLabel("0.0 MB/s")
        self.speed_label.setFont(QFont(FONT_FAMILY, 9))
        self.speed_label.setStyleSheet("color:#6B7280;background:#1F2937;padding:3px 8px;border-radius:4px;")
        
        self.status_label = QLabel("Ready")
        self.status_label.setFont(QFont(FONT_FAMILY, 9))
        self.status_label.setStyleSheet("color:#10B981;background:#1F2937;padding:3px 8px;border-radius:4px;")
        
        log_header.addWidget(log_label)
        log_header.addWidget(self.progress_label)
        log_header.addStretch()
        log_header.addWidget(self.speed_label)
        log_header.addWidget(self.status_label)
        layout.addLayout(log_header)
        
        # Log Text
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont(FONT_FAMILY, 9))
        layout.addWidget(self.log_text, 1)
        
        self.log("Ready for input.")
    
    def _label(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_FAMILY, 10))
        lbl.setStyleSheet("color:#9CA3AF;")
        return lbl
    
    def log(self, msg):
        self.log_text.append(f"{get_timestamp()} {msg}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", self.output_path)
        if folder:
            self.output_path = folder
            self.path_input.setText(folder)
    
    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self.log("ERROR: Please enter a channel URL")
            return
        
        if '/shorts' not in url:
            url = url.rstrip('/') + '/shorts'
        
        output_dir = Path(self.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.set_ui_busy(True)
        self.log(f"Starting download from: {url}")
        
        self.worker = DownloadWorker(url, output_dir, self.include_id_checkbox.isChecked())
        self.worker.progress.connect(self.on_progress)
        self.worker.status.connect(lambda m: self.log(m))
        self.worker.finished_download.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    def cancel_download(self):
        if self.worker:
            self.worker.cancel()
    
    def on_progress(self, current, total, speed):
        self.progress_label.setText(f"{current}/{total}")
        self.speed_label.setText(f"{speed:.1f} MB/s")
    
    def on_finished(self, success, total):
        self.log(f"Complete! {success}/{total} downloaded.")
        self.status_label.setText("Complete")
        self.status_label.setStyleSheet("color:#10B981;background:#1F2937;padding:3px 8px;border-radius:4px;")
        self.set_ui_busy(False)
    
    def on_error(self, msg):
        self.log(f"ERROR: {msg}")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color:#EF4444;background:#1F2937;padding:3px 8px;border-radius:4px;")
        self.set_ui_busy(False)
    
    def set_ui_busy(self, busy):
        self.download_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.browse_btn.setEnabled(not busy)
        self.url_input.setEnabled(not busy)
        self.include_id_checkbox.setEnabled(not busy)
        if busy:
            self.status_label.setText("Downloading")
            self.status_label.setStyleSheet("color:#F59E0B;background:#1F2937;padding:3px 8px;border-radius:4px;")
        if not busy:
            self.worker = None


# ==================== SUBTITLE TAB ====================

class SubtitleTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.input_paths = []
        self.output_path = str(Path.home() / "Downloads" / "Subtitled")
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Input File/Folder
        layout.addWidget(self._label("Input Video(s)"))
        input_row = QHBoxLayout()
        self.input_display = QLineEdit()
        self.input_display.setPlaceholderText("Select video file or folder...")
        self.input_display.setFont(QFont(FONT_FAMILY, 10))
        self.input_display.setMinimumHeight(32)
        self.input_display.setReadOnly(True)
        
        self.file_btn = QPushButton("File")
        self.file_btn.setMinimumHeight(32)
        self.file_btn.setFixedWidth(50)
        self.file_btn.clicked.connect(self.browse_file)
        
        self.folder_btn = QPushButton("Folder")
        self.folder_btn.setMinimumHeight(32)
        self.folder_btn.setFixedWidth(60)
        self.folder_btn.clicked.connect(self.browse_input_folder)
        
        input_row.addWidget(self.input_display, 1)
        input_row.addWidget(self.file_btn)
        input_row.addWidget(self.folder_btn)
        layout.addLayout(input_row)
        
        # Output Directory
        layout.addWidget(self._label("Output Directory"))
        output_row = QHBoxLayout()
        self.output_input = QLineEdit(self.output_path)
        self.output_input.setFont(QFont(FONT_FAMILY, 10))
        self.output_input.setMinimumHeight(32)
        self.output_input.setReadOnly(True)
        
        self.output_btn = QPushButton("Browse")
        self.output_btn.setMinimumHeight(32)
        self.output_btn.setFixedWidth(70)
        self.output_btn.clicked.connect(self.browse_output_folder)
        
        output_row.addWidget(self.output_input, 1)
        output_row.addWidget(self.output_btn)
        layout.addLayout(output_row)
        
        # Buttons
        btn_row = QHBoxLayout()
        self.process_btn = QPushButton("Generate Subtitles")
        self.process_btn.setFont(QFont(FONT_FAMILY, 10))
        self.process_btn.setMinimumHeight(32)
        self.process_btn.clicked.connect(self.start_processing)
        self.process_btn.setObjectName("action_btn")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFont(QFont(FONT_FAMILY, 10))
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setObjectName("cancel_btn")
        
        btn_row.addWidget(self.process_btn, 1)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)
        
        # Activity Log Header
        log_header = QHBoxLayout()
        log_label = QLabel("Activity Log")
        log_label.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
        log_label.setStyleSheet("color:#D1D5DB;")
        
        self.progress_label = QLabel("0/0")
        self.progress_label.setFont(QFont(FONT_FAMILY, 9))
        self.progress_label.setStyleSheet("color:#9CA3AF;background:#1F2937;padding:3px 8px;border-radius:4px;")
        
        self.status_label = QLabel("Ready")
        self.status_label.setFont(QFont(FONT_FAMILY, 9))
        self.status_label.setStyleSheet("color:#10B981;background:#1F2937;padding:3px 8px;border-radius:4px;")
        
        log_header.addWidget(log_label)
        log_header.addWidget(self.progress_label)
        log_header.addStretch()
        log_header.addWidget(self.status_label)
        layout.addLayout(log_header)
        
        # Log Text
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont(FONT_FAMILY, 9))
        layout.addWidget(self.log_text, 1)
        
        self.log("Ready for input.")
    
    def _label(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_FAMILY, 10))
        lbl.setStyleSheet("color:#9CA3AF;")
        return lbl
    
    def log(self, msg):
        self.log_text.append(f"{get_timestamp()} {msg}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def browse_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm)"
        )
        if file:
            self.input_paths = [Path(file)]
            self.input_display.setText(file)
    
    def browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            folder_path = Path(folder)
            video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}
            videos = [f for f in folder_path.iterdir() if f.suffix.lower() in video_extensions]
            self.input_paths = videos
            self.input_display.setText(f"{folder} ({len(videos)} videos)")
    
    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_path)
        if folder:
            self.output_path = folder
            self.output_input.setText(folder)
    
    def start_processing(self):
        if not self.input_paths:
            self.log("ERROR: Please select input video(s)")
            return
        
        output_dir = Path(self.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.set_ui_busy(True)
        self.log(f"Processing {len(self.input_paths)} video(s)...")
        
        self.worker = SubtitleWorker(self.input_paths, output_dir)
        self.worker.progress.connect(self.on_progress)
        self.worker.status.connect(lambda m: self.log(m))
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    def cancel_processing(self):
        if self.worker:
            self.worker.cancel()
    
    def on_progress(self, current, total):
        self.progress_label.setText(f"{current}/{total}")
    
    def on_finished(self, success, total):
        self.log(f"Complete! {success}/{total} processed.")
        self.status_label.setText("Complete")
        self.status_label.setStyleSheet("color:#10B981;background:#1F2937;padding:3px 8px;border-radius:4px;")
        self.set_ui_busy(False)
    
    def on_error(self, msg):
        self.log(f"ERROR: {msg}")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color:#EF4444;background:#1F2937;padding:3px 8px;border-radius:4px;")
        self.set_ui_busy(False)
    
    def set_ui_busy(self, busy):
        self.process_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.file_btn.setEnabled(not busy)
        self.folder_btn.setEnabled(not busy)
        self.output_btn.setEnabled(not busy)
        if busy:
            self.status_label.setText("Processing")
            self.status_label.setStyleSheet("color:#F59E0B;background:#1F2937;padding:3px 8px;border-radius:4px;")
        if not busy:
            self.worker = None


# ==================== MAIN WINDOW ====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("YT-Tool")
        self.setFixedSize(640, 540)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab Widget
        tabs = QTabWidget()
        tabs.setFont(QFont(FONT_FAMILY, 10))
        
        # Add tabs
        tabs.addTab(DownloadTab(), "⬇ Shorts Downloader")
        tabs.addTab(SubtitleTab(), "📝 Subtitle Generator")
        
        layout.addWidget(tabs)
        
        # Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(15, 5, 15, 10)
        footer_left = QLabel("PyQt6 MVP")
        footer_left.setFont(QFont(FONT_FAMILY, 8))
        footer_left.setStyleSheet("color:#4B5563;")
        footer_right = QLabel("Settings    Help")
        footer_right.setFont(QFont(FONT_FAMILY, 8))
        footer_right.setStyleSheet("color:#6B7280;")
        footer.addWidget(footer_left)
        footer.addStretch()
        footer.addWidget(footer_right)
        layout.addLayout(footer)
        
        # Styles
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: #111827; }}
            QTabWidget::pane {{
                border: none;
                background-color: #111827;
            }}
            QTabBar::tab {{
                background-color: #1F2937;
                color: #9CA3AF;
                padding: 10px 20px;
                border: none;
                font-family: "{FONT_FAMILY}";
            }}
            QTabBar::tab:selected {{
                background-color: #3B82F6;
                color: white;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #374151;
            }}
            QLineEdit {{
                background-color: #1F2937; color: #9CA3AF;
                border: 1px solid #374151; border-radius: 6px; padding: 0 12px;
                font-family: "{FONT_FAMILY}";
            }}
            QLineEdit:focus {{ border-color: #3B82F6; }}
            QPushButton {{
                font-family: "{FONT_FAMILY}"; font-weight: 600; border-radius: 6px;
                background-color: #1F2937; color: #D1D5DB; border: 1px solid #374151;
            }}
            QPushButton:hover {{ background-color: #374151; }}
            QPushButton#action_btn {{
                background-color: #3B82F6; color: white; border: none;
            }}
            QPushButton#action_btn:hover {{ background-color: #2563EB; }}
            QPushButton#action_btn:disabled {{ background-color: #4B5563; }}
            QPushButton#cancel_btn {{
                background-color: #1F2937; color: #F87171; border: 1px solid #374151;
            }}
            QPushButton#cancel_btn:hover {{ background-color: #374151; }}
            QPushButton#cancel_btn:disabled {{ color: #4B5563; }}
            QTextEdit {{
                background-color: #0D1117; color: #10B981;
                border: 1px solid #1F2937; border-radius: 6px; padding: 8px;
                font-family: "{FONT_FAMILY}";
            }}
            QCheckBox {{ color: #9CA3AF; }}
        """)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
