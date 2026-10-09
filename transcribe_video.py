"""Transcribe a local video; save UTF-8 TXT/SRT beside the unchanged source."""
import argparse
import ctypes as C
from pathlib import Path
import subprocess
import sys
import os
import hashlib
import tempfile
from time import perf_counter

from import_job import video_job_lock
from whisper_engine import WhisperEngine
from chinese_text import transcript_converter, convert_srt_text


def status(stage, message):
    print(f"STATUS|{stage}|{message}", flush=True)


def default_runtime():
    here = Path(__file__).resolve().parent
    return here / "runtime"


def extract_audio(video, audio, ffmpeg, overwrite=False):
    """Write the complete first audio track as mono 16 kHz PCM WAV."""
    start = perf_counter()
    completed = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
         "-y" if overwrite else "-n", "-i", str(video), "-map", "0:a:0",
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)],
        capture_output=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        raise RuntimeError("FFmpeg extraction failed (check that the video has audio):\n"
                           + completed.stderr.strip())
    return (perf_counter() - start) * 1000


def transcribe_audio(audio, runtime, language="zh", threads=8, device="cpu"):
    """Use this project's own CPU/CUDA Whisper engine."""
    status("init", "Loading the project-local Whisper engine and model...")
    with WhisperEngine(runtime, device=device, language=language, threads=threads) as engine:
        status("transcribe", "Whisper is running on the NVIDIA GPU (CUDA confirmed)"
               if engine.device == "gpu" else "Whisper is running on the CPU")
        result = engine.transcribe_file(
            audio, progress=lambda percent: status("transcribe", f"{engine.device.upper()} progress {percent}%"))
        if result["utf8_replacements"]:
            status("warning", f"Whisper UTF-8 replacements: {result['utf8_replacements']}")
        return result


def srt_timestamp(milliseconds):
    """SRT timestamps use hours:minutes:seconds,milliseconds."""
    milliseconds = int(milliseconds)
    if milliseconds < 0:
        raise ValueError("Subtitle timestamps must not be negative")
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, remainder = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{remainder:03d}"


def segments_to_srt(segments):
    """Use Whisper segment times, without inventing word-level alignment."""
    cues = []
    for segment in segments:
        text = "\n".join(line.strip() for line in segment["text"].splitlines() if line.strip())
        start, end = int(segment["start_ms"]), int(segment["end_ms"])
        if not text or end <= start:
            continue
        cues.append(f"{len(cues) + 1}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}")
    return "\n\n".join(cues) + ("\n\n" if cues else "")



def segments_to_text(segments):
    """Write one nonempty recognition segment per line, without timestamps."""
    lines = [" ".join(part.strip() for part in segment["text"].splitlines() if part.strip())
             for segment in segments]
    return "\n".join(line for line in lines if line) + ("\n" if any(lines) else "")


def srt_to_text(content):
    """Reformat cached transcripts using subtitle cue boundaries, without rerunning ASR."""
    segments = []
    for block in content.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit() or "-->" not in lines[1]:
            raise ValueError("Invalid cached SRT cue; use --overwrite to regenerate subtitles")
        segments.append({"text": "\n".join(lines[2:])})
    return segments_to_text(segments)


def save_text_outputs(text_path, subtitle_path, text_content, subtitle_content):
    """Prepare both files before replacing outputs; temporary files share their volume."""
    with tempfile.TemporaryDirectory(prefix=".save-", dir=text_path.parent) as folder:
        temporary_text = Path(folder) / "transcript.txt"
        temporary_subtitles = Path(folder) / "subtitles.srt"
        temporary_text.write_text(text_content, encoding="utf-8")
        temporary_subtitles.write_text(subtitle_content, encoding="utf-8")
        os.replace(temporary_text, text_path)
        os.replace(temporary_subtitles, subtitle_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Existing local video path")
    parser.add_argument("--language", "--lang", default="zh", help="zh, en, auto, etc. (default: zh)")
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu", help="Default: gpu")
    parser.add_argument("--chinese-script", choices=("simplified", "traditional"), default="simplified", help="Default: simplified")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--runtime-dir", type=Path, default=default_runtime(), help="Project-local Whisper runtime")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate TXT/SRT using the selected recognition parameters")
    args = parser.parse_args(argv)
    if not 0 <= args.threads <= 256:
        parser.error("--threads must be between 0 and 256")
    if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8:
        parser.error("This tool requires Windows and 64-bit Python")
    project = Path(__file__).resolve().parent
    work = project / ".work"
    runtime = args.runtime_dir.resolve()
    ffmpeg = project / "ffmpeg.exe"
    try:
        source = args.source.strip().strip('"')
        if source.lower().startswith(("http://", "https://", "bilibilitotext:")):
            raise ValueError("Select an existing local video file; browser jobs use launch_local.py.")
        video = Path(source).resolve()
        if not video.is_file() or video.suffix.lower() not in (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv", ".ts"):
            raise RuntimeError("Local input must be an existing supported video file")
        name = video.stem
        device, language, script = args.device, args.language, args.chinese_script
        converter = transcript_converter(language, script)
        text, subtitles = video.with_suffix(".txt"), video.with_suffix(".srt")
        lock = hashlib.sha256(str(video).casefold().encode("utf-8")).hexdigest()
        with video_job_lock(lock, work):
            if video.is_file() and text.is_file() and subtitles.is_file() and not args.overwrite:
                original_text = text.read_text(encoding="utf-8")
                original_subtitles = subtitles.read_text(encoding="utf-8")
                converted_subtitles = convert_srt_text(original_subtitles, converter)
                converted_text = srt_to_text(converted_subtitles)
                if converted_text != original_text or converted_subtitles != original_subtitles:
                    status("save", "Updating text layout and subtitle output...")
                    save_text_outputs(text, subtitles, converted_text, converted_subtitles)
                status("done", f"Existing result: {text}, {subtitles}")
                return 0
            for path in (ffmpeg, project / "models/whisper/ggml-small-q5_1.bin",
                         project / "models/whisper/ggml-silero-v6.2.0.bin", runtime / "whisper_bridge.dll"):
                if not path.is_file():
                    raise RuntimeError(f"Required project file not found: {path}")
            work.mkdir(parents=True, exist_ok=True)
            start = perf_counter()
            with tempfile.TemporaryDirectory(prefix=f"{name}-", dir=work) as folder:
                audio = Path(folder) / "audio.wav"
                status("extract", "Extracting the complete audio...")
                extract_ms = extract_audio(video, audio, ffmpeg)
                result = transcribe_audio(audio, runtime, language, args.threads, device)
                converter = transcript_converter(result["language"], script)
                if result["language"] == "zh":
                    status("convert", f"Converting Chinese output: {script}")
                converted_text = converter.convert(segments_to_text(result["segments"]))
                converted_subtitles = convert_srt_text(segments_to_srt(result["segments"]), converter)
                status("save", f"Saving UTF-8 text and SRT subtitles (language={result['language']})...")
                save_text_outputs(text, subtitles, converted_text, converted_subtitles)
            status("done", f"Saved: {text}, {subtitles}; total {(perf_counter()-start):.1f} s; "
                   f"extract {extract_ms:.0f} ms; transcription {result['transcribe_ms']:.0f} ms")
            return 0
    except (OSError, RuntimeError, ValueError, AttributeError) as error:
        status("error", str(error).replace("\n", " "))
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
