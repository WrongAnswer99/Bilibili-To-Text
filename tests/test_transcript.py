import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from transcribe_video import main, segments_to_text, srt_to_text


class TranscriptLayoutTests(unittest.TestCase):
    def test_each_segment_is_one_line_across_languages(self):
        segments = [{"text": " 你好。\r\n第二句。 "}, {"text": " "},
                    {"text": "Hello world."}, {"text": "日本語。"}, {"text": "Привет."}]
        self.assertEqual(segments_to_text(segments),
                         "你好。 第二句。\nHello world.\n日本語。\nПривет.\n")
        self.assertEqual(segments_to_text([]), "")

    def test_subtitles_supply_lines_without_timestamps(self):
        subtitles = ("1\n00:00:00,000 --> 00:00:01,000\n第一段。\n\n"
                     "2\n00:00:02,000 --> 00:00:04,000\nSecond\nline.\n\n")
        self.assertEqual(srt_to_text(subtitles), "第一段。\nSecond line.\n")
        self.assertEqual(srt_to_text(""), "")
        with self.assertRaises(ValueError):
            srt_to_text("bad subtitles")

    def test_cached_old_layout_is_updated_without_recognition(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "cached.mp4"
            text = video.with_suffix(".txt")
            subtitles = video.with_suffix(".srt")
            video.write_bytes(b"unchanged video")
            text.write_text("Hello.First line.Second line.", encoding="utf-8")
            original_srt = ("1\n00:00:00,000 --> 00:00:01,000\nHello.\n\n"
                            "2\n00:00:01,000 --> 00:00:02,000\nFirst line.\n\n"
                            "3\n00:00:02,000 --> 00:00:03,000\nSecond line.\n\n")
            subtitles.write_text(original_srt, encoding="utf-8")
            with patch("transcribe_video.transcribe_audio",
                       side_effect=AssertionError("Cached layout update must not run ASR")):
                self.assertEqual(main([str(video), "--lang", "en"]), 0)
                self.assertEqual(main([str(video), "--lang", "en"]), 0)
            self.assertEqual(text.read_text(encoding="utf-8"),
                             "Hello.\nFirst line.\nSecond line.\n")
            self.assertEqual(subtitles.read_text(encoding="utf-8"), original_srt)
            self.assertEqual(video.read_bytes(), b"unchanged video")
            self.assertEqual(len(list(Path(folder).iterdir())), 3)


if __name__ == "__main__":
    unittest.main()
