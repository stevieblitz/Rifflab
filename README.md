<p align="center">
  <img src="assets/rifflab-brand.png" alt="StevieBlitz's RiffLab — by StevieBlitz, powered by AI" width="480">
</p>

# StevieBlitz's RiffLab

### LESS GUESSING. MORE JAMMING.

**Find a song. Import it. Figure it out. Play along.**

RiffLab is a free Windows music analysis and practice toolkit for home jamming. **Import your favourite music directly from supported online video links, including YouTube, or use your own audio files.** Analyze notes, chords, basslines and rhythm, separate instruments into stems, tune up and jam, all in one application.

No switching between five tools just to learn a riff. And no subscription required.

> **Development status:** Alpha development; first public beta in preparation. Development builds are experimental and are not automatically published releases.

## Why RiffLab?

I'm a drummer who loves playing bass and guitar too, partly because carrying a drum kit everywhere gets old. I also have presbycusis, making some higher-frequency details harder to distinguish.

I've used plenty of music software over the years. Some of it is excellent. A lot of it is expensive, subscription-based or split across different apps. All I wanted was to find a song, get a better picture of what's being played and start jamming without managing a small portfolio of subscriptions.

So I started building RiffLab.

**The ambition: a free, genuinely open-source toolkit that makes exploring and learning music more accessible to everyone.** The open-source license has yet to be finalized; see [License status](#license-status).

## Import music your way

**Online video import:** Found a track, live performance or obscure song on YouTube? RiffLab's online import workflow is designed to bring supported video sources into the same practice workspace as local recordings. Support depends on the source and technical restrictions.

**Local audio import:** Already have the track? Open your audio file and get straight to work.

Once a track is imported, work with its stems, musical analysis, synchronized note grid and playback controls in one place.

Import only material you have permission to access and process. RiffLab is not affiliated with YouTube.

## Features

| Feature | What it does |
| --- | --- |
| **Online & local music import** | Bring supported online video audio and local recordings into your session. |
| **Four-stem separation** | Separate drums, bass, vocals and other instruments with Demucs. |
| **Bass Mode** | Follow estimated bass notes and roots, preferably analyzed from the separated bass stem. |
| **Chord Mode** | Explore estimated chords, harmonic changes and repeating patterns. |
| **Visual note grid** | See coloured, duration-based notes synchronized with playback. |
| **Interactive waveform** | Seek through a recording and track the playhead in real time. |
| **Stem mixer** | Adjust individual stem volume, mute and exclusive solo. |
| **Practice transport** | Play, pause, stop, seek and loop sections with IN and OUT markers. |
| **Tempo & rhythm** | Use BPM and timing analysis as a guide while playing along. |
| **Zoom & complexity** | Adjust horizontal and vertical views and filter how much note detail is shown. |
| **Chromatic tuner** | Tune an instrument without leaving your session. |
| **Notation transpose** | Shift displayed note names for different musical references; this does **not** pitch-shift audio. |
| **Projects & library** | Reopen songs and save project information and analysis results where available. |
| **Analysis benchmarks** | Compare chord predictions with timed reference data to guide improvements. |

RiffLab assists with listening and practice; it is **not guaranteed sheet-music transcription**. Distortion, harmonics, dense mixes and alternate tunings can confuse automatic analysis.

## A typical jam session

1. Import a song from a supported online video link or a local file.
2. Generate the stems.
3. Switch between **Bass** and **Chords** and choose your analysis settings.
4. Follow the waveform and note grid while the track plays.
5. Solo or mute instruments, loop a section and grab your own instrument.

Repeat until it clicks. Or until the neighbours learn the song too.

## Why free and open source?

Learning and making music should be accessible regardless of budget. Commercial music tools can be fantastic, but chord analysis, stem separation and other useful features often live in separate paid products.

There's nothing wrong with paying developers. But finding a bass note shouldn't necessarily require another monthly direct debit.

RiffLab aims to bring practical music tools together in a single free application, with a community-friendly open-source future.

## Alpha testers wanted

RiffLab is still evolving, and **I'd genuinely love to hear how it works for other musicians.** Guitarists, bassists, drummers, keyboard players and curious home jammers are all welcome.

I'm especially interested in hearing about note and chord accuracy, bass detection, stem quality, timing, interface clarity and anything that gets in the way of actually playing.

Found a bug, a confusing control or a feature that deserves improvement? [Open an issue](https://github.com/stevieblitz/Rifflab/issues). Please include your build version, Windows version, reproduction steps and a screenshot or log if useful.

Constructive criticism is welcome. At this stage, finding what doesn't work is basically part of the feature set.

## Download & getting started (Windows)

When a public build is available, get the **complete Windows package** from [GitHub Releases](https://github.com/stevieblitz/Rifflab/releases). Extract the full archive, keep the bundled folders together and run `RiffLab.exe`.

The packaged application includes a separate `RiffLabAI` worker and FFmpeg utilities. First-time stem separation may download model weights; processing time and resource requirements depend on your system. Minimum hardware requirements are still being tested.

**From source:** Use Python 3.11 with the project's `requirements-preview.txt` and `requirements-full.txt`, then start `app.py`. Full analysis additionally requires configured FFmpeg/FFprobe tools and model files. Refer to the build workflow for packaging details.

## Changelog

RiffLab has evolved through a series of experimental alpha iterations. Here are selected milestones from the existing development history:

| Alpha versions | Highlights |
| --- | --- |
| **1.3.0–1.3.7** | Song and project metadata, refined header presentation, typography and mixer cleanup. |
| **1.2.0–1.2.9** | Interactive waveform seeking, IN/OUT markers, synchronized chord display, mode switch and layout adjustments. |
| **1.1.0–1.1.9** | Stem mixer Mute/Solo behavior, compact controls, channel icons and workspace improvements. |
| **1.0.2–1.0.9** | Early Bass Mode refinements, panel dividers, tuner access and zoom/transport placement. |

These are development milestones, not claims of public releases. For detailed version-by-version notes, read **[CHANGELOG.md](CHANGELOG.md)**.

Current work also focuses on stem-based note detection, reducing harmonic false positives, beat synchronization, consistent zoom behavior and a compact, reliable interface. Planned or experimental work is not necessarily available in a published build.

## License status

RiffLab is intended to become free and open source. **No RiffLab source-code license has been selected yet.** A publicly visible GitHub repository is not, by itself, an open-source license or permission to redistribute code. An explicit license will be added before the project is presented as a formally licensed open-source release.

Third-party dependencies retain their own licensing terms.

## Technology & acknowledgements

| Area | Software |
| --- | --- |
| Desktop application | Python, PySide6 / Qt, Qt Multimedia |
| Interface icons | QtAwesome, Font Awesome |
| Stem separation | Demucs, PyTorch, torchaudio |
| Signal analysis | librosa, NumPy, SciPy |
| Audio input/output | SoundFile, sounddevice |
| Media handling | FFmpeg / FFprobe, yt-dlp |
| Data and packaging | SQLite, PyInstaller, GitHub Actions |
| Reference annotations | Isophonics chord datasets |

Thanks to the developers and maintainers of these tools. Distributions must respect the relevant third-party notices and licenses, especially Qt and FFmpeg.

## Contributing

Bug reports, tests, ideas, interface feedback and discussion are welcome through [GitHub Issues](https://github.com/stevieblitz/Rifflab/issues). Code reuse and redistribution terms will be clarified when the source license is selected.

## Credits

**Created by StevieBlitz.** Developed through hands-on musical experimentation and AI-assisted programming.

*Made for curious ears, impatient fingers and musicians who'd rather be playing.*

**LESS GUESSING. MORE JAMMING.**
