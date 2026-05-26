"""Voice layer: STT via faster-whisper, TTS via piper, recording via sounddevice."""

import io
import wave
from pathlib import Path
from typing import Optional

from infj_bot.core.config import PROJECT_ROOT

VOICE_DIR = PROJECT_ROOT / "voices"
DEFAULT_VOICE = VOICE_DIR / "en_US-lessac-medium.onnx"
MAX_AUDIO_BYTES = 50 * 1024 * 1024

# Lazy-loaded models
_whisper_model = None
_piper_voice = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def _get_piper():
    global _piper_voice
    if _piper_voice is None:
        from piper import PiperVoice

        voice_path = str(DEFAULT_VOICE) if DEFAULT_VOICE.exists() else None
        if voice_path is None:
            raise RuntimeError(
                f"No Piper voice found at {DEFAULT_VOICE}. Run: mkdir -p voices && curl ..."
            )
        _piper_voice = PiperVoice.load(voice_path)
    return _piper_voice


def _resolve_audio_path(path: str, must_exist: bool = True) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target = target.resolve()
    try:
        target.relative_to(Path.home().resolve())
    except ValueError:
        raise PermissionError(
            f"Audio path {path} is outside the allowed home directory."
        )
    if must_exist:
        if not target.exists():
            raise FileNotFoundError(path)
        if target.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError(
                f"Audio file is too large; max is {MAX_AUDIO_BYTES} bytes."
            )
    return target


def record_audio(
    duration: float = 5.0, sample_rate: int = 16000, channels: int = 1
) -> bytes:
    """Record audio from the microphone and return WAV bytes."""
    import sounddevice as sd

    frames = int(duration * sample_rate)
    recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="int16")
    sd.wait()

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(recording.tobytes())
    return buffer.getvalue()


def record_to_file(path: str, duration: float = 5.0):
    """Record audio from the microphone to a WAV file."""
    target = _resolve_audio_path(path, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    wav_bytes = record_audio(duration=duration)
    target.write_bytes(wav_bytes)


def transcribe(audio_path: str) -> str:
    """Transcribe an audio file to text."""
    resolved_path = _resolve_audio_path(audio_path)
    model = _get_whisper()
    segments, _info = model.transcribe(str(resolved_path), beam_size=5)
    return " ".join(segment.text for segment in segments).strip()


def synthesize(text: str) -> bytes:
    """Synthesize text to WAV bytes."""
    voice = _get_piper()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        voice.synthesize_wav(text, wav)
    return buffer.getvalue()


def synthesize_to_file(text: str, path: str):
    """Synthesize text to a WAV file."""
    out_path = _resolve_audio_path(path, must_exist=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = _get_piper()
    with wave.open(str(out_path), "wb") as wav:
        voice.synthesize_wav(text, wav)


def listen_and_transcribe(
    audio_path: str, wake_word: str = "companion"
) -> Optional[str]:
    """Transcribe audio and return text only if wake word is present."""
    text = transcribe(audio_path)
    if wake_word.lower() in text.lower():
        lowered = text.lower()
        idx = lowered.find(wake_word.lower())
        if idx >= 0:
            text = text[idx + len(wake_word) :].strip()
        return text
    return None


def speak(text: str, output_path: Optional[str] = None) -> Optional[bytes]:
    """Speak text. Returns WAV bytes if no path given, else writes to path."""
    if output_path:
        synthesize_to_file(text, output_path)
        return None
    return synthesize(text)


def play_audio(wav_bytes: bytes):
    """Play WAV bytes through the default audio output."""
    import sounddevice as sd
    import soundfile as sf

    buffer = io.BytesIO(wav_bytes)
    data, sr = sf.read(buffer, dtype="int16")
    sd.play(data, sr)
    sd.wait()


if __name__ == "__main__":
    print("Voice module ready.")
    print("Whisper model: base (CPU, int8)")
    print(f"Piper voice: {DEFAULT_VOICE}")
