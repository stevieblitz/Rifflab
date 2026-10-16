# Repository guide — current, historical and development files

**Current public build:** [RiffLab Alpha v0.2.0 for Windows](https://github.com/stevieblitz/Rifflab/releases/tag/v0.2.0-alpha.1). Older releases remain on the [Releases](https://github.com/stevieblitz/Rifflab/releases) page.

## Branches and preservation

- `main` — public project source and documentation, based on the Alpha 2 development series.
- `feature/dev85-rebuild` — ongoing development branch; changes here are not a public release until published.
- `archive/old-main-alpha1-2026-10-16` — exact old main state before Alpha 2 became main.
- `archive/main-before-public-cleanup-2026-10-16` — full pre-cleanup snapshot of main, including every existing workflow, script and document.

**No program files, tests, historical documents or workflows were deleted during the initial public-facing cleanup.** The snapshot above also preserves prior states for reference.

## Main application and assets

- `app.py` — primary PySide6 desktop application.
- `ai_worker.py`, `realtime_audio.py`, `chord_comparison.py`, `autocue_widget.py` — analysis and audio-related source modules.
- `assets/` — original RiffLab branding and application assets.
- `requirements-preview.txt`, `requirements-full.txt` — Python dependencies.
- `tests/`, `test_chord_patterns.py`, `test_chord_comparison.py` — automated checks and regressions.

## Scripts retained for compatibility

- `start-alpha.cmd`, `start-alpha.ps1` — historical source launchers.
- `install-ai.cmd`, `install-ai.ps1` — historical install helpers.
- `verify-ai.py`, `verify-ui.py` — development validation tools.

These are kept intentionally, not advertised as the primary public Windows download. For Windows users, point to the release ZIP.

## Documentation retained for reference

- `CHANGELOG.md` — historical alpha engineering notes, including iterations subsequently changed or superseded.
- `USER_REQUESTS_RECOVERY.md` — internal development/recovery requirements; historical reference, **not** end-user instructions.
- `BENCHMARK_REFERENCE.md` — reference benchmark notes and reproduction details.

## GitHub Actions workflows

The repository intentionally retains older build and verification workflows for reproducibility. Not all workflows are intended for releases:

| Workflow file | Purpose |
| --- | --- |
| `windows-lite.yml` | Complete development Windows build on the development branch |
| `windows-build.yml` | Historical/full Windows build workflow |
| `windows-ui-test.yml` | Qt/Windows UI validation |
| `real-ui-screenshot.yml` | Visual screenshot verification |
| `bass-root-regression.yml` | Bass-note regression checks |
| `recovery-smoke.yml` | Recovery-specific smoke tests |
| `ui-preview.yml` | UI preview (if present in an archived branch) |
| `publish-alpha.yml` | Older release automation |
| `publish-public-alpha.yml` | Alpha 2 release packaging/publication workflow |
| `harmonize-alpha1-release.yml` | One-off historical Alpha 1 release notes edit |
| `update-alpha2-notes.yml` | One-off Alpha 2 public description/changelog edit |

A successful development Actions run is **not** by itself a published version. Use GitHub Releases as the authoritative download location.

## Credits

**Stevieblitz [Teun Verhoeven]** — https://teunverhoeven.nl

**Less guessing. More playing.**
