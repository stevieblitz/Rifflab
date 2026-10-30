"""Lightweight recovery regression checks. No Demucs download or Windows packaging."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt, QSettings, QUrl
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
    assert window.confidence_timeline.isVisible(), "Confidence View missing beneath waveform"

    # Note settings are grouped; Input Settings opens the real tuner input page.
    assert window.advanced_toggle.text().startswith("Note Settings")
    window.advanced_toggle.click()
    assert window.advanced_toggle.isChecked()
    assert window.noteguard.isVisible(), "Note settings controls did not expand"
    window.advanced_toggle.click()
    assert not window.advanced_toggle.isChecked()
    window.view_tuner_action.setChecked(False)
    window.input_settings_button.click()
    assert window.view_tuner_action.isChecked(), "Input Settings must restore hidden Tuner"
    assert window.tabs.currentIndex() == tuner, "Input Settings did not open Tuner"
    window.tabs.setCurrentIndex(0)

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

        # Real local-file entry must request Demucs BEFORE any note analysis.
        # Mock only the expensive separation and asynchronous waveform decode.
        with patch.object(window, "start_split") as split, \
             patch.object(window, "load_waveform"), \
             patch.object(rifflab, "worker_command", side_effect=AssertionError("full-mix analysis")):
            window.load_local(stems["bass"], check_unsaved=False)
            split.assert_called_once_with(stems["bass"])
            assert window.source_audio == stems["bass"]
            assert not window.stems and not window.analysis_running

        # Generation state must be visible, non-clickable and must not claim
        # stems are ready until all four files exist.
        window._generating_stems = True
        window.processing = True
        window.refresh_stems_led()
        assert window.stems_led.text().endswith("CREATING")
        assert window.generate_stems_button.text() == "Generating Stems…"
        assert not window.generate_stems_button.isEnabled()
        assert window.mixer_overlay.isVisible()
        window.processing = False
        window._generating_stems = False
        window.refresh_stems_led()
        assert window.stems_led.text().endswith("STEMS OFF")

        # A short recording may have fewer than 16 detected beats. The ruler
        # must extend safely, while keeping measured beats unchanged and the
        # active-note indicator free from passing transient notes.
        window.display_chords = [(0.0, "E"), (0.10, "F"), (0.20, "E"), (1.5, "G")]
        window.display_times = [t for t, _ in window.display_chords]
        window.beat_times = [0.0, 0.5, 1.0, 1.5, 2.0]
        window._duration = 2500
        window.chord_lookahead.setValue(0)
        window.render_grid()
        assert len(window.beat_times) == 5, "Measured beat data was mutated"
        assert len(window.grid_beat_seconds) >= 16, "Short-song ruler not extended"
        window.update_chord_indicator(150)
        assert window.chord.text() == "E", "Passing transient became main note"
        window.update_chord_indicator(1600)
        assert window.chord.text() == "G", "Main note failed to follow beat ruler"
        window.update_grid_position(2600)
        assert window.grid_active >= 5, "Playhead stopped at last measured beat"

        # One sustained note spanning FOUR measures must remain a single
        # widget. Playback fill advances continuously across measure 1 -> 2
        # instead of restarting at the boundary (2.0s at 120 BPM).
        window.display_chords = [(0.0, "E")]
        window.display_times = [0.0]
        window.beat_times = [i * 0.5 for i in range(16)]
        window._duration = 8000
        window.grid_bpm.blockSignals(True)
        window.grid_bpm.setValue(120)
        window.grid_bpm.blockSignals(False)
        window.render_grid()
        assert window.grid_buttons[0] is window.grid_buttons[4]
        assert window.grid_buttons[4] is window.grid_buttons[15]
        assert [window.chord_grid.itemAtPosition(0, col).widget().text()
                for col in (1, 5, 9, 13)] == ["01", "02", "03", "04"]
        window.update_grid_position(1.75)
        before_measure = window._note_progress[0]
        window.update_grid_position(2.25)
        after_measure = window._note_progress[0]
        assert 0.20 < before_measure < after_measure < 0.40, (before_measure, after_measure)
        assert "qlineargradient" in window.grid_buttons[0].styleSheet()

        # Two merged note widgets must retain BOTH rounded endcaps when
        # playback crosses from the middle of one sustained note to another.
        window.display_chords = [(0.0, "E"), (4.0, "G")]
        window.display_times = [0.0, 4.0]
        window.render_grid()
        first_note = window.grid_buttons[0]
        assert first_note is window.grid_buttons[7]
        assert first_note is not window.grid_buttons[8]
        window.update_grid_position(2.25)
        window.update_grid_position(4.25)
        old_style = first_note.styleSheet()
        assert "border-top-left-radius:5px" in old_style, old_style
        assert "border-top-right-radius:5px" in old_style, old_style

        window.beat_times = []
        window.display_chords = []
        window.display_times = []
        window._duration = 0
        window.render_grid()

        # Notation transpose is never passed to the audio mix/export worker,
        # even if a nonzero transpose is requested by legacy callers.
        with patch.object(rifflab, "worker_command") as mix_worker:
            rifflab.mix_to_file(stems, {name: 100 for name in rifflab.STEMS},
                                7, folder / "transpose-must-not-shift.wav")
            assert mix_worker.call_args.args[0] == "mix"
            assert mix_worker.call_args.args[-1] == "0", "Audio export received pitch transpose"

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

        # Exercise the REAL UI handoff from an unstretched stem player to
        # tempo-stretched stems without opening a sound device. The display,
        # seek position and loop markers must remain in ORIGINAL song time.
        window.stems = stems
        window.refresh_stems_led()
        assert window.stems_led.text().endswith("STEMS READY")
        assert window.mixer_overlay.isHidden(), "Stem overlay stayed over ready mixer"
        window.live = LiveStemPlayer(stems, time_scale=1.0)
        window.live.seek(400)
        # Notation transpose and display zoom must not alter the live audio
        # object, seek position, Qt playback rate or stem gain settings.
        original_live = window.live
        original_live_position = original_live.position_ms
        original_qt_rate = window.player.playbackRate()
        original_levels = window.get_levels()
        window.transpose.setValue(3)
        assert window.transpose_chord("E") == "G"
        window.grid_zoom.setValue(122)
        window.grid_row_height.setValue(44)
        assert window.live is original_live
        assert window.live.position_ms == original_live_position
        assert window.player.playbackRate() == original_qt_rate
        assert window.get_levels() == original_levels
        window.transpose.setValue(0)
        window.speed_generation += 1
        window.speed_ratio = 1.25
        window.loop_enabled = True
        window.loop_a_ms = 250
        window.loop_b_ms = 750
        window.on_speed_ready(stems, 1.25, window.speed_generation)
        assert window.live is not None
        assert abs(window.live.duration_ms - 1000) <= 1
        assert window._duration == window.live.duration_ms
        assert window.timeline.maximum() == window._duration
        assert window.waveform.duration_ms == window._duration
        assert window.confidence_timeline.duration_ms == window._duration
        assert abs(window.live.position_ms - 400) <= 1
        assert window.waveform.position_ms == 400
        assert window.live.loop_enabled
        assert window.live.loop_a == 1600, window.live.loop_a
        assert window.live.loop_b == 4800, window.live.loop_b
        assert window.waveform.in_ms == 250 and window.waveform.out_ms == 750
        window.live.close()
        window.live = None
        window.loop_enabled = False
        window.clear_loop()

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
        response = '{"notes": [[0.0, "E"]], "confidence": [[0.0, 0.8, 0.32]]}'
        with patch.object(rifflab, "worker_command", return_value=response) as worker:
            window._analyze_mode(force=True)
            args = worker.call_args.args
            assert args[:3] == ("bass_notes_confidence", str(stems["bass"]), window._accuracy_key()), args
            assert not any(str(stems[n]) in args for n in ("vocals", "other", "drums"))
            assert window.confidence_timeline.segments == [[0.0, 0.8, 0.32]]
            assert window.waveform.confidence_segments == [[0.0, 0.8, 0.32]]
            window.confidence_timeline.set_duration(800)
            application.processEvents()
            confidence_image = window.confidence_timeline.grab().toImage()
            orange = confidence_image.pixelColor(confidence_image.width() // 2, 22)
            assert orange.red() > orange.blue(), "Low-confidence segment not painted orange"

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

        # QMediaPlayer holds an OS-level handle to the imported WAV on Windows.
        # Release the source BEFORE TemporaryDirectory deletes the test stems;
        # otherwise the test fails with WinError 32 even when assertions pass.
        window.player.stop()
        window.player.setSource(QUrl())
        window.source_audio = None
        application.processEvents()

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
    print("PASS: local import separation gate, short-song beat ruler and transient-safe main note")
    print("PASS: persisted workspace layout/zoom/panels after actual Qt window restart")
    print("PASS: Qt startup, tuner icon, layout, transpose isolation, note fill,")
    print("      stem-only Bass Mode, source import gates, stretched-time seek/A-B loop")
    print("SCREENSHOT:", target)


if __name__ == "__main__":
    main()
