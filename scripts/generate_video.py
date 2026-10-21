"""Generate an MP4 from the terminal using the installed FreeVideo runtime."""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Text prompt, including optional sound directions")
    source.add_argument("--prompt-file", type=Path, help="UTF-8 prompt file")
    parser.add_argument("--out", type=Path, default=Path("outputs/video.mp4"))
    parser.add_argument("--seconds", type=float, default=2)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=448)
    parser.add_argument("--vram-gib", type=float, default=24)
    parser.add_argument("--ram-gib", type=float, default=64)
    parser.add_argument("--seed", type=int, default=2026090901)
    args = parser.parse_args()
    if args.seconds <= 0 or min(args.width, args.height, args.vram_gib, args.ram_gib) <= 0:
        parser.error("duration, dimensions and resource budgets must be positive")
    if args.prompt is not None and not args.prompt.strip():
        parser.error("--prompt must not be blank")
    if args.prompt_file is not None and not args.prompt_file.is_file():
        parser.error("--prompt-file must name an existing file")

    # The managed CLI supplies installed model paths and selects its CUDA Python.
    # No ComfyUI HTTP server or browser is needed; its encoder library is reused.
    with tempfile.TemporaryDirectory(prefix="freevideo-prompt-") as folder:
        prompt = args.prompt_file
        if prompt is None:
            prompt = Path(folder) / "prompt.txt"
            prompt.write_text(args.prompt, encoding="utf-8")
        command = [sys.executable, "-m", "freevideo_engine.managed", "generate",
                   "--prompt-file", str(prompt), "--out", str(args.out),
                   "--seconds", str(args.seconds), "--width", str(args.width),
                   "--height", str(args.height), "--vram-gib", str(args.vram_gib),
                   "--ram-gib", str(args.ram_gib), "--seed", str(args.seed)]
        try:
            return subprocess.run(command, check=False).returncode
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
