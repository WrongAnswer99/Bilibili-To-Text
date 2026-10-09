import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chinese_text import chinese_converter, convert_srt_text, transcript_converter
from transcribe_video import main

class ChineseScriptTests(unittest.TestCase):
    def test_phrases_and_non_chinese(self):
        simplified = "汉字转换，头发和发展。English 123 � 🙂"
        traditional = "漢字轉換，頭髮和發展。English 123 � 🙂"
        self.assertEqual(chinese_converter("traditional").convert(simplified), traditional)
        self.assertEqual(chinese_converter("simplified").convert(traditional), simplified)

    def test_subtitle_headers_unchanged(self):
        original = "1\n00:00:01,230 --> 00:00:04,560\n漢字轉換\n\n2\n01:00:00,000 --> 01:00:01,500\n頭髮和發展\nEnglish 123 � 🙂\n\n"
        expected = "1\n00:00:01,230 --> 00:00:04,560\n汉字转换\n\n2\n01:00:00,000 --> 01:00:01,500\n头发和发展\nEnglish 123 � 🙂\n\n"
        self.assertEqual(convert_srt_text(original, chinese_converter("simplified")), expected)
        self.assertEqual(convert_srt_text("", chinese_converter("simplified")), "")
        with self.assertRaises(ValueError):
            convert_srt_text("bad subtitles", chinese_converter())

    def test_non_chinese_text_is_never_rewritten_by_opencc(self):
        for language, text in (("ja", "東京の図書館。気持ちと芸術。"),
                               ("en", "This is Skyblock."), ("ru", "Это пример.")):
            with self.subTest(language=language):
                converter = transcript_converter(language, "simplified")
                self.assertEqual(converter.convert(text), text)
                cue = "1\n00:00:00,000 --> 00:00:02,000\n" + text + "\n\n"
                self.assertEqual(convert_srt_text(cue, converter), cue)

    def test_cached_results_switch_without_asr(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            video = output / "cached.mp4"
            text = output / "cached.txt"
            srt = output / "cached.srt"
            video.write_bytes(b"existing video")
            text.write_text("頭髮和發展", encoding="utf-8")
            srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n頭髮和發展\n\n", encoding="utf-8")
            with patch("transcribe_video.transcribe_audio", side_effect=AssertionError("ASR must not run")):
                self.assertEqual(main([str(video)]), 0)
                self.assertEqual(text.read_text(encoding="utf-8"), "头发和发展\n")
                self.assertEqual(main([str(video),
                                      "--chinese-script", "traditional"]), 0)
                self.assertEqual(text.read_text(encoding="utf-8"), "頭髮和發展\n")
            self.assertIn("00:00:01,000 --> 00:00:02,000", srt.read_text(encoding="utf-8"))
            self.assertEqual(video.read_bytes(), b"existing video")
            self.assertEqual(len(list(output.iterdir())), 3)

if __name__ == "__main__":
    unittest.main()
