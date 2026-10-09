import unittest
from transcribe_video import segments_to_srt, srt_timestamp

class SubtitleTests(unittest.TestCase):
    def test_clock_boundaries(self):
        cases = {0: "00:00:00,000", 999: "00:00:00,999", 1000: "00:00:01,000",
                 59999: "00:00:59,999", 60000: "00:01:00,000", 3600000: "01:00:00,000",
                 3661234: "01:01:01,234"}
        for value, expected in cases.items():
            self.assertEqual(srt_timestamp(value), expected)
        with self.assertRaises(ValueError):
            srt_timestamp(-1)

    def test_utf8_cues_and_empty_segments(self):
        segments = [
            {"start_ms": 0, "end_ms": 20, "text": " "},
            {"start_ms": 1230, "end_ms": 4560, "text": " 你好。\r\n\r\n 第二行。 "},
            {"start_ms": 4560, "end_ms": 4560, "text": "zero duration"},
            {"start_ms": 3600000, "end_ms": 3601500, "text": "🙂"},
        ]
        expected = "1\n00:00:01,230 --> 00:00:04,560\n你好。\n第二行。\n\n2\n01:00:00,000 --> 01:00:01,500\n🙂\n\n"
        self.assertEqual(segments_to_srt(segments), expected)
        self.assertEqual(segments_to_srt([]), "")

if __name__ == "__main__":
    unittest.main()
