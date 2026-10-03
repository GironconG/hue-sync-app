import time
import math
import numpy as np

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except (Exception, OSError):
    HAS_SOUNDDEVICE = False

class AudioEngine:
    """
    Captures live system/microphone audio or generates simulated beats for testing.
    Processes audio using Fast Fourier Transform (FFT) with Automatic Gain Control (AGC).
    """
    def __init__(self, sample_rate=44100, chunk_size=1024, mode="mic", device_index=None, sensitivity=3.0):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.mode = mode  # 'mic' or 'simulator'
        self.device_index = device_index
        self.sensitivity = sensitivity # Gain multiplier
        self.stream = None
        self.is_running = False

        # FFT Analysis state
        self.bass = 0.0
        self.mids = 0.0
        self.treble = 0.0
        self.is_beat = False
        
        # Peak & AGC tracking
        self.bass_peak = 0.05
        self.mids_peak = 0.05
        self.treble_peak = 0.05
        self.energy_history = []
        self.history_size = 30
        
        # Audio buffer for FFT
        self.current_buffer = np.zeros(self.chunk_size)

    @staticmethod
    def get_available_devices():
        """Lists all input audio devices on the system."""
        if not HAS_SOUNDDEVICE:
            return []
        devices = []
        try:
            device_list = sd.query_devices()
            for idx, dev in enumerate(device_list):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append({
                        "index": idx,
                        "name": f"{dev['name']} ({dev.get('max_input_channels')} in)",
                        "is_default": idx == sd.default.device[0]
                    })
        except Exception as e:
            print(f"[AudioEngine] Error querying audio devices: {e}")
        return devices

    def start(self):
        self.is_running = True
        if self.mode == "mic" and HAS_SOUNDDEVICE:
            self._start_mic_stream()
        else:
            self.mode = "simulator"
            print("[AudioEngine] Running in Audio Simulator mode.")

    def set_mode(self, mode):
        if self.mode != mode:
            self.mode = mode
            print(f"[AudioEngine] Switching mode to: {mode}")
            if self.mode == "mic" and HAS_SOUNDDEVICE:
                self._start_mic_stream()
            else:
                self._stop_mic_stream()

    def set_device(self, device_index):
        if self.device_index != device_index:
            self.device_index = device_index
            if self.mode == "mic" and HAS_SOUNDDEVICE:
                self._start_mic_stream()

    def set_sensitivity(self, sensitivity):
        self.sensitivity = float(sensitivity)

    def _stop_mic_stream(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _start_mic_stream(self):
        self._stop_mic_stream()
        try:
            device_kw = {"device": self.device_index} if self.device_index is not None else {}
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                channels=1,
                dtype='float32',
                callback=self._audio_callback,
                **device_kw
            )
            self.stream.start()
            print(f"[AudioEngine] Live mic stream active on device index {self.device_index or 'Default'}.")
        except Exception as e:
            print(f"[AudioEngine] Failed to start mic stream on device {self.device_index}: {e}. Falling back to simulator.")
            self.mode = "simulator"

    def stop(self):
        self.is_running = False
        self._stop_mic_stream()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            pass
        # Raw mono samples
        samples = indata[:, 0]
        self._process_samples(samples)

    def update_simulator(self):
        """Generates synthetic audio waveform representing a music track with BPM beat kicks."""
        if not self.is_running:
            return

        t = time.time()
        bpm = 124
        beat_interval = 60.0 / bpm
        beat_phase = (t % beat_interval) / beat_interval
        
        kick = math.exp(-12.0 * beat_phase)
        synth = 0.4 * math.sin(2.0 * math.pi * 3.0 * t) + 0.3 * math.cos(2.0 * math.pi * 0.5 * t)
        synth = max(0.0, synth)
        
        hihat_phase = ((t + beat_interval / 2.0) % (beat_interval / 2.0)) / (beat_interval / 2.0)
        hihat = 0.3 * math.exp(-25.0 * hihat_phase)

        t_samples = np.linspace(t, t + (self.chunk_size / self.sample_rate), self.chunk_size)
        synthetic_wave = (
            kick * np.sin(2.0 * np.pi * 60.0 * t_samples) +
            synth * np.sin(2.0 * np.pi * 440.0 * t_samples) +
            hihat * (np.random.rand(self.chunk_size) * 2 - 1)
        )
        self._process_samples(synthetic_wave)

    def _process_samples(self, samples):
        self.current_buffer = samples
        
        # Calculate RMS volume
        rms = float(np.sqrt(np.mean(samples**2)))

        # FFT Analysis
        fft_vals = np.abs(np.fft.rfft(samples))
        freqs = np.fft.rfftfreq(len(samples), 1.0 / self.sample_rate)

        # Frequency Bands
        bass_mask = (freqs >= 20) & (freqs < 250)
        mids_mask = (freqs >= 250) & (freqs < 4000)
        treble_mask = (freqs >= 4000) & (freqs < 16000)

        raw_bass = float(np.mean(fft_vals[bass_mask])) if np.any(bass_mask) else 0.0
        raw_mids = float(np.mean(fft_vals[mids_mask])) if np.any(mids_mask) else 0.0
        raw_treble = float(np.mean(fft_vals[treble_mask])) if np.any(treble_mask) else 0.0

        # Automatic Gain Control (AGC Peak Tracking with smooth decay)
        decay = 0.96
        self.bass_peak = max(raw_bass, self.bass_peak * decay, 0.01)
        self.mids_peak = max(raw_mids, self.mids_peak * decay, 0.01)
        self.treble_peak = max(raw_treble, self.treble_peak * decay, 0.01)

        # Normalized values (0.0 to 1.0) boosted by user sensitivity multiplier
        norm_bass = (raw_bass / self.bass_peak) * (self.sensitivity / 3.0)
        norm_mids = (raw_mids / self.mids_peak) * (self.sensitivity / 3.0)
        norm_treble = (raw_treble / self.treble_peak) * (self.sensitivity / 3.0)

        # Noise gate: zero out if audio is silent (RMS < 0.005)
        if rms < 0.005 and self.mode == "mic":
            norm_bass = 0.0
            norm_mids = 0.0
            norm_treble = 0.0

        self.bass = float(np.clip(norm_bass, 0.0, 1.0))
        self.mids = float(np.clip(norm_mids, 0.0, 1.0))
        self.treble = float(np.clip(norm_treble, 0.0, 1.0))

        # Dynamic Peak Beat Detection
        current_energy = self.bass
        self.energy_history.append(current_energy)
        if len(self.energy_history) > self.history_size:
            self.energy_history.pop(0)

        avg_energy = np.mean(self.energy_history) if self.energy_history else 0.3
        threshold = avg_energy * 1.2
        
        self.is_beat = (current_energy > threshold) and (current_energy > 0.3)

    def get_metrics(self):
        if self.mode == "simulator":
            self.update_simulator()

        return {
            "bass": float(round(self.bass, 3)),
            "mids": float(round(self.mids, 3)),
            "treble": float(round(self.treble, 3)),
            "is_beat": bool(self.is_beat),
            "mode": str(self.mode),
            "sensitivity": float(self.sensitivity),
            "waveform": [float(round(float(x), 2)) for x in self.current_buffer[::32]]
        }
