"""Render synthetic first/last frames of a rotating cube using CPU only."""

import argparse
import itertools
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def render(angle, width=768, height=448):
    scale = 3
    size = (width * scale, height * scale)
    image = Image.new("RGB", size, (227, 233, 240))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 287 * scale, size[0], size[1]), fill=(205, 214, 225))
    shadow = Image.new("RGBA", size)
    ImageDraw.Draw(shadow).ellipse((255 * scale, 314 * scale, 540 * scale, 357 * scale),
                                   fill=(39, 51, 72, 85))
    image = Image.alpha_composite(image.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(12 * scale)))
    vertices = np.array(list(itertools.product((-1., 1.), repeat=3)))
    a = math.radians(angle)
    rotation = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0],
                         [-math.sin(a), 0, math.cos(a)]])
    vertices = vertices @ rotation.T
    # Camera above the object, fixed between frames.
    t = math.radians(-18)
    camera = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)],
                       [0, math.sin(t), math.cos(t)]])
    points = vertices @ camera.T
    projected = np.column_stack((384 + 530 * points[:, 0] / (points[:, 2] + 6),
                                 224 - 530 * points[:, 1] / (points[:, 2] + 6))) * scale
    faces = []
    for axis in range(3):
        for sign in (-1, 1):
            ids = [i for i, v in enumerate(itertools.product((-1., 1.), repeat=3)) if v[axis] == sign]
            ids = [ids[i] for i in (0, 1, 3, 2)]
            normal = np.zeros(3); normal[axis] = sign
            normal = camera @ rotation @ normal
            center = points[ids].mean(axis=0)
            if np.dot(normal, np.array([0, 0, -6]) - center) <= 0:
                continue
            light = np.array([-0.6, 0.8, -1.]); light /= np.linalg.norm(light)
            shade = 0.46 + 0.54 * max(0, float(np.dot(normal, light)))
            color = tuple(int(c * shade) for c in (255, 153, 55))
            faces.append((center[2], ids, color))
    draw = ImageDraw.Draw(image)
    for _, ids, color in sorted(faces, reverse=True):
        polygon = [tuple(projected[i]) for i in ids]
        draw.polygon(polygon, fill=color)
        draw.line(polygon + polygon[:1], fill=(88, 60, 39), width=2 * scale, joint="curve")
    return image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("outputs/geometry-demo"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    render(25).save(args.out / "first.png")
    render(85).save(args.out / "last.png")
    print("Rendered first.png and last.png")


if __name__ == "__main__":
    main()
