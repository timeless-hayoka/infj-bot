"""Tests for the voice module (mocked, since mic/speakers may not be available)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestVoiceHelpers(unittest.TestCase):
    @patch("voice._get_whisper")
    def test_transcribe(self, mock_get_whisper):
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_get_whisper.return_value = mock_model

        from voice import transcribe
        # Use a path inside the project (which is under home)
        tmp_path = Path(__file__).resolve().parent.parent / "test_tmp.wav"
        import wave
        with wave.open(str(tmp_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00" * 32000)
        try:
            result = transcribe(str(tmp_path))
            self.assertIn("hello world", result)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @patch("voice._get_piper")
    def test_synthesize(self, mock_get_piper):
        mock_voice = MagicMock()
        # Mock synthesize_wav to write valid WAV data
        def fake_synthesize(text, wav_file):
            import wave
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00" * 44100)
        mock_voice.synthesize_wav = fake_synthesize
        mock_get_piper.return_value = mock_voice

        from voice import synthesize
        result = synthesize("hello")
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    def test_record_audio_mocked(self):
        with patch("sounddevice.rec") as mock_rec, patch("sounddevice.wait") as mock_wait:
            import numpy as np
            mock_rec.return_value = np.zeros(16000, dtype="int16")
            from voice import record_audio
            wav = record_audio(duration=1.0)
            self.assertIsInstance(wav, bytes)
            self.assertTrue(len(wav) > 44)  # WAV header is 44 bytes


if __name__ == "__main__":
    unittest.main()
