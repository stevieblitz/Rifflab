# Recovery verification status — 2026-10-25

**NOT READY / NOT ACCEPTED.** Do not send a completion notice. Source of truth remains `USER_REQUESTS_RECOVERY.md`. Do not modify `main`, remove branches, or start heavyweight Windows builds before all lightweight/UI/audio checks pass.

## Basis and verified checks

- Base: `v2.0.0-dev.69`, commit `9f2865fa43856a5fe16f7b805c29bb9456bf1d58`. Recovery branch is ahead of that base, not a 1.3.x cherry-pick.
- Windows offscreen real Qt screenshot: successful run [39925446127](https://github.com/stevieblitz/Rifflab/actions/runs/39925446127), commit `1dba809e` (not final HEAD).
- Recovery UI smoke: successful run [39925507373](https://github.com/stevieblitz/Rifflab/actions/runs/39925507373), commit `4b998a19`. Checks Qt startup, icon-only Tuner tab, menus, slider orientation, mixer overlay/LED, notation-only transpose, gradient fill, stem-only Bass Mode, analysis entry gates, and synthetic stretched-stem seek/loop mapping.
- Seven synthetic bass-root cases: successful run [39925360715](https://github.com/stevieblitz/Rifflab/actions/runs/39925360715), commit `002014eb`.
- Latest combined light verification at code commit `918176d9`: [Qt/UI regression run 39925721806](https://github.com/stevieblitz/Rifflab/actions/runs/39925721806) **success** and [bass-root + FFmpeg atempo pitch/duration run 39925721814](https://github.com/stevieblitz/Rifflab/actions/runs/39925721814) **success**. These are synthetic and offscreen checks, not proof of actual Windows speaker playback or real-music Demucs results.
- Source fixes: mandatory stems for analysis/re-analysis/mode changes, no vocals/full-mix Bass Mode fallback; 33ms playback UI tick; correct tempo-stretched original-song timeline and A/B loop mapping; packaged FFmpeg path; reject unsafe Qt pitch-shifting BPM fallback.
- Code commit `918176d9` passed the lightweight Qt and synthetic audio suites.
- Added **View > Panels** checkable Mixer, Timeline, Main Indicator and Tuner toggles, plus workspace save/load/reset visibility and persistence to QSettings. The HEAD UI smoke run [40078770127](https://github.com/stevieblitz/Rifflab/actions/runs/40078770127) at commit `4113f3ec` passed, including toggling all four panels and workspace state round-trip. The actual Qt screenshot run [40078758793](https://github.com/stevieblitz/Rifflab/actions/runs/40078758793) passed for application-code commit `45280ab7` (the subsequent commit only added tests). These checks do not validate all restored dimensions or Windows audio hardware.

- **2026-10-25:** Added a real Qt close/reopen regression for workspace QSettings persistence: splitter width, zoom sliders, and panel visibility survive a new Window instance. [Smoke run 40180965832](https://github.com/stevieblitz/Rifflab/actions/runs/40180965832) passed, but its logs exposed a queued resize callback referencing a deleted, obsolete tuner footer button. Removed that dead widget and callback (code commit `7150cabe`). [HEAD smoke run 40181060577](https://github.com/stevieblitz/Rifflab/actions/runs/40181060577) **passed with no Qt RuntimeError/traceback**; [real Qt screenshot run 40181060570](https://github.com/stevieblitz/Rifflab/actions/runs/40181060570) **passed**. This remains an offscreen test, not physical Windows audio verification.

## Remaining acceptance blockers

- No end-to-end Windows playback recording/hardware test proving audible pitch stability and waveform/grid sync after changing BPM, steps/zoom and notation transpose.
- No validated Demucs import → separation → Bass Mode → export test on real music.
- Confidence View and confidence indicators under/on waveform are not implemented/verified.
- View > Panels visibility and representative splitter width/zoom/indicator state **now pass a real Qt close/reopen test**. Complete per-panel geometry restoration (especially hidden mixer, tuner and independently docked layouts) and user-visible layout comparison remain unverified.
- Grouped note settings / Input Settings, complete File menu semantics, saved workspace layout, and all requested visual details need manual/automated acceptance checks.
- The original official assets are present, but logo/EXE/window/Qt Designer prototype parity is not fully visually compared.
- The **HEAD** light UI test and real screenshot of identical application code are successful (commit `7150cabe`); full end-to-end audio/UI acceptance and user approval are still required before any heavy Windows build.

Do not mark `USER_REQUESTS_RECOVERY.md` complete until every requested item has evidence.
