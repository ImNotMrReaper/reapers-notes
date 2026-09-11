"""
voice.py: High-performance local real-time streaming voice dictation & CPU Whisper.
Zero cloud dependencies, sub-80ms chunk inference on Intel Raptor Lake CPU.
Streams words live onto the screen into the active note as the user speaks.
"""

import os
import sys
import math
import time
import signal
import struct
import threading
import subprocess
import re
import ctypes
from pathlib import Path
from gi.repository import GLib

WAV_FILE = "/tmp/reaper_notes_voice.wav"

WHISPER_LIB_PATHS = [
    Path(__file__).parent / "libwhisper_easy.so",
    Path.home() / ".local/share/whisper.cpp/build/bin/libwhisper_easy.so"
]

WHISPER_MODELS = [
    Path.home() / ".local/share/whisper.cpp/models/ggml-tiny.en.bin",
    Path.home() / ".local/share/whisper.cpp/models/ggml-base.en.bin"
]

WHISPER_BIN = Path.home() / ".local/share/whisper.cpp/build/bin/whisper-cli"


class CallableBool:
    """
    A boolean value that can also be called as a function without raising TypeError.
    Guarantees that both `if mgr.is_recording:` and `if mgr.is_recording():` work safely.
    """
    def __init__(self, val: bool = False):
        self.val = bool(val)

    def set(self, val: bool):
        self.val = bool(val)

    def __bool__(self):
        return self.val

    def __call__(self):
        return self.val

    def __repr__(self):
        return str(self.val)


class WhisperEngine:
    """Fast in-memory C++ Whisper wrapper via libwhisper_easy.so."""

    def __init__(self):
        self.lib = None
        self.ctx = None
        self.model_path = None
        self._lock = threading.Lock()
        self._load_library()

    def _load_library(self):
        lib_path = None
        for p in WHISPER_LIB_PATHS:
            if p.exists():
                lib_path = str(p)
                break
        if not lib_path:
            return

        try:
            self.lib = ctypes.CDLL(lib_path)
            self.lib.easy_init.argtypes = [ctypes.c_char_p]
            self.lib.easy_init.restype = ctypes.c_void_p

            self.lib.easy_free.argtypes = [ctypes.c_void_p]
            self.lib.easy_free.restype = None

            self.lib.easy_transcribe.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_char_p
            ]
            self.lib.easy_transcribe.restype = ctypes.c_void_p

            self.lib.easy_free_string.argtypes = [ctypes.c_void_p]
            self.lib.easy_free_string.restype = None
        except Exception as e:
            print(f"[WhisperEngine] Library load failed: {e}", file=sys.stderr)
            self.lib = None

    def ensure_model_loaded(self) -> bool:
        with self._lock:
            if self.ctx and self.lib:
                return True
            if not self.lib:
                self._load_library()
                if not self.lib:
                    return False

            for m in WHISPER_MODELS:
                if m.exists():
                    self.model_path = str(m)
                    break

            if not self.model_path:
                return False

            try:
                self.ctx = self.lib.easy_init(self.model_path.encode("utf-8"))
                return bool(self.ctx)
            except Exception as e:
                print(f"[WhisperEngine] Init failed: {e}", file=sys.stderr)
                return False

    def transcribe_samples(self, samples_int16, n_threads: int = 4, prompt: str = "") -> str:
        with self._lock:
            if not self.ensure_model_loaded() or not samples_int16:
                return ""

            try:
                float_samples = [s / 32768.0 for s in samples_int16]
                c_floats = (ctypes.c_float * len(float_samples))(*float_samples)
                c_prompt = prompt.encode("utf-8") if prompt else b""

                ptr = self.lib.easy_transcribe(
                    self.ctx,
                    c_floats,
                    len(float_samples),
                    n_threads,
                    c_prompt
                )
                if not ptr:
                    return ""

                raw = ctypes.string_at(ptr).decode("utf-8", errors="replace")
                self.lib.easy_free_string(ptr)

                # Filter audio markers, timestamps, bracketed tags
                clean = re.sub(r"\[.*?\]|\(.*?\)", "", raw)
                clean = re.sub(r"\s+", " ", clean).strip()
                return clean
            except Exception as e:
                print(f"[WhisperEngine] Transcribe error: {e}", file=sys.stderr)
                return ""

    def close(self):
        with self._lock:
            if self.ctx and self.lib:
                try:
                    self.lib.easy_free(self.ctx)
                except Exception:
                    pass
                self.ctx = None


