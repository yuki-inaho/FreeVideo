"""Encode the CPU-rendered studio guide frames into a silent 24 fps MP4."""

import argparse
from pathlib import Path

import av
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("outputs/studio-demo"))
    args = parser.parse_args()
    frames = [args.root / "guide-frames" / ("%04d.png" % i) for i in range(56)]
    if not all(p.is_file() for p in frames):
        parser.error("render all 56 guide frames with examples/render_studio.py first")
    target = args.root / "motion-guide.mp4"
    with av.open(str(target), "w") as output:
        stream = output.add_stream("libx264", rate=24)
        stream.width, stream.height, stream.pix_fmt = 512, 320, "yuv420p"
        stream.options = {"crf": "18"}
        for path in frames:
            with Image.open(path) as image:
                if image.size != (512, 320):
                    raise ValueError("guide frames must be 512 by 320")
                for packet in stream.encode(av.VideoFrame.from_image(image.convert("RGB"))):
                    output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    print("Encoded motion-guide.mp4 (56 frames at 24 fps)")


if __name__ == "__main__":
    main()
