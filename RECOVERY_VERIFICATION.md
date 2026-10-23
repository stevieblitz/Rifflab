# Recovery verification status — 2026-10-23

**NOT READY / NOT ACCEPTED.** Do not send a completion notice. Source of truth remains `USER_REQUESTS_RECOVERY.md`. Do not modify `main`, remove branches, or start heavyweight Windows builds before all lightweight/UI/audio checks pass.

## Basis and verified checks

- Base: `v2.0.0-dev.69`, commit `9f2865fa43856a5fe16f7b805c29bb9456bf1d58`. Recovery branch is ahead of that base, not a 1.3.x cherry-pick.
- Windows offscreen real Qt screenshot: successful run [39925446127](https://github.com/stevieblitz/Rifflab/actions/runs/39925446127), commit `1dba809e` (not final HEAD).
- Recovery UI smoke: successful run [39925507373](https://github.com/stevieblitz/Rifflab/actions/runs/39925507373), commit `4b998a19`. Checks Qt startup, icon-only Tuner tab, menus, slider orientation, mixer overlay/LED, notation-only transpose, gradient fill, stem-only Bass Mode, analysis entry gates, and synthetic stretched-stem seek/loop mapping.
- Seven synthetic bass-root cases: successful run [39925360715](https://github.com/stevieblitz/Rifflab/actions/runs/39925360715), commit `002014eb`.
- Additional synthetic FFmpeg atempo pitch/duration test is in `tests/test_tempo_pitch.py`; **its CI result must be verified** before treating it as passed.
- Source fixes: mandatory stems for analysis/re-analysis/mode changes, no vocals/full-mix Bass Mode fallback; 33ms playback UI tick; correct tempo-stretched original-song timeline and A/B loop mapping; packaged FFmpeg path; reject unsafe Qt pitch-shifting BPM fallback.
- The latest branch commit and its CI must be checked again; passing older commits does not prove HEAD.

## Remaining acceptance blockers

- No end-to-end Windows playback recording/hardware test proving audible pitch stability and waveform/grid sync after changing BPM, steps/zoom and notation transpose.
- No validated Demucs import → separation → Bass Mode → export test on real music.
- Confidence View and confidence indicators under/on waveform are not implemented/verified.
- View > Panels (Mixer, Timeline, Main Indicator, Tuner) with persistent geometry is not implemented/verified.
- Grouped note settings / Input Settings, complete File menu semantics, saved workspace layout, and all requested visual details need manual/automated acceptance checks.
- The original official assets are present, but logo/EXE/window/Qt Designer prototype parity is not fully visually compared.
- A clean, successful **HEAD** light test + screenshot and user acceptance are still required before any heavy Windows build.

Do not mark `USER_REQUESTS_RECOVERY.md` complete until every requested item has evidence.
