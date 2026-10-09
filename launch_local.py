"""Native browser bridge: reveal a download or open a locked local-video window."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from import_job import ROOT, load_config, parse_import_uri, prepare_browser_video, browser_folder_file


def launch_command(uri):
    action = urlsplit(uri).netloc
    job = parse_import_uri(uri, action=action)
    if action == "open-folder":
        file = browser_folder_file(job)
        return ["explorer.exe", "/select," + str(file)]
    source = prepare_browser_video(job)
    config = load_config()
    python = Path(config.get("python", sys.executable)).with_name("python.exe")
    if not python.is_file():
        raise RuntimeError("Configured Python executable is missing; register the protocol again")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-STA",
            "-WindowStyle", "Hidden", "-File", str(ROOT / "start.ps1"),
            "-Source", str(source), "-LockedSource", "-AutoStart",
            "-Device", job.device, "-ChineseScript", job.chinese_script, "-Language", job.language]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Validate and show arguments; never merge or launch")
    args = parser.parse_args()
    try:
        if args.dry_run:
            job = parse_import_uri(args.uri, action=urlsplit(args.uri).netloc)
            print(json.dumps({"action": urlsplit(args.uri).netloc, "files": job.files,
                              "device": job.device, "script": job.chinese_script}, ensure_ascii=False))
        else:
            command = launch_command(args.uri)
            subprocess.Popen(command, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        if args.dry_run:
            print(str(error), file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None, str(error), "BilibiliToText", 0x10)
        return 1


if __name__ == "__main__":
    sys.exit(main())
