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

## 2026-10-26 — additional recovery work (not final acceptance)

- Grouped the existing advanced note controls under **Note Settings** and added an **Input Settings** button that opens/focuses the real tuner audio input selector. A targeted real-Qt smoke run [40298777750](https://github.com/stevieblitz/Rifflab/actions/runs/40298777750) passed.
- Added a **Confidence View** aligned directly below the waveform, with orange overlays on corresponding low-support waveform intervals. Bass analysis now optionally returns relative **spectral-support estimates** alongside *unchanged* bass note events; no pitch/tempo engine or NoteGuard/Stability parameter was altered. These scores are **uncalibrated heuristics**, not verified probabilities or a guarantee of correct notes.
- Eight synthetic bass-note regression cases, including an invariant that confidence annotations never change note events, passed in [40299127871](https://github.com/stevieblitz/Rifflab/actions/runs/40299127871). Real Qt smoke including a painted orange confidence segment passed in [40299317172](https://github.com/stevieblitz/Rifflab/actions/runs/40299317172). A real Qt screenshot of the new UI was captured in [40299066047](https://github.com/stevieblitz/Rifflab/actions/runs/40299066047); this screenshot has no loaded audio.
- The four official asset blobs (app icon, brand image, SVG logo and window icon) have identical Git blob hashes to the approved dev.69 commit. This verifies source asset identity, **not** EXE embedding or Windows taskbar appearance.
- Synced confidence timeline duration when source audio is loaded, live stems start and pitch-preserving BPM changes. The final code commit for this step is `e0986a1d`; CI status must be checked before treating that exact code revision as smoke-verified.

## 2026-10-27 — lightweight tempo/UI regression coverage (not final acceptance)

- Added a real Qt UI handoff check that calls `on_speed_ready` with synthetic stretched stem files and verifies original-song-time position, waveform and Confidence View durations, timeline range, and A/B loop frame mapping. Code/test commit: `3db4afe6`.
- Extended the FFmpeg pitch test to four separate synthetic stems at both 0.8× and 1.25×. It checks each fundamental, the expected duration and bounded cross-stem tail skew; WSOLA can naturally produce small tone-dependent tail variations. Test commits: `b3864455`, `efbba039`.
- A local FFmpeg sample of four tones produced tail skews of 11 ms at 0.8× and 4.2 ms at 1.25×; the regression threshold is 25 ms. This is **not** real-music, Demucs, packaged-Windows or speaker-output verification.
- CI success at the **new HEAD** has not yet been established from accessible Actions evidence. Do not mark these new checks as passed or the recovery as ready without confirming the workflow runs.

## 2026-10-28 — short-song grid and import-path regression (not final acceptance)

- Compared the branch to dev.69 again: recovery HEAD was 53 commits ahead of base `9f2865fa`, with no commits behind it, before this change. `main` was not modified.
- Found a concrete short-song bug: `render_grid()` always created at least 16 beat cells but indexed the raw detected-beat array, which could contain fewer than 16 entries. This raised `IndexError` on short recordings.
- Fixed display-only beat ruler extension without changing measured beats, audio speed, detection or transpose; the playback position now indexes the same extended beat timestamps shown by the grid. Code commit: `58dc283c`.
- Added lightweight Qt regression cases for a five-beat track, transient-safe main-note selection, progress after the final measured beat, and the real local-file entry gate that must request stems before any analysis. Test commit: `f7197361`.
- **New HEAD CI has not yet been confirmed successful**. The connected GitHub commit-status endpoint returned no statuses for `f7197361`; this is not proof that the Actions smoke workflow passed. No heavyweight Windows build was requested.

## 2026-10-29 — additional UI/audio invariants (not final acceptance)

- Confirmed the recovery branch was **56 commits ahead of** the approved dev.69 base and **0 behind** at the start of this run; no changes to `main` or dev.69.
- Added lightweight Qt regression assertions for the complete **STEMS OFF → CREATING → STEMS READY** LED/overlay state transitions; Generate Stems must be disabled while processing and removed once all four stem files exist.
- Added a 16-beat/four-measure sustained-note regression: a single note widget must span measure boundaries; measure numbers 01–04 must remain present, and progress must increase across the measure-1/2 boundary rather than restart.
- Added live-mixer invariants: changing notation transpose and horizontal/vertical grid zoom must not replace the live audio player, change its playback position, alter Qt playback rate, or change stem gains.
- Added a legacy mix/export worker guard: a nonzero notation transpose request must still pass **zero audio pitch transpose** to the worker.
- Test-only commits: `bbdf35bd` and `4f2dafcd`. **The new assertions have not yet been confirmed green in GitHub Actions**; the GitHub commit-status API exposes no checks for the prior documentation HEAD. Do not count the tests as passed until their actual run/job evidence is available.
- Static review confirms that note widgets currently quantize transitions to beat timestamps and split at 16-beat row boundaries; exact free-timed note durations and row-crossing sustain still require acceptance testing. No speculative audio/detection changes were made.
- Fixed a concrete merged-note UI regression: when playback left the middle of a sustained note, the previous widget was repainted using an interior beat index and lost its left endcap; the right endcap also incorrectly used the first beat rather than the merged segment's true end. UI-only code commits `796e1c2c`, `7243f3be`; regression test commit `3486214c`. The new test must pass CI before this is accepted.
- No heavyweight Windows build was started.

## Remaining acceptance blockers

- No end-to-end Windows playback recording/hardware test proving audible pitch stability and waveform/grid sync after changing BPM, steps/zoom and notation transpose.
- No validated Demucs import → separation → Bass Mode → export test on real music.
- Confidence View and waveform highlighting are implemented and tested with synthetic note data, but spectral confidence calibration and real-music timing/accuracy remain unverified.
- View > Panels visibility and representative splitter width/zoom/indicator state **now pass a real Qt close/reopen test**. Complete per-panel geometry restoration (especially hidden mixer, tuner and independently docked layouts) and user-visible layout comparison remain unverified.
- Grouped Note Settings and Input Settings navigation pass a Qt smoke test. Complete File menu semantics, independently restored panel geometry, and all requested visual details still need manual/automated acceptance checks.
- The original official assets are present, but logo/EXE/window/Qt Designer prototype parity is not fully visually compared.
- The newest UI and confidence code has passed synthetic Qt/screenshot checks; the **current branch HEAD must still be rechecked after each commit**. Full end-to-end audio/UI acceptance and user approval are still required before any heavy Windows build.

Do not mark `USER_REQUESTS_RECOVERY.md` complete until every requested item has evidence.
