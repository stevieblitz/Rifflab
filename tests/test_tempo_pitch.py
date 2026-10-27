"""Synthetic audio regression for the FFmpeg atempo path used by RiffLab.

Checks speed change AND fundamental frequency; does not claim full hardware
playback, packaged Windows audio, or Demucs accuracy is validated.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def dominant_hz(signal, sample_rate):
    n = min(len(signal), sample_rate)
    center = len(signal) // 2
    window = signal[center - n // 2:center - n // 2 + n]
    assert len(window) == n
    spectrum = np.abs(np.fft.rfft(window * np.hanning(n), n=sample_rate * 4))
    freqs = np.fft.rfftfreq(sample_rate * 4, 1.0 / sample_rate)
    # Ignore DC and non-bass frequencies.
    allowed = (freqs > 50) & (freqs < 500)
    return float(freqs[allowed][np.argmax(spectrum[allowed])])


def main():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    assert Path(ffmpeg).is_file(), "FFmpeg is required to verify pitch-preserving BPM"
    rate = 16000
    seconds = 4
    time = np.arange(rate * seconds, dtype=np.float64) / rate
    original = (0.35 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "original.wav"
        sf.write(source, original, rate)
        for tempo in (0.8, 1.25):
            output = Path(tmp) / f"tempo-{tempo}.wav"
            subprocess.run(
                [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-y", "-i", str(source), "-af", f"atempo={tempo:.6f}",
                 "-c:a", "pcm_f32le", str(output)],
                check=True, capture_output=True, text=True,
            )
            samples, sr = sf.read(output, dtype="float32")
            duration = len(samples) / sr
            pitch = dominant_hz(samples, sr)
            assert abs(duration - seconds / tempo) < 0.16, (tempo, duration)
            assert abs(pitch - 220.0) < 2.0, (tempo, pitch)
            print(f"PASS: {tempo:.2f}x, duration {duration:.3f}s, pitch {pitch:.2f}Hz")

        # Four-stem regression: the same atempo pipeline must preserve each
        # stem's own pitch and keep stems mutually aligned for the live mixer.
        # This tests rendered audio files, not Windows speakers or Demucs.
        frequencies = {"bass": 110.0, "drums": 196.0,
                       "other": 146.83, "vocals": 261.63}
        for name, hz in frequencies.items():
            samples = (0.25 * np.sin(2 * np.pi * hz * time)).astype(np.float32)
            sf.write(Path(tmp) / f"{name}.wav", samples, rate)
        for tempo in (0.8, 1.25):
            lengths = []
            for name, hz in frequencies.items():
                output = Path(tmp) / f"{name}-{tempo:.2f}.wav"
                subprocess.run(
                    [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                     "-y", "-i", str(Path(tmp) / f"{name}.wav"),
                     "-af", f"atempo={tempo:.6f}",
                     "-c:a", "pcm_f32le", str(output)],
                    check=True, capture_output=True, text=True,
                )
                samples, sr = sf.read(output, dtype="float32")
                lengths.append(len(samples))
                assert abs(dominant_hz(samples, sr) - hz) < 2.0, (name, tempo)
                assert abs(len(samples) / sr - seconds / tempo) < 0.16, (name, tempo)
            # WSOLA/atempo can yield slightly different tail lengths per tone;
            # the player uses the shortest stem and shares a common start.
            assert (max(lengths) - min(lengths)) / rate < 0.025, (tempo, lengths)
            print(f"PASS: four synchronized stems at {tempo:.2f}x, pitch unchanged")


if __name__ == "__main__":
    main()
