"""RiffLab Alpha 0.9.5 — local four-stem music practice desktop app."""
import json
import sqlite3
from datetime import datetime
import bisect
from array import array
from collections import Counter
import shutil
import traceback
import os
import re
import subprocess
import sys
import threading
import math
import time
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtGui import QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QPen, QColor, QBrush, QDrag

from PySide6.QtCore import QSize, QObject, Qt, QUrl, Signal, QTimer, QSettings, QRectF, QMimeData
import qtawesome as qta
from PySide6.QtSvg import QSvgRenderer
from realtime_audio import LiveStemPlayer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QVBoxLayout, QWidget, QScrollArea, QSpinBox, QGridLayout, QComboBox, QSizePolicy, QTabWidget, QTabBar, QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QDialogButtonBox, QDoubleSpinBox, QAbstractItemView, QSplitter, QSplitterHandle, QInputDialog, QMenu
)

def loop_boundary_icon(which):
    """Minimal IN / OUT bracket icons, without arrows or lettering."""
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor('#7bd6ff'), 4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    if which == 'in':
        painter.drawLine(16, 9, 16, 39)
        painter.drawLine(16, 9, 31, 9)
        painter.drawLine(16, 39, 31, 39)
    else:
        painter.drawLine(32, 9, 32, 39)
        painter.drawLine(17, 9, 32, 9)
        painter.drawLine(17, 39, 32, 39)
    painter.end()
    return QIcon(pix)


class LibraryDragTable(QTableWidget):
    """Drag saved project paths to the waveform or note grid."""
    def startDrag(self, supported_actions):
        row = self.currentRow()
        item = self.item(row, 1) if row >= 0 else None
        path = item.data(Qt.UserRole) if item else None
        if not path:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class ScrollingSongTitle(QWidget):
    """Transparent header title; scrolls only when its text is wider than the viewport."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ''
        self._offset = 0.0
        self._hold = 0
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._advance)
        self.setMinimumHeight(34)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        font = self.font()
        font.setPointSize(17)
        font.setBold(True)
        self.setFont(font)

    def setText(self, text):
        self._text = str(text or '')
        self._offset = 0.0
        self._hold = 35
        self.setToolTip(self._text)
        self._sync_timer()
        self.update()

    def _overflow(self):
        return self.fontMetrics().horizontalAdvance(self._text) > max(0, self.width()-20)

    def _sync_timer(self):
        if self._text and self._overflow():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._offset = 0.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_timer()

    def _advance(self):
        if self._hold > 0:
            self._hold -= 1
            return
        text_width = self.fontMetrics().horizontalAdvance(self._text)
        self._offset += 0.75
        if self._offset >= text_width + 65:
            self._offset = 0.0
            self._hold = 35
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setPen(QColor('#edf5fc'))
        painter.setFont(self.font())
        painter.setClipRect(self.rect().adjusted(8, 0, -8, 0))
        fm = self.fontMetrics()
        baseline = (self.height() + fm.ascent() - fm.descent()) // 2
        width = fm.horizontalAdvance(self._text)
        if not self._overflow():
            painter.drawText((self.width()-width)//2, baseline, self._text)
        else:
            x = 10 - round(self._offset)
            painter.drawText(x, baseline, self._text)
            painter.drawText(x + width + 65, baseline, self._text)
        painter.end()


class WaveformTimeline(QWidget):
    """Clickable, draggable audio waveform with live playhead and seek preview."""
    seekRequested = Signal(int)
    markerMoved = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.peaks = []
        self.duration_ms = 0
        self.position_ms = 0
        self.dragging = False
        self.marker_drag = None
        self.in_ms = None
        self.out_ms = None
        self.setMinimumHeight(72)
        self.setMaximumHeight(100)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('Click or drag to seek; chord grid follows playback')

    def set_waveform(self, peaks):
        self.peaks = list(peaks)
        self.update()

    def set_duration(self, ms):
        self.duration_ms = max(0, int(ms))
        self.update()

    def set_position(self, ms):
        self.position_ms = max(0, int(ms))
        self.update()

    def set_markers(self, in_ms, out_ms):
        self.in_ms = in_ms
        self.out_ms = out_ms
        self.update()

    def _marker_x(self, ms):
        return round(max(0, min(self.duration_ms, ms)) / max(1, self.duration_ms) * (self.width()-1))

    def _marker_at(self, x):
        if not self.duration_ms:
            return None
        candidates = [(abs(x-self._marker_x(ms)), which) for which, ms in
                      (('a', self.in_ms), ('b', self.out_ms)) if ms is not None]
        if not candidates:
            return None
        distance, which = min(candidates)
        return which if distance <= 11 else None

    def _move_marker(self, x):
        if self.marker_drag is None or not self.duration_ms:
            return
        ms = round(max(0.0, min(1.0, x/max(1, self.width()-1))) * self.duration_ms)
        if self.marker_drag == 'a':
            self.in_ms = ms
        else:
            self.out_ms = ms
        self.markerMoved.emit(self.marker_drag, ms)
        self.update()

    def _seek_from_x(self, x):
        if self.duration_ms <= 0:
            return
        fraction = max(0.0, min(1.0, x / max(1, self.width()-1)))
        position = round(fraction * self.duration_ms)
        self.set_position(position)
        self.seekRequested.emit(position)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.marker_drag = self._marker_at(event.position().x())
            if self.marker_drag:
                self._move_marker(event.position().x())
            else:
                self.dragging = True
                self._seek_from_x(event.position().x())
            event.accept()

    def mouseMoveEvent(self, event):
        if self.marker_drag:
            self._move_marker(event.position().x())
        elif self.dragging:
            self._seek_from_x(event.position().x())
        else:
            self.setCursor(Qt.SizeHorCursor if self._marker_at(event.position().x()) else Qt.PointingHandCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.marker_drag:
                self._move_marker(event.position().x())
                self.marker_drag = None
            elif self.dragging:
                self._seek_from_x(event.position().x())
                self.dragging = False
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor('#101a26'))
        painter.setPen(QPen(QColor('#2c4153'), 1))
        painter.drawRect(0, 0, w-1, h-1)
        # Time labels occupy the top 17 px; waveform occupies the remaining area.
        if self.duration_ms:
            minutes = self.duration_ms / 60000.0
            step = 10 if minutes <= 4 else (30 if minutes <= 12 else 60)
            for t in range(0, int(self.duration_ms / 1000) + 1, step):
                x = int(t * 1000 / self.duration_ms * (w-1))
                painter.setPen(QColor('#496276'))
                painter.drawLine(x, 17, x, h-2)
                painter.setPen(QColor('#9bb6c8'))
                painter.drawText(x+3, 12, f'{t//60}:{t%60:02d}')
        if self.peaks:
            mid = (h+18)//2
            half = max(2, (h-23)//2)
            painter.setPen(QPen(QColor('#527b97'), 1))
            n = len(self.peaks)
            for x in range(w):
                i = min(n-1, int(x*n/max(1,w)))
                amp = max(1, int(self.peaks[i]*half))
                painter.drawLine(x, mid-amp, x, mid+amp)
        else:
            painter.setPen(QColor('#70889a'))
            painter.drawText(12, (h+18)//2, 'Waveform appears when audio is loaded')
        # Loop region and inward-facing draggable bracket markers.
        if self.duration_ms:
            a = self._marker_x(self.in_ms) if self.in_ms is not None else None
            b = self._marker_x(self.out_ms) if self.out_ms is not None else None
            if a is not None and b is not None and b > a:
                painter.fillRect(a, 18, b-a, max(0, h-20), QColor(123, 214, 255, 24))
            painter.setRenderHint(QPainter.Antialiasing, True)
            for x, which in ((a, 'a'), (b, 'b')):
                if x is None:
                    continue
                painter.setPen(QPen(QColor('#7bd6ff'), 2))
                painter.drawLine(x, 18, x, h-3)
                # IN: [ ; OUT: ] — tips point toward the selected loop.
                tip = 9 if which == 'a' else -9
                painter.drawLine(x, 19, x+tip, 19)
                painter.drawLine(x, h-4, x+tip, h-4)
                painter.setPen(QColor('#cceeff'))
                painter.drawText(x+4 if which == 'a' else x-28, 12, 'IN' if which == 'a' else 'OUT')
            painter.setRenderHint(QPainter.Antialiasing, False)
        if self.duration_ms:
            x = int(min(1, self.position_ms / self.duration_ms) * (w-1))
            painter.setPen(QPen(QColor('#7bd6ff'), 2))
            painter.drawLine(x, 17, x, h-2)
            painter.setBrush(QBrush(QColor('#7bd6ff')))
            painter.drawEllipse(x-4, 14, 8, 8)
        painter.end()


def extract_waveform_peaks(source, count=1800):
    """Read waveform directly from audio files; no FFmpeg process needed for stems."""
    import numpy as np
    import soundfile as sf

    paths = ([str(source[name]) for name in STEMS]
             if isinstance(source, dict) else [str(source)])
    missing = [path for path in paths if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError('Waveform input missing: ' + ', '.join(missing[:2]))

    try:
        with __import__('contextlib').ExitStack() as stack:
            streams = [stack.enter_context(sf.SoundFile(path)) for path in paths]
            rates = {stream.samplerate for stream in streams}
            if len(rates) != 1:
                raise ValueError('Stem sample rates do not match')
            total_frames = max(stream.frames for stream in streams)
            if total_frames <= 0:
                raise ValueError('Audio contains no samples')
            bins = np.zeros(count, dtype=np.float32)
            chunk_size = 16384
            position = 0
            while position < total_frames:
                length = min(chunk_size, total_frames - position)
                mixed = np.zeros(length, dtype=np.float32)
                for stream in streams:
                    samples = stream.read(length, dtype='float32', always_2d=True)
                    if len(samples):
                        mixed[:len(samples)] += samples.mean(axis=1)
                # Place each sample in its timeline bin; retain the maximum amplitude.
                indices = np.minimum(count - 1,
                                     ((np.arange(length, dtype=np.int64) + position)
                                      * count // total_frames))
                np.maximum.at(bins, indices, np.abs(mixed))
                position += length
            return np.clip(bins, 0.0, 1.0).tolist()
    except (RuntimeError, OSError) as exc:
        # Some compressed formats are not supported by libsndfile; use FFmpeg.
        if isinstance(source, dict):
            raise RuntimeError(f'Cannot read stem WAV files: {exc}') from exc

    exe = shutil.which('ffmpeg')
    if not exe:
        bundled = Path(sys.executable).resolve().parent / 'bin' / 'ffmpeg.exe'
        if bundled.is_file():
            exe = str(bundled)
    if not exe:
        raise RuntimeError('Audio decoder unavailable: FFmpeg missing')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    proc = subprocess.run(
        [exe, '-v', 'error', '-i', paths[0], '-vn', '-ac', '1',
         '-ar', '2000', '-f', 's16le', '-'],
        capture_output=True, timeout=120, creationflags=flags)
    if proc.returncode:
        detail = proc.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'FFmpeg exited {proc.returncode}: {detail[-350:] or paths[0]}')
    pcm = np.frombuffer(proc.stdout[:len(proc.stdout)//2*2], dtype='<i2')
    if not len(pcm):
        raise RuntimeError('FFmpeg returned empty audio')
    bins = np.zeros(count, dtype=np.float32)
    indices = np.minimum(count - 1, np.arange(len(pcm), dtype=np.int64) * count // len(pcm))
    np.maximum.at(bins, indices, np.abs(pcm.astype(np.float32)) / 32768.0)
    return np.clip(bins, 0.0, 1.0).tolist()


class MinimalSplitterHandle(QSplitterHandle):
    """Eight-pixel drag target with a single centered one-pixel divider."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hovered = False
        self._dragging = False
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        color = '#7bd6ff' if self._dragging else ('#7291a8' if self._hovered else '#344758')
        painter.setPen(QPen(QColor(color), 1))
        if self.orientation() == Qt.Horizontal:
            x = self.width() // 2
            painter.drawLine(x, 0, x, self.height() - 1)
        else:
            y = self.height() // 2
            painter.drawLine(0, y, self.width() - 1, y)
        painter.end()


class MinimalSplitter(QSplitter):
    def createHandle(self):
        return MinimalSplitterHandle(self.orientation(), self)


ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'RiffLab'
ROOT.mkdir(parents=True, exist_ok=True)
# Expose bundled tools to yt-dlp and its JS runtime discovery.
if getattr(sys, 'frozen', False):
    os.environ['PATH'] = str(Path(sys.executable).resolve().parent / 'bin') + os.pathsep + os.environ.get('PATH', '')
STEMS = ('drums', 'bass', 'other', 'vocals')
STEM_ICONS = {'drums': 'fa5s.drum', 'bass': 'fa5s.guitar',
              'other': 'fa5s.music', 'vocals': 'fa5s.microphone'}
NOTES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')


def infer_song_metadata(path):
    """Read embedded tags using the existing FFprobe installation; never guess key/tuning."""
    path = Path(path)
    result = {'title': path.stem, 'artist': '', 'album': '', 'tuning': 'Unknown', 'musical_key': ''}
    try:
        exe = shutil.which('ffprobe')
        if exe:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            proc = subprocess.run([exe, '-v', 'quiet', '-show_entries', 'format_tags:stream_tags',
                                   '-of', 'json', str(path)], capture_output=True, text=True,
                                  timeout=12, creationflags=flags)
            if proc.returncode == 0:
                info = json.loads(proc.stdout)
                tags = {}
                for stream in info.get('streams', []):
                    tags.update({k.lower(): str(v) for k,v in stream.get('tags', {}).items()})
                tags.update({k.lower(): str(v) for k,v in info.get('format', {}).get('tags', {}).items()})
                for field, names in [('title', ('title',)), ('artist', ('artist', 'album_artist')),
                                     ('album', ('album',))]:
                    value = next((tags[n].strip() for n in names if tags.get(n, '').strip()), '')
                    if value:
                        result[field] = value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    if result['title'] == path.stem:
        match = re.match(r'^(.+?)\s+-\s+(.+)$', path.stem)
        if match:
            result['artist'], result['title'] = match.group(1).strip(), match.group(2).strip()
    return result


def valid_youtube_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme == 'https' and parsed.hostname in {
            'youtube.com', 'www.youtube.com', 'm.youtube.com',
            'music.youtube.com', 'youtu.be'
        }
    except ValueError:
        return False


def command(args):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    proc = subprocess.run(args, capture_output=True, text=True, creationflags=flags)
    if proc.returncode:
        detail = (proc.stderr or proc.stdout or '').strip()
        if not detail:
            detail = (
                f'AI subprocess exited with code {proc.returncode} without output. '
                f'Executable: {args[0]}. '
                'Possible native DLL or PyInstaller startup failure.'
            )
        raise RuntimeError(detail[-2500:])
    return proc.stdout


def ffmpeg_path():
    """Return a directory containing BOTH ffmpeg and ffprobe for yt-dlp."""
    exe_dir = Path(sys.executable).resolve().parent
    # Frozen PyInstaller apps may resolve __file__ inside _internal.
    # Prefer the portable application's bundled tools beside RiffLab.exe.
    search_dirs = [exe_dir / 'bin', exe_dir, Path(__file__).resolve().parent / 'bin']
    ffmpeg_exe = shutil.which('ffmpeg')
    ffprobe_exe = shutil.which('ffprobe')
    # A PATH-installed Chocolatey shim may be broken. Always prefer our
    # tested portable binaries before trying anything installed globally.
    if ffmpeg_exe:
        search_dirs.append(Path(ffmpeg_exe).resolve().parent)
    if ffprobe_exe:
        search_dirs.append(Path(ffprobe_exe).resolve().parent)
    for folder in search_dirs:
        if (folder / 'ffmpeg.exe').is_file() and (folder / 'ffprobe.exe').is_file():
            return str(folder)
    if ffmpeg_exe and ffprobe_exe:
        # Separate PATH directories are supported by yt-dlp; do not point
        # ffmpeg_location at one incomplete directory.
        return None
    raise RuntimeError('FFmpeg en FFprobe ontbreken. Controleer met: Get-Command ffmpeg, ffprobe')


class AnalysisCancelled(Exception):
    """A user-requested cancellation, not an AI processing failure."""


def worker_command(*args, cancel_event=None):
    """Run the AI worker; support cancelling long analysis jobs on Windows."""
    if not getattr(sys, 'frozen', False):
        command_args = [sys.executable, str(Path(__file__).resolve().parent / 'ai_worker.py'), *map(str, args)]
        env = None
    else:
        worker = Path(sys.executable).resolve().parent / 'RiffLabAI' / 'RiffLabAI.exe'
        if not worker.is_file():
            raise RuntimeError(f'AI worker missing: {worker}. Keep the entire RiffLab folder together.')
        command_args = [str(worker), *map(str, args)]
        env = os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        for name in ('PYTHONHOME', 'PYTHONPATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                     'QT_PLUGIN_PATH', 'QT_QPA_FONTDIR'):
            env.pop(name, None)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled()
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        # Prevent a second PyInstaller executable inheriting the UI DLL path.
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        proc = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                creationflags=flags, env=env)
    finally:
        if os.name == 'nt' and getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(str(Path(sys._MEIPASS)))
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=0.2 if cancel_event else None)
                break
            except subprocess.TimeoutExpired:
                if cancel_event is not None and cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    raise AnalysisCancelled()
        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelled()
        if proc.returncode:
            detail = (stderr or stdout or '').strip()
            if not detail:
                detail = (f'AI worker exited with code {proc.returncode} '
                          f'(0x{proc.returncode & 0xffffffff:08X}). '
                          'Check the packaged AI worker runtime/DLLs.')
            raise RuntimeError(detail[-2500:])
        return stdout
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def mix_to_file(stem_paths, levels, transpose, output):
    # Transpose is notation-only. Preserve original audio pitch in every mix/export.
    worker_command('mix', str(output), json.dumps({name: str(stem_paths[name]) for name in STEMS}),
                   json.dumps(levels), '0')


