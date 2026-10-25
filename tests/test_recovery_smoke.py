"""Lightweight recovery regression checks. No Demucs download or Windows packaging."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as rifflab
from realtime_audio import LiveStemPlayer


def main():
    # Isolate settings so a real close/reopen test cannot reuse runner/user state.
    settings_dir = tempfile.mkdtemp(prefix='rifflab-recovery-settings-')
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, settings_dir)
    application = QApplication.instance() or QApplication(sys.argv)
    window = rifflab.Window()
    window.resize(1440, 900)
    window.show()
    application.processEvents()

    # The tuner tab is now ICON-ONLY. Do not regress to the obsolete TUNER text assertion.
    tuner = window.tabs.indexOf(window.tuner_dialog)
    assert tuner >= 0, "Tuner must be a real tab"
    assert not window.tabs.tabIcon(tuner).isNull(), "Missing tuning-fork icon"
    assert window.tabs.tabToolTip(tuner) == "Chromatic Tuner"
    assert window.menuBar().actions(), "File/View menus missing"
    assert window.grid_row_height.orientation() == Qt.Vertical
    assert window.grid_zoom.orientation() == Qt.Horizontal
    assert window.stems_led.text().endswith("STEMS OFF")
    assert window.progress.isHidden(), "Duplicate idle progress/READY footer"
    assert window.mixer_overlay.isVisible(), "Generate Stems overlay missing"

    # View > Panels must control four actual UI surfaces, and workspace
    # round-trips their visibility without losing the current tab.
    view_menu = next(a.menu() for a in window.menuBar().actions()
                     if a.text().replace("&", "") == "View")
    panels = next(a.menu() for a in view_menu.actions()
                  if a.menu() and a.text() == "Panels")
    assert {a.text() for a in panels.actions()} == {
        "Mixer", "Timeline", "Main Indicator", "Tuner"}
    state = window.workspace_state()
    window.view_mixer_action.setChecked(False)
    assert window.play_splitter.widget(0).isHidden()
    window.view_timeline_action.setChecked(False)
    assert window.chord_scroll.isHidden()
    window.view_indicator_action.setChecked(False)
    assert window.chord.isHidden()
    window.tabs.setCurrentIndex(tuner)
    window.view_tuner_action.setChecked(False)
    assert not window.tabs.isTabVisible(tuner)
    assert window.tabs.currentIndex() == 0
    window.apply_workspace_state(state)
    application.processEvents()
    assert window.view_mixer_action.isChecked()
    assert window.view_timeline_action.isChecked()
    assert window.view_indicator_action.isChecked()
    assert window.tabs.isTabVisible(tuner)
    assert window.workspace_state()["tuner_visible"]

    # Notation transpose must not change playback rate, audio source or stem gains.
    original_rate = window.player.playbackRate()
    original_source = window.player.source()
    window.transpose.setValue(2)
    assert window.transpose_chord("C") == "D"
    assert window.player.playbackRate() == original_rate
    assert window.player.source() == original_source
    assert window.live is None, "Transpose must not start the audio mixer"
    window.transpose.setValue(0)

    # Smooth note progress is rendered as a partial gradient, not a whole-beat toggle.
    assert window.grid_buttons, "Missing timeline note widgets"
    window._note_progress[0] = 0.5
    style = window._chord_segment_style(0, True)
    assert "qlineargradient" in style and "stop:0.4980" in style

    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        # Processed 0.8s file represents 1.0s original at 1.25x playback.
        samples = np.zeros((6400, 2), dtype=np.float32)
        stems = {}
        for name in rifflab.STEMS:
            path = folder / (name + ".wav")
            sf.write(path, samples, 8000)
            stems[name] = path
        live = LiveStemPlayer(stems, time_scale=1.25)
        try:
            assert live.duration_ms == 1000, live.duration_ms
            live.seek(500)
            assert live.position == 3200, live.position
            assert abs(live.position_ms - 500) <= 1
            live.set_loop(True, 250, 750)
            assert live.loop_a == 1600, live.loop_a
            assert live.loop_b == 4800, live.loop_b
        finally:
            live.close()

        # An unsplit/offline track must NEVER fall back to pitch-shifting Qt rate.
        window.source_audio = stems["bass"]
        window.stems = {}
        window.live = None
        window.detected_bpm = 120.0
        original_rate = window.player.playbackRate()
        window.grid_bpm.setValue(90)
        assert window.grid_bpm.value() == 120, "Unsafe BPM fallback was not rejected"
        assert window.player.playbackRate() == original_rate, "BPM changed unsplit audio pitch"

        # Bass Mode must invoke bass_notes on the isolated bass file ONLY.
        window.folder = folder
        window.stems = stems
        window.analysis_cancel.clear()
        window.analysis_mode.blockSignals(True)
        window.analysis_mode.setCurrentIndex(0)
        window.analysis_mode.blockSignals(False)
        with patch.object(rifflab, "worker_command", return_value='[[0.0, "E"]]') as worker:
            window._analyze_mode(force=True)
            args = worker.call_args.args
            assert args[:3] == ("bass_notes", str(stems["bass"]), window._accuracy_key()), args
            assert not any(str(stems[n]) in args for n in ("vocals", "other", "drums"))

        # Every manual analysis entry point must split first when stems are absent.
        window.stems = {}
        window.folder = None
        window.source_audio = stems["bass"]
        window.analysis_running = False
        window.processing = False
        with patch.object(window, "start_split") as split:
            window.analyze_current()
            split.assert_called_once_with(window.source_audio)
        with patch.object(window, "start_split") as split:
            window.reanalyze_current()
            split.assert_called_once_with(window.source_audio)
        with patch.object(window, "start_split") as split:
            window.switch_analysis_mode()
            split.assert_called_once_with(window.source_audio)

    window.tabs.setCurrentIndex(tuner)
    application.processEvents()
    target = Path("recovery-ui.png")
    assert window.grab().save(str(target)), "Qt screenshot capture failed"
    # Exercise actual QSettings persistence across closing and reopening the
    # application window, not just in-memory workspace_state round-trips.
    window.source_audio = None
    window.stems = {}
    window.project_file = None
    window.grid_zoom.setValue(117)
    window.grid_row_height.setValue(46)
    window.view_indicator_action.setChecked(False)
    window.view_mixer_action.setChecked(True)
    window.view_timeline_action.setChecked(True)
    window.view_tuner_action.setChecked(True)
    window.tabs.setCurrentIndex(0)
    window.play_splitter.setSizes([340, 1000])
    application.processEvents()
    saved = window.workspace_state()
    assert window.close(), "Original window refused to close"
    reopened = rifflab.Window()
    reopened.resize(1440, 900)
    reopened.show()
    application.processEvents()  # Executes QTimer.singleShot(0, restore_last_workspace)
    restored = reopened.workspace_state()
    assert restored["grid_zoom"] == saved["grid_zoom"], (saved, restored)
    assert restored["grid_height"] == saved["grid_height"], (saved, restored)
    assert restored["indicator_visible"] is False, restored
    assert restored["mixer_visible"] and restored["timeline_visible"], restored
    assert restored["tuner_visible"], restored
    assert abs(restored["splitter"][0] - saved["splitter"][0]) <= 30, (saved, restored)
    reopened.close()
    print("PASS: persisted workspace layout/zoom/panels after actual Qt window restart")
    print("PASS: Qt startup, tuner icon, layout, transpose isolation, note fill,")
    print("      stem-only Bass Mode, source import gates, stretched-time seek/A-B loop")
    print("SCREENSHOT:", target)


if __name__ == "__main__":
    main()
