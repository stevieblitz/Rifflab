# RiffLab: independent chord benchmark

**Song:** The Beatles — *I Saw Her Standing There* (original *Please Please Me* album master).

**Reference:** Isophonics / Centre for Digital Music (Queen Mary University of London), version 1.2; manually checked chord annotations. This is not a Chordify export.

- Source collection: https://isophonics.net/content/reference-annotations-beatles
- Annotation file: https://isophonics.net/files/annotations/chordlab/The%20Beatles/01_-_Please_Please_Me/01_-_I_Saw_Her_Standing_There.lab

RiffLab fetches the **actual time-aligned .lab file at comparison time** (no made-up timestamps), extracts each chord's start time, and compares the result to its own Chord Mode estimates. The resulting report is in the local RiffLab data directory.

### Run the test
1. Import the correct *Please Please Me* album recording of *I Saw Her Standing There*; differences between masters, live recordings, or edits can shift timings.
2. Separate the stems, select Chord Mode, and analyze the instrument stems.
3. Select **File > Benchmark Beatles Chords (Isophonics)**. Requires internet access to retrieve the published reference annotation.

The benchmark reports normalized chord/root agreement and time ranges of mismatches. It is a comparison against human annotations, **not** a claim of accuracy against Chordify's particular output. The audio track is not redistributed.

Note: annotations may contain extended/slash chords that RiffLab's current simplified model cannot distinguish. Scores reflect the normalized quality categories, not full harmonic equivalence.
