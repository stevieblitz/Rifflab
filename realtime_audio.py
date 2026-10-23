"""Four synchronized WAV stems, mixed in a PortAudio callback without rendering files."""
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf

class LiveStemPlayer:
    def __init__(self, paths, time_scale=1.0):
        self.lock = threading.RLock()
        self.files = {name: sf.SoundFile(str(path)) for name, path in paths.items()}
        rates = {f.samplerate for f in self.files.values()}
        if len(rates) != 1:
            self.close()
            raise ValueError('Stems have different sample rates')
        self.rate = rates.pop()
        self.time_scale = float(time_scale)
        self.channels = 2
        self.frames = min(f.frames for f in self.files.values())
        self.position = 0
        self.levels = {name: 1.0 for name in self.files}
        self.playing = False
        self.stream = None
        self.speed = 1.0
        self.loop_enabled = False
        self.loop_a = 0
        self.loop_b = self.frames

    @property
    def duration_ms(self):
        return round(self.frames * 1000 * self.time_scale / self.rate)

    @property
    def position_ms(self):
        with self.lock:
            return round(self.position * 1000 * self.time_scale / self.rate)

    def set_levels(self, levels):
        with self.lock:
            self.levels.update(levels)

    def seek(self, ms):
        with self.lock:
            frame = max(0, min(self.frames, int(ms * self.rate / (1000 * self.time_scale))))
            for f in self.files.values():
                f.seek(frame)
            self.position = frame

    def set_speed(self, speed):
        with self.lock:
            self.speed = max(0.5, min(1.5, float(speed)))

    def set_loop(self, enabled, start_ms=None, end_ms=None):
        with self.lock:
            self.loop_enabled = bool(enabled)
            # UI timestamps refer to original-song time. FFmpeg tempo-stretched
            # files have fewer/more frames, so use the same mapping as seek().
            def to_frame(ms):
                return int(ms * self.rate / (1000 * self.time_scale))
            self.loop_a = max(0, min(max(0, self.frames - 1), to_frame(start_ms))) if start_ms is not None else 0
            self.loop_b = max(self.loop_a + 1, min(self.frames, to_frame(end_ms))) if end_ms is not None else self.frames

    def _callback(self, outdata, frames, time_info, status):
        # Lightweight pitch-preserving? No: linear interpolation changes pitch.
        # Used only at 100%; variable speed is handled by the Qt backend until
        # a proper pitch-preserving stretcher is integrated.
        with self.lock:
            outdata.fill(0)
            if not self.playing:
                return
            offset = 0
            while offset < frames and self.playing:
                limit = self.loop_b if self.loop_enabled else self.frames
                count = min(frames - offset, limit - self.position)
                if count <= 0:
                    if self.loop_enabled:
                        self.seek(round(self.loop_a * 1000 * self.time_scale / self.rate))
                        continue
                    self.playing = False
                    break
                for name, f in self.files.items():
                    gain = self.levels.get(name, 0.0)
                    if gain == 0:
                        f.seek(f.tell() + count)
                        continue
                    samples = f.read(count, dtype='float32', always_2d=True)
                    if samples.shape[1] == 1:
                        outdata[offset:offset + len(samples), :] += samples * gain
                    else:
                        outdata[offset:offset + len(samples), :] += samples[:, :2] * gain
                self.position += count
                offset += count
            np.clip(outdata, -1, 1, out=outdata)

    def play(self):
        with self.lock:
            if self.position >= self.frames:
                self.seek(0)
            if self.stream is None:
                self.stream = sd.OutputStream(samplerate=self.rate, channels=2,
                    dtype='float32', blocksize=2048, callback=self._callback)
                self.stream.start()
            self.playing = True

    def pause(self):
        with self.lock:
            self.playing = False

    def close(self):
        self.playing = False
        stream, self.stream = self.stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        for f in self.files.values():
            f.close()
