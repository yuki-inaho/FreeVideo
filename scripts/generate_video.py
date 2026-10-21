"""Generate an MP4 from the terminal using the installed FreeVideo runtime."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Text prompt, including optional sound directions")
    source.add_argument("--prompt-file", type=Path, help="UTF-8 prompt file")
    source.add_argument("--prompt-stdin", action="store_true", help="Read the prompt from standard input")
    parser.add_argument("--first-frame", type=Path, help="Starting image")
    parser.add_argument("--last-frame", type=Path, help="Ending image")
    parser.add_argument("--reference-image", type=Path, nargs="+", action="extend", default=[],
                        help="Reference images (repeatable; at most 32 total; cannot mix with first/last)")
    parser.add_argument("--reference-video", type=Path, nargs="+", action="extend", default=[],
                        help="Reference videos (repeatable; images + videos at most 32 total)")
    parser.add_argument("--reference-video-sound", action="store_true",
                        help="Also use reference videos' audio (default: visual guidance only)")
    media_source = parser.add_mutually_exclusive_group()
    media_source.add_argument("--media", type=Path, help="Existing version-1 media JSON file")
    media_source.add_argument("--media-json", help="Inline version-1 JSON; relative paths use the current directory")
    parser.add_argument("--out", type=Path, default=Path("outputs/video.mp4"))
    parser.add_argument("--seconds", type=float, default=2)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=448)
    parser.add_argument("--vram-gib", type=float, default=24)
    parser.add_argument("--ram-gib", type=float, default=64)
    parser.add_argument("--seed", type=int, default=2026090901)
    args = parser.parse_args()
    if args.prompt_stdin:
        args.prompt = sys.stdin.read()
    if args.seconds <= 0 or min(args.width, args.height, args.vram_gib, args.ram_gib) <= 0:
        parser.error("duration, dimensions and resource budgets must be positive")
    if args.prompt is not None and not args.prompt.strip():
        parser.error("--prompt must not be blank")
    if args.prompt_file is not None and not args.prompt_file.is_file():
        parser.error("--prompt-file must name an existing file")
    explicit_images = bool(args.first_frame or args.last_frame or args.reference_image or args.reference_video)
    if (args.media or args.media_json is not None) and explicit_images:
        parser.error("use direct media flags or --media/--media-json, not both")
    if (args.reference_image or args.reference_video) and (args.first_frame or args.last_frame):
        parser.error("reference images/videos cannot be mixed with first/last frames")
    if len(args.reference_image) + len(args.reference_video) > 32:
        parser.error("at most 32 reference images/videos in total are supported")
    if args.reference_video_sound and not args.reference_video:
        parser.error("--reference-video-sound requires --reference-video")
    for path in [args.first_frame, args.last_frame, *args.reference_image, *args.reference_video]:
        if path is not None and not path.expanduser().is_file():
                parser.error("media file does not exist: " + str(path))

    # The managed CLI supplies installed model paths and selects its CUDA Python.
    # No ComfyUI HTTP server or browser is needed; its encoder library is reused.
    with tempfile.TemporaryDirectory(prefix="freevideo-prompt-") as folder:
        media_path = args.media
        media = None
        if args.media_json is not None:
            try:
                media = json.loads(args.media_json)
                if not isinstance(media, dict):
                    raise ValueError("expected an object")
                for key in ("first", "last"):
                    if media.get(key):
                        media[key] = str(Path(media[key]).expanduser().resolve())
                for key in ("references", "loras"):
                    for row in media.get(key, []):
                        row["path"] = str(Path(row["path"]).expanduser().resolve())
            except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
                parser.error("invalid --media-json: " + str(error))
        elif explicit_images:
            media = {"version": 1}
            for key, path in (("first", args.first_frame), ("last", args.last_frame)):
                if path is not None:
                    media[key] = str(path.expanduser().resolve())
            if args.reference_image or args.reference_video:
                media["references"] = [{"kind": "image", "path": str(p.expanduser().resolve())}
                                       for p in args.reference_image]
                media["references"] += [{"kind": "video", "path": str(p.expanduser().resolve()),
                                         "sound": args.reference_video_sound}
                                        for p in args.reference_video]
        if media is not None:
            media_path = Path(folder) / "media.json"
            media_path.write_text(json.dumps(media), encoding="utf-8")
        if media_path is not None:
            from freevideo_engine.media_request import read
            try:
                read(media_path)
            except (OSError, ValueError, TypeError) as error:
                parser.error("invalid media request: " + str(error))
        prompt = args.prompt_file
        if prompt is None:
            prompt = Path(folder) / "prompt.txt"
            prompt.write_text(args.prompt, encoding="utf-8")
        command = [sys.executable, "-m", "freevideo_engine.managed", "generate",
                   "--prompt-file", str(prompt), "--out", str(args.out),
                   "--seconds", str(args.seconds), "--width", str(args.width),
                   "--height", str(args.height), "--vram-gib", str(args.vram_gib),
                   "--ram-gib", str(args.ram_gib), "--seed", str(args.seed)]
        if media_path is not None:
            command += ["--media", str(media_path)]
        try:
            return subprocess.run(command, check=False).returncode
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
