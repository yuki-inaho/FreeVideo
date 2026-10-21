"""Make CPU-only review sheets; metrics do not establish motion-transfer quality."""

import json
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path("outputs/studio-demo")
INDICES = (0, 14, 28, 42, 55)


def frames(path):
    with av.open(str(path)) as container:
        return [frame.to_image() for frame in container.decode(video=0)]


def main():
    guide = frames(ROOT / "motion-guide.mp4")
    report = {}
    for name in ("copper-first-last", "ring-guided"):
        generated = frames(ROOT / (name + ".mp4"))
        if len(generated) != 56 or len(guide) != 56:
            raise ValueError("this review expects 56-frame demo clips")
        sheet = Image.new("RGB", (1600, 450), "white")
        draw = ImageDraw.Draw(sheet)
        for column, index in enumerate(INDICES):
            if name == "copper-first-last":
                with Image.open(ROOT / "rigid-frames" / ("%04d.png" % index)) as image:
                    reference = image.convert("RGB")
                label = "Rigid linear-rotation target"
            else:
                reference, label = guide[index], "Motion guide: different shape"
            for row, image, text in ((0, generated[index], "Generated frame %d" % index),
                                      (1, reference, label)):
                sheet.paste(image.resize((320, 200)), (320 * column, 225 * row + 25))
                draw.text((320 * column + 8, 225 * row + 7), text, fill="black")
        sheet.save(ROOT / (name + "-review.png"))
        row = {"frames": len(generated), "fps": 24, "seconds": len(generated) / 24,
               "width": generated[0].width, "height": generated[0].height}
        if name == "copper-first-last":
            for filename, index in (("first.png", 0), ("last.png", -1)):
                with Image.open(ROOT / filename) as image:
                    source = np.asarray(image.convert("RGB"), dtype=float)
                row[filename + "_pixel_mae"] = float(np.abs(source - np.asarray(generated[index], dtype=float)).mean())
        report[name] = row
    report["scope"] = "Endpoint pixel error is not a quality score. No no-video baseline; motion-transfer causality untested."
    (ROOT / "review.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