class TunerMeter(QWidget):
    """Read-only, high-contrast tuning needle: center is in tune (0 cents)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cents = 0.0
        self.signal_active = False
        self.setMinimumHeight(76)
        self.setToolTip('Pitch deviation in cents: flat on the left, sharp on the right, in tune at center.')

    def set_reading(self, cents, active=True):
        self.cents = max(-50.0, min(50.0, float(cents)))
        self.signal_active = bool(active)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        left, right = 27, max(28, width - 27)
        middle = (left + right) / 2
        y = 38
        painter.setPen(QPen(QColor('#38566c'), 3))
        painter.drawLine(left, y, right, y)
        for cent in range(-50, 51, 10):
            x = round(middle + cent * (right-left) / 100)
            is_center = cent == 0
            painter.setPen(QPen(QColor('#66d2c1' if is_center else '#54778e'),
                                2 if is_center else 1))
            painter.drawLine(x, y - (14 if is_center else 7),
                             x, y + (14 if is_center else 7))
        painter.setPen(QColor('#98b9ce'))
        painter.drawText(left-8, 70, '-50')
        painter.drawText(round(middle)-5, 70, '0')
        painter.drawText(right-17, 70, '+50')
        if self.signal_active:
            x = round(middle + self.cents * (right-left) / 100)
            color = QColor('#51dec1' if abs(self.cents) <= 5 else '#f2ba66')
            painter.setPen(QPen(color, 3))
            painter.drawLine(x, y-21, x, y+21)
        painter.end()


class Signals(QObject):
    status = Signal(str)
    stage = Signal(str)
    separated = Signal(str)
    chords = Signal(object)
    mixed = Signal(str, int, bool)
    error = Signal(str)
    beats = Signal(object)
    exported = Signal(str)
    analysis_done = Signal()
    speed_ready = Signal(object, float, int)
    downloaded_metadata = Signal(object)
    waveform_ready = Signal(str, object)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            from build_info import BUILD_NUMBER
        except ImportError:
            BUILD_NUMBER = 'local'
        self.setWindowTitle(f"StevieBlitz's RiffLab — Alpha v0.2.0-dev.{BUILD_NUMBER}")
        self.assets_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets'
        self.brand_asset = self.assets_dir / 'rifflab-logo.svg'
        self.new_brand_asset = self.assets_dir / 'rifflab-brand.png'
        # Windows titlebar icon is the supplied RL mark. The .exe / desktop
        # icon is intentionally different: the standalone Erlenmeyer flask.
        window_icon = self.assets_dir / 'rifflab-window-icon.png'
        if window_icon.is_file():
            self.setWindowIcon(QIcon(str(window_icon)))
        self.resize(1280, 800)
        self.layout_settings = QSettings('RiffLab', 'RiffLab')
        self.setMinimumSize(640, 430)
        self.setAcceptDrops(True)
        self.signals = Signals()
        self.signals.status.connect(self.status_message)
        self.signals.stage.connect(self.set_stage)
        self.signals.separated.connect(self.on_separated)
        self.signals.chords.connect(self.on_chords)
        self.signals.mixed.connect(self.on_mixed)
        self.signals.error.connect(self.on_error)
        self.signals.beats.connect(self.on_beats)
        self.signals.analysis_done.connect(self.on_analysis_done)
        self.signals.speed_ready.connect(self.on_speed_ready)
        self.signals.downloaded_metadata.connect(self.on_downloaded_metadata)
        self.signals.waveform_ready.connect(self.on_waveform_ready)
        self._waveform_source = None
        self.song_metadata = {}
        self.speed_ratio = 1.0
        self.detected_bpm = 130.0
        self.speed_generation = 0
        self.signals.exported.connect(lambda path: self.status_message(f'WAV saved: {path}'))
        self.stems = {}
        self.live = None
        self.folder = None
        self.chord_data = []
        self.chord_times = []
        self.display_chords = []
        self.display_times = []
        self.processing = False
        self.import_stage = ''
        self.mixing = False
        self.pending_mix = False
        self.mix_counter = 0
        self._seek_after_load = None
        self._play_after_load = False
        self._duration = 0
        self.grid_buttons = []
        self.grid_cells = []
        self.grid_active = -1
        self.grid_row = -1
        self.beat_times = []
        self.pattern_matches = {}
        self.section_overrides = {}
        self.beat_offset = 0.0
        self.loop_enabled = False
        self.loop_a_ms = None
        self.loop_b_ms = None
        self.source_audio = None
        self.analysis_running = False
        self.analysis_cancel = threading.Event()
        self._last_render_duration = 0
        self.tuner_stream = None
        self.tuner_pitch = 0.0
        self.tuner_level = 0.0
        self.tuner_last = 0.0
        self._tuner_display_cents = None
        self.project_file = None
        self._pending_project = None
        self.library_db = ROOT / "library.sqlite3"
        self.init_library()

        main = QWidget()
        self.setCentralWidget(main)
        outer = QVBoxLayout(main)
        layout = outer
        project_header = QWidget()
        project_header.setObjectName('projectHeader')
        project_row = QHBoxLayout(project_header)
        project_row.setContentsMargins(10, 0, 10, 0)
        project_row.setSpacing(8)
        project_header.setFixedHeight(42)
        self.header_import = QPushButton('Import / Export')
        self.header_import.setIcon(qta.icon('fa5s.exchange-alt', color='#7bd6ff'))
        self.header_import.setToolTip('Open the complete Import / Export workspace')
        self.header_import.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        project_row.addWidget(self.header_import)
        self.header_practice = QPushButton('Practice')
        self.header_practice.setIcon(qta.icon('fa5s.play-circle', color='#7bd6ff'))
        self.header_practice.setToolTip('Return to the note timeline and stem mixer')
        self.header_practice.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        self.header_practice.setText('Practice')
        self.header_practice.setObjectName('practiceNav')
        self.header_practice.setAccessibleName('Practice timeline')
        self.project_save = QPushButton('Save')
        self.project_save.setIcon(qta.icon('fa5s.save', color='#7bd6ff'))
        self.project_save.setToolTip('Save project (Ctrl+S)')
        self.project_save.clicked.connect(self.save_project)
        self.project_save.setText('')
        self.project_save.setFixedSize(32, 30)
        self.project_save.setAccessibleName('Save project')
        project_row.addWidget(self.project_save)
        self.project_load = QPushButton('Open')
        self.project_load.setIcon(qta.icon('fa5s.folder-open', color='#7bd6ff'))
        self.project_load.setToolTip('Open a saved project (Ctrl+O)')
        self.project_load.clicked.connect(self.open_project)
        self.project_load.setText('')
        self.project_load.setFixedSize(32, 30)
        self.project_load.setAccessibleName('Open project')
        project_row.addWidget(self.project_load)
        project_row.addWidget(QLabel('◷ Recent'))
        self.recent_projects = QComboBox()
        self.recent_projects.setMinimumWidth(100)
        self.recent_projects.setToolTip('Quickly switch between saved songs')
        self.recent_projects.activated.connect(self.open_recent_project)
        self.recent_projects.setMaximumWidth(185)
        self.recent_projects.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        project_row.addWidget(self.recent_projects)
        self.now_playing = ScrollingSongTitle()
        self.now_playing.setObjectName('nowPlayingTitle')
        self.now_playing.setMinimumWidth(115)
        self.now_playing.setMaximumWidth(260)
        self.now_playing.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.now_playing.setMinimumHeight(40)
        project_row.addWidget(self.now_playing)
        # Compact playback clock is displayed beside the transport buttons.
        self.time_label = QLabel('00:00 / 00:00')
        self.time_label.setObjectName('timeLabel')
        self.time_label.setFixedWidth(135)
        self.time_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.time_label.setToolTip('Current playback position / track duration')
        self.header_time_label = QLabel('00:00 / 00:00')
        self.header_time_label.setObjectName('headerTimeLabel')
        self.header_time_label.setFixedWidth(120)
        self.header_time_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.header_time_label.setToolTip('Playback time (also shown in transport)')
        project_row.addWidget(self.header_time_label)
        self.header_tuner = QPushButton('Tuner')
        self.header_tuner.setObjectName('headerTuner')
        self.header_tuner.setMinimumWidth(78)
        self.header_tuner.setFixedHeight(32)
        self.header_tuner.setIcon(self.tuning_fork_icon())
        self.header_tuner.setIconSize(QSize(22, 22))
        self.header_tuner.setToolTip('Open Chromatic Tuner (Ctrl+Shift+T)')
        self.header_tuner.clicked.connect(self.toggle_tuner_panel)
        project_row.addStretch(1)
        # A genuine QTabBar is docked inline in this header, not on a second row.
        self.update_now_playing()
        # This widget is installed in the left corner of the main tab bar below.
        self.refresh_recent_projects()
        self.shortcuts = []
        for sequence, callback in (
            ('Space', self._shortcut_play), ('Escape', self._shortcut_stop),
            ('I', lambda: self._shortcut_marker('a')),
            ('O', lambda: self._shortcut_marker('b')),
            ('Ctrl+S', self.save_project), ('Ctrl+O', self.open_project),
            ('Ctrl+V', self.paste_youtube_link),
            ('Ctrl+1', lambda: self.tabs.setCurrentIndex(0)),
            ('Ctrl+2', lambda: self.tabs.setCurrentIndex(1)),
            ('Ctrl+3', lambda: self.tabs.setCurrentIndex(2)),
            ('Ctrl+Shift+O', self.open_file),
            ('Ctrl+Shift+T', self.toggle_tuner_panel),
            ('Ctrl+R', self.reanalyze_current),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.status = QLabel('Ready. Open an audio file or paste a YouTube URL.')
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat('Ready')
        self.progress.setTextVisible(True)
        # One compact header row shared with the right-aligned navigation tabs.
        # Avoid an extra toolbar row and prevent expanding Save/Open buttons.
        self.tabs = QTabWidget()
        self.tabs.setObjectName('mainTabs')
        outer.addWidget(project_header, 0)
        outer.addWidget(self.tabs, 1)
        def tab_page(name):
            page = QWidget()
            self.tabs.addTab(page, name)
            tab_layout = QVBoxLayout(page)
            tab_layout.setContentsMargins(10, 8, 10, 8)
            tab_layout.setSpacing(8)
            return tab_layout
        practice_layout = tab_page('Play Along')
        library_layout = tab_page('Library')
        io_layout = tab_page('Import / Export')
        self.tabs.setTabIcon(0, qta.icon('fa5s.play-circle', color='#7bd6ff'))
        self.tabs.setTabIcon(1, qta.icon('fa5s.book', color='#9bb7cb'))
        self.tabs.setTabIcon(2, qta.icon('fa5s.exchange-alt', color='#9bb7cb'))
        self.tabs.setTabToolTip(0, 'Note Timeline / Playback')
        self.tabs.setCurrentIndex(0)
        self.tabs.tabBar().setObjectName('mainTabBar')
        # Project controls have fixed widths, leaving the right-hand tabs visible.
        self.tuner_dialog = QDialog(self)
        self.tuner_dialog.setWindowTitle("StevieBlitz's RiffLab · Chromatic Tuner")
        self.tuner_dialog.setMinimumWidth(430)
        self.tuner_dialog.setModal(False)
        tuner_layout = QVBoxLayout(self.tuner_dialog)
        tuner_layout.setContentsMargins(18, 18, 18, 18)
        tuner_layout.setSpacing(12)
        # Local searchable song library, backed by SQLite.
        library_filters = QVBoxLayout()
        library_filters.setSpacing(3)
        advanced_filters = QVBoxLayout()
        advanced_filters.setSpacing(5)
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText('Search song, artist or album…')
        self.library_search.textChanged.connect(self.refresh_library)
        library_filters.addWidget(self.library_search)
        self.library_tuning = QComboBox()
        self.library_tuning.addItems(['All tunings', 'Unknown', 'E Standard', 'Eb Standard', 'D Standard',
                                      'Drop D', 'Drop C#', 'Drop C', 'Other'])
        self.library_tuning.currentIndexChanged.connect(self.refresh_library)
        advanced_filters.addWidget(self.library_tuning)
        self.library_min_bpm = QSpinBox()
        self.library_min_bpm.setRange(0, 300)
        self.library_min_bpm.setValue(0)
        self.library_min_bpm.setPrefix('From ')
        self.library_min_bpm.setSuffix(' BPM')
        self.library_min_bpm.valueChanged.connect(self.refresh_library)
        bpm_filter_row = QHBoxLayout()
        bpm_filter_row.setSpacing(5)
        bpm_filter_row.addWidget(self.library_min_bpm)
        self.library_max_bpm = QSpinBox()
        self.library_max_bpm.setRange(0, 300)
        self.library_max_bpm.setValue(300)
        self.library_max_bpm.setPrefix('To ')
        self.library_max_bpm.setSuffix(' BPM')
        self.library_max_bpm.valueChanged.connect(self.refresh_library)
        bpm_filter_row.addWidget(self.library_max_bpm)
        advanced_filters.addLayout(bpm_filter_row)
        self.library_advanced_panel = QWidget()
        self.library_advanced_panel.setObjectName('libraryAdvanced')
        self.library_advanced_panel.setLayout(advanced_filters)
        self.library_advanced_panel.hide()
        self.library_filter_toggle = QPushButton('Filters  ▾')
        self.library_filter_toggle.setObjectName('libraryFilterToggle')
        self.library_filter_toggle.setCheckable(True)
        self.library_filter_toggle.setToolTip('Show or hide tuning and BPM filters')
        self.library_filter_toggle.toggled.connect(self.library_advanced_panel.setVisible)
        self.library_filter_toggle.toggled.connect(
            lambda checked: self.library_filter_toggle.setText('Filters  ▴' if checked else 'Filters  ▾'))
        library_filters.addWidget(self.library_filter_toggle)
        library_filters.addWidget(self.library_advanced_panel)
        library_layout.addLayout(library_filters)
        library_toolbar = QVBoxLayout()
        library_toolbar.setSpacing(3)
        library_filter_row = QHBoxLayout()
        library_filter_row.setSpacing(4)
        library_actions = QGridLayout()
        library_actions.setSpacing(5)
        self.library_favorites = QCheckBox('Favorites only')
        self.library_favorites.toggled.connect(self.refresh_library)
        library_filter_row.addWidget(self.library_favorites)
        self.library_sort = QComboBox()
        self.library_sort.addItems(['Title', 'Artist', 'Original BPM', 'Recently played'])
        self.library_sort.currentIndexChanged.connect(self.refresh_library)
        self.library_sort.setMinimumWidth(110)
        library_filter_row.addWidget(self.library_sort, 1)
        library_toolbar.addLayout(library_filter_row)
        self.library_add = QPushButton('Add')
        self.library_add.setToolTip('Save the current song as a project and add it to Library')
        self.library_add.clicked.connect(self.add_current_to_library)
        library_actions.addWidget(self.library_add, 0, 0)
        self.library_edit = QPushButton('Details')
        self.library_edit.clicked.connect(self.edit_library_song)
        library_actions.addWidget(self.library_edit, 0, 1)
        self.library_star = QPushButton('Favorite')
        self.library_star.clicked.connect(self.toggle_library_favorite)
        library_actions.addWidget(self.library_star, 1, 0)
        self.library_remove = QPushButton('Remove')
        self.library_remove.setToolTip('Remove from library only; keep project and audio files')
        self.library_remove.clicked.connect(self.remove_library_song)
        library_actions.addWidget(self.library_remove, 1, 1)
        # Compact icon-only actions; the existing callbacks and confirmation stay.
        library_icons = QHBoxLayout()
        library_icons.setSpacing(3)
        for button, icon_name, hint in (
            (self.library_add, 'fa5s.plus', 'Add current song to Library'),
            (self.library_edit, 'fa5s.edit', 'Edit selected song details'),
            (self.library_star, 'fa5s.star', 'Toggle selected song favorite'),
            (self.library_remove, 'fa5s.trash-alt', 'Remove selected song from Library (keeps files)'),
        ):
            button.setText('')
            button.setIcon(qta.icon(icon_name, color='#7bd6ff'))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(26, 26)
            button.setObjectName('libraryIconAction')
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(hint)
            button.setAccessibleName(hint)
            library_icons.addWidget(button)
        library_icons.addStretch(1)
        library_toolbar.addLayout(library_icons)
        self.library_table = LibraryDragTable(0, 8)
        self.library_table.setObjectName('librarySongTable')
        self.library_table.setHorizontalHeaderLabels(
            ['★', 'Artist · Song', 'Artist', 'Album', 'Tuning', 'BPM', 'Practice BPM', 'Last Played'])
        self.library_table.setDragEnabled(True)
        self.library_table.setDragDropMode(QAbstractItemView.DragOnly)
        self.library_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.library_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.library_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.library_table.setAlternatingRowColors(True)
        self.library_table.verticalHeader().hide()
        self.library_table.verticalHeader().setDefaultSectionSize(24)
        self.library_table.setShowGrid(False)
        self.library_table.setWordWrap(False)
        self.library_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.library_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.library_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        # Narrow sidebar: retain every data column for existing actions, but show a clean list.
        for column in range(2, 8):
            self.library_table.setColumnHidden(column, True)
        self.library_table.setColumnWidth(0, 22)
        self.library_table.horizontalHeader().setFixedHeight(22)
        self.library_table.horizontalHeader().setStretchLastSection(False)
        self.library_table.setToolTip('Double-click to open; drag a song onto the waveform or grid to load.')
        self.library_table.setMinimumHeight(180)
        self.library_table.doubleClicked.connect(self.open_library_song)
        self.library_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.library_table.customContextMenuRequested.connect(self.show_library_context_menu)
        for sequence, callback in (
            ('Return', self.open_library_song), ('Enter', self.open_library_song),
            ('F2', self.edit_library_song), ('Delete', self.remove_library_song),
            ('Ctrl+D', self.toggle_library_favorite),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self.library_table)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        library_layout.addWidget(self.library_table, 1)
        library_layout.addLayout(library_toolbar)
        self.library_summary = QLabel('Double-click a song to open its saved project.')
        self.library_summary.setObjectName('ioDescription')
        library_layout.addWidget(self.library_summary)
        self.refresh_library()
        # Migrate the existing Recent list and default projects without moving audio.
        self.discover_existing_projects()
        # Always-visible return path from Import / Export to the practice view.
        io_navigation = QHBoxLayout()
        io_navigation.setContentsMargins(0, 0, 0, 0)
        self.io_back_to_play = QPushButton('Play Along')
        self.io_back_to_play.setObjectName('ioBackToPlay')
        self.io_back_to_play.setIcon(qta.icon('fa5s.arrow-left', color='#7bd6ff'))
        self.io_back_to_play.setToolTip('Back to Play Along (Esc)')
        self.io_back_to_play.setAccessibleName('Back to Play Along')
        self.io_back_to_play.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        io_navigation.addWidget(self.io_back_to_play)
        io_navigation.addStretch(1)
        io_layout.addLayout(io_navigation)
        # Import and Export have distinct workspaces inside the main I/O tab.
        self.io_sections = QTabWidget()
        self.io_sections.setObjectName('ioSections')
        io_layout.addWidget(self.io_sections, 1)
        import_page = QWidget()
        export_page = QWidget()
        self.io_sections.addTab(import_page, qta.icon('fa5s.file-import', color='#7bd6ff'), 'Import')
        self.io_sections.addTab(export_page, qta.icon('fa5s.file-export', color='#7bd6ff'), 'Export')
        import_layout = QVBoxLayout(import_page)
        import_layout.setContentsMargins(12, 14, 12, 12)
        import_layout.setSpacing(12)
        export_layout = QVBoxLayout(export_page)
        export_layout.setContentsMargins(12, 14, 12, 12)
        export_layout.setSpacing(12)
        import_layout.addWidget(QLabel('IMPORT AUDIO'))
        io_intro = QLabel('Paste a YouTube link or open an audio file from your computer.')
        io_intro.setObjectName('ioDescription')
        import_layout.addWidget(io_intro)
        url_row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText('Paste YouTube URL…')
        url_row.addWidget(self.url, 1)
        self.load_url = QPushButton('Download & Split')
        self.load_url.clicked.connect(self.download_url)
        self.url.returnPressed.connect(self.download_url)
        url_row.addWidget(self.load_url)
        import_layout.addLayout(url_row)
        local_row = QHBoxLayout()
        self.load_file = QPushButton('Open Audio')
        self.load_file.clicked.connect(self.open_file)
        local_row.addWidget(self.load_file)
        self.split_local = QPushButton('Split Local')
        self.split_local.setEnabled(False)
        self.split_local.clicked.connect(lambda: self.start_split(self.source_audio) if self.source_audio else None)
        self.split_local.setIcon(qta.icon('fa5s.layer-group', color='white'))
        local_row.addWidget(self.split_local)
        self.analyze_local = QPushButton('Analyze')
        self.analyze_local.setEnabled(False)
        self.analyze_local.clicked.connect(self.analyze_current)
        self.analyze_local.setIcon(qta.icon('fa5s.wave-square', color='white'))
        local_row.addWidget(self.analyze_local)
        local_row.addStretch()
        import_layout.addLayout(local_row)
        import_layout.addStretch(1)

        export_layout.addWidget(QLabel('EXPORT AUDIO'))
        export_info = QLabel('Adjust your stem mix below, then export it as a WAV file. '
                             'These controls stay synchronized with the Chord Grid mixer.')
        export_info.setObjectName('ioDescription')
        export_info.setWordWrap(True)
        export_layout.addWidget(export_info)
        self.export_splitter = MinimalSplitter(Qt.Horizontal)
        self.export_splitter.setObjectName('exportSplitter')
        self.export_splitter.setHandleWidth(12)
        self.export_splitter.setToolTip('Drag the divider to resize panels')
        self.export_splitter.setChildrenCollapsible(False)
        export_layout.addWidget(self.export_splitter, 1)
        export_left = QWidget()
        export_left.setMinimumWidth(210)
        export_options = QVBoxLayout(export_left)
        export_options.setContentsMargins(6, 6, 6, 6)
        export_options.setSpacing(12)
        self.export_splitter.addWidget(export_left)
        export_options.addWidget(QLabel('CURRENT MIX'))
        export_options.addWidget(QLabel('WAV  ·  Four-stem mix  ·  Current mute and volume settings'))
        self.export = QPushButton('Export WAV')
        self.export.setIcon(qta.icon('fa5s.file-export', color='#7bd6ff'))
        self.export.setToolTip('Export current mix as WAV')
        self.export.clicked.connect(self.export_mix)
        self.export.setEnabled(False)
        export_options.addWidget(self.export)
        export_options.addStretch(1)

        self.export_mixer = QWidget()
        self.export_mixer.setObjectName('stemPanel')
        self.export_mixer.setMinimumWidth(180)
        self.export_mixer.setMaximumWidth(500)
        self.export_mixer_layout = QVBoxLayout(self.export_mixer)
        self.export_mixer_layout.setContentsMargins(13, 14, 13, 13)
        self.export_mixer_layout.setSpacing(12)
        self.export_splitter.insertWidget(0, self.export_mixer)
        self.export_splitter.setStretchFactor(0, 0)
        self.export_splitter.setStretchFactor(1, 1)
        self.export_splitter.setSizes([240, 680])
        self.restore_splitter(self.export_splitter, 'export_splitter_left_v2')
        header = QHBoxLayout()
        title = QLabel('EXPORT STEM MIXER')
        title.setObjectName('mixerTitle')
        header.addWidget(title)
        header.addStretch()
        self.export_reset_mixer = QPushButton()
        self.export_reset_mixer.setIcon(qta.icon('fa5s.undo', color='#7bd6ff'))
        self.export_reset_mixer.setToolTip('Reset all stem volumes; mute bass by default')
        self.export_reset_mixer.setFixedSize(25, 24)
        self.export_reset_mixer.clicked.connect(self.reset_mixer)
        header.addWidget(self.export_reset_mixer)
        self.export_mixer_layout.addLayout(header)
        self.export_checks = {}
        self.export_solos = {}
        self.export_volumes = {}
        self.export_volume_labels = {}
        self.export_stem_names = {}
        self.export_stem_icons = {}
        for stem in STEMS:
            channel = QWidget()
            channel_layout = QVBoxLayout(channel)
            channel_layout.setContentsMargins(0, 0, 0, 0)
            channel_layout.setSpacing(3)
            heading = QHBoxLayout()
            stem_icon = QLabel()
            stem_icon.setPixmap(qta.icon(STEM_ICONS[stem], color='#7bd6ff').pixmap(16, 16))
            stem_icon.setFixedSize(19, 20)
            stem_icon.setAlignment(Qt.AlignCenter)
            stem_icon.setToolTip(stem.title())
            heading.addWidget(stem_icon)
            name = QLabel(stem.title())
            name.setObjectName('stemName')
            self.export_stem_names[stem] = name
            self.export_stem_icons[stem] = stem_icon
            heading.addWidget(name)
            heading.addStretch(1)
            mute = QPushButton()
            mute.setCheckable(True)
            mute.setChecked(stem != 'bass')
            mute.setEnabled(False)
            mute.setFixedSize(28, 26)
            mute.setProperty('stemToggle', True)
            mute.setToolTip(f'Mute or unmute {stem}')
            mute.setText('M')
            mute.setToolTip(f'Mute {stem.title()} (M)')
            mute.setAccessibleName(f'Mute {stem}')
            heading.addWidget(mute)
            solo = QPushButton('S')
            solo.setCheckable(True)
            solo.setEnabled(False)
            solo.setFixedSize(24, 23)
            solo.setProperty('soloToggle', True)
            solo.setToolTip(f'Solo {stem.title()} (exclusive)')
            heading.addWidget(solo)
            self.export_solos[stem] = solo
            channel_layout.addLayout(heading)
            volume_row = QHBoxLayout()
            volume = QSlider(Qt.Horizontal)
            volume.setRange(0, 150)
            volume.setValue(100)
            volume.setEnabled(False)
            volume.setToolTip(f'{stem.title()} export volume')
            volume_row.addWidget(volume, 1)
            amount = QLabel('100%')
            amount.setFixedWidth(35)
            amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            volume_row.addWidget(amount)
            channel_layout.addLayout(volume_row)
            self.export_checks[stem] = mute
            self.export_volumes[stem] = volume
            self.export_volume_labels[stem] = amount
            self.export_mixer_layout.addWidget(channel)
        self.export_mixer_layout.addStretch(1)
        export_layout.addWidget(QLabel('Export uses the same mix as the Chord Grid.'))
        self.load_url.setIcon(qta.icon('fa5s.download', color='white'))
        self.load_file.setIcon(qta.icon('fa5s.folder-open', color='white'))
        # Full-width waveform and analysis controls; the mixer only shares the grid row.
        play_left = QWidget()
        layout = QVBoxLayout(play_left)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        practice_layout.addWidget(play_left, 1)
        # Current chord sits BEFORE the waveform, never on top of its audio peaks.
        waveform_row = QHBoxLayout()
        waveform_row.setContentsMargins(0, 0, 0, 0)
        waveform_row.setSpacing(8)
        # Actual user-supplied brand sits beside the current note and waveform.
        self.header_brand = QLabel()
        self.header_brand.setObjectName('headerBrand')
        self.header_brand.setFixedSize(170, 72)
        self.header_brand.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.header_brand.setStyleSheet('background:transparent;border:0;')
        # The supplied full wordmark includes STEVIEBLITZ'S and Powered by AI.
        # The old SVG is a different artwork and must not replace it.
        if self.new_brand_asset.is_file():
            logo = QPixmap(str(self.new_brand_asset))
            if not logo.isNull():
                ratio = max(1.0, self.devicePixelRatioF())
                width = min(168, logo.width() / ratio)
                height = min(68, logo.height() / ratio)
                fitted = logo.size().scaled(
                    QSize(max(1, round(width * ratio)),
                          max(1, round(height * ratio))), Qt.KeepAspectRatio)
                rendered = logo.scaled(
                    fitted, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                rendered.setDevicePixelRatio(ratio)
                self.header_brand.setPixmap(rendered)
            else:
                self.header_brand.setText('RiffLab')
        else:
            self.header_brand.setText('RiffLab')
            self.header_brand.setStyleSheet(
                'background:transparent;border:0;color:#13a2d7;'
                'font-size:22px;font-weight:800;')
        waveform_row.addWidget(self.header_brand)
        self.chord = QLabel('—')
        self.chord.setAlignment(Qt.AlignCenter)
        self.chord.setFixedSize(100, 72)
        self._set_current_chord('—')
        waveform_row.addWidget(self.chord)
        self.waveform = WaveformTimeline(self)
        self.waveform.setAcceptDrops(True)
        self.waveform.installEventFilter(self)
        self.waveform.seekRequested.connect(self.seek_waveform)
        self.waveform.markerMoved.connect(self.move_loop_marker)
        waveform_row.addWidget(self.waveform, 1)
        layout.addLayout(waveform_row)
        self.next_chords = QLabel('NEXT: —')
        self.next_chords.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.next_chords.setStyleSheet('font-size:12px;color:#9bb7cb;padding:3px')
        self.next_chords.hide()  # No NEXT strip: the grid shows upcoming notes.
        # Two comfortable, logical rows instead of one overflowing toolbar.
        analysis_options = QHBoxLayout()
        analysis_options.setSpacing(8)
        analysis_options.setContentsMargins(0, 0, 0, 0)
        playback_options = QHBoxLayout()
        playback_options.setSpacing(5)
        playback_options.setContentsMargins(0, 0, 0, 0)
        navigation_options = QHBoxLayout()
        navigation_options.setSpacing(6)
        navigation_options.setContentsMargins(0, 0, 0, 0)
        options = analysis_options
        self.analysis_mode = QComboBox()
        self.analysis_mode.addItems(['Bass Mode', 'Chord Mode'])
        self.analysis_mode.setToolTip('Bass Mode tracks actual bass-note changes, including semitone steps; Chord Mode estimates harmony')
        self.analysis_mode.currentIndexChanged.connect(self.switch_analysis_mode)
        self.analysis_mode.hide()  # Backing mode state for existing analysis and project logic.
        options.addWidget(QLabel('◈ Accuracy'))
        self.accuracy = QComboBox()
        self.accuracy.addItems(['Fast · preview', 'Balanced · standard', 'Detailed · precise'])
        self.accuracy.setCurrentIndex(1)
        self.accuracy.setMinimumWidth(165)
        self.accuracy.setToolTip('Analysis speed and detail. Press Re-analyze to apply the selection.')
        options.addWidget(self.accuracy)
        self.reanalyze_button = QPushButton('Re-analyze')
        self.reanalyze_button.setMinimumWidth(110)
        self.reanalyze_button.setIcon(qta.icon('fa5s.sync-alt', color='#b6dcf2'))
        self.reanalyze_button.setToolTip('Run analysis again using the selected accuracy. Display filters update immediately.')
        self.reanalyze_button.clicked.connect(self.toggle_analysis_action)
        options.addWidget(self.reanalyze_button)
        self.cancel_analysis_button = QPushButton('Stop Analyze')
        self.cancel_analysis_button.setIcon(qta.icon('fa5s.stop-circle', color='#ffbdab'))
        self.cancel_analysis_button.setToolTip('Stop the running AI analysis while keeping the current song.')
        self.cancel_analysis_button.clicked.connect(self.stop_analysis)
        self.cancel_analysis_button.hide()
        # Legacy stop widget remains as a signal/status hook, not a second toolbar button.
        # Root-note display is independent of NoteGuard and comes first.
        self.root_notes_only = QCheckBox('Root notes')
        self.root_notes_only.setToolTip('Display note roots only, without chord quality. Does not affect analysis.')
        self.root_notes_only.toggled.connect(self.rebuild_chords)
        options.addWidget(self.root_notes_only)
        options.addWidget(QLabel('◇ NoteGuard'))
        self.noteguard = QComboBox()
        self.noteguard.addItems(['Off', 'Light', 'Normal · recommended', 'Strong'])
        self.noteguard.setCurrentIndex(2)
        self.noteguard.setMinimumWidth(162)
        self.noteguard.setToolTip(
            'Filter uncertain notes in the timeline (no re-analysis).\n'
            'Off: all detections. Light: preserve fast riffs. Normal: recommended.\n'
            'Strong: remove more short glitches. Use Root notes for pitch-only display.')
        for index, explanation in enumerate((
            'Off — Show every detected note, including uncertain ones.',
            'Light — Reduce obvious errors while keeping fast passages.',
            'Normal — Balanced filtering, recommended for most songs.',
            'Strong — Suppress more short notes; may also hide real quick changes.'
        )):
            self.noteguard.setItemData(index, explanation, Qt.ToolTipRole)
        self.noteguard.currentIndexChanged.connect(self.rebuild_chords)
        options.addWidget(self.noteguard)
        noteguard_help = QLabel('ⓘ')
        noteguard_help.setToolTip(
            'Not sure? Start with Normal.\n'
            'Missing fast notes? Try Light or Off.\n'
            'Too many false notes? Try Strong.\n'
            'Only want the root notes? Enable Root notes.')
        options.addWidget(noteguard_help)
        self.sensitivity = QSlider(Qt.Horizontal)
        self.sensitivity.setRange(0, 20)  # minimum duration of a displayed segment, 0-2 seconds
        self.sensitivity.setValue(0)
        self.sensitivity.setToolTip('Minimum note duration. Higher values reduce rapid changes; display only.')
        self.sensitivity.setFixedWidth(90)
        self.sensitivity.valueChanged.connect(self.rebuild_chords)
        self.sensitivity_label = QLabel('≥0.0 s')
        # Complexity only filters the note display; it never changes playback speed,
        # sample rate, analysis source or audio pitch.
        options = analysis_options
        options.addWidget(QLabel('Complexity'))
        self.complexity = QSlider(Qt.Horizontal)
        self.complexity.setRange(0, 100)
        self.complexity.setFixedWidth(88)
        self.complexity.setValue(25)
        self.complexity.setToolTip('How much short-note detail to display. Lower = simpler. Higher = more detail. Does not change NoteGuard or audio pitch.')
        self.complexity_label = QLabel('25%')
        def apply_complexity(value):
            self.complexity_label.setText(f'{value}%')
            # Complexity only adjusts minimum segment duration (Stability);
            # changing it must not silently override the user's NoteGuard choice.
            self.sensitivity.setValue(round((100 - value) * 0.16))
        self.complexity.valueChanged.connect(apply_complexity)
        self.sensitivity.setValue(round((100 - self.complexity.value()) * 0.16))
        options.addWidget(self.complexity)
        options.addWidget(self.complexity_label)
        # Tuning belongs inline with the main analysis actions at the top.
        options = analysis_options
        options.addWidget(QLabel('♮ Transpose'))
        self.transpose = QSpinBox()
        self.transpose.setMinimumWidth(92)
        self.transpose.setRange(-12, 12)
        self.transpose.setValue(0)
        self.transpose.setSuffix(' st')
        self.transpose.setToolTip('Notation only: changes displayed notes/chords, never the audio pitch or the instrument tuning.')
        self.transpose.valueChanged.connect(self.transpose_changed)
        options.addWidget(self.transpose)
        self.note_spelling = QComboBox()
        self.note_spelling.addItems(['♭ Flats (Bb)', '♯ Sharps (A#)'])
        self.note_spelling.setObjectName('noteSpelling')
        self.note_spelling.setToolTip('Choose how equivalent notes are named; audio and detection are unchanged.')
        self.note_spelling.setFixedWidth(125)
        self.note_spelling.setCurrentIndex(int(self.layout_settings.value('note_spelling', 0)))
        self.note_spelling.currentIndexChanged.connect(self.note_spelling_changed)
        options.addWidget(self.note_spelling)
        self.tuning_advice = QPushButton('Tuning guide ↗')
        self.tuning_advice.setMinimumWidth(120)
        self.tuning_advice.setToolTip(
            'Open the tuner and choose a string tuning. Transpose does not retune audio.')
        self.tuning_advice.clicked.connect(self.open_tuning_guide)
        self.tuning_advice.setAccessibleName('Open optional tuning advice')
        options.addWidget(self.tuning_advice)
        options = playback_options
        self.grid_bpm = QSpinBox()
        self.grid_bpm.setFixedWidth(62)
        self.grid_bpm.setRange(40, 250)
        self.grid_bpm.setValue(130)
        self.grid_bpm.valueChanged.connect(self.bpm_changed)
        self.reset_bpm_button = QPushButton()
        self.reset_bpm_button.setObjectName('resetBpmButton')
        self.reset_bpm_button.setIcon(qta.icon('fa5s.undo', color='#9bb7cb'))
        self.reset_bpm_button.setIconSize(QSize(13, 13))
        self.reset_bpm_button.setFixedSize(20, 24)
        self.reset_bpm_button.setToolTip('Reset BPM to detected tempo (100% playback speed)')
        self.reset_bpm_button.setAccessibleName('Reset BPM')
        self.reset_bpm_button.clicked.connect(self.reset_bpm)
        # Single tight BPM group: label, digits, small reset on the RIGHT.
        bpm_group = QHBoxLayout()
        bpm_group.setSpacing(2)
        bpm_group.setContentsMargins(0, 0, 0, 0)
        bpm_group.addWidget(QLabel('BPM'))
        bpm_group.addWidget(self.grid_bpm)
        bpm_group.addWidget(self.reset_bpm_button)
        options.addLayout(bpm_group)
        options = navigation_options
        self.follow = QCheckBox('↧ Auto-scroll')
        self.follow.setChecked(True)
        options.addWidget(self.follow)
        options.addSpacing(12)
        options.addWidget(QLabel('◷ Lookahead'))
        self.chord_lookahead = QSpinBox()
        self.chord_lookahead.setMinimumWidth(110)
        self.chord_lookahead.setRange(0, 500)
        self.chord_lookahead.setSingleStep(25)
        self.chord_lookahead.setSuffix(' ms')
        self.chord_lookahead.setValue(150)
        self.chord_lookahead.setToolTip('Show the next chord this many milliseconds early; audio and grid timing remain unchanged')
        self.chord_lookahead.valueChanged.connect(self.refresh_chord_indicator)
        options.addWidget(self.chord_lookahead)
        toolbar_panel = QWidget()
        toolbar_panel.setObjectName('analysisToolbar')
        toolbar_layout = QVBoxLayout(toolbar_panel)
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        toolbar_layout.setSpacing(0)
        analysis_options.addStretch(1)
        toolbar_layout.addLayout(analysis_options)
        layout.addWidget(toolbar_panel)
        # The display mode belongs to the grid, not the analysis controls.
        grid_column = QVBoxLayout()
        grid_column.setContentsMargins(0, 0, 0, 0)
        grid_column.setSpacing(4)
        self.bass_mode_button = QPushButton('Notes')
        self.chord_mode_button = QPushButton('Chords')
        for button in (self.bass_mode_button, self.chord_mode_button):
            button.setCheckable(True)
            button.setProperty('gridModeButton', True)
            button.setFixedHeight(25)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.bass_mode_button.setFixedWidth(70)
        self.chord_mode_button.setFixedWidth(76)
        self.bass_mode_button.setToolTip('Bass Mode: detect and display the bass-note roots')
        self.chord_mode_button.setToolTip('Detect and display chords')
        self.bass_mode_button.clicked.connect(lambda: self.analysis_mode.setCurrentIndex(0))
        self.chord_mode_button.clicked.connect(lambda: self.analysis_mode.setCurrentIndex(1))
        self.analysis_mode.currentIndexChanged.connect(self.update_grid_mode_buttons)
        self.update_grid_mode_buttons()
        self.chord_scroll = QScrollArea()
        self.chord_scroll.setObjectName('noteGridScroll')
        self.chord_scroll.setAcceptDrops(True)
        self.chord_scroll.viewport().setAcceptDrops(True)
        self.chord_scroll.setWidgetResizable(True)
        self.chord_scroll.setMinimumHeight(160)
        self.chord_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.grid_host = QWidget()
        self.chord_grid = QGridLayout(self.grid_host)
        self.chord_grid.setContentsMargins(5, 3, 12, 5)
        self.chord_grid.setHorizontalSpacing(0)
        self.chord_grid.setVerticalSpacing(5)
        self.chord_grid.setSpacing(5)
        self.chord_grid.setAlignment(Qt.AlignTop)
        # Keep the note rows' intrinsic height when the scroll area is resized.
        self.grid_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.chord_scroll.setWidget(self.grid_host)
        self.grid_host.setAcceptDrops(True)
        self.grid_host.installEventFilter(self)
        self.chord_loading = QWidget(self.chord_scroll.viewport())
        self.chord_loading.setObjectName('chordLoading')
        self.chord_loading.setStyleSheet(
            'QWidget#chordLoading {background-color:rgba(9,19,30,225);}')
        loading_layout = QVBoxLayout(self.chord_loading)
        loading_layout.setAlignment(Qt.AlignCenter)
        self.chord_loading_label = QLabel('Analyzing notes…')
        self.chord_loading_label.setAlignment(Qt.AlignCenter)
        self.chord_loading_label.setStyleSheet(
            'color:#eaf6ff;font-size:17px;font-weight:700;background:transparent;')
        loading_layout.addWidget(self.chord_loading_label)
        self.chord_loading_bar = QProgressBar()
        self.chord_loading_bar.setFixedWidth(260)
        self.chord_loading_bar.setRange(0, 0)
        self.chord_loading_bar.setTextVisible(False)
        loading_layout.addWidget(self.chord_loading_bar, alignment=Qt.AlignHCenter)
        self.chord_loading_stop = QPushButton('■ Stop Analyze')
        self.chord_loading_stop.setFixedWidth(165)
        self.chord_loading_stop.clicked.connect(self.stop_analysis)
        loading_layout.addWidget(self.chord_loading_stop, alignment=Qt.AlignHCenter)
        self.chord_loading.hide()
        self.chord_scroll.viewport().installEventFilter(self)
        # Dock mode controls in the measure-ruler strip itself, not a separate
        # full-width row above the timeline. This saves vertical grid space.
        self.grid_mode_overlay = QWidget(self.chord_scroll.viewport())
        self.grid_mode_overlay.setObjectName('gridModeOverlay')
        mode_row = QHBoxLayout(self.grid_mode_overlay)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(0)
        mode_row.addWidget(self.bass_mode_button)
        mode_row.addWidget(self.chord_mode_button)
        self.grid_mode_overlay.setFixedSize(146, 27)
        self.grid_mode_overlay.setStyleSheet('QWidget#gridModeOverlay{background:#111923;border:1px solid #304559;border-radius:4px;}')
        self.grid_mode_overlay.move(max(0, self.chord_scroll.viewport().width() - 151), 2)
        self.grid_mode_overlay.raise_()
        # Only the grid area is horizontally split with the compact stem mixer.
        self.play_splitter = MinimalSplitter(Qt.Horizontal)
        self.play_splitter.setObjectName('playSplitter')
        self.play_splitter.setHandleWidth(8)
        self.play_splitter.setToolTip('Drag the divider to resize the mixer and note grid')
        self.play_splitter.setChildrenCollapsible(False)
        # The grid consumes all available vertical space above the pinned transport.
        self.play_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.play_splitter.setMinimumHeight(190)
        grid_host_panel = QWidget()
        grid_host_panel.setObjectName('noteGridPanel')
        grid_content_row = QHBoxLayout()
        grid_content_row.setContentsMargins(7, 7, 7, 7)
        grid_content_row.setSpacing(6)
        grid_content_row.addWidget(self.chord_scroll, 1)
        grid_column.addLayout(grid_content_row, 1)
        grid_host_panel.setLayout(grid_column)
        grid_host_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.play_splitter.addWidget(grid_host_panel)
        layout.addWidget(self.play_splitter, 1)
        self.grid_notice = QLabel('Open audio to play. Install AI dependencies for automatic beat and chord analysis.')
        self.grid_notice.setWordWrap(True)
        self.grid_notice.setObjectName('gridNotice')
        # Retain analysis status for code and accessibility, without consuming grid height.
        self.grid_notice.hide()
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderReleased.connect(self.seek)
        self.timeline.hide()  # Keep backing range/value for existing project and transport logic.
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self.on_position)
        # Repaint a fluid in-note progress fill independently of coarse beat changes.
        self.note_fill_timer = QTimer(self)
        self.note_fill_timer.setInterval(33)
        self.note_fill_timer.timeout.connect(self.update_note_fill)
        self.note_fill_timer.start()
        self.player.durationChanged.connect(self.on_duration)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        # Keep the transport geometrically centered, regardless of the right-side loop status.
        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(6)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(2, 1)
        transport_buttons = QHBoxLayout()
        transport_buttons.setSpacing(6)
        self.play = QPushButton()
        self.play.setToolTip('Play / Pause')
        self.play.setIcon(qta.icon('fa5s.play', color='white'))
        self.play.clicked.connect(self.toggle_play)
        transport_buttons.addWidget(self.play)
        self.stop_button = QPushButton()
        self.stop_button.setToolTip('Stop')
        self.stop_button.setIcon(qta.icon('fa5s.stop', color='white'))
        self.stop_button.clicked.connect(self.stop_playback)
        transport_buttons.addWidget(self.stop_button)
        self.loop_button = QPushButton()
        self.loop_button.setCheckable(True)
        self.loop_button.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        self.loop_button.setToolTip('Toggle looping (whole track or between In and Out markers)')
        self.loop_button.toggled.connect(self.toggle_loop)
        transport_buttons.addWidget(self.loop_button)
        self.loop_a_button = QPushButton()
        self.loop_a_button.setIcon(loop_boundary_icon('in'))
        self.loop_a_button.setToolTip('Set loop In marker at current playback position')
        self.loop_a_button.clicked.connect(lambda: self.set_loop_point('a'))
        transport_buttons.addWidget(self.loop_a_button)
        self.loop_b_button = QPushButton()
        self.loop_b_button.setIcon(loop_boundary_icon('out'))
        self.loop_b_button.setToolTip('Set loop Out marker at current playback position')
        self.loop_b_button.clicked.connect(lambda: self.set_loop_point('b'))
        transport_buttons.addWidget(self.loop_b_button)
        self.loop_clear_button = QPushButton()
        self.loop_clear_button.setIcon(qta.icon('fa5s.times', color='white'))
        self.loop_clear_button.setToolTip('Clear In and Out markers')
        self.loop_clear_button.clicked.connect(self.clear_loop)
        transport_buttons.addWidget(self.loop_clear_button)
        for button in (self.play, self.stop_button, self.loop_button, self.loop_a_button, self.loop_b_button, self.loop_clear_button):
            button.setFixedSize(32, 30)
            button.setIconSize(QSize(24, 24) if button in (self.loop_a_button, self.loop_b_button) else QSize(15, 15))
            button.setProperty('transportIcon', True)
        # Both zoom axes use identical compact transport controls.
        zoom_controls = QHBoxLayout()
        zoom_controls.setContentsMargins(0, 0, 0, 0)
        zoom_controls.setSpacing(6)
        zoom_minus = QPushButton('−')
        zoom_minus.setObjectName('gridZoomStep')
        zoom_minus.setFixedSize(18, 20)
        zoom_minus.setToolTip('Zoom out horizontally')
        zoom_controls.addWidget(QLabel('H'))
        zoom_minus.hide()  # Keep handler but omit +/- from the compact UI.
        self.grid_zoom = QSlider(Qt.Horizontal)
        self.grid_zoom.setObjectName('gridZoom')
        self.grid_zoom.setRange(65, 200)
        self.grid_zoom.setSingleStep(1)
        self.grid_zoom.setPageStep(5)
        self.grid_zoom.setValue(max(65, min(200, int(self.layout_settings.value('grid_zoom', 100)))))
        self.grid_zoom.setFixedWidth(74)
        self.grid_zoom.setToolTip('Adjust note-block width by dragging or scrolling')
        self.grid_zoom.valueChanged.connect(self.apply_grid_zoom)
        self.grid_zoom.valueChanged.connect(lambda value: self.layout_settings.setValue('grid_zoom', value))
        self.grid_zoom.installEventFilter(self)
        zoom_controls.addWidget(self.grid_zoom)
        zoom_plus = QPushButton('+')
        zoom_plus.setObjectName('gridZoomStep')
        zoom_plus.setFixedSize(18, 20)
        zoom_plus.setToolTip('Zoom in horizontally')
        zoom_plus.hide()  # No permanent zoom step buttons.
        zoom_minus.clicked.connect(lambda: self.grid_zoom.setValue(max(self.grid_zoom.minimum(), self.grid_zoom.value() - 5)))
        zoom_plus.clicked.connect(lambda: self.grid_zoom.setValue(min(self.grid_zoom.maximum(), self.grid_zoom.value() + 5)))
        self.grid_zoom_label = QLabel('100%')
        self.grid_zoom_label.setFixedWidth(38)
        self.grid_zoom_label.installEventFilter(self)
        self.grid_zoom_label.hide()  # Keep value updates without a visible percent.
        # Single compact vertical zoom control, rendered horizontally alongside H.
        zoom_controls.addSpacing(6)
        zoom_controls.addWidget(QLabel('V'))
        height_minus = QPushButton('−')
        height_minus.setObjectName('gridZoomStep')
        height_minus.setFixedSize(18, 20)
        height_minus.setToolTip('Decrease note row height')
        height_minus.hide()
        self.grid_row_height = QSlider(Qt.Horizontal)
        self.grid_row_height.setObjectName('gridRowHeight')
        self.grid_row_height.setRange(24, 96)
        self.grid_row_height.setFixedWidth(74)
        self.grid_row_height.setSingleStep(1)
        self.grid_row_height.setPageStep(4)
        self.grid_row_height.setValue(max(24, min(96, int(self.layout_settings.value('grid_row_height', 52)))))
        self.grid_row_height.setToolTip('Adjust note row height')
        self.grid_row_height.valueChanged.connect(self.apply_grid_row_height)
        self.grid_row_height.valueChanged.connect(lambda value: self.layout_settings.setValue('grid_row_height', value))
        self.grid_row_height.installEventFilter(self)
        zoom_controls.addWidget(self.grid_row_height)
        height_plus = QPushButton('+')
        height_plus.setObjectName('gridZoomStep')
        height_plus.setFixedSize(18, 20)
        height_plus.setToolTip('Increase note row height')
        height_plus.hide()
        height_minus.clicked.connect(lambda: self.grid_row_height.setValue(max(self.grid_row_height.minimum(), self.grid_row_height.value() - 4)))
        height_plus.clicked.connect(lambda: self.grid_row_height.setValue(min(self.grid_row_height.maximum(), self.grid_row_height.value() + 4)))
        self.grid_row_height_label = QLabel(f'{round(self.grid_row_height.value() / 38 * 100)}%')
        self.grid_row_height_label.setFixedWidth(38)
        self.grid_row_height_label.hide()
        self._height_wheel_targets = (self.grid_row_height,)
        self._zoom_wheel_targets = (self.grid_zoom,)
        # Equal-width outer columns keep transport geometrically centered.
        controls.addLayout(playback_options, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        centered_transport = QHBoxLayout()
        centered_transport.setContentsMargins(0, 0, 0, 0)
        centered_transport.setSpacing(9)
        centered_transport.addWidget(self.time_label)
        centered_transport.addLayout(transport_buttons)
        controls.addLayout(centered_transport, 0, 1, Qt.AlignCenter)
        self.loop_info = QLabel('Whole track')
        self.loop_info.setObjectName('loopInfo')
        self.loop_info.hide()  # Retain state; the single-row controlbar stays uncluttered.
        # Navigation stays to the right; clock is now next to the song title.
        right_controls = QHBoxLayout()
        right_controls.setSpacing(6)
        right_controls.addStretch(1)
        right_controls.addLayout(zoom_controls)
        right_controls.addSpacing(8)
        right_controls.addLayout(navigation_options)
        controls.addLayout(right_controls, 0, 2)
        bottom_panel = QWidget()
        bottom_panel.setObjectName('bottomControlBar')
        bottom_panel_layout = QVBoxLayout(bottom_panel)
        bottom_panel_layout.setContentsMargins(10, 6, 10, 6)
        bottom_panel_layout.setSpacing(0)
        bottom_panel_layout.addLayout(controls)
        grid_column.addWidget(bottom_panel, 0)  # Only below the grid, not below the mixer.
        # Compact left-hand mixer beside the grid only; waveform remains full width.
        stem_panel = QWidget()
        stem_panel.setObjectName('playStemPanel')
        stem_panel.setMinimumWidth(165)
        stem_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel = QVBoxLayout(stem_panel)
        panel.setContentsMargins(7, 6, 7, 6)
        panel.setSpacing(5)
        mixer_header = QHBoxLayout()
        mixer_header.setContentsMargins(0, 0, 0, 0)
        mixer_title = QLabel('STEM MIXER')
        mixer_title.setObjectName('mixerTitle')
        mixer_header.addWidget(mixer_title)
        mixer_header.addStretch()
        self.reset_mixer_button = QPushButton()
        self.reset_mixer_button.setIcon(qta.icon('fa5s.undo', color='#b8cbdc'))
        self.reset_mixer_button.setToolTip('Reset to default: bass muted, all levels 100%')
        self.reset_mixer_button.setFixedSize(24, 22)
        self.reset_mixer_button.setObjectName('mixerIconAction')
        self.reset_mixer_button.clicked.connect(self.reset_mixer)
        mixer_header.addWidget(self.reset_mixer_button)
        panel.addLayout(mixer_header)
        self.checks = {}
        self.solos = {}
        self.volumes = {}
        self.volume_labels = {}
        self.stem_names = {}
        self.stem_icons = {}
        for stem in STEMS:
            channel = QWidget()
            channel_layout = QVBoxLayout(channel)
            channel_layout.setContentsMargins(0, 0, 0, 0)
            channel_layout.setSpacing(5)
            heading = QHBoxLayout()
            heading.setContentsMargins(0, 0, 0, 0)
            stem_icon = QLabel()
            stem_icon.setPixmap(qta.icon(STEM_ICONS[stem], color='#91b6ce').pixmap(16, 16))
            stem_icon.setFixedSize(19, 20)
            stem_icon.setAlignment(Qt.AlignCenter)
            stem_icon.setToolTip(stem.title())
            heading.addWidget(stem_icon)
            name = QLabel(stem.title())
            name.setObjectName('stemName')
            heading.addWidget(name)
            heading.addStretch(1)
            cb = QPushButton()
            cb.setCheckable(True)
            cb.setChecked(stem != 'bass')
            cb.setEnabled(False)
            cb.setFixedSize(24, 23)
            cb.setProperty('stemToggle', True)
            cb.setToolTip(f'Mute {stem.title()} (M)')
            cb.setAccessibleName(f'Mute {stem}')
            cb.setText('M')
            cb.toggled.connect(lambda checked, stem=stem: self.stem_toggled(stem, checked))
            self.checks[stem] = cb
            self.stem_names[stem] = name
            self.stem_icons[stem] = stem_icon
            heading.addWidget(cb)
            solo = QPushButton('S')
            solo.setCheckable(True)
            solo.setEnabled(False)
            solo.setFixedSize(28, 26)
            solo.setProperty('soloToggle', True)
            solo.setToolTip(f'Solo {stem.title()} (exclusive)')
            solo.toggled.connect(lambda _checked, name=stem: self.solo_toggled(name))
            self.solos[stem] = solo
            heading.addWidget(solo)
            channel_layout.addLayout(heading)
            volume_row = QHBoxLayout()
            volume_row.setContentsMargins(0, 0, 0, 0)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 150)
            slider.setValue(100)
            slider.setEnabled(False)
            slider.setToolTip(f'{stem.title()} volume')
            slider.valueChanged.connect(self.volume_changed)
            volume_row.addWidget(slider, 1)
            amount = QLabel('100%')
            amount.setFixedWidth(35)
            amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            volume_row.addWidget(amount)
            channel_layout.addLayout(volume_row)
            self.volumes[stem] = slider
            self.volume_labels[stem] = amount
            panel.addWidget(channel)
        panel.addStretch(0)
        self.stem_panel = stem_panel
        self.mixer_overlay = QWidget(stem_panel)
        self.mixer_overlay.setObjectName('stemOverlay')
        self.mixer_overlay.setStyleSheet(
            'QWidget#stemOverlay{background:rgba(15,23,34,204);border-radius:4px;}'
            'QPushButton#generateStems{background:#276080;color:white;border:1px solid #7bd6ff;'
            'border-radius:5px;padding:12px;font-weight:700;}')
        overlay_layout = QVBoxLayout(self.mixer_overlay)
        overlay_layout.setContentsMargins(12, 12, 12, 12)
        overlay_layout.addStretch(1)
        self.generate_stems_button = QPushButton('Generate Stems')
        self.generate_stems_button.setObjectName('generateStems')
        self.generate_stems_button.clicked.connect(self.generate_stems_clicked)
        overlay_layout.addWidget(self.generate_stems_button)
        overlay_layout.addStretch(1)
        stem_panel.installEventFilter(self)
        self.mixer_overlay.setGeometry(stem_panel.rect())
        # A full-height transparent holder lets the mixer itself stay compact.
        mixer_holder = QWidget()
        mixer_holder.setMinimumWidth(165)
        mixer_holder.setMaximumWidth(460)
        mixer_holder.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        mixer_holder_layout = QVBoxLayout(mixer_holder)
        mixer_holder_layout.setContentsMargins(0, 0, 0, 0)
        mixer_holder_layout.setSpacing(0)
        # No nested scroll area around four stem controls. The parent tab owns
        # the entire left panel, avoiding the inset rectangle and dead gutter.
        self.mixer_scroll = None
        mixer_holder_layout.addWidget(stem_panel, 1)
        # The actual Library page and the actual Stem Mixer share a left sidebar.
        # Reparent existing widgets: no replacement logic, duplicated controls or data.
        library_page = self.tabs.widget(1)
        self.tabs.removeTab(1)
        self.tabs.insertTab(1, QWidget(), 'Library')  # Compatibility for saved tab IDs.
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName('sidebarTabs')
        self.sidebar_tabs.setMinimumWidth(235)
        self.sidebar_tabs.setMaximumWidth(460)
        self.sidebar_tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar_tabs.addTab(mixer_holder, 'Stem Mixer')
        self.sidebar_tabs.addTab(library_page, 'Library')
        self.sidebar_tabs.setTabIcon(0, qta.icon('fa5s.sliders-h', color='#7bd6ff'))
        self.sidebar_tabs.setTabIcon(1, qta.icon('fa5s.book', color='#7bd6ff'))
        self.sidebar_tabs.setCurrentIndex(0)
        self.play_splitter.insertWidget(0, self.sidebar_tabs)
        self.sidebar_tabs.currentChanged.connect(
            lambda _index: self.tabs.setCurrentIndex(0) if self.tabs.currentIndex() == 1 else None)
        self.tabs.currentChanged.connect(
            lambda index: self.show_library_sidebar() if index == 1 else None)
        self.play_splitter.setStretchFactor(0, 0)
        self.play_splitter.setStretchFactor(1, 1)
        self.play_splitter.setSizes([320, 780])
        self.restore_splitter(self.play_splitter, 'play_splitter_grid_v3')
        # Mirror each control; both tabs edit the SAME live mixer state.
        self.connect_export_mixer()
        self.tabs.currentChanged.connect(lambda _i: self.sync_all_export_mixer())
        self.io_sections.currentChanged.connect(lambda _i: self.sync_all_export_mixer())
        # Move the original tuner widget to its own page, without recreating controls.
        self.tuner_dialog.setWindowFlags(Qt.Widget)
        self.tuner_dialog.setMinimumWidth(0)
        self.tuner_dialog.setContentsMargins(8, 6, 8, 6)
        self.tabs.addTab(self.tuner_dialog, 'Tuner')
        tuner_index = self.tabs.indexOf(self.tuner_dialog)
        self.tabs.setTabIcon(tuner_index, self.tuning_fork_icon())
        self.tabs.setTabToolTip(tuner_index, 'Chromatic Tuner')
        layout = tuner_layout
        layout.addWidget(QLabel('CHROMATIC TUNER  /  AUDIO INPUT'))
        tuner_row = QHBoxLayout()
        self.devices = QComboBox()
        tuner_row.addWidget(self.devices, 1)
        self.device_refresh = QPushButton('Refresh Inputs')
        self.device_refresh.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        self.device_refresh.clicked.connect(self.find_devices)
        tuner_row.addWidget(self.device_refresh)
        self.tuner_button = QPushButton('Start Tuner')
        self.tuner_button.setIcon(qta.icon('fa5s.microphone', color='white'))
        self.tuner_button.clicked.connect(self.toggle_tuner)
        tuner_row.addWidget(self.tuner_button)
        layout.addLayout(tuner_row)
        # Rocksmith-style guided tuning, alongside free chromatic mode.
        tuning_row = QHBoxLayout()
        self.tuner_preset = QComboBox()
        self.tuner_preset.addItems([
            'Chromatic · free', 'Guitar · E Standard', 'Guitar · Eb / half step',
            'Guitar · D Standard', 'Guitar · Drop D', 'Guitar · Drop C#',
            'Bass · E Standard', 'Bass · Eb / half step', 'Bass · D Standard',
        ])
        self.tuner_preset.setToolTip(
            'Choose the instrument tuning and check each string against its target frequency and cent meter.')
        self.tuner_preset.currentIndexChanged.connect(self.refresh_tuner_strings)
        self.tuner_preset.currentIndexChanged.connect(
            lambda index: self.layout_settings.setValue('preferred_tuning_preset', index))
        tuning_row.addWidget(self.tuner_preset, 2)
        self.tuner_string = QComboBox()
        self.tuner_string.setToolTip('Choose a string to tune against its reference frequency.')
        self.tuner_string.currentIndexChanged.connect(self.refresh_tuner_target)
        tuning_row.addWidget(self.tuner_string, 1)
        layout.addLayout(tuning_row)
        self.tuner_target = QLabel('Chromatic mode · select a tuning preset for guided tuning')
        self.tuner_target.setAlignment(Qt.AlignCenter)
        self.tuner_target.setStyleSheet(
            'font-size:13px;color:#a4d4f1;background:transparent;padding:4px;')
        layout.addWidget(self.tuner_target)
        self.tuner_note = QLabel('—')
        self.tuner_note.setAlignment(Qt.AlignCenter)
        self.tuner_note.setMinimumHeight(78)
        self.tuner_note.setStyleSheet(
            'font-size:46px;font-weight:800;color:#eaf7ff;'
            'background-color:rgba(41,76,99,95);'
            'border:1px solid rgba(150,201,229,75);border-radius:8px;')
        layout.addWidget(self.tuner_note)
        self.tuner_details = QLabel('Play one string · A4 = 440 Hz')
        self.tuner_details.setAlignment(Qt.AlignCenter)
        self.tuner_details.setStyleSheet('font-size:14px;color:#aac8db;')
        layout.addWidget(self.tuner_details)
        self.tuner_meter = TunerMeter()
        layout.addWidget(self.tuner_meter)
        layout.addStretch(1)
        saved_tuning = int(self.layout_settings.value('preferred_tuning_preset', 0))
        self.tuner_preset.setCurrentIndex(max(0, min(8, saved_tuning)))
        self.refresh_tuner_strings()
        self.find_devices()
        self.tuner_timer = QTimer(self)
        self.tuner_timer.timeout.connect(self.update_tuner)
        self.tuner_timer.start(50)  # Responsive needle; ~20 UI updates per second.
        self.render_grid()
        self.mix_debounce = QTimer(self)
        self.mix_debounce.setSingleShot(True)
        self.mix_debounce.timeout.connect(self.request_mix)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.live_tick)
        self.live_timer.start(80)
        self.player.playbackStateChanged.connect(self.on_playback_state)
        self.player.positionChanged.connect(self.check_qt_loop)
        self.player.errorOccurred.connect(lambda error, msg: self.status_message(f'Audiofout: {msg}') if msg else None)
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 3, 4, 0)
        footer.setSpacing(10)
        footer.addWidget(self.status, 1)
        self.stems_led = QLabel('● STEMS OFF')
        self.stems_led.setMinimumWidth(125)
        footer.addWidget(self.stems_led)
        self.refresh_stems_led()
        self.maker_credit = QLabel(
            'by <a href="https://github.com/stevieblitz/Rifflab" '
            'style="color:#7bd6ff;text-decoration:none;">StevieBlitz\'s RiffLab</a> · <a href="https://teunverhoeven.nl" style="color:#9bb7cb;text-decoration:none;">Teun Verhoeven</a> · powered by AI'
        )
        self.maker_credit.setObjectName('makerCredit')
        self.maker_credit.setTextFormat(Qt.RichText)
        self.maker_credit.setOpenExternalLinks(True)
        self.maker_credit.setToolTip('RiffLab on GitHub')
        self.maker_credit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        footer.addWidget(self.maker_credit, 0)
        outer.addLayout(footer)
        outer.addWidget(self.progress)
        self.progress.hide()  # Show only while a task is running; avoid duplicate READY footer.
        self.setStyleSheet('''
          QMainWindow,QWidget{background:#111923;color:#e8edf2;font-family:'Segoe UI';font-size:13px}
          QWidget#bottomControlBar{background:#111923;border:1px solid #304559;border-radius:5px}
          QWidget#bottomControlBar QLabel,QWidget#bottomControlBar QCheckBox{background:transparent;border:0}
          QTabWidget#sidebarTabs::pane{background:#111923;border:1px solid #304559;border-radius:5px}
          QTableWidget#librarySongTable{background:transparent;border:0;gridline-color:transparent;font-size:11px;outline:0}
          QTableWidget#librarySongTable::item{padding:0px 3px;border:0}
          QTableWidget#librarySongTable::item:selected{background:#223e54;color:#e9f7ff}
          QTableWidget#librarySongTable::item:alternate{background:#142333}
          QTableWidget#librarySongTable::item:selected{border-left:2px solid #7bd6ff}
          QTableWidget#librarySongTable QHeaderView::section{background:transparent;border:0;border-bottom:1px solid #304559;color:#819cac;font-size:10px;padding:2px 4px}
          QTabWidget#sidebarTabs QTabBar::tab{font-size:12px;padding:5px 9px}
          QWidget#libraryAdvanced{background:#142432;border:1px solid #31495c;border-radius:4px}
          QPushButton#libraryFilterToggle{background:#1a3041;border:1px solid #2b455a;padding:3px 8px;text-align:left}
          QPushButton#libraryIconAction{background:transparent;border:0;border-radius:3px;padding:3px;min-width:0;min-height:0}
          QPushButton#libraryIconAction:hover{background:#203547;border:0}
          QPushButton#libraryIconAction:pressed{background:#29465b;border:0}
          QPushButton#ioBackToPlay{background:transparent;border:1px solid #294559;border-radius:4px;color:#d2edfc;padding:4px 10px}
          QPushButton#ioBackToPlay:hover{background:#203d51;border-color:#7bd6ff}
          QPushButton#mixerIconAction{background:transparent;border:0;border-radius:3px;padding:2px}
          QPushButton#mixerIconAction:hover{background:#203d51;border:0}
          QPushButton#headerTuner,QPushButton#practiceNav{background:#1b2938;border:1px solid #304a60;padding:4px 8px;border-radius:4px}
          QPushButton#headerTuner:hover,QPushButton#practiceNav:hover{background:#294e69}
          QPushButton[gridModeButton='true']{padding:2px 5px;min-height:20px}
          QPushButton{font-family:'Bahnschrift','Segoe UI';font-weight:500}
          QComboBox,QSpinBox{font-family:'Bahnschrift','Segoe UI'}
          QLabel#gridTitle,QLabel#mixerTitle{font-family:'Bahnschrift','Segoe UI';font-weight:600}
          ScrollingSongTitle#nowPlayingTitle{font-family:'Bahnschrift','Segoe UI';font-weight:600}
          QPushButton#gridZoomStep{background:transparent;border:0;color:#7bd6ff;font-size:14px;font-weight:500;padding:0}
          QPushButton#gridZoomStep:hover{color:#c5f1ff;background:transparent;border:0}
          QPushButton#gridZoomStep:pressed{color:#4daedb;background:transparent;border:0}
          QLabel#makerCredit{font-size:10px;color:#71889b;background:transparent;padding-right:3px}
          ScrollingSongTitle#nowPlayingTitle{background:transparent;border:none}
          QWidget#projectHeader{background:#111923;border:none}
          QWidget#nowPlayingTitle{background:transparent;border:none}
          QWidget#analysisToolbar{background:#111923;border:1px solid #304559;border-radius:5px}
          QWidget#noteGridPanel{background:#111923;border:1px solid #304559;border-radius:5px}
          QScrollArea#noteGridScroll{background:#111923;border:0}
          QScrollArea#noteGridScroll QWidget#qt_scrollarea_viewport{background:#111923}
          QPushButton[gridModeButton='true']{background:#1c2d3d;border:1px solid #34536d;border-radius:3px;color:#a7bfd0;padding:2px 5px;font-weight:600}
          QPushButton[gridModeButton='true']:hover{background:#263e51}
          QPushButton[gridModeButton='true']:checked{background:#244661;border:1px solid #4a7695;border-bottom:3px solid #7bd6ff;color:#e1f4ff}
          QLabel#gridHint{color:#8fa9bb;font-size:11px}
          QLabel#gridTitle{color:#c2d4e2;font-size:12px;font-weight:600;background:transparent}
          QWidget#analysisToolbar QLabel{background:transparent}
          QLabel#headerTimeLabel{color:#9dbcd0;background:transparent;border:0;font-family:'Cascadia Mono','Consolas',monospace;font-size:12px;font-weight:600;padding:0}
          QLabel#timeLabel{background:transparent;color:#a5e5ff;border:0;font-family:'Cascadia Mono','Consolas',monospace;font-size:14px;font-weight:600;padding:0px 2px}
          QLabel#loopInfo{background:transparent}
          QLabel#menuAppTitle{color:#a5e5ff;font-family:'Bahnschrift','Segoe UI';font-weight:700;font-size:15px}
          QTabWidget#mainTabs::pane{border:1px solid #293f52;border-radius:4px;background:#111923}
          QTabBar#mainTabBar{background:#111923}
          QTabBar#headerWorkspaceTabs{background:transparent}
          QTabBar#headerWorkspaceTabs::tab{padding:6px 11px;min-width:74px;border:1px solid #25455c;border-bottom:2px solid transparent;background:#122638;color:#c9dae6}
          QTabBar#headerWorkspaceTabs::tab:selected{background:#254d6d;color:#e8f6ff;border-bottom:2px solid #7bd6ff}
          QTabBar#headerWorkspaceTabs::tab:hover:!selected{background:#263e51}
          QTabBar#mainTabBar::tab{margin-top:2px;padding:7px 15px;min-width:90px;border-bottom:2px solid transparent}
          QTabBar#mainTabBar::tab:selected{background:#234b68;color:#d4efff;border-bottom:2px solid #7bd6ff}
          QLabel#ioDescription{color:#9bb0c1;font-size:12px;padding:2px 0}
          QTabWidget#ioSections::pane{border:1px solid #34495d;border-radius:7px;background:#15212d}
          QTabWidget#ioSections QTabBar::tab{padding:9px 24px;background:#1c2b3a}
          QTabWidget#ioSections QTabBar::tab:selected{background:#31526e;color:#a8e2ff}
          QTabWidget#mainTabs::tab-bar{alignment:right}
          QTabWidget::pane{border:1px solid #2c3b4b;border-radius:5px}
          QTabBar::tab{background:#1b2938;padding:7px 16px;margin-right:2px;border-radius:4px}
          QTabBar::tab:selected{background:#2b4862;color:#7bd6ff}
          QTabBar#mainTabBar::tab:first{font-weight:700;min-width:110px;padding:7px 15px}
          QTabBar#mainTabBar::tab:first:selected{background:#254d6d;border-bottom:2px solid #7bd6ff}
          QPushButton#tunerQuickButton{background:#1b2938;border:1px solid #34495d;border-radius:4px;padding:0px;min-height:0px;min-width:0px}
          QPushButton#tunerQuickButton:hover{background:#294d70;border-color:#7bd6ff}
          QPushButton{background:#172d40;border:1px solid #31516a;padding:4px 8px;border-radius:4px;min-height:19px}
          QPushButton:hover{background:#366b9a}
          QPushButton[transportIcon='true']{padding:2px;min-width:30px;min-height:28px;max-height:30px}
          QPushButton:disabled{background:#28333e;color:#7d8a96;border-color:#34404c}
          QLineEdit,QComboBox,QSpinBox{padding:5px;background:#202d3b;border:1px solid #34475c;border-radius:4px}
          /* Small arrow controls share the frameless cyan treatment. */
          QSpinBox::up-button,QSpinBox::down-button{background:transparent;border:0;width:14px;color:#7bd6ff}
          QSpinBox::up-arrow,QSpinBox::down-arrow{width:8px;height:8px}
          QComboBox::drop-down{background:transparent;border:0;width:19px;color:#7bd6ff}
          QComboBox::down-arrow{width:8px;height:8px}
          QSpinBox,QComboBox{selection-background-color:#245474}
          QScrollArea{border:0}
          QCheckBox{spacing:5px}
          QWidget#stemPanel{background:#172431;border:1px solid #33485d;border-radius:6px}
          QWidget#playStemPanel{background:transparent;border:0;border-radius:0}
          QWidget#sidebarTabs{background:#111923}
          QWidget#playStemPanel{background:#111923;border:0}
          QTabWidget#sidebarTabs QWidget{border-radius:0}
          QScrollArea#mixerScroll{background:transparent;border:0}
          QLabel#mixerTitle{background:transparent;font-size:12px;font-weight:600;color:#c2d4e2}
          QLabel#stemName{background:transparent;font-size:12px;font-weight:400;color:#d5e1ed}
          QWidget#playStemPanel QLabel{background:transparent}
          QWidget#noteGridPanel QLabel{background:transparent}
          QPushButton[stemToggle='true']{background:transparent;padding:1px;border:1px solid #294559;border-radius:3px;color:#7bd6ff}
          QPushButton[soloToggle='true']{background:transparent;padding:1px;border:1px solid #294559;border-radius:3px;color:#7bd6ff;font-weight:700}
          QLabel[soloDimmed='true']{color:#657686}
          QSlider[soloDimmed='true']::groove:horizontal{background:#25313c}
          QSlider[soloDimmed='true']::sub-page:horizontal{background:#344656}
          QSlider[soloDimmed='true']::handle:horizontal{background:#5b6e7d}
          QPushButton[stemToggle='true'][soloDimmed='true']{color:#667989;border-color:#2a3947}
          QPushButton[soloToggle='true']:checked{background:#214662;border-bottom:2px solid #7bd6ff;color:#d4f3ff}
          QPushButton[stemToggle='true']:!checked{background:#263c51;color:#ffe0c8;border-bottom:3px solid #e5a37b;font-weight:700}
          QPushButton[stemToggle='true']:checked{background:transparent;color:#7bd6ff;border:1px solid #294559}
          QPushButton#resetBpmButton{background:transparent;border:0;padding:2px;border-radius:3px}
          QPushButton#resetBpmButton:hover{background:#243e51;border:0}
          QLabel#gridNotice{color:#819aad;font-size:11px}
          QLabel#loopInfo{color:#a2b8ca;font-size:11px}
          /* Uniform subtle housing for all sliders: stem mixer, export, complexity, zoom. */
          QSlider{background:transparent;border:0;border-radius:2px;padding:2px}
          QSlider:hover{background:transparent;border:0}
          QSlider:disabled{background:#15222f;border-color:#253645}
          QSlider::groove:horizontal{height:5px;background:#2b4052;border-radius:2px}
          QSlider::sub-page:horizontal{background:#64b9e9;border-radius:2px}
          QSlider::handle:horizontal{background:#7bd6ff;border:1px solid #48a6d9;width:11px;margin:-5px 0;border-radius:6px}
          /* Both zoom axes share exactly the same rail, thumb, and accent. */
          QSlider#gridZoom,QSlider#gridRowHeight{background:transparent;border:0;padding:0}
          QSlider#gridZoom::groove:horizontal,QSlider#gridRowHeight::groove:horizontal{height:5px;background:#2b4052;border-radius:2px}
          QSlider#gridZoom::sub-page:horizontal,QSlider#gridRowHeight::sub-page:horizontal{background:#64b9e9;border-radius:2px}
          QSlider#gridZoom::handle:horizontal,QSlider#gridRowHeight::handle:horizontal{background:#d5ecfa;border:1px solid #72bde9;width:11px;margin:-5px 0;border-radius:6px}
          /* Identical slim native scrollbars on both axes. */
          QScrollBar:vertical{background:#101c28;width:9px;margin:0;border:0}
          QScrollBar:horizontal{background:#101c28;height:9px;margin:0;border:0}
          QScrollBar::handle:vertical,QScrollBar::handle:horizontal{background:#35546a;border-radius:4px;min-height:22px;min-width:22px}
          QScrollBar::handle:vertical:hover,QScrollBar::handle:horizontal:hover{background:#4a7d99}
          QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical,QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;height:0;border:0;background:transparent}
          QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical,QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:transparent}
          QScrollArea{background:#141e2a}
          QPushButton[transportIcon='true']{background:#122638;border:1px solid #28506a;border-radius:4px;color:#7bd6ff}
          QPushButton[transportIcon='true']:hover{background:#1d4157;border-color:#7bd6ff}
          /* Hardware-style status LED: same button face, only a slim light at its foot. */
          QPushButton[transportIcon='true']:checked{background:#1d3042;border:1px solid #34526b;border-bottom:3px solid #7bd6ff;border-radius:6px}
          QPushButton[transportIcon='true']:checked:hover{background:#263d52;border:1px solid #47657c;border-bottom:3px solid #9ce4ff}
          QPushButton[stemToggle='true']{min-height:19px;min-width:23px}
          /* Export mixer keeps its own panel; PLAY mixer has no dark box. */
          QProgressBar{max-height:4px;background:#202d3b;border:0}
          QProgressBar::chunk{background:#7bd6ff}
        ''')
        self.setup_developer_menus()
        # No duplicate top navigation: existing workspaces remain accessible
        # through Import / Export, Practice, the sidebar and the tuner.
        self.tabs.setTabVisible(1, False)  # Library uses the left-hand sidebar tabs.
        self.tabs.setTabVisible(2, False)  # Import / Export uses the header action.
        self.tabs.tabBar().hide()
        # Native QTabBar in the same header row as the project controls.
        # Its selection drives the existing QTabWidget and vice versa.
        self.header_tabs = QTabBar(project_header)
        self.header_tabs.setObjectName('headerWorkspaceTabs')
        self.header_tabs.setExpanding(False)
        self.header_tabs.setDrawBase(False)
        self.header_tabs.addTab(qta.icon('fa5s.play-circle', color='#7bd6ff'), 'Play Along')
        self.header_tabs.addTab(self.tuning_fork_icon(), 'Tuner')
        self.header_tabs.setCurrentIndex(0)
        self.header_tabs.currentChanged.connect(
            lambda index: self.tabs.setCurrentIndex(
                0 if index == 0 else self.tabs.indexOf(self.tuner_dialog)))
        self.tabs.currentChanged.connect(
            lambda index: self.header_tabs.setCurrentIndex(
                1 if self.tabs.widget(index) is self.tuner_dialog else 0))
        project_row.addWidget(self.header_tabs, 0, Qt.AlignVCenter)

    def compare_with_isophonics(self):
        """Benchmark the original Beatles recording against verified chord labels."""
        if self.analysis_mode.currentIndex() == 0 or not self.chord_data:
            QMessageBox.information(self, 'Isophonics benchmark',
                                    'Analyze the song in Chord Mode first.')
            return
        title = str((self.song_metadata or {}).get('title', ''))
        filename = str(getattr(self, 'source_audio', '') or '')
        candidate = (title + ' ' + Path(filename).stem).lower()
        if 'i saw her standing there' not in candidate.replace('_', ' ').replace('-', ' '):
            QMessageBox.warning(
                self, 'Wrong recording',
                'This benchmark belongs to The Beatles - I Saw Her Standing There '
                '(Please Please Me album version). Load that track first. '
                'Other recordings have different chord timing.')
            return
        try:
            from chord_comparison import (fetch_isophonics_benchmark, compare,
                                          save_report)
            reference = fetch_isophonics_benchmark()
            predictions = [(float(t), str(note)) for t, note in self.chord_data]
            end_time = self._duration / 1000.0 if self._duration > 0 else None
            result = compare(predictions, reference, end_seconds=end_time)
            output = ROOT / 'isophonics-beatles-i-saw-her-standing-there-report.csv'
            save_report(output, result)
            QMessageBox.information(
                self, 'Isophonics benchmark',
                f"Chord agreement: {result['exact_percent']}%\n"
                f"Root agreement: {result['root_percent']}%\n"
                f"Compared: {result['compared_seconds']} seconds\n"
                f"Disagreement regions: {len(result['intervals'])}\n\n"
                f"Report: {output}\n\n"
                "Reference: Isophonics v1.2, human-annotated; not Chordify.")
        except (OSError, ValueError, IndexError, TimeoutError) as exc:
            QMessageBox.warning(self, 'Reference unavailable',
                                f'Could not retrieve or compare Isophonics annotations: {exc}')

    def compare_chords_with_reference(self):
        """Compare the current AI chord timeline against a timestamped reference."""
        if self.analysis_mode.currentIndex() == 0:
            QMessageBox.information(self, 'Chord comparison',
                                    'Switch to Chord Mode and analyze the song before comparing chord accuracy.')
            return
        if not self.chord_data:
            QMessageBox.information(self, 'Chord comparison',
                                    'Analyze a song in Chord Mode first.')
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Choose reference CSV (time,chord)', str(ROOT),
            'CSV reference (*.csv)')
        if not path:
            return
        try:
            from chord_comparison import parse_csv, compare, save_report
            reference = parse_csv(path)
            predictions = [(float(t), str(note)) for t, note in self.chord_data]
            duration = self._duration / 1000.0 if self._duration > 0 else None
            report = compare(predictions, reference, end_seconds=duration)
            target = str(Path(path).with_name(Path(path).stem + '-rifflab-comparison.csv'))
            save_report(target, report)
            QMessageBox.information(
                self, 'Chord comparison',
                f"Exact chord agreement: {report['exact_percent']}%\n"
                f"Root-note agreement: {report['root_percent']}%\n"
                f"Compared: {report['compared_seconds']} seconds\n"
                f"Disagreement intervals: {len(report['intervals'])}\n\n"
                f"Detailed CSV report saved to:\n{target}\n\n"
                "Reference chords are user-supplied, not fetched from Chordify.")
        except (OSError, ValueError, IndexError) as exc:
            QMessageBox.warning(self, 'Chord comparison failed', str(exc))

    def setup_developer_menus(self):
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        bar.setStyleSheet("QMenuBar{background:#172331;color:#e8edf2;border-bottom:1px solid #344658;}"
                          "QMenuBar::item{padding:6px 13px;}"
                          "QMenuBar::item:selected{background:#28455b;}"
                          "QMenu{background:#172331;color:#e8edf2;border:1px solid #344658;}"
                          "QMenu::item{padding:6px 24px;}"
                          "QMenu::item:selected{background:#28455b;}")
        # Center brand over the entire menu bar, not just the unused right corner.
        # Mouse-transparent label leaves File / View menus fully interactive.
        self.menu_title_label = QLabel('RiffLab', bar)
        self.menu_title_label.setObjectName('menuAppTitle')
        self.menu_title_label.setAlignment(Qt.AlignCenter)
        self.menu_title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        bar.installEventFilter(self)
        QTimer.singleShot(0, lambda: self.menu_title_label.setGeometry(
            max(0, (bar.width() - 190) // 2), 0, 190, bar.height()))
        file_menu = bar.addMenu('&File')
        file_menu.addAction('Open Project…', self.open_project)
        file_menu.addAction('Save Project', self.save_project)
        file_menu.addAction('Save Project As…', self.save_project_as_menu)
        recent = file_menu.addMenu('Recent Projects')
        recent.aboutToShow.connect(lambda: self.fill_recent_file_menu(recent))
        file_menu.addSeparator()
        file_menu.addAction('Import Audio…', self.open_file)
        file_menu.addAction('Import / Export', lambda: self.tabs.setCurrentIndex(2))
        file_menu.addAction('Export WAV…', self.export_mix)
        file_menu.addAction('Compare Chords with Reference CSV…', self.compare_chords_with_reference)
        file_menu.addAction('Benchmark Beatles Chords (Isophonics)…', self.compare_with_isophonics)
        file_menu.addSeparator()
        file_menu.addAction('Exit', self.close)
        view = bar.addMenu('&View')
        self.view_mixer_action = view.addAction('Stem Mixer')
        self.view_mixer_action.setCheckable(True)
        self.view_mixer_action.setChecked(True)
        self.view_mixer_action.toggled.connect(self.play_splitter.widget(0).setVisible)
        self.view_tuner_action = view.addAction('Tuner')
        self.view_tuner_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.tuner_dialog))
        view.addSeparator()
        workspace = view.addMenu('Workspace')
        workspace.addAction('Save Workspace…', self.save_workspace_as)
        workspace.addAction('Load Workspace…', self.load_workspace_from)
        workspace.addAction('Reset Workspace', self.reset_workspace)
        view.addSeparator()
        self.view_timeline_action = view.addAction('Timeline')
        self.view_timeline_action.setCheckable(True)
        self.view_timeline_action.setChecked(True)
        self.view_timeline_action.toggled.connect(self.chord_scroll.setVisible)
        self.view_indicator_action = view.addAction('Main Indicator')
        self.view_indicator_action.setCheckable(True)
        self.view_indicator_action.setChecked(True)
        self.view_indicator_action.toggled.connect(self.chord.setVisible)
        view.addAction('Reset Mixer Layout', self.reset_mixer_layout)
        view.addAction('Show PLAY', lambda: self.tabs.setCurrentIndex(0))
        view.addAction('Show Library', lambda: self.tabs.setCurrentIndex(1))

    def save_project_as_menu(self):
        original = self.project_file
        self.project_file = None
        self.save_project()
        if self.project_file is None:
            self.project_file = original

    def fill_recent_file_menu(self, menu):
        menu.clear()
        for idx in range(self.recent_projects.count()):
            path = self.recent_projects.itemData(idx)
            if path:
                menu.addAction(self.recent_projects.itemText(idx),
                               lambda checked=False, p=path: self.load_project(p))
        if not menu.actions():
            action = menu.addAction('No recent projects')
            action.setEnabled(False)

    def workspace_state(self):
        return {
            'splitter': list(self.play_splitter.sizes()),
            'grid_zoom': self.grid_zoom.value(),
            'grid_height': self.grid_row_height.value(),
            'mixer_visible': self.play_splitter.widget(0).isVisible(),
            'timeline_visible': self.chord_scroll.isVisible(),
            'indicator_visible': self.chord.isVisible(),
            'active_tab': self.tabs.currentIndex(),
        }

    def apply_workspace_state(self, state):
        if not isinstance(state, dict):
            raise ValueError('Invalid workspace')
        for key, slider in [('grid_zoom',self.grid_zoom),('grid_height',self.grid_row_height)]:
            if key in state:
                slider.setValue(max(slider.minimum(),min(slider.maximum(),int(state[key]))))
        sizes = state.get('splitter')
        if isinstance(sizes, list) and len(sizes) == self.play_splitter.count():
            self.play_splitter.setSizes([max(1,int(n)) for n in sizes])
        for key, action in [('mixer_visible',self.view_mixer_action),
                            ('timeline_visible',self.view_timeline_action),
                            ('indicator_visible',self.view_indicator_action)]:
            if key in state:
                action.setChecked(bool(state[key]))
        tab = int(state.get('active_tab',0))
        if 0 <= tab < self.tabs.count():
            self.tabs.setCurrentIndex(tab)

    def save_workspace_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self,'Save RiffLab Workspace','RiffLab-workspace.json','Workspace (*.json)')
        if path:
            Path(path).write_text(json.dumps(self.workspace_state(),indent=2),encoding='utf-8')
            self.status_message('Workspace saved.')

    def load_workspace_from(self):
        path, _ = QFileDialog.getOpenFileName(
            self,'Load RiffLab Workspace','','Workspace (*.json)')
        if path:
            try:
                self.apply_workspace_state(json.loads(Path(path).read_text(encoding='utf-8')))
                self.status_message('Workspace loaded.')
            except (ValueError,TypeError,OSError) as exc:
                QMessageBox.warning(self,'Workspace',str(exc))

    def reset_workspace(self):
        self.apply_workspace_state({'grid_zoom':100,'grid_height':38,
                                    'splitter':[270,780],'mixer_visible':True,
                                    'timeline_visible':True,'indicator_visible':True,
                                    'active_tab':0})
        self.status_message('Workspace reset.')

    def reset_mixer_layout(self):
        self.play_splitter.widget(0).show()
        self.view_mixer_action.setChecked(True)
        self.play_splitter.setSizes([270, 780])

    def show_library_sidebar(self):
        """Open the real Library in the left pane and keep the timeline visible."""
        self.tabs.setCurrentIndex(0)
        self.play_splitter.widget(0).show()
        self.sidebar_tabs.setCurrentIndex(1)

    def toggle_tuner_panel(self):
        self.tabs.setCurrentWidget(self.tuner_dialog)

    def status_message(self, message):
        self.status.setText(message)

    def _shortcut_allowed(self):
        # Never steal typing from the YouTube URL or other editable text fields.
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox
        focus = QApplication.focusWidget()
        return not isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox))

    def _shortcut_play(self):
        if self._shortcut_allowed():
            self.toggle_play()

    def _shortcut_stop(self):
        if self._shortcut_allowed():
            self.stop_playback()

    def _shortcut_marker(self, which):
        if self._shortcut_allowed():
            self.set_loop_point(which)

    def discover_existing_projects(self):
        candidates = set((ROOT / 'projects').glob('*.riff'))
        try:
            candidates.update(Path(p) for p in json.loads(
                (ROOT / 'recent_projects.json').read_text(encoding='utf-8')))
        except (OSError, ValueError, TypeError):
            pass
        for path in candidates:
            if path.is_file():
                self.index_library_project(path)

    @staticmethod
    def tuning_fork_icon():
        """Draw a small genuine tuning-fork symbol, without another icon package."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#7bd6ff'), 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        # Two prongs and the curved bridge; handle continues below.
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPainterPath
        path = QPainterPath(QPointF(8, 4))
        path.lineTo(8, 14)
        path.cubicTo(8, 25, 24, 25, 24, 14)
        path.lineTo(24, 4)
        painter.drawPath(path)
        painter.drawLine(16, 22, 16, 30)
        painter.end()
        return QIcon(pixmap)

    def init_library(self):
        with sqlite3.connect(self.library_db) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS songs (
                    project_path TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL DEFAULT '',
                    album TEXT NOT NULL DEFAULT '',
                    tuning TEXT NOT NULL DEFAULT 'Unknown',
                    musical_key TEXT NOT NULL DEFAULT '',
                    original_bpm REAL NOT NULL DEFAULT 0,
                    practice_bpm REAL NOT NULL DEFAULT 0,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    last_played TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def get_library_metadata(self, path):
        if not path:
            return {}
        with sqlite3.connect(self.library_db) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM songs WHERE project_path=?',
                             (str(Path(path).resolve()),)).fetchone()
        if not row:
            return {}
        return {k: row[k] for k in ('title', 'artist', 'album', 'tuning', 'musical_key')}

    def index_library_project(self, path, data=None, played=False):
        path = Path(path).resolve()
        if not path.is_file():
            return
        if data is None:
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                return
        if data.get('format') != 'RiffLab Project':
            return
        meta = data.get('metadata') or {}
        title = str(meta.get('title') or path.stem)
        artist = str(meta.get('artist') or '')
        album = str(meta.get('album') or '')
        tuning = str(meta.get('tuning') or 'Unknown')
        musical_key = str(meta.get('musical_key') or '')
        original_bpm = float(data.get('detected_bpm') or 0)
        practice_bpm = float(data.get('bpm') or original_bpm)
        now = datetime.now().isoformat(timespec='seconds') if played else None
        with sqlite3.connect(self.library_db) as db:
            db.execute("""
                INSERT INTO songs (project_path,title,artist,album,tuning,musical_key,
                                   original_bpm,practice_bpm,last_played)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_path) DO UPDATE SET
                    title=excluded.title, artist=excluded.artist, album=excluded.album,
                    original_bpm=CASE WHEN songs.original_bpm=0 THEN excluded.original_bpm ELSE songs.original_bpm END,
                    practice_bpm=excluded.practice_bpm,
                    last_played=COALESCE(excluded.last_played,songs.last_played)
            """, (str(path), title, artist, album, tuning, musical_key,
                  original_bpm, practice_bpm, now))
        if hasattr(self, 'library_table'):
            self.refresh_library()

    def refresh_library(self, *_args):
        if not hasattr(self, 'library_table'):
            return
        query = self.library_search.text().strip().lower()
        tuning = self.library_tuning.currentText()
        lo, hi = self.library_min_bpm.value(), self.library_max_bpm.value()
        favorite = self.library_favorites.isChecked()
        sorts = ('title COLLATE NOCASE', 'artist COLLATE NOCASE',
                 'original_bpm', 'last_played DESC')
        order = sorts[self.library_sort.currentIndex()]
        with sqlite3.connect(self.library_db) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(f"""
                SELECT * FROM songs WHERE
                (LOWER(title) LIKE ? OR LOWER(artist) LIKE ? OR LOWER(album) LIKE ?)
                AND (?='All tunings' OR tuning=?)
                AND original_bpm BETWEEN ? AND ?
                AND (?=0 OR favorite=1)
                ORDER BY {order}, title COLLATE NOCASE
            """, (f'%{query}%',)*3 + (tuning, tuning, lo, hi, int(favorite))).fetchall()
        self.library_table.setSortingEnabled(False)
        self.library_table.setRowCount(len(rows))
        for row_index, song in enumerate(rows):
            values = ('★' if song['favorite'] else '', song['title'], song['artist'],
                      song['album'], song['tuning'], f"{song['original_bpm']:g}",
                      f"{song['practice_bpm']:g}", song['last_played'] or '—')
            for col, value in enumerate(values):
                # One line per song: artist and title, no stacked labels.
                display_value = str(value)
                if col == 1 and song['artist']:
                    display_value = f"{song['artist']} · {song['title']}"
                item = QTableWidgetItem(display_value)
                if col == 1:
                    item.setToolTip(display_value)
                item.setData(Qt.UserRole, song['project_path'])
                if col in (5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.library_table.setItem(row_index, col, item)
            self.library_table.setRowHeight(row_index, 24)
        self.library_table.setSortingEnabled(False)
        self.library_summary.setText(
            f'{len(rows)} songs · Double-click or drag to open')

    def show_library_context_menu(self, pos):
        """Right-click actions for the song actually under the cursor."""
        item = self.library_table.itemAt(pos)
        if item is None:
            return
        self.library_table.selectRow(item.row())
        path = self.selected_library_path()
        if not path:
            return
        menu = QMenu(self.library_table)
        open_action = menu.addAction('Open project')
        details_action = menu.addAction('Edit song details')
        favorite_action = menu.addAction('Toggle favorite')
        menu.addSeparator()
        copy_action = menu.addAction('Copy project path')
        menu.addSeparator()
        remove_action = menu.addAction('Remove from Library')
        selected = menu.exec(self.library_table.viewport().mapToGlobal(pos))
        if selected == open_action:
            self.open_library_song()
        elif selected == details_action:
            self.edit_library_song()
        elif selected == favorite_action:
            self.toggle_library_favorite()
        elif selected == copy_action:
            QApplication.clipboard().setText(path)
            self.status_message('Project path copied.')
        elif selected == remove_action:
            self.remove_library_song()

    def selected_library_path(self):
        row = self.library_table.currentRow()
        if row < 0:
            return None
        item = self.library_table.item(row, 1)
        return item.data(Qt.UserRole) if item else None

    def open_library_song(self, *_args):
        path = self.selected_library_path()
        if not path:
            return
        if not Path(path).is_file():
            QMessageBox.warning(self, 'Missing project',
                                'This project was moved or deleted. Remove it from the Library or restore it.')
            return
        self.load_project(path)
        if self.project_file and str(Path(self.project_file).resolve()) == str(Path(path).resolve()):
            self.tabs.setCurrentIndex(0)

    def add_current_to_library(self):
        if self.project_file and Path(self.project_file).is_file():
            self.index_library_project(self.project_file)
            self.status_message('Current project is in the Library.')
        else:
            self.save_project()

    def toggle_library_favorite(self):
        path = self.selected_library_path()
        if not path:
            return
        with sqlite3.connect(self.library_db) as db:
            db.execute('UPDATE songs SET favorite=1-favorite WHERE project_path=?', (path,))
        self.refresh_library()

    def remove_library_song(self):
        path = self.selected_library_path()
        if not path:
            return
        answer = QMessageBox.question(
            self, 'Remove from Library',
            'Remove this song from the Library?\nThe .riff project and audio files will be kept.')
        if answer != QMessageBox.Yes:
            return
        with sqlite3.connect(self.library_db) as db:
            db.execute('DELETE FROM songs WHERE project_path=?', (path,))
        self.refresh_library()

    def edit_library_song(self):
        path = self.selected_library_path()
        if not path:
            return
        with sqlite3.connect(self.library_db) as db:
            db.row_factory = sqlite3.Row
            song = db.execute('SELECT * FROM songs WHERE project_path=?', (path,)).fetchone()
        if not song:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit Song Details')
        form = QFormLayout(dialog)
        fields = {}
        for key, label in [('title', 'Song Title'), ('artist', 'Artist'),
                           ('album', 'Album'), ('musical_key', 'Key')]:
            field = QLineEdit(str(song[key]))
            fields[key] = field
            form.addRow(label, field)
        tuning = QComboBox()
        tuning.setEditable(True)
        tuning.addItems(['Unknown', 'E Standard', 'Eb Standard', 'D Standard',
                         'Drop D', 'Drop C#', 'Drop C', 'Other'])
        tuning.setCurrentText(song['tuning'])
        form.addRow('Tuning', tuning)
        bpm = QDoubleSpinBox()
        bpm.setRange(0, 300)
        bpm.setDecimals(1)
        bpm.setValue(song['original_bpm'])
        form.addRow('Original BPM', bpm)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        if not fields['title'].text().strip():
            QMessageBox.warning(self, 'Song title', 'A song title is required.')
            return
        with sqlite3.connect(self.library_db) as db:
            db.execute("""
                UPDATE songs SET title=?, artist=?, album=?, tuning=?, musical_key=?,
                                 original_bpm=? WHERE project_path=?
            """, (fields['title'].text().strip(), fields['artist'].text().strip(),
                  fields['album'].text().strip(), tuning.currentText().strip(),
                  fields['musical_key'].text().strip(), bpm.value(), path))
        # Persist manually edited details to the project manifest too.
        try:
            project = Path(path)
            data = json.loads(project.read_text(encoding='utf-8'))
            data['metadata'] = {
                'title': fields['title'].text().strip(), 'artist': fields['artist'].text().strip(),
                'album': fields['album'].text().strip(), 'tuning': tuning.currentText().strip(),
                'musical_key': fields['musical_key'].text().strip()}
            temp = project.with_suffix('.riff.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(project)
            if self.project_file and str(Path(self.project_file).resolve()) == str(project.resolve()):
                self.song_metadata = dict(data['metadata'])
                self.update_now_playing()
        except (OSError, ValueError):
            pass
        self.refresh_library()

    def _recent_file(self):
        return ROOT / 'recent_projects.json'

    def refresh_recent_projects(self):
        try:
            paths = json.loads(self._recent_file().read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            paths = []
        paths = [str(p) for p in paths if isinstance(p, str) and Path(p).is_file()]
        self.recent_projects.blockSignals(True)
        self.recent_projects.clear()
        self.recent_projects.addItem('Choose a saved song…', None)
        for path in paths[:15]:
            self.recent_projects.addItem(Path(path).stem, path)
            self.recent_projects.setItemData(self.recent_projects.count()-1, path, Qt.ToolTipRole)
        self.recent_projects.setCurrentIndex(0)
        self.recent_projects.blockSignals(False)

    def remember_project(self, path):
        path = str(Path(path).resolve())
        try:
            previous = json.loads(self._recent_file().read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            previous = []
        recent = [path] + [p for p in previous if p != path and Path(p).is_file()]
        self._recent_file().write_text(json.dumps(recent[:15], indent=2), encoding='utf-8')
        self.refresh_recent_projects()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'now_playing'):
            # Preserve room for tabs and the tuner at small window sizes.
            self.now_playing.setFixedWidth(max(0, min(560, self.width() - 1090)))

    def update_now_playing(self):
        if not hasattr(self, 'now_playing'):
            return
        meta = self.song_metadata or {}
        title = str(meta.get('title') or '').strip()
        artist = str(meta.get('artist') or '').strip()
        if not title and self.project_file:
            title = Path(self.project_file).stem
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', title) and getattr(self, 'url', None) and self.url.text().strip():
            title = ''
        label = f'{artist} — {title}' if artist and title else title
        self.now_playing.setText(label)
        self.now_playing.setToolTip(label)

    @staticmethod
    def safe_project_filename(value):
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(value))
        value = re.sub(r'\s+', ' ', value).strip(' .')
        return value[:130] or 'Untitled Song'

    def ask_first_save_details(self):
        """Collect editable metadata only for the first save of a new song."""
        meta = dict(self.song_metadata or {})
        title = str(meta.get('title') or '').strip()
        artist = str(meta.get('artist') or '').strip()
        album = str(meta.get('album') or '').strip()
        if not title and self.source_audio:
            title = self.source_audio.stem
        # YouTube cache paths are IDs, not human-readable titles.
        if title and re.fullmatch(r'[A-Za-z0-9_-]{11}', title) and self.url.text().strip():
            title = ''
        suggested = f'{artist} - {title}' if artist and title else title
        dialog = QDialog(self)
        dialog.setWindowTitle('Save Song Details')
        dialog.setMinimumWidth(390)
        form = QFormLayout(dialog)
        fields = {}
        for key, label, value in (
            ('project_name', 'Project Name', suggested),
            ('artist', 'Artist', artist),
            ('album', 'Album', album),
            ('title', 'Song Title', title),
        ):
            edit = QLineEdit(value)
            edit.setPlaceholderText(label)
            form.addRow(label, edit)
            fields[key] = edit
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return None
        values = {key: field.text().strip() for key, field in fields.items()}
        if not values['title']:
            QMessageBox.warning(self, 'Song details', 'Please enter a song title.')
            return None
        if not values['project_name']:
            values['project_name'] = (f"{values['artist']} - {values['title']}"
                                      if values['artist'] else values['title'])
        return values

    def save_project(self):
        if self.processing:
            self.status_message('Wait for import and analysis to finish before saving.')
            return
        if not self.stems and not self.source_audio:
            self.status_message('Open a song before saving a project.')
            return
        first_save = not (self.project_file and Path(self.project_file).is_file())
        new_details = None
        if first_save:
            new_details = self.ask_first_save_details()
            if new_details is None:
                return
            filename = self.safe_project_filename(new_details['project_name']) + '.riff'
            default = str(ROOT / 'projects' / filename)
            Path(default).parent.mkdir(parents=True, exist_ok=True)
            path, _ = QFileDialog.getSaveFileName(self, 'Save RiffLab Project', default,
                                                  'RiffLab Projects (*.riff)')
            if not path:
                return
        else:
            path = self.project_file
        path = Path(path)
        if path.suffix.lower() != '.riff':
            path = path.with_suffix('.riff')
        metadata = dict((self.get_library_metadata(self.project_file) if self.project_file else {})
                        or self.song_metadata)
        if new_details:
            metadata.update({key: new_details[key] for key in ('artist', 'album', 'title')})
            metadata['project_name'] = new_details['project_name']
        pos = self.live.position_ms if self.live else self.player.position()
        data = {
            'format': 'RiffLab Project', 'version': 1,
            'metadata': metadata,
            'source_audio': str(self.source_audio.resolve()) if self.source_audio else None,
            'stem_folder': str(self.folder.resolve()) if self.stems and self.folder else None,
            'youtube_url': self.url.text().strip(),
            'position_ms': int(pos),
            'in_ms': self.loop_a_ms, 'out_ms': self.loop_b_ms,
            'loop': self.loop_enabled,
            'bpm': self.grid_bpm.value(), 'detected_bpm': self.detected_bpm,
            'analysis_mode': self.analysis_mode.currentIndex(), 'accuracy': self.accuracy.currentIndex(),
            'stability': self.sensitivity.value(), 'transpose': self.transpose.value(),
            'zoom': self.grid_zoom.value(), 'row_height': self.grid_row_height.value(), 'lookahead_ms': self.chord_lookahead.value(),
            'auto_scroll': self.follow.isChecked(),
            'levels': {name: self.volumes[name].value() for name in STEMS},
            'enabled': {name: self.checks[name].isChecked() for name in STEMS},
            'solo': {name: self.solos[name].isChecked() for name in STEMS},
            'chord_data': self.chord_data, 'beat_times': self.beat_times,
            'section_overrides': self.section_overrides,
        }
        temp = path.with_suffix('.riff.tmp')
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(path)
            self.project_file = str(path)
            self.song_metadata = dict(metadata)
            self.update_now_playing()
            self.remember_project(path)
            self.index_library_project(path, data)
            self.status_message(f'Project saved: {path.name}')
            return True
        except OSError as exc:
            QMessageBox.warning(self, 'Save project', str(exc))
        return False

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open RiffLab Project',
                                              str(ROOT / 'projects'), 'RiffLab Projects (*.riff)')
        if path:
            self.load_project(path)

    def open_recent_project(self, index):
        path = self.recent_projects.itemData(index)
        if path:
            self.load_project(path)

    def load_project(self, path):
        if self.processing:
            self.status_message('Please wait until the current processing finishes.')
            return
        try:
            path = Path(path).resolve()
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('format') != 'RiffLab Project' or data.get('version') != 1:
                raise ValueError('Not a supported RiffLab project.')
            folder = Path(data['stem_folder']) if data.get('stem_folder') else None
            source = Path(data['source_audio']) if data.get('source_audio') else None
            if folder is not None and not all((folder / f'{name}.wav').is_file() for name in STEMS):
                raise FileNotFoundError(f'Saved stems are missing: {folder}')
            if folder is None and (source is None or not source.is_file()):
                raise FileNotFoundError(f'Song file is missing: {source}')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, 'Open project', f'Cannot load project:\n{exc}')
            self.refresh_recent_projects()
            return
        if not self._confirm_unsaved_changes():
            return
        self.speed_generation += 1  # invalidate previous tempo renders
        self.project_file = str(path)
        self.url.setText(str(data.get('youtube_url') or ''))
        self.song_metadata = dict(data.get('metadata') or {})
        self.update_now_playing()
        if folder:
            self.stop_live()
            self.player.stop()
            self.source_audio = None
            self.folder = folder
            self.stems = {name: folder / f'{name}.wav' for name in STEMS}
            self.refresh_stems_led()
            self.load_waveform(self.stems)
            self.chord_data = []
            self.display_chords = []
            self.display_times = []
            self.beat_times = []
            for name in STEMS:
                self.checks[name].setEnabled(True)
                self.solos[name].setEnabled(True)
                self.volumes[name].setEnabled(True)
            self.sync_all_export_mixer()
            self.export.setEnabled(True)
            self.split_local.setEnabled(False)
            self.analyze_local.setEnabled(False)
            self.start_live()
        else:
            self.load_local(source, check_unsaved=False)
        self._restore_project_settings(data)
        self.sync_all_export_mixer()
        self.project_file = str(path)
        self.remember_project(path)
        self.index_library_project(path, data, played=True)
        self.tabs.setCurrentIndex(0)
        self.status_message(f'Project loaded: {path.stem}')
        # Restored mode is signal-blocked; explicitly start the right analysis.
        self.switch_analysis_mode()

    def _restore_project_settings(self, data):
        self.section_overrides = {int(k): str(v) for k, v in (data.get('section_overrides') or {}).items()}
        self.detected_bpm = max(1.0, float(data.get('detected_bpm', 130)))
        for name in STEMS:
            slider = self.volumes[name]
            toggle = self.checks[name]
            slider.blockSignals(True)
            toggle.blockSignals(True)
            slider.setValue(int(data.get('levels', {}).get(name, 100)))
            toggle.setChecked(bool(data.get('enabled', {}).get(name, name != 'bass')))
            slider.blockSignals(False)
            toggle.blockSignals(False)
            solo = self.solos[name]
            solo.blockSignals(True)
            solo.setChecked(bool(data.get('solo', {}).get(name, False)))
            solo.blockSignals(False)
            toggle.setAccessibleName(f'Mute {name}' if toggle.isChecked() else f'Unmute {name}')
        # Older projects may contain multiple solos or a soloed muted stem.
        # Normalize to one audible solo channel.
        active_solos = [name for name in STEMS if self.solos[name].isChecked()]
        if active_solos:
            chosen = active_solos[0]
            for name in STEMS:
                self.solos[name].blockSignals(True)
                self.solos[name].setChecked(name == chosen)
                self.solos[name].blockSignals(False)
            self.checks[chosen].blockSignals(True)
            self.checks[chosen].setChecked(True)
            self.checks[chosen].blockSignals(False)
        self.sync_all_export_mixer()
        self.volume_changed()
        self.analysis_mode.blockSignals(True)
        self.analysis_mode.setCurrentIndex(int(data.get('analysis_mode', 0)))
        self.analysis_mode.blockSignals(False)
        self.update_grid_mode_buttons()
        self.accuracy.setCurrentIndex(max(0, min(2, int(data.get('accuracy', 1)))))
        self.sensitivity.setValue(int(data.get('stability', 0)))
        self.transpose.setValue(int(data.get('transpose', 0)))
        # Workstation zoom preferences survive loading and re-analysis.
        self.chord_lookahead.setValue(int(data.get('lookahead_ms', 150)))
        self.follow.setChecked(bool(data.get('auto_scroll', True)))
        self.chord_data = data.get('chord_data', [])
        self.chord_times = [float(item[0]) for item in self.chord_data]
        self.beat_times = [float(t) for t in data.get('beat_times', [])]
        self.rebuild_chords()
        self.render_grid()
        self.loop_a_ms = data.get('in_ms')
        self.loop_b_ms = data.get('out_ms')
        self.loop_button.setChecked(bool(data.get('loop', False)))
        self._sync_loop()
        bpm = int(data.get('bpm', round(self.detected_bpm)))
        if self.grid_bpm.value() == bpm:
            self.bpm_changed(bpm)
        else:
            self.grid_bpm.setValue(bpm)
        pos = max(0, int(data.get('position_ms', 0)))
        if self.live:
            self.live.seek(pos)
            self.on_position(pos)
        elif self.player.source().isValid():
            self._seek_after_load = pos
            self._play_after_load = False
            self.player.setPosition(pos)
        # Projects restore paused; the user decides when to resume.

    def set_chord_loading(self, loading, message='Analyzing notes and chords…'):
        if not hasattr(self, 'chord_loading'):
            return
        self.chord_loading.setGeometry(self.chord_scroll.viewport().rect())
        self.chord_loading_label.setText(message)
        self.chord_loading.setVisible(bool(loading))
        if hasattr(self, 'chord_loading_stop'):
            self.chord_loading_stop.setVisible(bool(loading and self.analysis_running))
        if loading:
            self.chord_loading.raise_()

    def eventFilter(self, obj, event):
        # Let Library project drags land on waveform, grid, or grid note buttons.
        drop_target = (obj is getattr(self, 'waveform', None)
                       or obj is getattr(self, 'grid_host', None)
                       or (hasattr(self, 'chord_scroll') and obj is self.chord_scroll.viewport())
                       or bool(obj.property('riffDropTarget')))
        if drop_target and event.type() in (event.Type.DragEnter, event.Type.DragMove, event.Type.Drop):
            candidate = self._drop_candidate(event)
            if candidate is not None:
                if event.type() == event.Type.Drop:
                    if self.processing or self.analysis_running:
                        self.status_message('Finish or stop the current analysis before loading another song.')
                        event.ignore()
                        return True
                    event.acceptProposedAction()
                    if candidate.suffix.lower() == '.riff':
                        self.load_project(candidate)
                    else:
                        self.load_local(candidate.resolve())
                else:
                    event.acceptProposedAction()
                return True
        if (hasattr(self, 'menu_title_label') and obj is self.menuBar()
                and event.type() == event.Type.Resize):
            self.menu_title_label.setGeometry(
                max(0, (obj.width() - 190) // 2), 0, 190, obj.height())
        # The loading mask belongs to the grid viewport, never underneath it.
        if (hasattr(self, 'chord_loading') and obj is self.chord_scroll.viewport()
                and event.type() == event.Type.Resize):
            self.chord_loading.setGeometry(obj.rect())
            if hasattr(self, 'grid_mode_overlay'):
                self.grid_mode_overlay.move(max(0, obj.width() - self.grid_mode_overlay.width() - 5), 2)
                self.grid_mode_overlay.raise_()
            if self.chord_loading.isVisible():
                self.chord_loading.raise_()
        if (hasattr(self, 'mixer_overlay') and obj is self.stem_panel
                and event.type() == event.Type.Resize):
            self.mixer_overlay.setGeometry(self.stem_panel.rect())
            self.mixer_overlay.raise_()
        # Wheel scrolling in the nearby L-shaped controls adjusts that axis.
        # Elsewhere (especially over the note grid) standard scrolling remains.
        if event.type() == event.Type.Wheel:
            slider = None
            if obj in getattr(self, '_height_wheel_targets', ()):
                slider = self.grid_row_height
            elif obj in getattr(self, '_zoom_wheel_targets', ()):
                slider = self.grid_zoom
            if slider is not None:
                delta = event.angleDelta().y() or event.angleDelta().x()
                if not delta:
                    delta = event.pixelDelta().y() or event.pixelDelta().x()
                    step = 1 if delta > 0 else -1
                else:
                    step = max(1, round(abs(delta) / 60)) * (1 if delta > 0 else -1)
                if delta:
                    slider.setValue(slider.value() + step)
                event.accept()
                return True
        if (hasattr(self, 'chord_scroll') and
                obj is self.chord_scroll.viewport() and
                event.type() == event.Type.Resize):
            if hasattr(self, 'chord_loading'):
                self.chord_loading.setGeometry(obj.rect())
        return super().eventFilter(obj, event)

    def set_stage(self, stage):
        """Main-thread update: no fabricated percentages for Demucs/AI."""
        self.import_stage = stage
        if 'analy' in stage.lower() or 'notes' in stage.lower():
            self.set_chord_loading(True, stage)
        self.progress.setFormat(stage)
        if self.processing:
            self.progress.setRange(0, 0)
        self.status_message(stage)

    def set_busy(self, busy):
        self.processing = busy
        if hasattr(self, 'progress'):
            self.progress.setVisible(busy)
        if hasattr(self, 'stems_led'):
            self.refresh_stems_led()
        if not busy and not self.analysis_running:
            self.set_chord_loading(False)
        for widget in (self.load_url, self.load_file, self.project_save,
                       self.project_load, self.recent_projects, self.split_local,
                       self.analyze_local, self.reanalyze_button):
            widget.setEnabled(not busy)
        if busy:
            self.progress.setRange(0, 0)
            self.progress.setFormat('Preparing import…')
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.progress.setFormat('Ready')
            self.split_local.setEnabled(self.source_audio is not None)
            self.analyze_local.setEnabled(self.source_audio is not None)
            self.reanalyze_button.setEnabled(True)

    def on_error(self, message):
        self._generating_stems = False
        self.analysis_running = False
        self.cancel_analysis_button.hide()
        self.update_analysis_action()
        self.set_chord_loading(False)
        self.set_busy(False)
        self.mixing = False
        self.status_message('Error — see details and rifflab-errors.log')
        QMessageBox.warning(self, 'RiffLab', message)

    @staticmethod
    def _supported_audio_path(path):
        path = Path(path)
        return path.is_file() and path.suffix.lower() in (
            '.mp3', '.wav', '.flac', '.m4a', '.ogg')

    def _drop_candidate(self, event):
        data = event.mimeData()
        if not data.hasUrls():
            return None
        for url in data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if self._supported_audio_path(path):
                return path
            if path.is_file() and path.suffix.lower() == '.riff':
                return path
        return None

    def dragEnterEvent(self, event):
        if self._drop_candidate(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drop_candidate(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        candidate = self._drop_candidate(event)
        if candidate is None:
            event.ignore()
            return
        if self.processing or self.analysis_running:
            self.status_message('Finish or stop the current analysis before importing.')
            event.ignore()
            return
        event.acceptProposedAction()
        if candidate.suffix.lower() == '.riff':
            self.load_project(candidate)
        else:
            self.tabs.setCurrentIndex(0)
            self.load_local(candidate.resolve())

    def open_file(self):
        if self.processing:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Open Audio', '', 'Audio (*.mp3 *.wav *.flac *.m4a *.ogg)')
        if path:
            self.load_local(Path(path))

    def paste_youtube_link(self):
        """Ctrl+V accepts YouTube URLs AND existing local audio files."""
        if not self._shortcut_allowed():
            return
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        candidates = []
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    candidates.append(Path(url.toLocalFile()))
        raw = clipboard.text().strip().strip('"').strip("'")
        if raw:
            # Windows Explorer Copy as path, plain-text paths and file:// URLs.
            if raw.startswith('file://'):
                url = QUrl(raw)
                if url.isLocalFile():
                    candidates.append(Path(url.toLocalFile()))
            else:
                candidates.append(Path(raw))
        for candidate in candidates:
            if (candidate.is_file()
                    and candidate.suffix.lower() in ('.mp3', '.wav', '.flac', '.m4a', '.ogg')):
                if self.processing or self.analysis_running:
                    self.status_message('Wait until the current import or analysis is finished.')
                    return
                self.tabs.setCurrentIndex(0)
                self.load_local(candidate.resolve())
                return
        if valid_youtube_url(raw):
            self.tabs.setCurrentIndex(2)
            self.url.setText(raw)
            self.url.setFocus()
        else:
            self.status_message('Ctrl+V: copy a local audio file or YouTube link.')

    def download_url(self):
        url = self.url.text().strip()
        if not valid_youtube_url(url):
            self.on_error('Please paste a valid HTTPS YouTube URL.')
            return
        if self.processing:
            return
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Question)
        confirm.setWindowTitle('Download audio?')
        confirm.setText('Download and split audio from this YouTube link?')
        confirm.setInformativeText(url)
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.Yes)
        if confirm.exec() != QMessageBox.Yes:
            return
        self.set_busy(True)
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url):
        try:
            self.signals.stage.emit('1/3 · Downloading audio…')
            output = ROOT / 'downloads'
            output.mkdir(exist_ok=True)
            # Print the actual destination, never guess by modification time.
            from yt_dlp import YoutubeDL
            opts = {
                'format': 'bestaudio/best', 'noplaylist': True,
                'restrictfilenames': True, 'outtmpl': str(output / '%(id)s.%(ext)s'),
                'ffmpeg_location': ffmpeg_path(),
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
                'quiet': True,
                'no_warnings': False,
                'js_runtimes': {'deno': {}},
                'remote_components': ['ejs:github'],
            }
            # yt-dlp/FFmpeg subprocesses must see the bundled tools on PATH,
            # even when the app was launched from Explorer without a shell.
            bundled_ffmpeg = ffmpeg_path()
            if bundled_ffmpeg:
                opts['ffmpeg_location'] = bundled_ffmpeg
                os.environ['PATH'] = bundled_ffmpeg + os.pathsep + os.environ.get('PATH', '')
            with YoutubeDL(opts) as downloader:
                info = downloader.extract_info(url, download=True)
                video_id = re.sub(r'[^A-Za-z0-9_-]', '_', info['id'])
                raw_title = str(info.get('track') or info.get('title') or '').strip()
                artist = str(info.get('artist') or info.get('creator') or '').strip()
                album = str(info.get('album') or '').strip()
                if not artist:
                    match = re.match(r'^(.+?)\s+[-–—]\s+(.+)$', raw_title)
                    if match:
                        artist, raw_title = match.group(1).strip(), match.group(2).strip()
                # A channel/uploader is not necessarily the recording artist.
                # Leave Artist editable rather than silently claiming the uploader is the artist.
                self.signals.downloaded_metadata.emit({
                    'title': raw_title, 'artist': artist, 'album': album,
                    'tuning': 'Unknown', 'musical_key': ''})
            wav = output / f'{video_id}.wav'
            if not wav.is_file():
                raise RuntimeError('Download finished but no WAV file was found.')
            self.signals.stage.emit('2/3 · Separating stems…')
            self._split(wav)
        except Exception as exc:
            self.signals.error.emit(f'{exc}\n\nTechnical details saved in the RiffLab log.')
            self._log_exception()

    def _log_exception(self):
        with (ROOT / 'rifflab-errors.log').open('a', encoding='utf-8') as logfile:
            logfile.write(traceback.format_exc() + '\n')

    def on_downloaded_metadata(self, metadata):
        self.song_metadata = dict(metadata)
        self.update_now_playing()

    def load_local(self, path, check_unsaved=True):
        """Play immediately and automatically analyze a newly imported audio file."""
        if self.processing or self.analysis_running:
            return
        if check_unsaved and not self._confirm_unsaved_changes():
            return
        self.stop_live()
        self.source_audio = Path(path)
        self.load_waveform(path)
        self.waveform.set_duration(0)
        # YouTube tags are supplied by yt-dlp; local files use embedded audio tags.
        downloaded = self.song_metadata if self.processing and self.url.text().strip() else None
        self.song_metadata = dict(downloaded or infer_song_metadata(path))
        self.update_now_playing()
        self.project_file = None
        self.stems = {}
        self.folder = None
        self.refresh_stems_led()
        self.chord_data = []
        self.display_chords = []
        self.display_times = []
        self.beat_times = []
        self.section_overrides = {}
        self.player.stop()
        self.clear_loop()
        self.speed_generation += 1
        self.speed_ratio = 1.0
        self.detected_bpm = 130.0
        self.grid_bpm.blockSignals(True)
        self.grid_bpm.setValue(130)
        self.grid_bpm.blockSignals(False)
        self.player.setPlaybackRate(1.0)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.status_message(f'Opened: {path.name} — ready to play.')
        self.chord.setText('—')
        self.render_grid()
        for cb in self.checks.values():
            cb.setEnabled(False)
        for cb in self.solos.values():
            cb.setEnabled(False)
        for slider in self.volumes.values():
            slider.setEnabled(False)
        self.export.setEnabled(False)
        self.split_local.setEnabled(True)
        self.analyze_local.setEnabled(True)
        # Always separate first. Never analyze full-mix transients or vocals.
        self.set_stage('1/3 · Preparing stem separation…')
        self.start_split(self.source_audio)

    def update_analysis_action(self):
        """One stable toolbar action for Analyze / Stop / stopping."""
        if not hasattr(self, 'reanalyze_button'):
            return
        if self.analysis_running:
            stopping = self.analysis_cancel.is_set()
            self.reanalyze_button.setText('Stopping…' if stopping else 'Stop Analyze')
            self.reanalyze_button.setIcon(qta.icon('fa5s.stop-circle', color='#ffbdab'))
            self.reanalyze_button.setEnabled(not stopping)
            self.reanalyze_button.setToolTip('Cancel current analysis without closing this song')
        else:
            self.reanalyze_button.setText('Re-analyze')
            self.reanalyze_button.setIcon(qta.icon('fa5s.sync-alt', color='#b6dcf2'))
            self.reanalyze_button.setEnabled(True)
            self.reanalyze_button.setToolTip('Analyze the current song using the chosen accuracy')

    def toggle_analysis_action(self):
        if self.analysis_running:
            self.stop_analysis()
        else:
            self.reanalyze_current()

    def pause_for_reanalysis(self):
        """Pause current music before starting analysis; never auto-resume."""
        if self.live:
            if self.live.playing:
                self.live.pause()
                self.update_live_button()
        elif self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()

    def stop_analysis(self):
        """Ask the running worker to exit; its completion unlocks the UI."""
        if not self.analysis_running:
            return
        self.analysis_cancel.set()
        self.status_message('Stopping analysis…')
        self.cancel_analysis_button.setEnabled(False)
        self.update_analysis_action()
        self.chord_loading_label.setText('Stopping analysis…')
        self.chord_loading_stop.setEnabled(False)

    def _start_analysis_ui(self):
        self.analysis_cancel = threading.Event()
        self.analysis_running = True
        self.cancel_analysis_button.setEnabled(True)
        self.cancel_analysis_button.hide()
        self.update_analysis_action()
        self.chord_loading_stop.setEnabled(True)
        self.chord_loading_stop.show()

    def _accuracy_key(self):
        """Stable worker/cache identifier independent of translated UI labels."""
        return ('fast', 'balanced', 'detailed')[self.accuracy.currentIndex()]

    def reanalyze_current(self):
        if self.analysis_running:
            return
        if not self.stems and self.source_audio is None:
            self.status_message('Open a song before re-analyzing.')
            return
        self.pause_for_reanalysis()
        self._start_analysis_ui()
        self.set_chord_loading(True, 'Re-analyzing notes…')
        self.update_analysis_action()
        self.analyze_local.setEnabled(False)
        self.status_message('Re-analyzing audio with ' + self.accuracy.currentText() + ' accuracy…')
        if self.stems and self.folder:
            threading.Thread(target=self._reanalyze_stems, daemon=True).start()
        else:
            threading.Thread(target=self._analyze_source, args=(self.source_audio, True), daemon=True).start()

    def _reanalyze_stems(self):
        try:
            self._analyze_mode(force=True)
            beats = json.loads(worker_command('beats', str(self.stems['drums']), cancel_event=self.analysis_cancel))
            (self.folder / 'beats_drums_v2.json').write_text(json.dumps(beats), encoding='utf-8')
            if not self.analysis_cancel.is_set():
                self.signals.beats.emit(beats)
        except AnalysisCancelled:
            pass
        except Exception as exc:
            self.signals.error.emit(f'Re-analysis failed: {exc}')
            self._log_exception()
        finally:
            self.signals.analysis_done.emit()

    def analyze_current(self):
        if self.source_audio is None or self.analysis_running:
            return
        self._start_analysis_ui()
        self.set_chord_loading(True)
        self.analyze_local.setEnabled(False)
        self.status_message('Analyzing original mix (including vocals). Split first for instrument-only chords.')
        threading.Thread(target=self._analyze_source, args=(self.source_audio,), daemon=True).start()

    def _analyze_source(self, path, force=False):
        try:
            cache = ROOT / 'analysis' / (path.stem + '_' + str(path.stat().st_size))
            cache.mkdir(parents=True, exist_ok=True)
            beats_file = cache / 'beats.json'
            bass_mode = self.analysis_mode.currentIndex() == 0
            chords_file = cache / f"{'bass_notes_v4' if bass_mode else 'chords_v2'}_{self._accuracy_key()}.json"
            beats = json.loads(beats_file.read_text()) if beats_file.exists() and not force else json.loads(worker_command('beats', str(path), cancel_event=self.analysis_cancel))
            if force or not beats_file.exists(): beats_file.write_text(json.dumps(beats))
            chords = json.loads(chords_file.read_text()) if chords_file.exists() and not force else json.loads(worker_command('bass_notes' if bass_mode else 'chords', str(path), self._accuracy_key(), cancel_event=self.analysis_cancel))
            if force or not chords_file.exists(): chords_file.write_text(json.dumps(chords))
            if not self.analysis_cancel.is_set():
                self.signals.beats.emit(beats)
                self.signals.chords.emit(chords)
        except AnalysisCancelled:
            pass
        except Exception as exc:
            self.signals.error.emit(f'Analysis failed: {exc}\nDetails: {ROOT / "rifflab-errors.log"}')
            self._log_exception()
        finally:
            self.signals.analysis_done.emit()

    def on_analysis_done(self):
        was_cancelled = self.analysis_cancel.is_set()
        self.analysis_running = False
        self.cancel_analysis_button.hide()
        self.update_analysis_action()
        self.set_chord_loading(False)
        if self.processing:
            self.set_busy(False)
            self.status_message('Analysis stopped.' if was_cancelled else 'Import complete — notes and stems ready.')
        self.analyze_local.setEnabled(self.source_audio is not None)
        self.reanalyze_button.setEnabled(True)
        if was_cancelled:
            self.status_message('Analysis stopped. Existing audio remains available.')

    def reset_bpm(self):
        # Use the actual detected BPM, rather than a fixed 130 BPM default.
        original = max(self.grid_bpm.minimum(),
                       min(self.grid_bpm.maximum(), round(self.detected_bpm)))
        if self.grid_bpm.value() != original:
            self.grid_bpm.setValue(original)  # triggers bpm_changed once
        else:
            self.bpm_changed(original)
        self.status_message(f'BPM reset to {original} (original tempo).')

    def bpm_changed(self, bpm):
        """BPM changes the actual audio rate, never just the grid."""
        self.speed_ratio = max(0.5, min(1.5, float(bpm) / max(1.0, self.detected_bpm)))
        if self.live and self.stems:
            self.speed_generation += 1
            generation = self.speed_generation
            self.status_message(f'Preparing pitch-preserving playback at {self.speed_ratio:.0%}…')
            threading.Thread(target=self._prepare_speed, args=(self.speed_ratio, generation), daemon=True).start()
        else:
            self.player.setPlaybackRate(self.speed_ratio)
            # Qt pitch compensation availability depends on the multimedia backend.
            if hasattr(self.player, 'setPitchCompensation'):
                try:
                    self.player.setPitchCompensation(True)
                except Exception:
                    pass
            self.status_message(f'Playback speed: {self.speed_ratio:.0%}.')
        self.render_grid()

    def _prepare_speed(self, ratio, generation):
        try:
            if abs(ratio - 1.0) < 0.0001:
                paths = dict(self.stems)
            else:
                exe = shutil.which('ffmpeg')
                if not exe:
                    raise RuntimeError('FFmpeg is required for pitch-preserving speed control.')
                folder = self.folder / 'tempo_cache' / f'{ratio:.5f}'
                folder.mkdir(parents=True, exist_ok=True)
                paths = {}
                for name, original in self.stems.items():
                    target = folder / f'{name}.wav'
                    if not target.exists() or target.stat().st_size < 1024:
                        temp = folder / f'{name}.tmp.wav'
                        command([exe, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(original),
                                 '-af', f'atempo={ratio:.6f}', '-c:a', 'pcm_f32le', str(temp)])
                        temp.replace(target)
                    paths[name] = target
            self.signals.speed_ready.emit(paths, ratio, generation)
        except Exception as exc:
            self.signals.status.emit(f'Playback speed unavailable: {exc}')
            self._log_exception()

    def on_speed_ready(self, paths, ratio, generation):
        if generation != self.speed_generation or not self.stems or abs(ratio-self.speed_ratio)>0.0001:
            return
        old = self.live
        position = old.position_ms if old else 0
        playing = old.playing if old else False
        try:
            replacement = LiveStemPlayer(paths, time_scale=1.0/ratio)
            replacement.set_levels(self.get_levels())
            replacement.seek(position)
            self.live = replacement
            self._sync_loop()
            self._duration = replacement.duration_ms
            self.timeline.setRange(0, self._duration)
            self.waveform.set_duration(self._duration)
            if old:
                old.close()
            if playing:
                replacement.play()
            self.update_live_button()
            self.on_position(position)
            self.status_message(f'Playback speed: {ratio:.0%} (pitch preserved).')
        except Exception as exc:
            self.live = old
            self.status_message(f'Cannot switch playback speed: {exc}')

    def on_beats(self, data):
        if self.analysis_cancel.is_set():
            return
        self.beat_times = [float(t) for t in data.get('beats', [])]
        bpm = round(float(data.get('bpm', 130)))
        self.grid_bpm.blockSignals(True)
        self.grid_bpm.setValue(max(40, min(250, bpm)))
        self.grid_bpm.blockSignals(False)
        self.detected_bpm = float(data.get('bpm', 130)) or 130.0
        self.speed_ratio = 1.0
        self.player.setPlaybackRate(1.0)
        self.render_grid()
        self.grid_notice.setText(f'Auto BPM: {bpm}. Playback speed: 100%.')
        self.grid_bpm.setToolTip(self.grid_notice.text())
        if self.project_file:
            try:
                with sqlite3.connect(self.library_db) as db:
                    db.execute('UPDATE songs SET original_bpm=?, practice_bpm=? WHERE project_path=?',
                               (self.detected_bpm, float(self.grid_bpm.value()), str(Path(self.project_file).resolve())))
            except sqlite3.Error:
                pass

    def refresh_stems_led(self):
        if not hasattr(self, 'stems_led'):
            return
        ready = all(name in self.stems and Path(self.stems[name]).is_file() for name in STEMS)
        creating = bool(getattr(self, '_generating_stems', False) and self.processing)
        label, color = (('● STEMS READY', '#6dd2aa') if ready else
                        ('● CREATING', '#efb760') if creating else
                        ('● STEMS OFF', '#92a1ad'))
        self.stems_led.setText(label)
        self.stems_led.setStyleSheet(f'color:{color};font-size:11px;font-weight:700;')
        self.mixer_overlay.setVisible(not ready)
        if not ready:
            self.mixer_overlay.raise_()
        self.generate_stems_button.setEnabled(
            not self.processing and self.source_audio is not None
            and Path(self.source_audio).is_file())
        self.generate_stems_button.setText('Generating Stems…' if creating else 'Generate Stems')

    def generate_stems_clicked(self):
        if self.processing or self.analysis_running:
            self.status_message('Wait for the current import or analysis to finish.')
            return
        if self.source_audio and Path(self.source_audio).is_file():
            self.start_split(Path(self.source_audio))
        else:
            self.status_message('Open an audio file to create stems.')

    def start_split(self, path):
        if self.processing:
            return
        self._generating_stems = True
        self.set_busy(True)
        threading.Thread(target=self._split_safe, args=(path,), daemon=True).start()

    def _split_safe(self, path):
        try:
            self._split(path)
        except Exception as exc:
            self.signals.error.emit(f'{exc}\n\nTechnical details saved in the RiffLab log.')
            self._log_exception()

    def _split(self, path):
        self.signals.stage.emit('2/3 · Separating 4 stems (Demucs)…')
        output = ROOT / 'separated'
        output.mkdir(exist_ok=True)
        worker_command('split', str(path), str(output))
        folder = output / 'htdemucs' / path.stem
        if not all((folder / f'{stem}.wav').is_file() for stem in STEMS):
            raise RuntimeError('Demucs did not produce all four WAV stems.')
        self.signals.separated.emit(str(folder))

    def on_separated(self, folder):
        self._generating_stems = False
        self.project_file = None
        self.folder = Path(folder)
        self.source_audio = None
        self.beat_times = []
        self.section_overrides = {}
        self.stems = {stem: self.folder / f'{stem}.wav' for stem in STEMS}
        self.refresh_stems_led()
        self.load_waveform(self.stems)
        self.chord_data = []
        self.chord_times = []
        self.display_chords = []
        self.display_times = []
        self.chord.setText('…')
        for cb in self.checks.values():
            cb.setEnabled(True)
        for cb in self.solos.values():
            cb.setEnabled(True)
        self.export.setEnabled(True)
        for slider in self.volumes.values():
            slider.setEnabled(True)
        self.set_stage('3/3 · Analyzing notes and beats…')
        self.set_chord_loading(True, 'Analyzing stems, notes and beats…')
        self.split_local.setEnabled(False)
        self.analyze_local.setEnabled(False)
        self.clear_loop()
        self.speed_generation += 1
        self.speed_ratio = 1.0
        self.detected_bpm = 130.0
        self.grid_bpm.blockSignals(True)
        self.grid_bpm.setValue(130)
        self.grid_bpm.blockSignals(False)
        self.status_message('Stems ready — Bass Mode analyzes the isolated bass stem only.')
        self.start_live()
        self._start_analysis_ui()
        threading.Thread(target=self._analyze, daemon=True).start()

    def update_grid_mode_buttons(self, _index=None):
        mode = self.analysis_mode.currentIndex()
        for index, button in enumerate((self.bass_mode_button, self.chord_mode_button)):
            button.blockSignals(True)
            button.setChecked(index == mode)
            button.blockSignals(False)

    def switch_analysis_mode(self, _index=None):
        if self.analysis_running:
            self.status_message('Stop the current analysis before changing modes.')
            return
        if not self.stems and not self.source_audio:
            self.rebuild_chords()
            return
        self._start_analysis_ui()
        self.set_chord_loading(True, 'Analyzing selected mode…')
        if self.stems and self.folder:
            threading.Thread(target=self._switch_analysis_mode_worker, daemon=True).start()
        elif self.source_audio and self.source_audio.is_file():
            self.set_chord_loading(False)
            self.analysis_running = False
            self.status_message('Generate stems before analyzing notes.')
            self.start_split(self.source_audio)

    def _switch_analysis_mode_worker(self):
        try:
            self._analyze_mode()
        finally:
            self.signals.analysis_done.emit()

    def _analyze_mode(self, force=False):
        try:
            if self.analysis_mode.currentIndex() == 0:
                cache = self.folder / f'bass_stem_only_v1_{self._accuracy_key()}.json'
                task, paths = 'bass_notes', [str(self.stems['bass']), self._accuracy_key()]
            else:
                cache = self.folder / f'chords_instruments_v6_patterns_{self._accuracy_key()}.json'
                task, paths = 'chords_instruments', [str(self.stems['other']), str(self.stems['bass']), self._accuracy_key()]
            if cache.exists() and not force:
                result = json.loads(cache.read_text(encoding='utf-8'))
            else:
                result = json.loads(worker_command(task, *paths, cancel_event=self.analysis_cancel))
                cache.write_text(json.dumps(result), encoding='utf-8')
            if not self.analysis_cancel.is_set():
                self.signals.chords.emit(result)
        except AnalysisCancelled:
            pass
        except Exception as exc:
            self.signals.status.emit(f'Analysis failed: {exc}')
            self._log_exception()

    def _analyze(self):
        try:
            self.signals.stage.emit('3/3 · Analyzing notes and beats…')
            self._analyze_mode()
            # Drums are used for beat detection, not for chord recognition.
            beats_cache = self.folder / 'beats_drums_v2.json'
            beats = json.loads(beats_cache.read_text(encoding='utf-8')) if beats_cache.exists() else json.loads(worker_command('beats', str(self.stems['drums']), cancel_event=self.analysis_cancel))
            if not beats_cache.exists():
                beats_cache.write_text(json.dumps(beats), encoding='utf-8')
            if not self.analysis_cancel.is_set():
                self.signals.beats.emit(beats)
        except AnalysisCancelled:
            pass
        except Exception as exc:
            self.signals.error.emit(f'Chord analysis failed: {exc}')
            self._log_exception()
        finally:
            self.signals.analysis_done.emit()

    def auto_index_analyzed_song(self):
        """Add analyzed songs as saved projects, without opening a save dialog."""
        if self.project_file or (not self.stems and not self.source_audio):
            return
        song_name = self.folder.name if self.folder else self.source_audio.stem
        safe_name = re.sub(r'[^a-zA-Z0-9._ -]+', '_', song_name).strip(' .') or 'Untitled'
        folder = ROOT / 'projects'
        folder.mkdir(parents=True, exist_ok=True)
        project_path = folder / f'{safe_name}.riff'
        source_path = str(self.source_audio.resolve()) if self.source_audio else None
        stem_path = str(self.folder.resolve()) if self.stems and self.folder else None
        if project_path.exists():
            try:
                previous = json.loads(project_path.read_text(encoding='utf-8'))
                if previous.get('source_audio') != source_path or previous.get('stem_folder') != stem_path:
                    # Avoid overwriting another song with the same title.
                    import hashlib
                    suffix = hashlib.sha256(str(stem_path or source_path).encode()).hexdigest()[:8]
                    project_path = folder / f'{safe_name}-{suffix}.riff'
            except (OSError, ValueError):
                return
        data = {
            'format': 'RiffLab Project', 'version': 1,
            'metadata': dict(self.song_metadata),
            'source_audio': source_path, 'stem_folder': stem_path,
            'youtube_url': self.url.text().strip(), 'position_ms': 0,
            'in_ms': None, 'out_ms': None, 'loop': False,
            'bpm': self.grid_bpm.value(), 'detected_bpm': self.detected_bpm,
            'analysis_mode': self.analysis_mode.currentIndex(), 'accuracy': self.accuracy.currentIndex(),
            'stability': self.sensitivity.value(), 'transpose': self.transpose.value(),
            'zoom': self.grid_zoom.value(), 'row_height': self.grid_row_height.value(), 'lookahead_ms': self.chord_lookahead.value(),
            'auto_scroll': self.follow.isChecked(),
            'levels': {name: self.volumes[name].value() for name in STEMS},
            'enabled': {name: self.checks[name].isChecked() for name in STEMS},
            'solo': {name: self.solos[name].isChecked() for name in STEMS},
            'chord_data': self.chord_data, 'beat_times': self.beat_times,
        }
        try:
            temp = project_path.with_suffix('.riff.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(project_path)
            self.project_file = str(project_path)
            self.index_library_project(project_path, data)
            self.remember_project(project_path)
        except OSError as exc:
            self.status_message(f'Could not add song to Library: {exc}')

    def on_chords(self, chords):
        self.set_chord_loading(False)
        if self.analysis_cancel.is_set():
            return
        self.chord_data = chords
        self.chord_times = [float(item[0]) for item in chords]
        self.rebuild_chords()
        self.auto_index_analyzed_song()
        self.status_message('Bass notes ready (estimates).' if self.analysis_mode.currentIndex() == 0 else 'Chord grid ready. Chord changes are estimates.')

    def connect_export_mixer(self):
        for stem in STEMS:
            main_mute = self.checks[stem]
            export_mute = self.export_checks[stem]
            self.export_solos[stem].toggled.connect(
                lambda checked, name=stem: self.solos[name].setChecked(checked))
            self.solos[stem].toggled.connect(
                lambda _checked, name=stem: self.sync_export_mixer(name))
            main_volume = self.volumes[stem]
            export_volume = self.export_volumes[stem]
            export_mute.toggled.connect(
                lambda checked, name=stem: self.checks[name].setChecked(checked))
            export_volume.valueChanged.connect(
                lambda value, name=stem: self.volumes[name].setValue(value))
            main_mute.toggled.connect(
                lambda checked, name=stem: self.sync_export_mixer(name))
            main_volume.valueChanged.connect(
                lambda _value, name=stem: self.sync_export_mixer(name))
            self.sync_export_mixer(stem)

    def sync_export_mixer(self, stem):
        if not hasattr(self, 'export_checks'):
            return
        main_mute = self.checks[stem]
        main_volume = self.volumes[stem]
        export_mute = self.export_checks[stem]
        export_volume = self.export_volumes[stem]
        export_mute.blockSignals(True)
        export_volume.blockSignals(True)
        export_mute.setChecked(main_mute.isChecked())
        export_mute.setEnabled(main_mute.isEnabled())
        export_solo = self.export_solos[stem]
        export_solo.blockSignals(True)
        export_solo.setChecked(self.solos[stem].isChecked())
        export_solo.setEnabled(self.solos[stem].isEnabled())
        export_solo.blockSignals(False)
        export_volume.setValue(main_volume.value())
        export_volume.setEnabled(main_volume.isEnabled())
        export_mute.blockSignals(False)
        export_volume.blockSignals(False)
        enabled = main_mute.isChecked()
        export_mute.setAccessibleName(f'Mute {stem}' if enabled else f'Unmute {stem}')
        self.export_volume_labels[stem].setText(f'{main_volume.value()}%')

    def refresh_solo_visuals(self):
        """Dim non-solo channels visually without disabling Solo switching."""
        solo_stem = next((name for name in STEMS if self.solos[name].isChecked()), None)
        for stem in STEMS:
            dimmed = solo_stem is not None and stem != solo_stem
            for widget in (self.stem_names[stem], self.stem_icons[stem],
                           self.export_stem_icons[stem], self.volume_labels[stem],
                           self.volumes[stem], self.checks[stem],
                           self.export_stem_names[stem],
                           self.export_volume_labels[stem],
                           self.export_volumes[stem], self.export_checks[stem]):
                widget.setProperty('soloDimmed', dimmed)
                style = widget.style()
                style.unpolish(widget)
                style.polish(widget)
                widget.update()
            for icon_label in (self.stem_icons[stem], self.export_stem_icons[stem]):
                icon_label.setEnabled(not dimmed)
            # Other S buttons must remain fully visible and clickable.
            self.solos[stem].setToolTip(
                f'Switch solo to {stem.title()}' if dimmed else f'Solo {stem.title()} (exclusive)')
            self.export_solos[stem].setToolTip(
                f'Switch solo to {stem.title()}' if dimmed else f'Solo {stem.title()} (exclusive)')

    def sync_all_export_mixer(self):
        if hasattr(self, 'export_checks'):
            for stem in STEMS:
                self.sync_export_mixer(stem)
            self.refresh_solo_visuals()

    def stem_toggled(self, stem, checked):
        # M buttons use checked=audible. Muting a soloed channel cancels solo.
        if not checked and self.solos[stem].isChecked():
            solo = self.solos[stem]
            solo.blockSignals(True)
            solo.setChecked(False)
            solo.blockSignals(False)
        self.checks[stem].setAccessibleName(
            f'Unmute {stem}' if not checked else f'Mute {stem}')
        self.sync_all_export_mixer()
        self.apply_mixer_levels()

    def apply_mixer_levels(self):
        """Single realtime path for M, S and volume controls."""
        levels = self.get_levels()
        if self.live:
            self.live.set_levels(levels)
        else:
            self.request_mix()

    def reset_mixer(self):
        # Suppress four individual mix requests; update playback once at the end.
        for stem in STEMS:
            slider = self.volumes[stem]
            button = self.checks[stem]
            slider.blockSignals(True)
            button.blockSignals(True)
            slider.setValue(100)
            button.setChecked(stem != 'bass')
            slider.blockSignals(False)
            button.blockSignals(False)
            button.setAccessibleName(f'Mute {stem}' if stem != 'bass' else 'Unmute bass')
        for solo in self.solos.values():
            solo.blockSignals(True)
            solo.setChecked(False)
            solo.blockSignals(False)
        self.sync_all_export_mixer()
        self.volume_changed()
        if not self.live and self.stems:
            self.request_mix()

    def solo_toggled(self, stem):
        # Exclusive solo; its own channel is always audible.
        if self.solos[stem].isChecked():
            for other, button in self.solos.items():
                if other != stem:
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)
            mute = self.checks[stem]
            if not mute.isChecked():
                mute.blockSignals(True)
                mute.setChecked(True)
                mute.blockSignals(False)
                mute.setAccessibleName(f'Mute {stem}')
        self.sync_all_export_mixer()
        self.apply_mixer_levels()

    def get_levels(self):
        solo_stem = next(
            (name for name, button in self.solos.items() if button.isChecked()),
            None)
        return {
            stem: (self.volumes[stem].value() / 100.0
                   if self.checks[stem].isChecked()
                   and (solo_stem is None or stem == solo_stem)
                   else 0.0)
            for stem in STEMS
        }

    def volume_changed(self, _value=None):
        for stem, slider in self.volumes.items():
            self.volume_labels[stem].setText(f'{slider.value()}%')
        if self.live:
            self.live.set_levels(self.get_levels())
        else:
            self.mix_debounce.start(350)

    def transpose_changed(self, _value=None):
        """Notation-only transpose: never restart, repitch or remix playback."""
        self.render_grid()
        self.on_position(self.live.position_ms if self.live else self.player.position())

    def note_spelling_changed(self, index):
        self.layout_settings.setValue('note_spelling', index)
        self.render_grid()
        self.on_position(self.live.position_ms if self.live else self.player.position())

    def transpose_chord(self, chord):
        match = re.fullmatch(r'([A-G])([#b]?)(.*)', chord)
        if not match:
            return chord
        root, accidental, suffix = match.groups()
        offsets = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
        idx = (offsets[root] + (1 if accidental == '#' else -1 if accidental == 'b' else 0)
               + self.transpose.value()) % 12
        names = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B') if self.note_spelling.currentIndex() == 0 else ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
        return names[idx] + suffix

    @staticmethod
    def verify_note_events(events, level, bass_mode):
        """Remove isolated low-duration pitch glitches without inventing notes.

        Keep the original events untouched for instant A/B comparison.
        Preserve repeated same-note attacks and fast notes corroborated by
        neighbouring events; never quantize the performance to a beat grid.
        """
        if level <= 0 or len(events) < 3:
            return list(events)
        minimum = (0, 0.085, 0.14, 0.22)[min(level, 3)]
        # Full chords need longer evidence than individual bass attacks.
        if not bass_mode:
            minimum *= 1.5
        result = [events[0]]
        for i in range(1, len(events) - 1):
            t, note = events[i]
            prev_t, prev_note = events[i - 1]
            next_t, next_note = events[i + 1]
            duration = next_t - t
            # An isolated A-B-A excursion is the clearest sign of a glitch.
            isolated = prev_note == next_note and note != prev_note
            # Short runs in fast passages can be intentional, especially bass.
            fast_context = (t - prev_t < 0.24 and next_t - t < 0.24)
            threshold = minimum * (0.65 if fast_context else 1.0)
            if isolated and duration < threshold:
                continue
            # Strict mode can suppress a very short isolated change even
            # without an A-B-A pattern, but protects dense bass riffs.
            if level == 3 and not fast_context and duration < minimum * 0.45 and note != prev_note:
                continue
            result.append((t, note))
        result.append(events[-1])
        # Collapse identical adjacent pitch labels; retain separate bass
        # attacks because repeated plucks are musically meaningful.
        if not bass_mode:
            compact = []
            for t, note in result:
                if not compact or compact[-1][1] != note:
                    compact.append((t, note))
            return compact
        return result

    def rebuild_chords(self, _value=None):
        seconds = self.sensitivity.value() * 0.1
        self.sensitivity_label.setText(f'≥{seconds:.1f} s')
        if not self.chord_data:
            return
        # Never expose harmonic chord suffixes in Bass Mode, even for old
        # projects/caches or results arriving while switching modes.
        bass_mode = self.analysis_mode.currentIndex() == 0
        roots_only = self.root_notes_only.isChecked()
        raw = [(float(t), re.match(r'^[A-G](?:#|b)?', str(c)).group(0)
                if (bass_mode or roots_only) and re.match(r'^[A-G](?:#|b)?', str(c)) else str(c))
               for t, c in self.chord_data]
        guard_level = self.noteguard.currentIndex()
        raw = self.verify_note_events(raw, guard_level, bass_mode)
        if bass_mode:
            # A bass-root timeline has one event per root change, not per pluck.
            root_changes = []
            for t, note in raw:
                if not root_changes or note != root_changes[-1][1]:
                    root_changes.append((t, note))
            raw = root_changes
        # Show a *minimum-duration segment*, not an arbitrary skip of its
        # starting event. Remove short runs in reverse so A-B-A returns to A.
        # This is a display-only edit: original AI events stay untouched.
        output = list(raw)
        if seconds > 0 and len(output) > 1:
            for _ in range(3):
                changed = False
                filtered = [output[0]]
                for i in range(1, len(output)):
                    t, note = output[i]
                    end = output[i + 1][0] if i + 1 < len(output) else float('inf')
                    if end - t < seconds and filtered:
                        changed = True
                        continue
                    if note != filtered[-1][1]:
                        filtered.append((t, note))
                output = filtered
                if not changed:
                    break
        # In Bass Mode a repeated attack on the current root is not a change.
        if bass_mode:
            collapsed = []
            for t, note in output:
                if not collapsed or collapsed[-1][1] != note:
                    collapsed.append((t, note))
            output = collapsed
        self.display_chords = output
        self.refresh_tuning_advice()
        self.display_times = [t for t, _ in output]
        self.render_grid()
        self.on_position(self.live.position_ms if self.live else self.player.position())

    def request_mix(self, _checked=None):
        if self.live:
            self.live.set_levels(self.get_levels())
            return
        if not self.stems:
            return
        if self.mixing:
            self.pending_mix = True
            return
        self.mixing = True
        self.mix_counter += 1
        seq = self.mix_counter
        levels = self.get_levels()
        transpose = 0  # Grid transpose never changes the playback pitch.
        pos = self.player.position()
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.player.pause()
        self.status_message('Processing mix…')
        threading.Thread(target=self._mix, args=(levels, transpose, seq, pos, playing), daemon=True).start()

    def _mix(self, levels, transpose, seq, pos, playing):
        try:
            output = ROOT / f'mix_{seq % 2}.wav'
            mix_to_file(self.stems, levels, transpose, output)
            self.signals.mixed.emit(str(output), pos, playing)
        except Exception as exc:
            self.signals.error.emit(f'Mix failed: {exc}')
            self._log_exception()

    def on_mixed(self, path, pos, playing):
        self.mixing = False
        if self.pending_mix:
            self.pending_mix = False
            self.request_mix()
            return
        self._seek_after_load = pos
        self._play_after_load = playing
        self.player.setSource(QUrl.fromLocalFile(path))
        self.status_message('Mix ready.')

    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.loop_enabled and not self.live:
            self.player.setPosition(self.loop_a_ms if self.loop_a_ms is not None else 0)
            self.player.play()
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._seek_after_load is not None:
            self.player.setPosition(self._seek_after_load)
            self._seek_after_load = None
            if self._play_after_load:
                self.player.play()
            self._play_after_load = False

    def toggle_play(self):
        if self.live:
            try:
                if self.live.playing:
                    self.live.pause()
                else:
                    self.live.play()
                self.update_live_button()
            except Exception as exc:
                self.status_message(f'Audio output: {exc}')
            return
        if not self.player.source().isValid():
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek_and_play(self, ms):
        ms = max(0, int(ms))
        if self.live:
            self.live.seek(ms)
            self.live.play()
            self.update_live_button()
            self.on_position(self.live.position_ms)
        elif self.player.source().isValid():
            self.player.setPosition(ms)
            self.player.play()
            self.on_position(ms)

    def stop_playback(self):
        if self.live:
            self.live.pause()
            self.live.seek(0)
            self.update_live_button()
        else:
            self.player.stop()
        self.on_position(0)

    def toggle_loop(self, enabled):
        self.loop_enabled = bool(enabled)
        self.loop_button.setToolTip('Disable loop' if enabled else 'Enable loop')
        self._sync_loop()

    def set_loop_point(self, which):
        ms = self.live.position_ms if self.live else self.player.position()
        if which == 'a':
            self.loop_a_ms = ms
        else:
            self.loop_b_ms = ms
        self._sync_loop()

    def move_loop_marker(self, which, ms):
        if which == 'a':
            self.loop_a_ms = ms
        else:
            self.loop_b_ms = ms
        self._sync_loop()

    def clear_loop(self):
        self.loop_a_ms = None
        self.loop_b_ms = None
        self._sync_loop()

    def _sync_loop(self):
        a, b = self.loop_a_ms, self.loop_b_ms
        if hasattr(self, 'waveform'):
            self.waveform.set_markers(a, b)
        valid = a is not None and b is not None and b > a
        if hasattr(self, 'loop_info'):
            if valid:
                self.loop_info.setText(f'In {a/1000:.1f}s  /  Out {b/1000:.1f}s')
            elif a is not None or b is not None:
                self.loop_info.setText('Set In marker' if a is None else 'Set Out after In')
            else:
                self.loop_info.setText('Whole track')
        if self.live:
            self.live.set_loop(self.loop_enabled, a if valid else None, b if valid else None)

    def check_qt_loop(self, ms):
        if not self.loop_enabled or self.live:
            return
        a, b = self.loop_a_ms, self.loop_b_ms
        if a is not None and b is not None and b > a and ms >= b:
            self.player.setPosition(a)

    def on_duration(self, duration):
        self._duration = duration
        self.timeline.setRange(0, duration)
        self.waveform.set_duration(duration)
        if abs(duration - self._last_render_duration) > 1000:
            self._last_render_duration = duration
            self.render_grid()

    def refresh_chord_indicator(self, *_):
        ms = self.live.position_ms if self.live else self.player.position()
        self.update_chord_indicator(ms)

    def update_chord_indicator(self, ms):
        if not self.display_chords:
            self._set_current_chord('—')
            self.next_chords.setText('NEXT: —')
            return
        actual_time = max(0.0, ms / 1000.0)
        # Lookahead changes ONLY the large current-chord label, not playback,
        # the beat grid, loop markers, or the underlying chord timestamps.
        preview_time = actual_time + self.chord_lookahead.value() / 1000.0
        # Match the note sampled by the visible beat grid, not passing notes.
        if self.grid_cells and self.display_times:
            times = [cell[0] for cell in self.grid_cells]
            cell = bisect.bisect_right(times, preview_time) - 1
            if cell < 0:
                self._set_current_chord('—')
                return
            cell_time = times[min(cell, len(times) - 1)]
            note_index = bisect.bisect_right(self.display_times, cell_time) - 1
            current = (self.transpose_chord(self.display_chords[note_index][1])
                       if note_index >= 0 else '—')
            self._set_current_chord(current)
            return
        idx = bisect.bisect_right(self.display_times, preview_time) - 1
        self._set_current_chord(self.transpose_chord(self.display_chords[idx][1])
                           if idx >= 0 else '—')

    def _note_accent(self, chord):
        """Consistent pitch colors for the grid and current-note display."""
        root = str(chord).replace('♯', '#').replace('♭', 'b')
        root = root[:2] if len(root) > 1 and root[1] in '#b' else root[:1]
        return {
            'C': '#268ed1', 'C#': '#4286df', 'D': '#ce6385',
            'D#': '#bd68b6', 'E': '#368fc2', 'F': '#8a70d2',
            'F#': '#7165c8', 'G': '#a76be4', 'G#': '#bb6ad2',
            'A': '#30bba8', 'A#': '#dc9556', 'B': '#c89b4e',
        }.get(root, '#56748b')

    def _set_current_chord(self, name):
        """Match the current-note glass and horizontal accent to the grid."""
        self.chord.setText(name)
        accent = self._note_accent(name)
        # Translucent blue glass: crisp top accent, no glow or neon shadow.
        self.chord.setStyleSheet(
            'font-size:23px;font-weight:750;color:#f4faff;'
            'background-color:rgba(33,64,86,105);'
            'border:1px solid rgba(165,205,230,80);'
            f'border-top:3px solid {accent};'
            'border-radius:7px;padding:4px;'
        )

    def _grid_note_font_px(self):
        # Height is the primary legibility control; horizontal zoom makes
        # smaller proportional changes. Keep large text on tall note rows.
        height = self.grid_row_height.value()
        width_factor = 0.88 + 0.12 * self.grid_zoom.value() / 100.0
        return max(11, min(34, round((12 + (height - 24) * 0.25) * width_factor)))

    def _chord_segment_style(self, index, active=False):
        """Translucent blue-white glass with horizontal pitch-color accents."""
        chord = self.grid_chord_names[index] if index < len(self.grid_chord_names) else '—'
        accent = self._note_accent(chord)
        beginning = index == 0 or index % 16 == 0 or chord != self.grid_chord_names[index - 1]
        ending = index == len(self.grid_chord_names) - 1 or index % 16 == 15 or chord != self.grid_chord_names[index + 1]
        # Alpha is deliberately low: let the actual app background show through.
        progress = (getattr(self, '_note_progress', {}).get(index, 0.0) if active else 0.0)
        # Fill smoothly from left to right; avoid stepwise flashes between beats.
        ratio = max(0.0, min(1.0, float(progress)))
        pct = ratio
        if 0.001 < pct < 0.999:
            accent_fill = QColor(accent)
            filled = f'rgba({accent_fill.red()},{accent_fill.green()},{accent_fill.blue()},170)'
            background = ('qlineargradient(x1:0,y1:0,x2:1,y2:0,'
                          f'stop:0 {filled},stop:{max(0.0,pct-0.002):.4f} {filled},'
                          f'stop:{min(1.0,pct+0.002):.4f} rgba(49,93,123,56),'
                          'stop:1 rgba(49,93,123,56))')
        elif pct >= 0.999:
            background = accent
        else:
            background = 'rgba(49,93,123,56)'
        foreground = '#ffffff' if active else '#e9f5fd'
        # Top edge carries pitch information. No vertical color strips or glow.
        border_top = f'3px solid {accent}' if active else f'2px solid {accent}'
        return (
            f'background-color:{background};'
            'border:0px;'
            f'border-top:{border_top};'
            f'border-bottom:1px solid {"rgba(221,241,255,120)" if active else "rgba(173,211,233,45)"};'
            f'border-left:{"1px solid rgba(190,223,240,65)" if beginning else "0px"};'
            f'border-right:{"1px solid rgba(190,223,240,65)" if ending else "0px"};'
            f'border-top-left-radius:{5 if beginning else 0}px;'
            f'border-bottom-left-radius:{5 if beginning else 0}px;'
            f'border-top-right-radius:{5 if ending else 0}px;'
            f'border-bottom-right-radius:{5 if ending else 0}px;'
            f'font-size:{self._grid_note_font_px()}px;'
            f'font-weight:{"800" if active else ("650" if self.grid_buttons[index].text().strip() else "400")};'
            f'padding:{max(1, round(2 * self.grid_zoom.value() / 100))}px '
            f'{max(3, round(5 * self.grid_zoom.value() / 100))}px;'
            f'text-align:left;color:{foreground};'
        )

    def apply_grid_zoom(self, zoom):
        """Horizontal zoom changes geometry only, never timing or pitch."""
        self.grid_zoom_label.setText(f'{zoom}%')
        scale = zoom / 100.0
        for index,(end,button) in getattr(self,'grid_segments',{}).items():
            intended_width = max(38, round(36*scale*(end-index)))
            button.setMinimumWidth(intended_width)
            button.setFixedHeight(self.grid_row_height.value())
            full_label = self.grid_chord_names[index]
            full_label = '' if full_label == '—' else full_label
            font = button.font()
            font.setPixelSize(self._grid_note_font_px())
            font.setBold(bool(full_label))
            from PySide6.QtGui import QFontMetrics
            metrics = QFontMetrics(font)
            if metrics.horizontalAdvance(full_label) + 14 > intended_width:
                root_match = re.match(r'^[A-G](?:#|b)?', full_label)
                short_label = root_match.group(0) if root_match else full_label
                font.setPixelSize(max(11, min(font.pixelSize(), 13)))
                button.setText(short_label)
            else:
                button.setText(full_label)
            button.setFont(font)
            button.setStyleSheet(self._chord_segment_style(index, self.grid_active>=index and self.grid_active<end))
        self.chord_grid.setHorizontalSpacing(0)
        self.chord_grid.setVerticalSpacing(3)

    def apply_grid_row_height(self, height):
        """True vertical zoom of the continuous note bars."""
        self.grid_row_height_label.setText(f'{round(height / 38 * 100)}%')
        for index,(end,button) in getattr(self,'grid_segments',{}).items():
            font = button.font()
            font.setPixelSize(self._grid_note_font_px())
            button.setFont(font)
            button.setStyleSheet(self._chord_segment_style(index, index<=self.grid_active<end))
            button.setFixedHeight(height)
        for section in getattr(self,'grid_section_buttons',()):
            section.setFixedHeight(height+16)
        if hasattr(self,'chord_grid'):
            # A resizable QScrollArea otherwise compresses the fresh grid on
            # import/reanalysis until the next manual V-slider interaction.
            rows = (len(getattr(self, 'grid_buttons', ())) + 15) // 16
            for row in range(rows):
                self.chord_grid.setRowMinimumHeight(row * 2, 28)
                self.chord_grid.setRowMinimumHeight(row * 2 + 1, height)
            if rows:
                margins = self.chord_grid.contentsMargins()
                minimum = (rows * (height + 28)
                           + max(0, rows * 2 - 1) * self.chord_grid.verticalSpacing()
                           + margins.top() + margins.bottom())
                self.grid_host.setMinimumHeight(minimum)
            else:
                self.grid_host.setMinimumHeight(0)
            self.chord_grid.invalidate()
            self.grid_host.updateGeometry()

    def on_position(self, ms):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(ms)
        self.waveform.set_position(ms)
        self.time_label.setText(f'{ms // 60000:02d}:{(ms // 1000) % 60:02d} / '
                                f'{self._duration // 60000:02d}:{(self._duration // 1000) % 60:02d}')
        self.header_time_label.setText(self.time_label.text())
        self.update_chord_indicator(ms)
        self.update_grid_position(ms / 1000)

    def load_waveform(self, source):
        if isinstance(source, dict):
            source = {name: str(Path(source[name]).resolve()) for name in STEMS}
            key = '|'.join(source[name] for name in STEMS)
        else:
            source = str(Path(source).resolve())
            key = source
        self._waveform_source = key
        self.waveform.set_waveform([])
        self.waveform.set_position(0)
        def task():
            try:
                peaks = extract_waveform_peaks(source)
                self.signals.waveform_ready.emit(key, peaks)
            except Exception as exc:
                self.signals.error.emit(f'Waveform: {exc}')
                self.signals.waveform_ready.emit(key, [])
        threading.Thread(target=task, daemon=True).start()

    def on_waveform_ready(self, path, peaks):
        if path == self._waveform_source:
            self.waveform.set_waveform(peaks)
            if not peaks:
                self.status_message('Waveform unavailable — check FFmpeg and audio file')

    def seek_waveform(self, ms):
        if self._duration <= 0:
            return
        ms = max(0, min(int(ms), self._duration))
        self.timeline.setValue(ms)
        if self.live:
            self.live.seek(ms)
            self.on_position(self.live.position_ms)
        else:
            self.player.setPosition(ms)
            self.on_position(ms)

    def seek(self):
        if self.live:
            self.live.seek(self.timeline.value())
            self.on_position(self.live.position_ms)
        else:
            self.player.setPosition(self.timeline.value())

    def export_mix(self):
        if not self.stems:
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Export backing track', 'RiffLab-backing.wav', 'WAV (*.wav)')
        if filename:
            try:
                self.status_message('Exporting WAV…')
                threading.Thread(target=self._export_background, args=(filename,self.get_levels(),0), daemon=True).start()
            except Exception as exc:
                self.on_error(str(exc))


    def _export_background(self, filename, levels, transpose):
        try:
            mix_to_file(self.stems, levels, transpose, Path(filename))
            self.signals.exported.emit(filename)
        except Exception as exc:
            self.signals.error.emit(f'Export failed: {exc}')
            self._log_exception()

    def on_playback_state(self, state):
        playing = state == QMediaPlayer.PlayingState
        self.play.setToolTip('Pause' if playing else 'Play')
        self.play.setIcon(qta.icon('fa5s.pause' if playing else 'fa5s.play', color='white'))

    def find_riff_patterns(self, beats, beat_length):
        """Compare two-bar pitch-class sequences on the beat grid.

        Only label repeated phrases with some movement; avoid calling an entire
        song on one chord a repeated riff. Labels are similarity estimates.
        """
        if len(beats) < 32 or not self.display_chords:
            return {}
        from difflib import SequenceMatcher
        notes = []
        for t in beats:
            i = bisect.bisect_right(self.display_times, t + beat_length * 0.15) - 1
            name = self.display_chords[i][1] if i >= 0 else ''
            m = re.match(r'^([A-G](?:#|b)?)', name)
            notes.append(m.group(1) if m else '?')
        # Each block is two bars. Compare aligned, non-overlapping blocks.
        blocks = [tuple(notes[i:i+8]) for i in range(0, len(notes)-7, 8)]
        groups = []
        matches = {}
        for block_idx, seq in enumerate(blocks):
            if len(set(seq) - {'?'}) < 2 or seq.count('?') > 2:
                continue
            best, score = -1, 0.0
            for group_idx, reference in enumerate(groups):
                similarity = sum(a == b and a != '?' for a, b in zip(seq, reference)) / 8
                if similarity > score:
                    best, score = group_idx, similarity
            if score >= 0.75:
                group_idx = best
                confidence = score
            else:
                if len(groups) >= 8:
                    continue
                group_idx = len(groups)
                groups.append(seq)
                confidence = 1.0
            letter = chr(ord('A') + group_idx)
            matches[block_idx * 8] = (letter, confidence, group_idx)
        # Only show patterns that actually recur; no speculative A/B labels.
        counts = Counter(v[0] for v in matches.values())
        return {beat: info for beat, info in matches.items() if counts[info[0]] >= 2}

    def infer_song_sections(self, beat_count):
        """Display only user-confirmed sections; do not invent verse/chorus."""
        rows = (beat_count + 15) // 16
        return [self.section_overrides.get(row, '') for row in range(rows)]

    def edit_section_label(self, row):
        choices = ['Intro', 'Verse', 'Chorus', 'Pre-Chorus', 'Bridge',
                   'Solo', 'Breakdown', 'Outro', 'Instrumental', 'Part A', 'Part B']
        current = self.section_overrides.get(row, '')
        label, ok = QInputDialog.getItem(self, 'Song section',
                                          f'Section starting at bar {row * 4 + 1}:',
                                          choices, max(0, choices.index(current)) if current in choices else 0,
                                          True)
        if ok and label.strip():
            self.section_overrides[row] = label.strip()
            self.render_grid()

    def render_grid(self, *_):
        """Four bars per row, four clickable beat cells per bar. Grid uses a fixed BPM estimate."""
        while self.chord_grid.count():
            item = self.chord_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.grid_buttons = []
        self.grid_cells = []
        self._note_progress = {}
        self.grid_chord_names = []
        self.grid_section_buttons = []
        bpm = self.grid_bpm.value()
        beat_length = 60.0 / bpm
        total = max(self._duration / 1000, self.display_times[-1] + 4 if self.display_times else 0, 45)
        beats = min(800, max(16, len(self.beat_times) if self.beat_times else math.ceil(total / beat_length)))
        beat_seconds = [self.beat_times[i] if self.beat_times else i * beat_length for i in range(beats)]
        patterns = {}  # Pattern assistance happens during audio analysis, not in the grid
        occurrences = Counter()
        pattern_labels = {}
        for start, (letter, confidence, group_idx) in sorted(patterns.items()):
            occurrences[letter] += 1
            pattern_labels[start] = (f'{letter}{occurrences[letter]}', confidence, group_idx)
        self.pattern_matches = pattern_labels
        section_labels = self.infer_song_sections(beats)
        section_colors = ('#139ed0', '#1886b9', '#087da9', '#2074a2')
        # Section markers remain editable, but do not spam guessed Part A/B
        # on every row. Show bar ranges until the user names a section.
        current_section = 0
        for section_row, section_label in enumerate(section_labels):
            if section_label:
                current_section = (current_section + 1) % len(section_colors)
            accent = section_colors[current_section]
            label = section_label or f'{section_row * 4 + 1}–{section_row * 4 + 4}'
            section = QPushButton(label)
            section.setToolTip('Click to name this section (Intro, Verse, Chorus, etc.)')
            section.setFixedWidth(90)
            section.setStyleSheet(
                f'background:#152633;color:{"#f2faff" if section_label else "#728c9e"};'
                f'border:0;border-left:{"4px" if section_label else "2px"} solid {accent};'
                f'font-size:11px;font-weight:{"700" if section_label else "400"};'
                'text-align:left;padding:3px 6px;')
            section.clicked.connect(lambda checked=False, row=section_row: self.edit_section_label(row))
            self.chord_grid.addWidget(section, section_row * 2, 0, 2, 1)
            self.grid_section_buttons.append(section)
        # Independent bar ruler: measure boundaries stay visible even when
        # the note above/below is sustained across the bar boundary.
        for row_start in range(0, beats, 16):
            header_row = (row_start//16)*2
            for offset in range(0, min(16, beats-row_start), 4):
                measure = QLabel(f'{(row_start+offset)//4 + 1:02d}')
                measure.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                measure.setFixedHeight(28)
                measure.setStyleSheet(
                    'background:transparent;color:#a8c8dc;font-size:11px;font-weight:600;'
                    'border-left:2px solid #8fc4e3;padding-left:7px;')
                self.chord_grid.addWidget(measure,header_row,offset+1,1,
                                          min(4,beats-row_start-offset))
        # One real QWidget per sustained note, not sixteen separately styled
        # beat buttons. Retain beat-index mapping for existing transport logic.
        labels = []
        for beat_index in range(beats):
            t = self.beat_times[beat_index] if self.beat_times else beat_index * beat_length
            idx = bisect.bisect_right(self.display_times, t) - 1
            labels.append(self.transpose_chord(self.display_chords[idx][1]) if idx >= 0 else '—')
        self.grid_chord_names = labels
        self.grid_cells = [(self.beat_times[i] if self.beat_times else i * beat_length, i % 4)
                           for i in range(beats)]
        self.grid_buttons = [None] * beats
        self.grid_segments = {}
        for start in range(0, beats, 16):
            end = min(start + 16, beats)
            i = start
            while i < end:
                chord = labels[i]
                j = i + 1
                while j < end and labels[j] == chord:
                    j += 1
                t = self.grid_cells[i][0]
                button = QPushButton('' if chord == '—' else chord)
                button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                button.setToolTip(f'{chord} · {t:.2f}s · {j-i} beats')
                button.setAcceptDrops(True)
                button.setProperty('riffDropTarget', True)
                button.installEventFilter(self)
                button.clicked.connect(lambda checked=False, seconds=t:
                                       self.seek_and_play(int(seconds * 1000)))
                self.chord_grid.addWidget(button, (start//16)*2+1, i-start+1, 1, j-i)
                self.grid_segments[i] = (j, button)
                for k in range(i,j):
                    self.grid_buttons[k] = button
                i = j
        self.chord_grid.setColumnStretch(0, 0)
        for col in range(1, 17):
            self.chord_grid.setColumnStretch(col, 1)
        self.apply_grid_zoom(self.grid_zoom.value())
        self.apply_grid_row_height(self.grid_row_height.value())
        self.grid_active = -1
        self.grid_row = -1
        self.update_grid_position((self.live.position_ms if self.live else self.player.position())/1000)

    def update_note_fill(self):
        """Smooth playback fill based on absolute audio time; no pitch processing."""
        if self.grid_buttons:
            ms = self.live.position_ms if self.live else self.player.position()
            self.update_grid_position(ms / 1000.0)

    def update_grid_position(self, seconds):
        if not self.grid_buttons:
            return
        idx = max(0, min(len(self.grid_buttons)-1,
            bisect.bisect_right(self.beat_times, seconds)-1 if self.beat_times
            else int(seconds*self.grid_bpm.value()/60.0)))
        old_idx = self.grid_active
        current = self.grid_buttons[idx]
        old = self.grid_buttons[old_idx] if 0 <= old_idx < len(self.grid_buttons) else None
        if old is not None and old is not current:
            self._note_progress = {}
            old.setStyleSheet(self._chord_segment_style(old_idx, False))
        self.grid_active = idx
        # Find beginning/end of the merged note widget in this row.
        run_start = idx
        while run_start > (idx//16)*16 and self.grid_buttons[run_start-1] is current:
            run_start -= 1
        run_end = idx+1
        while run_end < min(((idx//16)+1)*16,len(self.grid_buttons)) and self.grid_buttons[run_end] is current:
            run_end += 1
        start_sec = self.grid_cells[run_start][0]
        end_sec = (self.grid_cells[run_end][0] if run_end < len(self.grid_cells)
                   else self.grid_cells[-1][0] + 60.0/max(1,self.grid_bpm.value()))
        progress = max(0.0,min(1.0,(seconds-start_sec)/max(0.001,end_sec-start_sec)))
        # Keep the layout static; only paint progress, no per-beat recoloring.
        last = self._note_progress.get(run_start, -1.0)
        if old is not current or abs(last-progress) >= 0.004:
            self._note_progress[run_start] = progress
            current.setStyleSheet(self._chord_segment_style(run_start, True))
        row = idx//16
        if self.follow.isChecked() and row != self.grid_row:
            self.grid_row = row
            scrollbar = self.chord_scroll.verticalScrollBar()
            scrollbar.setValue(max(0, current.y()-int(self.chord_scroll.viewport().height()*.25)))


    def find_devices(self):
        self.devices.clear()
        try:
            import sounddevice as sd
            for i,d in enumerate(sd.query_devices()):
                if d['max_input_channels'] > 0:
                    self.devices.addItem(f'{d["name"]} ({int(d["default_samplerate"])} Hz)',i)
        except Exception as exc:
            self.devices.addItem(f'No input: {exc}',None)

    def refresh_tuning_advice(self):
        """A tentative suggestion only; note names do not establish tuning."""
        if not hasattr(self, 'tuning_advice'):
            return
        roots = []
        for _, name in getattr(self, 'display_chords', []):
            match = re.match(r'^([A-G](?:#|b)?)', str(name))
            if match:
                roots.append(match.group(1))
        # Many notes written as sharps/flats can be a *key* instead of a
        # down-tuned instrument. Therefore never infer or apply a tuning.
        flat_family = {'Eb', 'Ab', 'Bb', 'Db', 'Gb', 'D#', 'G#', 'A#', 'C#', 'F#'}
        is_flat_heavy = (len(roots) >= 8
                         and sum(note in flat_family for note in roots) / len(roots) >= .6)
        self._suggest_eb_tuning = bool(is_flat_heavy)
        if is_flat_heavy:
            self.tuning_advice.setText('Check Eb tuning  ↗')
            self.tuning_advice.setToolTip(
                'Many accidentals detected. This can be the musical key, NOT proof '
                'of Eb tuning. Open the tuner to compare before deciding.')
        else:
            self.tuning_advice.setText('Tuning guide  ↗')
            self.tuning_advice.setToolTip(
                'Choose instrument tuning manually. Transpose affects notation only.')

    def open_tuning_guide(self):
        """Explain the difference; never auto-transpose or auto-retune."""
        if getattr(self, '_suggest_eb_tuning', False):
            response = QMessageBox.question(
                self, 'Optional tuning suggestion',
                'This song contains many sharp/flat note names. That can reflect '
                'the musical key and does NOT confirm the recording uses Eb tuning.\n\n'
                'Would you like to compare your instrument with Eb Standard? '
                'This changes only the tuner preset, never the audio or transpose.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if response == QMessageBox.Yes:
                self.tuner_preset.setCurrentIndex(
                    7 if self.tuner_preset.currentIndex() >= 6 else 2)
        self.tabs.setCurrentWidget(self.tuner_dialog)
        self.tuner_dialog.raise_()
        self.status_message(
            'Tuning is a manual instrument choice. Transpose changes notation only.')

    def refresh_tuner_strings(self, _index=None):
        """Per-string reference pitches (MIDI); don't guess a song's tuning."""
        tunings = {
            1: (40, 45, 50, 55, 59, 64),  # E A D G B E
            2: (39, 44, 49, 54, 58, 63),  # Eb Ab Db Gb Bb Eb
            3: (38, 43, 48, 53, 57, 62),  # D G C F A D
            4: (38, 45, 50, 55, 59, 64),  # D A D G B E
            5: (37, 44, 49, 54, 58, 63),  # C# G# C# F# A# D#
            6: (28, 33, 38, 43),          # E A D G bass
            7: (27, 32, 37, 42),
            8: (26, 31, 36, 41),
        }
        self._tuning_targets = tunings.get(self.tuner_preset.currentIndex(), ())
        self.tuner_string.blockSignals(True)
        self.tuner_string.clear()
        if not self._tuning_targets:
            self.tuner_string.addItem('All notes', None)
        else:
            for index, midi in enumerate(self._tuning_targets):
                self.tuner_string.addItem(
                    f'{index + 1} · {NOTES[midi % 12]}{midi // 12 - 1}', midi)
        self.tuner_string.blockSignals(False)
        self.refresh_tuner_target()

    def refresh_tuner_target(self, _index=None):
        midi = self.tuner_string.currentData()
        self._tuner_display_cents = None
        if midi is None:
            self.tuner_target.setText('Chromatic · no fixed target frequency')
        else:
            frequency = 440 * (2 ** ((midi - 69) / 12))
            self.tuner_target.setText(
                f'TARGET  {NOTES[midi % 12]}{midi // 12 - 1}  ·  {frequency:.2f} Hz'
                '    —    tune until the needle reaches 0')
        if hasattr(self, 'tuner_meter'):
            self.tuner_meter.set_reading(0, False)

    def toggle_tuner(self):
        if self.tuner_stream is not None:
            self.tuner_stream.stop()
            self.tuner_stream.close()
            self.tuner_stream = None
            self._tuner_display_cents = None
            self.tuner_meter.set_reading(0, False)
            self.tuner_note.setText('—')
            self.tuner_details.setText('Tuner stopped')
            self.tuner_button.setText('Start Tuner')
            return
        try:
            import sounddevice as sd
            import numpy as np
            device = self.devices.currentData()
            if device is None:
                raise RuntimeError('No input device selected')
            sr = int(sd.query_devices(device)['default_samplerate'])
            def callback(indata, frames, time_info, status):
                x = np.asarray(indata[:,0],dtype=np.float32)
                self.tuner_level = float(np.sqrt(np.mean(x*x)))
                if self.tuner_level < .006:
                    return
                x = x - np.mean(x)
                n = len(x)
                spec = np.fft.rfft(x,n=2*n)
                corr = np.fft.irfft(spec*np.conj(spec))[:n]
                sample_rate = float(sr)
                lo = max(1,int(sample_rate/1000))
                hi = min(n-1,int(sample_rate/40))
                if hi <= lo:
                    return
                k = lo + int(np.argmax(corr[lo:hi]))
                freq = sample_rate/k
                if 40 <= freq <= 1000:
                    self.tuner_pitch = freq
                    self.tuner_last = time.monotonic()
            # 4096 frames (~93 ms at 44.1 kHz) updates more often than 8192.
            # Autocorrelation still supports low bass notes down to 40 Hz.
            self.tuner_stream = sd.InputStream(device=device,channels=1,samplerate=sr,blocksize=4096,callback=callback)
            self.tuner_stream.start()
            self._tuner_display_cents = None
            self.tuner_details.setText('Listening… · A4 = 440 Hz')
            self.tuner_button.setText('Stop Tuner')
        except Exception as exc:
            self.tuner_stream = None
            QMessageBox.warning(self,'Tuner',str(exc))

    def update_tuner(self):
        if self.tuner_stream is None:
            return
        if self.tuner_level < .006 or time.monotonic()-self.tuner_last > .45:
            self.tuner_note.setText('—')
            self.tuner_details.setText('Play one string · A4 = 440 Hz')
            self.tuner_meter.set_reading(0, False)
            self._tuner_display_cents = None
            return
        frequency = self.tuner_pitch
        if frequency <= 0:
            return
        detected = round(69 + 12 * math.log2(frequency / 440))
        target = self.tuner_string.currentData()
        # Guide against the selected open string rather than the closest
        # chromatic note; this makes half-step and drop tuning usable.
        reference = target if target is not None else detected
        target_hz = 440 * 2 ** ((reference-69) / 12)
        cents = 1200 * math.log2(frequency / target_hz)
        if self._tuner_display_cents is None or abs(cents-self._tuner_display_cents) > 60:
            self._tuner_display_cents = cents
        else:
            self._tuner_display_cents += .42 * (cents-self._tuner_display_cents)
        smooth = self._tuner_display_cents
        self.tuner_note.setText(f'{NOTES[detected%12]}{detected//12-1}')
        in_tune = abs(smooth) <= 5 and (target is None or abs(cents) <= 8)
        self.tuner_note.setStyleSheet(
            'font-size:46px;font-weight:800;'
            f'color:{"#69e7cb" if in_tune else "#eaf7ff"};'
            'background-color:rgba(41,76,99,95);'
            'border:1px solid rgba(150,201,229,75);border-radius:8px;')
        direction = ('IN TUNE' if in_tune else '↑ TUNE UP' if smooth < -5
                     else '↓ TUNE DOWN' if smooth > 5 else 'ALMOST')
        self.tuner_details.setText(
            f'{smooth:+.1f} cents   ·   {frequency:.2f} Hz   ·   {direction}')
        self.tuner_meter.set_reading(smooth)

    def stop_live(self):
        if self.live:
            self.live.close()
            self.live = None

    def start_live(self):
        self.stop_live()
        try:
            self.player.stop()
            self.player.setSource(QUrl())
            self.live = LiveStemPlayer(self.stems, time_scale=1.0 / self.speed_ratio)
            self.live.set_levels(self.get_levels())
            self._sync_loop()
            self._duration = self.live.duration_ms
            self.timeline.setRange(0, self._duration)
            self.waveform.set_duration(self._duration)
            self.render_grid()
            self.status_message('Realtime stems ready. Press Play.')
        except Exception as exc:
            self.live = None
            self.status_message(f'Realtime mixer unavailable: {exc}; creating an offline mix.')
            self.request_mix()

    def live_tick(self):
        if not self.live:
            return
        self.on_position(self.live.position_ms)
        self.update_live_button()

    def update_live_button(self):
        if not self.live:
            return
        playing = self.live.playing
        self.play.setToolTip('Pause' if playing else 'Play')
        self.play.setIcon(qta.icon('fa5s.pause' if playing else 'fa5s.play', color='white'))

    def restore_splitter(self, splitter, key):
        saved = self.layout_settings.value(key)
        if saved:
            try:
                splitter.restoreState(saved)
            except (TypeError, ValueError):
                pass

    def _has_unsaved_project_changes(self):
        """Detect changed project data, not playback time or global zoom."""
        if not self.stems and not self.source_audio:
            return False
        if not self.project_file or not Path(self.project_file).is_file():
            return True
        try:
            data = json.loads(Path(self.project_file).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return True
        values = {
            'metadata': self.song_metadata,
            'in_ms': self.loop_a_ms,
            'out_ms': self.loop_b_ms,
            'loop': self.loop_enabled,
            'bpm': self.grid_bpm.value(),
            'analysis_mode': self.analysis_mode.currentIndex(),
            'accuracy': self.accuracy.currentIndex(),
            'stability': self.sensitivity.value(),
            'transpose': self.transpose.value(),
            'lookahead_ms': self.chord_lookahead.value(),
            'auto_scroll': self.follow.isChecked(),
            'levels': {name: self.volumes[name].value() for name in STEMS},
            'enabled': {name: self.checks[name].isChecked() for name in STEMS},
            'solo': {name: self.solos[name].isChecked() for name in STEMS},
            'section_overrides': {str(k): str(v) for k,v in self.section_overrides.items()},
            'chord_data': [list(item) for item in self.chord_data],
        }
        for key, value in values.items():
            old = data.get(key)
            if key == 'section_overrides':
                old = {str(k): str(v) for k,v in (old or {}).items()}
            if old != value:
                return True
        return False

    def _confirm_unsaved_changes(self):
        """Save / discard / cancel, without destroying the current project."""
        if not self._has_unsaved_project_changes():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle('Unsaved changes')
        box.setText('Save your project changes?')
        box.setInformativeText(
            'Your edits to notes, mixer, analysis settings or song details '
            'will be lost if you discard them.')
        box.setStandardButtons(
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        answer = box.exec()
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Discard:
            return True
        if answer == QMessageBox.Save:
            if self.processing or self.analysis_running:
                QMessageBox.information(
                    self, 'Analysis running',
                    'Stop or finish the current analysis before saving.')
                return False
            return bool(self.save_project())
        return False

    def closeEvent(self,event):
        if not self._confirm_unsaved_changes():
            event.ignore()
            return

        self.layout_settings.setValue('grid_zoom', self.grid_zoom.value())
        self.layout_settings.setValue('grid_row_height', self.grid_row_height.value())
        self.layout_settings.setValue('play_splitter_grid_v3', self.play_splitter.saveState())
        self.layout_settings.setValue('export_splitter_left_v2', self.export_splitter.saveState())
        self.stop_live()
        if self.tuner_stream is not None:
            self.tuner_stream.stop()
            self.tuner_stream.close()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
