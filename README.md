# RiffLab Alpha 1.0.2 — Minimal panel dividers

- Removed thick/gradient-like splitter styling.
- PLAY and Export splitters now have a single centered 1px muted blue-gray divider, brighter on hover and blue while dragging.
- Kept an 8px draggable hit area, resize limits and saved panel widths.
- No changes to audio analysis, stems or dependencies.

Run `start-alpha.cmd` on Windows. Python syntax and ZIP integrity verified; GUI behavior not tested on Windows.


Alpha 1.0.3: Bass Mode displays note roots only, including legacy caches; local unsplit Bass Mode runs bass pitch analysis rather than harmony analysis; mode changes and restored projects trigger matching analysis. Full stem-based bass detection remains preferred.


Alpha 1.0.4: Tuning fork button moved from bottom footer to far right of main tab bar, inline with PLAY / Library / Import / Export.

Alpha 1.0.5: square tuning-fork button on the far right of the main tab row; dynamically matches main tab height, larger icon.


Alpha 1.0.6: Centered PLAY transport buttons horizontally in the PLAY workspace, with loop status remaining right-aligned.


Alpha 1.0.7: Checked transport controls (e.g. Loop) use a thin cyan LED strip along the bottom instead of a filled highlight.


Alpha 1.0.8: Grid zoom moved to the left side of the transport row, directly below the timeline. Playback controls remain centered.


Alpha 1.0.9: Stem mixer moved to far left in PLAY and Export; resize handles and saved widths retained. New splitter settings keys prevent reversed legacy sizes.


Alpha 1.1.0: Independent M (mute) and S (solo) buttons for each stem in PLAY and Export. Multiple solos supported; any solo isolates soloed, unmuted channels. Mute takes precedence. Settings synchronized and saved with projects. Reset clears solos.

Alpha 1.1.1: Grid Zoom slider shifted left within transport row; label and percentage now follow slider. Playback buttons remain centered.

Alpha 1.1.2: Main PLAY / Library / Import & Export tabs aligned to the right, immediately before the tuning-fork button.


Alpha 1.1.3: Exclusive solo: selecting S automatically unmutes that channel and turns off other solos. Selecting M cancels S on the same channel. M and S cannot both be active on the same channel. Old projects normalized on load.


Alpha 1.1.4: Reworked exclusive solo and mute to share a direct realtime gain update path. Solo explicitly sets all other gains to zero without changing their mute states. Solo and mute remain mutually exclusive. Export mixer synced.


Alpha 1.1.5: Fix Solo buttons staying disabled when opening an existing project with saved stems. Enable Solo alongside Mute/Volume and synchronize Export mixer after loading/restoring the project.


Alpha 1.1.6: While a stem is soloed, other channels are visually dimmed in PLAY and Export (labels, sliders and mute buttons), but their S buttons stay enabled so you can switch solo immediately. Original mute/volume values remain unchanged.


Alpha 1.1.7: Compact instrument icons beside channel names in both PLAY and Export mixers (drum kit, bass guitar, music/other, microphone). Icons dim with non-solo channels. No changes to audio routing.


Alpha 1.1.8: Mute and Solo buttons both 28x26 px, grouped and right-aligned in each stem header, in PLAY and Export. No audio behavior changes.


Alpha 1.1.9 — compact workspace:
- PROJECT / Save / Open / Recent integrated into the main tab-header strip, with tabs and tuner at the right.
- Chord analysis controls regrouped in a compact two-row toolbar; NEXT, lookahead and grid hint on second row.
- Subtle consistent blue borders and dark panel background; no extra banner or unused top row.
- Existing chord grid, mixer, transport, keyboard shortcuts, tab behavior and audio engine retained.
- Reference mockup's waveform is not implemented; the actual working timeline stays below the grid.


Alpha 1.2.0 — waveform seeking:
- Removed PROJECT label; Save/Open remain in top header.
- Added clickable and draggable waveform with time marks and live playhead above the chord controls.
- Waveform preview decoded asynchronously from source audio or mixed four stems using FFmpeg; no Demucs rerun.
- Seeking the waveform moves audio playback and updates current/next chord and highlighted grid position through the existing on_position() path.
- Previous timeline QSlider retained internally for compatibility with existing transport/loop logic.
- No Windows GUI runtime test performed.


Alpha 1.2.1: Move the current chord indicator from the analysis toolbar into the top-left of the waveform, as marked in orange on the screenshot. Overlay does not intercept waveform clicks/drags. Remove NEXT strip (green marking) entirely. Other controls and chord-grid sync unchanged.


Alpha 1.2.2: Bass | Chords segmented switch moved from analysis toolbar to right edge above playback grid. Existing analysis mode combo retained invisibly as source of truth for analysis, saved projects, and keyboard behavior. Mode buttons stay in sync after loading projects. No changes to analysis engine.

Alpha 1.2.3: Tiny, muted by Teun Verhoeven signature at bottom right of status footer. No functional changes.

Alpha 1.2.4: Current chord is placed immediately to the left of the waveform in a horizontal layout; no overlay or waveform obstruction.


Alpha 1.2.5: IN/OUT bracket markers drawn on waveform, independently draggable; matching transport button labels.


Alpha 1.2.6: Full-width waveform and analysis toolbar; compact stem mixer in the lower grid row. Splitter state uses a new key to avoid old full-height proportions.


Alpha 1.2.7: Playback grid expands vertically to occupy available window height; transport, zoom, loop controls and clock remain pinned at the bottom. Mixer is a compact panel at top-left of the grid, not a full-height sidebar.

Alpha 1.2.8: IN and OUT transport buttons are icon-only, identical dimensions and styling to other transport buttons; tooltips and marker functionality unchanged.


Alpha 1.2.9: custom IN/OUT bracket icons; compact single-row analysis toolbar; removed grid hint and redundant grid notice from visible layout; time moved into fixed bottom transport row.


Alpha 1.3.0: Now-playing title in header; first-save metadata dialog (Project Name, Artist, Album, Song Title); YouTube metadata prefills fields; readable safe .riff filenames; subsequent saves do not prompt.

Alpha 1.3.1: IN/OUT buttons are clean opposing bracket-only icons, no arrows. Header song title remains centered between Recent and PLAY. First-save Project Name, Artist, Album and Song Title dialog; YouTube metadata prefills available fields, artist/title can be parsed from a common video title format. Human-readable .riff names; no YouTube ID fallback.


Alpha 1.3.2: larger transparent header song title, auto-scrolling marquee for long titles only.


## Alpha 1.3.3 — Layout polish
Consistent padding and alignment across PLAY header, analysis panel, grid, mixer, transport, and status bar. No changes to analysis or audio processing.

Alpha 1.3.4: Larger 17pt song title, transparent background without blue rectangle.


Alpha 1.3.5: Removed the lighter blue header background behind Recent and the song title; header now matches the main dark surface.

Alpha 1.3.6: Removed PLAYBACK GRID heading while keeping Bass/Chords controls.


## Alpha 1.3.7 — UI typography and mixer cleanup
- Removed the PLAYBACK GRID heading (already hidden in 1.3.6).
- Removed the PLAY stem mixer's darker boxed background and border.
- Unified general interface text to Segoe UI 12px, with consistent mixer heading and labels.
- Export mixer retains its panel styling.
