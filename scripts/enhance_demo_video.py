"""Add neural voiceover, readable chapter captions, and gentler pacing.

Run from the repository root::

    python scripts/enhance_demo_video.py

The input is the real browser recording made by record_demo.py. Voice clips are
cached in demo_assets/open_file_voiceover_clips so later edits do not need to regenerate
them. No API key is used.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

try:
    import edge_tts
except ImportError as exc:
    raise SystemExit("Install voice synthesis with: python -m pip install edge-tts") from exc


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "demo_assets"
SOURCE = ASSETS / "pfa2026_grounded_demo.mp4"
OUTPUT = ASSETS / "pfa2026_grounded_demo_narrated.mp4"
CLIPS = ASSETS / "redesigned_voiceover_clips"
ASS_FILE = ASSETS / "pfa2026_grounded_demo_narration.ass"
SRT_FILE = ASSETS / "pfa2026_grounded_demo_narration.srt"
VOICE = "en-US-JennyNeural"
RATE = "+6%"
SPEED = 1.1
INTRO_HOLD = 1.0
OUTRO_HOLD = 4.0


@dataclass(frozen=True)
class Cue:
    start: float
    title: str
    caption: str
    narration: str


CUES: list[Cue] = []


def load_cues() -> list[Cue]:
    timings = json.loads(SOURCE.with_suffix(".timings.json").read_text(encoding="utf-8"))
    sections = [
        ("intro", "01  WORKSPACE", "Four uploads and four redesigned exports",
         "Explore four uploads and four redesigned files."),
        ("upload", "02  UPLOAD", "PDF + Word + CSV + TXT",
         "PDF, Word, CSV, and text enter the upload queue."),
        ("answer", "03  CHAT ANSWER", "Three facts in one answer",
         "The answer shows Casablanca, Amal Benali, and M L."),
        ("refusal", "04  NO DATA", "Lunar geology request declined",
         "The chatbot declines the lunar geology request."),
        ("pdf", "05  ML PDF REQUEST", "Generate and preview the PDF",
         "Create and preview an M L PDF."),
        ("pdf_open", "06  OPEN PDF", "ML brief with clear sections",
         "Open the M L brief to review its highlights, source index, and detailed evidence."),
        ("docx_open", "07  OPEN WORD", "36 items grouped by document",
         "The Word report organizes thirty six evidence items by document."),
        ("txt_open", "08  OPEN TXT", "Readable plain text sections",
         "The text export keeps the same sections in a readable plain text layout."),
        ("csv_open", "09  OPEN CSV", "Structured evidence table",
         "The C S V opens as a table with document, file type, and evidence columns."),
        ("end", "10  FOUR FILES", "PDF · Word · TXT · CSV",
         "All four redesigned files were opened and downloaded."),
    ]
    return [
        Cue(INTRO_HOLD + SPEED * float(timings[key]) + 0.35, title, caption, narration)
        for key, title, caption, narration in sections
    ]


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required (install ffmpeg).")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


async def synthesize() -> list[Path]:
    CLIPS.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, cue in enumerate(CUES, start=1):
        path = CLIPS / f"voice_{index:02}.mp3"
        if not path.exists() or path.stat().st_size == 0:
            print(f"Generating voice {index}/{len(CUES)}: {cue.title}")
            await edge_tts.Communicate(cue.narration, VOICE, rate=RATE).save(str(path))
        paths.append(path)
    return paths


def ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remaining = divmod(centiseconds, 360_000)
    minutes, remaining = divmod(remaining, 6_000)
    whole_seconds, hundredths = divmod(remaining, 100)
    return f"{hours}:{minutes:02}:{whole_seconds:02}.{hundredths:02}"


def srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remaining = divmod(milliseconds, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    whole_seconds, fraction = divmod(remaining, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{fraction:03}"


def make_captions(total_duration: float, voice_durations: list[float]) -> None:
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Label,Segoe UI,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,2,80,80,34,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    srt_lines: list[str] = []
    for index, (cue, voice_duration) in enumerate(zip(CUES, voice_durations, strict=True), start=1):
        end = min(total_duration - 0.1, cue.start + voice_duration + 0.35)
        if index < len(CUES):
            end = min(end, CUES[index].start - 0.05)
        label = f"{cue.title}   •   {cue.caption}".replace("\n", " ")
        ass_lines.append(
            f"Dialogue: 0,{ass_time(cue.start)},{ass_time(end)},Label,,0,0,0,,{label}"
        )
        srt_lines.extend([str(index), f"{srt_time(cue.start)} --> {srt_time(end)}", cue.narration, ""])
    ASS_FILE.write_text("\n".join(ass_lines) + "\n", encoding="utf-8-sig")
    SRT_FILE.write_text("\n".join(srt_lines), encoding="utf-8")


def render(clips: list[Path], total_duration: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to render the narrated video.")
    input_args: list[str] = ["-i", str(SOURCE)]
    for clip in clips:
        input_args.extend(["-i", str(clip)])
    input_args.extend(["-i", str(SRT_FILE)])

    video_filter = (
        f"[0:v]setpts={SPEED}*(PTS-STARTPTS),fps=30,"
        f"tpad=start_mode=clone:start_duration={INTRO_HOLD}:stop_mode=clone:stop_duration={OUTRO_HOLD},"
        "scale=1720:968:flags=lanczos,pad=1920:1080:100:0:color=0x07182b,"
        "ass=demo_assets/pfa2026_grounded_demo_narration.ass[v]"
    )
    audio_parts: list[str] = []
    mixed_inputs: list[str] = []
    for index, cue in enumerate(CUES, start=1):
        delay_ms = round(cue.start * 1000)
        audio_parts.append(f"[{index}:a]aresample=48000,adelay={delay_ms}:all=1[a{index}]")
        mixed_inputs.append(f"[a{index}]")
    audio_filter = (
        "".join(mixed_inputs) + f"amix=inputs={len(CUES)}:duration=longest:normalize=0,"
        f"apad,atrim=0:{total_duration:.3f},loudnorm=I=-16:TP=-1.5:LRA=11[a]"
    )
    filter_complex = ";".join([video_filter, *audio_parts, audio_filter])
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *input_args,
        "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
        "-map", f"{len(clips) + 1}:s:0",
        "-t", f"{total_duration:.3f}", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-disposition:s:0", "0",
        "-movflags", "+faststart", str(OUTPUT),
    ]
    print("Rendering narrated video...")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    global CUES
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Record the browser demo first: {SOURCE}")
    source_duration = probe_duration(SOURCE)
    CUES = load_cues()
    total_duration = INTRO_HOLD + SPEED * source_duration + OUTRO_HOLD
    clips = asyncio.run(synthesize())
    durations = [probe_duration(clip) for clip in clips]
    for index, (cue, duration) in enumerate(zip(CUES[:-1], durations[:-1], strict=True)):
        available = CUES[index + 1].start - cue.start
        if duration > available - 0.2:
            raise RuntimeError(
                f"Voice clip {index + 1} lasts {duration:.1f}s but has only {available:.1f}s before the next cue."
            )
    if CUES[-1].start + durations[-1] > total_duration - 0.2:
        raise RuntimeError("Final voice clip exceeds video duration.")
    make_captions(total_duration, durations)
    render(clips, total_duration)
    print(f"Narrated video: {OUTPUT}")
    print(f"Captions: {SRT_FILE}")


if __name__ == "__main__":
    main()
