"""CPU-only checks of CLI media contracts; never run a generation worker."""

from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image


spec = importlib.util.spec_from_file_location(
    "generate_video", Path(__file__).resolve().parents[1] / "scripts/generate_video.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class VideoCLITest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.image = Path(self.folder.name) / "reference image.png"
        Image.new("RGB", (32, 32), "orange").save(self.image)
        self.saved = []

    def run_cli(self, options, code=0):
        def run(command, check):
            prompt = Path(command[command.index("--prompt-file") + 1])
            item = {"prompt": prompt.read_text(), "path": prompt, "command": command}
            if "--media" in command:
                media = Path(command[command.index("--media") + 1])
                item.update(media=json.loads(media.read_text()), media_path=media)
            self.saved.append(item)
            return SimpleNamespace(returncode=code)
        with patch("sys.argv", ["generate_video.py", *options]), patch.object(cli.subprocess, "run", run):
            return cli.main()

    def test_first_last_prompt_and_cleanup(self):
        text = 'A cube says "hello".\nRotate slowly.'
        self.assertEqual(self.run_cli(["--prompt", text, "--first-frame", str(self.image),
                                     "--last-frame", str(self.image)], code=7), 7)
        item = self.saved[0]
        self.assertEqual(item["prompt"], text)
        self.assertEqual(item["media"]["first"], str(self.image))
        self.assertEqual(item["media"]["last"], str(self.image))
        self.assertFalse(item["path"].exists())
        self.assertFalse(item["media_path"].exists())

    def test_repeatable_reference_lists(self):
        p = str(self.image)
        self.run_cli(["--prompt", "Scene", "--reference-image", p, p, "--reference-image", p])
        self.assertEqual(len(self.saved[0]["media"]["references"]), 3)

    def test_stdin_and_inline_json(self):
        media = json.dumps({"version": 1, "first": str(self.image)})
        with patch("sys.stdin", io.StringIO("Rotate the cube.")):
            self.run_cli(["--prompt-stdin", "--media-json", media])
        self.assertEqual(self.saved[0]["prompt"], "Rotate the cube.")
        self.assertEqual(self.saved[0]["media"]["first"], str(self.image))

    def test_video_and_image_references(self):
        import av
        video = Path(self.folder.name) / "motion guide.mp4"
        with av.open(str(video), "w") as output:
            stream = output.add_stream("libx264", rate=24)
            stream.width, stream.height, stream.pix_fmt = 32, 32, "yuv420p"
            for _ in range(24):
                for packet in stream.encode(av.VideoFrame.from_image(Image.open(self.image))):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        options = ["--prompt", "Use <Video 1> motion for <Picture 1>.",
                   "--reference-image", str(self.image), "--reference-video", str(video)]
        self.run_cli(options)
        refs = self.saved[-1]["media"]["references"]
        self.assertEqual([r["kind"] for r in refs], ["image", "video"])
        self.assertFalse(refs[1]["sound"])
        self.run_cli([*options, "--reference-video-sound"])
        self.assertTrue(self.saved[-1]["media"]["references"][1]["sound"])
        self.assert_rejected(["--prompt", "Scene", "--reference-image", *([str(self.image)] * 32),
                              "--reference-video", str(video)])
        self.assert_rejected(["--prompt", "Scene", "--first-frame", str(self.image),
                              "--reference-video", str(video)])
        self.assert_rejected(["--prompt", "Scene", "--reference-video-sound"])

    def test_reference_limit_boundary(self):
        p = str(self.image)
        self.run_cli(["--prompt", "Scene", "--reference-image", *([p] * 32)])
        self.assertEqual(len(self.saved[0]["media"]["references"]), 32)
        self.assert_rejected(["--prompt", "Scene", "--reference-image", *([p] * 33)])

    def assert_rejected(self, options):
        with patch("sys.argv", ["generate_video.py", *options]), patch.object(cli.subprocess, "run") as run:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli.main()
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_conflicting_and_malformed_media_rejected_before_gpu_work(self):
        p = str(self.image)
        for options in (["--first-frame", p, "--reference-image", p],
                        ["--first-frame", p, "--media-json", "{}"],
                        ["--media-json", "[]"],
                        ["--media-json", '{"version":1,"references":[1]}'],
                        ["--media-json", '{"version":1,"references":[]}garbage']):
            with self.subTest(options=options):
                self.assert_rejected(["--prompt", "Scene", *options])


if __name__ == "__main__":
    unittest.main()
