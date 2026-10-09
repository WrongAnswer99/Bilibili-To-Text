"""Validate browser filenames and resolve completed downloads to local videos."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"


def default_download_directory():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            return Path(os.path.expandvars(value)).resolve()
    except OSError:
        return (Path.home() / "Downloads").resolve()


def load_config():
    if not CONFIG.is_file():
        return {}
    data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("config.json must contain an object")
    return data


def download_directory():
    value = load_config().get("download_directory")
    if value and not Path(value).is_absolute():
        raise ValueError("Download directory in config.json must be absolute")
    return Path(value).resolve() if value else default_download_directory()


@dataclass(frozen=True)
class ImportJob:
    bvid: str
    part: int
    files: tuple[str, ...]
    device: str = "gpu"
    chinese_script: str = "simplified"
    language: str = "zh"

    @property
    def name(self):
        return self.bvid + (f"_P{self.part}" if self.part > 1 else "")


def parse_import_uri(uri, *, action="import"):
    if action not in ("import", "open-folder"):
        raise ValueError("Unknown browser action")
    if len(uri) > 8192:
        raise ValueError("Import URI is too long")
    parsed = urlsplit(uri)
    if parsed.scheme != "bilibilitotext" or parsed.netloc != action or parsed.path not in ("", "/") or parsed.fragment:
        raise ValueError("Expected bilibilitotext://import?... URI")
    parameters = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=105)
    if set(parameters) - {"bv", "p", "file", "device", "script", "lang"}:
        raise ValueError("Unknown import parameter")

    def single(name, default=None):
        values = parameters.get(name, [default])
        if len(values) != 1 or values[0] is None or not values[0]:
            raise ValueError(f"Missing or duplicate import parameter: {name}")
        return values[0]

    bvid = single("bv")
    if not re.fullmatch(r"BV[0-9A-Za-z]{10}", bvid):
        raise ValueError("Invalid BV identifier")
    part_text = single("p", "1")
    if not re.fullmatch(r"[1-9][0-9]{0,4}", part_text):
        raise ValueError("Invalid part number")
    part = int(part_text)
    device, script, language = single("device", "gpu"), single("script", "simplified"), single("lang", "zh")
    if device not in ("cpu", "gpu") or script not in ("simplified", "traditional"):
        raise ValueError("Invalid device or Chinese script")
    if not re.fullmatch(r"[a-z]{2,3}|auto", language):
        raise ValueError("Invalid language")
    files = tuple(parameters.get("file", ()))
    if not 1 <= len(files) <= 100 or len(set(files)) != len(files):
        raise ValueError("Import must contain unique downloaded filenames")
    prefix = re.escape(bvid) + (f"_P{part}" if part > 1 else "")
    pattern = prefix + r"_[0-9]{17}(?:\.part[1-9][0-9]*|\.video|\.audio)?(?: \([0-9]+\))?\.(?:mp4|m4s)"
    for filename in files:
        if not re.fullmatch(pattern, filename):
            raise ValueError("Invalid download filename: " + filename)
    stems = {re.split(r"\.(?:part[0-9]+|video|audio)(?: |\.)", name)[0]
             if re.search(r"\.(?:part[0-9]+|video|audio)(?: |\.)", name) else
             re.sub(r"(?: \([0-9]+\))?\.mp4$", "", name) for name in files}
    if len(stems) != 1:
        raise ValueError("Downloaded tracks must belong to the same download")
    job = ImportJob(bvid, part, files, device, script, language)
    if action == "import":
        media_groups(job)
    return job


def media_groups(job):
    video = [name for name in job.files if re.search(r"\.video(?: \([0-9]+\))?\.m4s$", name)]
    audio = [name for name in job.files if re.search(r"\.audio(?: \([0-9]+\))?\.m4s$", name)]
    if video or audio:
        if len(job.files) != 2 or len(video) != 1 or len(audio) != 1:
            raise ValueError("DASH import requires exactly one video track and one audio track")
        return "dash", [video[0], audio[0]]
    parts = [(int(match.group(1)), name) for name in job.files
             if (match := re.search(r"\.part([0-9]+)(?: \([0-9]+\))?\.mp4$", name))]
    if parts:
        parts.sort()
        if len(parts) != len(job.files) or [number for number, _ in parts] != list(range(1, len(parts) + 1)):
            raise ValueError("MP4 parts must be contiguous and start at 1")
        return "parts", [name for _, name in parts]
    if len(job.files) != 1 or not job.files[0].endswith(".mp4"):
        raise ValueError("Expected one MP4 or a complete DASH/MP4-part group")
    return "mp4", list(job.files)


def source_paths(job, directory=None):
    directory = Path(directory or download_directory()).resolve()
    paths = []
    for filename in job.files:
        path = (directory / filename).resolve()
        if path.parent != directory:
            raise ValueError("Downloaded file resolves outside configured download directory")
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Downloaded file not found or empty: {path}. Check browser downloads and config.json.")
        paths.append(path)
    return {name: path for name, path in zip(job.files, paths)}


@contextmanager
def video_job_lock(name, work):
    """One conversion per resolved source path; different videos run independently."""
    import msvcrt
    locks = Path(work) / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / (name + ".lock")).open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("This video is already being converted in another window") from error
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)



def merged_video_path(job, directory=None):
    directory = Path(directory or download_directory()).resolve()
    kind, names = media_groups(job)
    if kind == "mp4":
        return directory / names[0]
    stem = re.split(r"\.(?:part[0-9]+|video|audio)(?: |\.)", names[0])[0]
    return directory / (stem + ".mp4")


def prepare_browser_video(job, ffmpeg=None, *, directory=None):
    """Keep single MP4s in place; merge tracks beside downloads before conversion."""
    target = merged_video_path(job, directory)
    resolved_target = target.resolve()
    if resolved_target.parent != target.parent:
        raise ValueError("Merged video resolves outside configured download directory")
    target = resolved_target
    kind, names = media_groups(job)
    if kind == "mp4":
        return source_paths(job, directory)[names[0]]
    with video_job_lock("merge-" + hashlib.sha256(
            str(target).casefold().encode("utf-8")).hexdigest(), ROOT / ".work"):
        # Repeated protocol requests can reuse our committed merged MP4.
        if target.is_file() and target.stat().st_size:
            return target
        sources = source_paths(job, directory)
        ffmpeg = Path(ffmpeg or ROOT / "ffmpeg.exe")
        if not ffmpeg.is_file():
            raise RuntimeError("Project-local FFmpeg is missing")
        with tempfile.TemporaryDirectory(prefix=".merge-", dir=target.parent) as folder:
            folder = Path(folder)
            temporary = folder / "video.mp4"
            if kind == "dash":
                command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                           "-i", str(sources[names[0]]), "-i", str(sources[names[1]]),
                           "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                           "-movflags", "+faststart", str(temporary)]
            else:
                for index, name in enumerate(names):
                    shutil.copyfile(sources[name], folder / f"part{index}.mp4")
                listing = folder / "parts.txt"
                listing.write_text("".join(f"file 'part{index}.mp4'\n" for index in range(len(names))), encoding="utf-8")
                command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                           "-f", "concat", "-safe", "1", "-i", str(listing), "-c", "copy",
                           "-movflags", "+faststart", str(temporary)]
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode:
                raise RuntimeError("FFmpeg merge failed: " + completed.stderr.strip())
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("Merge did not produce a nonempty MP4")
            os.replace(temporary, target)
        # Only remove the requested component downloads after committing the MP4.
        for path in sources.values():
            try:
                path.unlink()
            except OSError:
                pass  # Keep any file which cannot be removed; the merged MP4 is ready.
        return target


def browser_folder_file(job, directory=None):
    """Select an existing downloaded file, including a previously merged MP4."""
    directory = Path(directory or download_directory()).resolve()
    for filename in job.files:
        candidate = (directory / filename).resolve()
        if candidate.parent != directory:
            raise ValueError("Downloaded file resolves outside configured download directory")
        if candidate.is_file():
            return candidate
    try:
        candidate = merged_video_path(job, directory).resolve()
    except ValueError:
        candidate = None
    if candidate and candidate.parent == directory and candidate.is_file():
        return candidate
    raise RuntimeError("Downloaded file not found; check the browser download directory and config.json")