class VoiceDictationManager:
    """
    Manages microphone audio capture via PipeWire and streaming speech-to-text.
    Yields live partial transcriptions to the UI as words are spoken.
    """

    def __init__(self):
        self.is_recording = CallableBool(False)
        self.proc = None
        self.engine = WhisperEngine()
        self._lock = threading.Lock()
        self._cancel_flag = False
        self._stop_flag = False
        self._thread = None
        self._legacy_transcribe_cb = None

        # Pre-warm model in background so first dictation has zero latency
        threading.Thread(target=self.engine.ensure_model_loaded, daemon=True).start()

    def is_active(self) -> bool:
        return bool(self.is_recording)

    def start_streaming(self, on_partial_cb, on_complete_cb=None, on_error_cb=None) -> bool:
        """
        Starts live microphone streaming.
        on_partial_cb(text: str, is_final: bool) is invoked on GLib main thread.
        """
        with self._lock:
            if self.is_recording:
                return False

            self._cancel_flag = False
            self._stop_flag = False
            self.is_recording.set(True)

            cmd = ["pw-record", "--format=s16", "--rate=16000", "--channels=1", "-"]
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )
            except Exception as e:
                self.is_recording.set(False)
                if on_error_cb:
                    GLib.idle_add(on_error_cb, f"PipeWire error: {e}")
                return False

            self._thread = threading.Thread(
                target=self._streaming_worker,
                args=(on_partial_cb, on_complete_cb, on_error_cb),
                daemon=True
            )
            self._thread.start()
            return True

    def _streaming_worker(self, on_partial_cb, on_complete_cb, on_error_cb):
        """
        Continuous audio reading and energy-based sentence streaming loop.
        Processes audio in chunks of 100ms (1600 samples).
        """
        accumulated_sentence = []
        silence_count = 0
        speech_detected_in_sentence = False
        last_context_prompt = ""
        sample_rate = 16000
        chunk_samples = 1600  # 100ms
        chunk_bytes = chunk_samples * 2  # 16-bit signed PCM
        min_sentence_samples = int(0.6 * sample_rate)  # at least 600ms before transcribing
        max_sentence_samples = int(3.5 * sample_rate)  # auto-commit long sentence at 3.5s
        energy_threshold = 400.0  # speech activity threshold

        try:
            while not self._cancel_flag:
                if self._stop_flag:
                    break

                raw_data = self.proc.stdout.read(chunk_bytes)
                if not raw_data:
                    break

                num_samples = len(raw_data) // 2
                samples = struct.unpack(f"<{num_samples}h", raw_data)
                
                # Compute RMS energy
                sum_sq = sum(s * s for s in samples)
                rms = math.sqrt(sum_sq / num_samples) if num_samples > 0 else 0.0

                if rms > energy_threshold:
                    speech_detected_in_sentence = True
                    silence_count = 0
                else:
                    silence_count += 1

                # If speech has started in this phrase, keep accumulating
                if speech_detected_in_sentence:
                    accumulated_sentence.extend(samples)

                    # Condition A: Natural pause (silence >= 400ms after speech)
                    silence_duration_ms = silence_count * 100
                    if silence_duration_ms >= 400 and len(accumulated_sentence) >= min_sentence_samples:
                        text = self.engine.transcribe_samples(
                            accumulated_sentence,
                            prompt=last_context_prompt
                        )
                        if text:
                            last_context_prompt = text[-40:]
                            GLib.idle_add(on_partial_cb, text, True)

                        accumulated_sentence = []
                        speech_detected_in_sentence = False
                        silence_count = 0

                    # Condition B: Continuous speech streaming (every 1.5s while talking)
                    elif len(accumulated_sentence) >= int(1.5 * sample_rate):
                        text = self.engine.transcribe_samples(
                            accumulated_sentence,
                            prompt=last_context_prompt
                        )
                        if text:
                            GLib.idle_add(on_partial_cb, text, False)

                        # If sentence gets too long (>= 3.5s), commit and reset
                        if len(accumulated_sentence) >= max_sentence_samples:
                            if text:
                                last_context_prompt = text[-40:]
                                GLib.idle_add(on_partial_cb, text, True)
                            accumulated_sentence = []
                            speech_detected_in_sentence = False

        except Exception as e:
            print(f"[Voice Worker] Streaming loop error: {e}", file=sys.stderr)
            if on_error_cb:
                GLib.idle_add(on_error_cb, str(e))
        finally:
            # Terminate PipeWire process
            self._cleanup_process()

            # If stopped normally and user spoke, transcribe any final tail
            if not self._cancel_flag and accumulated_sentence and len(accumulated_sentence) >= int(0.3 * sample_rate):
                final_text = self.engine.transcribe_samples(
                    accumulated_sentence,
                    prompt=last_context_prompt
                )
                if final_text:
                    GLib.idle_add(on_partial_cb, final_text, True)

            self.is_recording.set(False)
            if on_complete_cb and not self._cancel_flag:
                GLib.idle_add(on_complete_cb)

    def stop_streaming(self):
        """Stops streaming dictation and commits final transcribed text."""
        with self._lock:
            if not self.is_recording:
                return
            self._stop_flag = True
            self.is_recording.set(False)
            self._cleanup_process()

    def cancel_streaming(self):
        """Cancels streaming dictation immediately, discarding any pending audio."""
        with self._lock:
            if not self.is_recording:
                return
            self._cancel_flag = True
            self._stop_flag = True
            self._cleanup_process()
            self.is_recording.set(False)

    def _cleanup_process(self):
        if self.proc:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except OSError:
                try:
                    self.proc.terminate()
                except OSError:
                    pass
            self.proc = None

    # -------------------------------------------------------------------------
    # Legacy Batch Mode (Kept for backwards compatibility)
    # -------------------------------------------------------------------------
    def start_recording(self) -> bool:
        with self._lock:
            if self.is_recording:
                return False
            if os.path.exists(WAV_FILE):
                try:
                    os.remove(WAV_FILE)
                except OSError:
                    pass

            cmd = ["pw-record", "--format=s16", "--rate=16000", "--channels=1", WAV_FILE]
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )
                self.is_recording.set(True)
                return True
            except Exception as e:
                print(f"[Voice Error] Failed to start pw-record: {e}", file=sys.stderr)
                return False

    def stop_and_transcribe(self, on_complete_cb):
        with self._lock:
            if not self.is_recording or not self.proc:
                return
            self._cleanup_process()
            self.is_recording.set(False)

        def worker():
            time.sleep(0.15)
            if not os.path.exists(WAV_FILE) or os.path.getsize(WAV_FILE) < 1000:
                GLib.idle_add(on_complete_cb, "")
                return

            cmd = [
                str(WHISPER_BIN),
                "-m", str(self.engine.model_path or WHISPER_MODELS[0]),
                "-f", WAV_FILE,
                "--no-timestamps",
                "-nt",
                "-t", "4"
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                lines = []
                for line in res.stdout.splitlines():
                    clean = re.sub(r"\[.*?\]|\(.*?\)", "", line.strip()).strip()
                    if clean:
                        lines.append(clean)
                transcription = " ".join(lines).strip()
                GLib.idle_add(on_complete_cb, transcription)
            except Exception as e:
                print(f"[Voice Error] Whisper failed: {e}", file=sys.stderr)
                GLib.idle_add(on_complete_cb, "")

        threading.Thread(target=worker, daemon=True).start()

    def cancel(self):
        self.cancel_streaming()
        if os.path.exists(WAV_FILE):
            try:
                os.remove(WAV_FILE)
            except OSError:
                pass
