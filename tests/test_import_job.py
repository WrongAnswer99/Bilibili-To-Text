import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch
from import_job import (parse_import_uri, media_groups, prepare_browser_video,
                        source_paths, video_job_lock, browser_folder_file)
from launch_local import launch_command

BV = "BV1ewwxesEu4"
STEM = BV + "_20261009083024124"


def uri(files=None, action="import", **options):
    params = [("bv", BV), *options.items()]
    params += [("file", name) for name in (files or [STEM + ".mp4"])]
    return "bilibilitotext://" + action + "?" + urlencode(params)


class ImportTests(unittest.TestCase):
    def test_options_and_locked_launch_are_literal_local_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            video = folder / (STEM + ".mp4")
            video.write_bytes(b"fixture")
            value = uri(device="cpu", script="traditional", lang="zh")
            job = parse_import_uri(value)
            self.assertEqual((job.bvid, job.device, job.chinese_script), (BV, "cpu", "traditional"))
            with patch("import_job.download_directory", return_value=folder):
                command = launch_command(value)
                normalized = launch_command(value.replace("//import?", "//import/?"))
            self.assertEqual(command, normalized)
            self.assertEqual(command[command.index("-Source") + 1], str(video))
            self.assertIn("-LockedSource", command)
            self.assertIn("-AutoStart", command)
            self.assertEqual(command[-6:], ["-Device", "cpu", "-ChineseScript", "traditional", "-Language", "zh"])
            self.assertNotIn("cmd.exe", command)

    def test_reject_invalid_jobs(self):
        values = [
            "https://example.com", uri(["../test.mp4"]), uri([r"C:\test.mp4"]),
            uri(device="cuda"), uri(script="bad"), uri(command="calc"),
            uri() + "&bv=" + BV, uri([STEM + ".video.m4s"]),
            uri([STEM + ".mp4", STEM + ".audio.m4s"]),
            uri([STEM + ".part2.mp4"]), uri([STEM + ".mp4", STEM + ".mp4"]),
            uri([STEM + ".video.m4s", BV + "_20261009083024125.audio.m4s"]),
            uri() + "#fragment", uri() + "&file=", uri(action="delete"),
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_import_uri(value)

    def test_track_and_part_order(self):
        dash = parse_import_uri(uri([STEM + ".audio.m4s", STEM + ".video.m4s"]))
        self.assertEqual(media_groups(dash), ("dash", [STEM + ".video.m4s", STEM + ".audio.m4s"]))
        parts = parse_import_uri(uri([STEM + ".part2.mp4", STEM + ".part1.mp4"]))
        self.assertEqual(media_groups(parts)[1], [STEM + ".part1.mp4", STEM + ".part2.mp4"])
        part = parse_import_uri(uri([BV + "_P2_20261009083024124.mp4"], p="2"))
        self.assertEqual(part.name, BV + "_P2")

    def test_single_mp4_stays_in_original_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            requested = folder / (STEM + ".mp4")
            requested.write_bytes(b"mp4 fixture")
            other = folder / "keep.txt"
            other.write_text("keep", encoding="utf-8")
            with patch("import_job.subprocess.run", side_effect=AssertionError("MP4 needs no FFmpeg merge")):
                target = prepare_browser_video(parse_import_uri(uri()), directory=folder)
            self.assertEqual(target, requested)
            self.assertEqual(requested.read_bytes(), b"mp4 fixture")
            self.assertEqual(set(p.name for p in folder.iterdir()), {requested.name, "keep.txt"})

    def test_failed_merge_preserves_downloads_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            filenames = [STEM + ".video.m4s", STEM + ".audio.m4s"]
            for name in filenames:
                (folder / name).write_bytes(b"track fixture")
            job = parse_import_uri(uri(filenames))
            completed = type("Completed", (), {"returncode": 1, "stderr": "bad media"})()
            with patch("import_job.subprocess.run", return_value=completed), self.assertRaises(RuntimeError):
                prepare_browser_video(job, directory=folder)
            self.assertEqual(set(p.name for p in folder.iterdir()), set(filenames))
            # A committed merge can be reopened even after component files are removed.
            merged = folder / (STEM + ".mp4")
            merged.write_bytes(b"merged video")
            for name in filenames:
                (folder / name).unlink()
            self.assertEqual(prepare_browser_video(job, directory=folder), merged)
            self.assertEqual(browser_folder_file(job, folder), merged)

    def test_folder_action_never_converts_and_accepts_partial_download(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            file = folder / (STEM + ".video.m4s")
            file.write_bytes(b"fixture")
            value = uri([file.name], action="open-folder")
            with patch("import_job.download_directory", return_value=folder), \
                    patch("launch_local.prepare_browser_video", side_effect=AssertionError("No conversion")):
                self.assertEqual(launch_command(value), ["explorer.exe", "/select," + str(file)])
            for invalid in (uri(["../x.mp4"], action="open-folder"), uri(action="execute")):
                with self.assertRaises(ValueError):
                    launch_command(invalid)

    def test_missing_file_and_duplicate_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                source_paths(parse_import_uri(uri()), folder)
            with video_job_lock(BV, folder):
                with self.assertRaises(RuntimeError):
                    with video_job_lock(BV, folder):
                        self.fail("duplicate lock should fail")
                with video_job_lock(BV + "_different_file", folder):
                    pass
            with video_job_lock(BV, folder):
                pass


if __name__ == "__main__":
    unittest.main()
