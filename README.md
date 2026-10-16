# RiffLab

**LESS GUESSING. MORE PLAYING.**

A Windows music practice and analysis app for musicians who want to hear what's really going on in a song.

Isolate the bass. Follow the chords. Loop the tricky bit until it clicks.

**Created by Stevieblitz [Teun Verhoeven].** [teunverhoeven.nl](https://teunverhoeven.nl)

> **Current release:** [RiffLab | Alpha v0.2.0 — Windows](https://github.com/stevieblitz/Rifflab/releases/tag/v0.2.0-alpha.1). This is experimental software; builds on development branches are not automatically public releases.

## Download and releases

**[Download the current Windows Alpha v0.2.0](https://github.com/stevieblitz/Rifflab/releases/tag/v0.2.0-alpha.1)** · [All releases / older versions](https://github.com/stevieblitz/Rifflab/releases)

The original [Alpha v0.1.0](https://github.com/stevieblitz/Rifflab/releases/tag/v0.1.0-alpha.1) remains available as an older version. The tagged release is the download source; GitHub's `main` branch contains the current application source and ongoing documentation.

[Release changes](https://github.com/stevieblitz/Rifflab/releases/tag/v0.2.0-alpha.1) · [Historical changelog](CHANGELOG.md) · [Repository file and workflow guide](docs/REPOSITORY_GUIDE.md)

## What it does

RiffLab combines local audio analysis, instrument separation, a synchronized note grid and practical playback controls in one desktop application.

- **Four-stem separation:** drums, bass, vocals and other, using Demucs.
- **Bass Mode:** follow detected bass notes, preferably from the separated bass stem.
- **Chord Mode:** see estimated harmonic changes and recurring patterns.
- **Interactive note grid:** colored, duration-based notes/chords, synchronized to the waveform and playhead.
- **Stem mixer:** volume, mute and solo individual instruments.
- **Practice transport:** play/pause, stop, seeking, looping, and IN/OUT markers.
- **Grid zoom:** horizontal and vertical sliders to adjust the note display.
- **Complexity:** choose how much detected note detail is visible. Internal NoteGuard and Stability settings help filter the display without altering audio pitch.
- **Tuning:** chromatic tuner, tuning guide and notation transpose.
- **Local projects and library:** reopen songs and retain analyzed results where available.
- **Benchmarks:** comparison of chord predictions against timed reference CSVs and Isophonics annotations.

RiffLab is for **practice and exploration**, not guaranteed sheet-music transcription. Noisy mixes, distortion and nonstandard tunings can cause incorrect estimates.

## Getting started (Windows)

Get the **complete Alpha v0.2.0 Windows package** from [GitHub Releases](https://github.com/stevieblitz/Rifflab/releases/tag/v0.2.0-alpha.1). Extract the entire archive, keep its bundled folders together and launch `RiffLab.exe`. The full build includes a separate `RiffLabAI` worker and FFmpeg executables.

The initial separation may download model weights and can take a while, depending on your hardware. Local analysis requires adequate disk space and RAM. Minimum hardware requirements are still being established during testing.

**From source:** use Python 3.11, install the appropriate dependencies from `requirements-preview.txt` and `requirements-full.txt`, and run `app.py`. Audio-analysis features additionally depend on the configured FFmpeg/FFprobe executables and supported model files. Consult the build workflow for the Windows packaging process.

## A typical session

1. Open or import a song.
2. Generate its stems.
3. Choose **Bass** or **Chords** and an analysis accuracy.
4. Follow the waveform and note grid; change the display complexity if needed.
5. Solo or mute a stem, mark a loop, and play.

**Audio pitch and note display are separate concerns:** grid zoom and Complexity affect what you see. Notation Transpose changes displayed note names rather than retuning the audio.

## Alpha notes

RiffLab is actively developed. Expect occasional wrong notes/chords, imperfect stem isolation, variable processing speed and bugs. Tested benchmarks help direct improvements, but they do not make any individual song's transcription definitive.

If something breaks, [open an issue](https://github.com/stevieblitz/Rifflab/issues) with the version/build number, Windows version, steps to reproduce, expected vs. actual behavior and logs or screenshots if available.

[Development history](CHANGELOG.md)

## Clone, fork, improve

**Curious? Clone it. Want to experiment? Fork it. Found a better approach? Show me.**

RiffLab is open to improvements, bug reports, discussion and pull requests. Improvements to analysis accuracy, stability, accessibility, performance and the interface are especially welcome.

I'd genuinely love to see what others build with RiffLab. If you create a fork or make something interesting, feel free to open an issue or discussion and share it. That isn't a requirement — just curiosity.

**License note:** No `LICENSE` file has been selected for RiffLab yet. The repository being visible does **not** by itself grant permission to copy, modify or redistribute its code under an open-source license. Until a license is added, clone/fork functionality on GitHub is subject to GitHub's terms; broader reuse, redistribution and third-party contributions should wait for an explicit license. A license must be chosen before the project can be presented as openly licensed software.

## Technology & acknowledgements

RiffLab is an independent project built with open-source tools. Thanks to the people who develop and maintain them.

| Area | Software |
| --- | --- |
| Desktop UI | [Python](https://python.org), [PySide6 / Qt](https://doc.qt.io/qtforpython-6/), [Qt Multimedia](https://doc.qt.io/qt-6/qtmultimedia-index.html) |
| Icons | [QtAwesome](https://github.com/spyder-ide/qtawesome), [Font Awesome](https://fontawesome.com/) |
| Source separation | [Demucs](https://github.com/facebookresearch/demucs), [PyTorch](https://pytorch.org/), [torchaudio](https://github.com/pytorch/audio) |
| Music/signal processing | [librosa](https://librosa.org/), [NumPy](https://numpy.org/), [SciPy](https://scipy.org/) |
| Audio I/O | [SoundFile](https://github.com/bastibe/python-soundfile) / libsndfile, [sounddevice](https://python-sounddevice.readthedocs.io/) / PortAudio |
| Media utilities | [FFmpeg / FFprobe](https://ffmpeg.org/), [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| Data & packaging | SQLite, [PyInstaller](https://pyinstaller.org/), GitHub Actions |
| Reference annotations | [Isophonics](https://isophonics.net/) chord datasets |

**Upstream projects and binary distributions:** [yt-dlp](https://github.com/yt-dlp/yt-dlp) is derived from [youtube-dl](https://github.com/ytdl-org/youtube-dl). The Windows workflow fetches FFmpeg binaries from [Gyan's FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) or [BtbN's FFmpeg builds](https://github.com/BtbN/FFmpeg-Builds). These are independent third-party projects, not RiffLab-maintained forks. No RiffLab-specific forks of Demucs, PyTorch, Qt or librosa have been verified in the current repository.

The build must retain any required copyright notices and license terms for bundled third-party components, especially FFmpeg and Qt. This README is not a substitute for those notices.

## Credits

**Created by Stevieblitz [Teun Verhoeven].** [teunverhoeven.nl](https://teunverhoeven.nl). Built around a musician's workflow, with a healthy amount of experimentation. AI-assisted development tools have been used along the way.

RiffLab is not affiliated with or endorsed by the maintainers of its dependencies or reference datasets.

---

**Made for curious ears and impatient fingers.**

**RiffLab — Less guessing. More playing.**
