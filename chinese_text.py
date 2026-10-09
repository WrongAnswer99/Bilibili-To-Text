"""Offline Chinese script conversion for application text/subtitle outputs."""
from pathlib import Path
import re
import sys

def chinese_converter(script="simplified"):
    configs = {"simplified": "t2s.json", "traditional": "s2t.json"}
    if script not in configs:
        raise ValueError("Chinese script must be simplified or traditional")
    vendor = Path(__file__).resolve().parent / ".vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    try:
        from opencc import OpenCC
    except ImportError as error:
        raise RuntimeError("OpenCC unavailable; run: python -m pip install --target .vendor OpenCC==1.4.2") from error
    return OpenCC(configs[script])

def convert_srt_text(content, converter):
    """Convert cue bodies while preserving numbering, timing and separators."""
    blocks = re.split(r"(\n\n+)", content)
    for i in range(0, len(blocks), 2):
        if not blocks[i].strip():
            continue
        lines = blocks[i].splitlines(keepends=True)
        if len(lines) < 3 or not lines[0].strip().isdigit() or "-->" not in lines[1]:
            raise ValueError("Invalid cached SRT cue; use --overwrite to regenerate subtitles")
        blocks[i] = "".join(lines[:2]) + converter.convert("".join(lines[2:]))
    return "".join(blocks)


class UnchangedText:
    def convert(self, content):
        return content


def transcript_converter(language, script="simplified"):
    """Only convert Chinese orthography; preserve Japanese kanji and other languages."""
    return chinese_converter(script) if language == "zh" else UnchangedText()
