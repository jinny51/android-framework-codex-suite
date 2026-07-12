#!/usr/bin/env python3
"""Extract frames from a screen recording with ffmpeg."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_framework_ops.artifact_paths import require_safe_artifact_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="Input video path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--every", type=float, default=0.25, help="Seconds between frames")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in seconds")
    parser.add_argument("--duration", type=float, help="Duration to extract in seconds")
    parser.add_argument("--prefix", default="frame", help="Output filename prefix")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = require_safe_artifact_path(Path(args.out), purpose="video frame output")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found in PATH.")
        return 2

    video = Path(args.video)
    if not video.exists():
        print(f"Video does not exist: {video}")
        return 2

    out.mkdir(parents=True, exist_ok=True)
    output_pattern = out / f"{args.prefix}_%05d.png"
    fps = 1.0 / args.every if args.every > 0 else 4.0

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(args.start),
        "-i",
        str(video),
    ]
    if args.duration is not None:
        cmd.extend(["-t", str(args.duration)])
    cmd.extend(["-vf", f"fps={fps}", str(output_pattern)])

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        return result.returncode

    count = len(list(out.glob(f"{args.prefix}_*.png")))
    print(f"Extracted {count} frame(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
