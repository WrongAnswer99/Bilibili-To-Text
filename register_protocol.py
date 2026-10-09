"""Register bilibilitotext:// for the current Windows user."""
import argparse
import json
from pathlib import Path
import sys
import winreg
from import_job import ROOT, CONFIG, default_download_directory, load_config

KEY = r"Software\Classes\bilibilitotext"


def protocol_command():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise RuntimeError("pythonw.exe is missing beside the current Python")
    return f'"{pythonw}" "{ROOT / "launch_local.py"}" --uri "%1"'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-directory", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--unregister", action="store_true")
    parser.add_argument("--force", action="store_true", help="Replace an existing registration after moving the project")
    args = parser.parse_args(argv)
    existing = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY + r"\shell\open\command") as key:
            existing = winreg.QueryValue(key, None)
    except FileNotFoundError:
        pass
    if args.check:
        expected = protocol_command()
        if existing != expected:
            raise RuntimeError("Protocol is not registered for this project")
        print("PASS: bilibilitotext:// registered for " + str(ROOT))
        return 0
    if args.unregister:
        for suffix in (r"\shell\open\command", r"\shell\open", r"\shell", ""):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY + suffix)
            except FileNotFoundError:
                pass
        print("Protocol unregistered")
        return 0
    expected = protocol_command()
    if existing and existing != expected and not args.force:
        raise RuntimeError("bilibilitotext:// is registered to another location; use --force to update it after moving the project")
    directory = Path(args.download_directory or load_config().get("download_directory")
                     or default_download_directory()).resolve()
    if not directory.is_dir():
        raise RuntimeError("Download directory does not exist: " + str(directory))
    config = {"download_directory": str(directory), "python": str(Path(sys.executable).with_name("python.exe"))}
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:BilibiliToText")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY + r"\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, expected)
    print("Registered bilibilitotext:// for current user")
    print("Download directory: " + str(directory))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
