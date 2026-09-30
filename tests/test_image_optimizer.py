"""Tests for the image processing pipeline (no GUI). Run: python3 -m unittest discover tests"""

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import image_optimizer as io_mod  # noqa: E402

ORIENTATION = 0x0112
MAKE = 0x010F


def load(path):
    with Image.open(path) as im:
        im.load()
        return im


class OptimizeImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"
        self.cfg = {**io_mod._defaults(), "output_dir": str(self.out), "target_kb": 0}

    def tearDown(self):
        self._tmp.cleanup()

    def run_one(self, src, **overrides):
        result = io_mod.optimize_image(src, {**self.cfg, **overrides})
        self.assertTrue(result["ok"], result["message"])
        return sorted(self.out.iterdir())[-1]

    def test_quality_below_floor_still_saves(self):
        src = self.tmp / "a.jpg"
        Image.new("RGB", (200, 200), "blue").save(src)
        out = self.run_one(src, quality=50, quality_min=60, target_kb=1)
        self.assertTrue(out.exists() and out.stat().st_size > 0)

    def test_quality_steps_down_to_floor_not_past_it(self):
        src = self.tmp / "noise.png"
        Image.effect_noise((400, 400), 80).convert("RGB").save(src)
        result = io_mod.optimize_image(src, {**self.cfg, "quality": 85, "quality_min": 62, "target_kb": 1})
        self.assertTrue(result["ok"])
        self.assertIn("over target", result["message"])

    def test_exif_orientation_is_applied(self):
        src = self.tmp / "rot.jpg"
        img = Image.new("RGB", (40, 20), "red")
        exif = Image.Exif()
        exif[ORIENTATION] = 6  # rotate 90 CW on display
        img.save(src, exif=exif)
        out = load(self.run_one(src))
        self.assertEqual(out.size, (20, 40))

    def test_palette_gif_keeps_colors(self):
        src = self.tmp / "p.gif"
        img = Image.new("P", (30, 30))
        img.putpalette([255, 0, 0] + [0, 0, 0] * 255)  # index 0 = red
        img.save(src)
        out = load(self.run_one(src)).convert("RGB")
        r, g, b = out.getpixel((15, 15))
        self.assertGreater(r, 200)
        self.assertLess(g, 60)
        self.assertLess(b, 60)

    def test_transparent_gif_flattens_on_white_not_black(self):
        src = self.tmp / "t.gif"
        img = Image.new("P", (30, 30), 1)
        img.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        img.info["transparency"] = 1
        img.save(src, transparency=1)
        out = load(self.run_one(src)).convert("RGB")
        self.assertTrue(all(c > 240 for c in out.getpixel((15, 15))))

    def test_png_with_a_single_transparent_pixel_stays_png(self):
        src = self.tmp / "a.png"
        img = Image.new("RGBA", (100, 100), (10, 200, 10, 255))
        img.putpixel((0, 0), (0, 0, 0, 0))
        img.save(src)
        out = self.run_one(src)
        self.assertEqual(out.suffix, ".png")
        self.assertEqual(load(out).convert("RGBA").getpixel((0, 0))[3], 0)

    def test_opaque_png_becomes_jpg(self):
        src = self.tmp / "o.png"
        Image.new("RGBA", (50, 50), (1, 2, 3, 255)).save(src)
        self.assertEqual(self.run_one(src).suffix, ".jpg")

    def test_strip_metadata_removes_exif(self):
        src = self.tmp / "m.jpg"
        exif = Image.Exif()
        exif[MAKE] = "TestCam"
        Image.new("RGB", (50, 50), "green").save(src, exif=exif)
        out = load(self.run_one(src, strip_metadata=True))
        self.assertEqual(len(out.getexif()), 0)

    def test_keep_metadata_preserves_exif(self):
        src = self.tmp / "m.jpg"
        exif = Image.Exif()
        exif[MAKE] = "TestCam"
        Image.new("RGB", (50, 50), "green").save(src, exif=exif)
        out = load(self.run_one(src, strip_metadata=False))
        self.assertEqual(out.getexif().get(MAKE), "TestCam")

    def test_resize_never_produces_zero_dimension(self):
        img = Image.new("RGB", (10000, 2), "white")
        self.assertGreaterEqual(io_mod.resize_if_needed(img, 100).size[1], 1)


class HelperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_unique_path_adds_counter_on_collision(self):
        (self.tmp / "photo.jpg").write_bytes(b"x")
        (self.tmp / "photo_1.jpg").write_bytes(b"x")
        self.assertEqual(io_mod.unique_path(self.tmp, "photo", ".jpg").name, "photo_2.jpg")

    def test_collect_files_recurses_and_filters(self):
        (self.tmp / "sub" / "deep").mkdir(parents=True)
        for rel in ("a.jpg", "sub/b.PNG", "sub/deep/c.webp", "notes.txt", "sub/d.pdf"):
            (self.tmp / rel).write_bytes(b"x")
        found = io_mod.collect_files([str(self.tmp)])
        self.assertEqual(sorted(p.name for p in found), ["a.jpg", "b.PNG", "c.webp"])
        single = io_mod.collect_files([str(self.tmp / "a.jpg"), str(self.tmp / "notes.txt")])
        self.assertEqual([p.name for p in single], ["a.jpg"])

    def test_unsupported_file_is_reported_not_raised(self):
        src = self.tmp / "doc.txt"
        src.write_text("hi")
        result = io_mod.optimize_image(src, {**io_mod._defaults(), "output_dir": str(self.tmp / "out")})
        self.assertFalse(result["ok"])

    def test_corrupt_image_is_reported_and_leaves_no_output(self):
        src = self.tmp / "bad.jpg"
        src.write_bytes(b"not an image")
        out = self.tmp / "out"
        result = io_mod.optimize_image(src, {**io_mod._defaults(), "output_dir": str(out)})
        self.assertFalse(result["ok"])
        self.assertFalse(out.exists() and any(out.iterdir()))

    def test_failed_save_removes_partial_output(self):
        src = self.tmp / "a.jpg"
        Image.new("RGB", (20, 20), "red").save(src)
        out = self.tmp / "out"
        original = io_mod.save_jpg

        def failing(img, out_path, cfg, meta):
            out_path.write_bytes(b"partial")
            raise OSError("disk full")

        io_mod.save_jpg = failing
        try:
            result = io_mod.optimize_image(src, {**io_mod._defaults(), "output_dir": str(out)})
        finally:
            io_mod.save_jpg = original
        self.assertFalse(result["ok"])
        self.assertEqual(list(out.iterdir()), [])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = Path(self._tmp.name) / "settings.json"
        self._orig = io_mod._settings_file
        io_mod._settings_file = lambda: self.file

    def tearDown(self):
        io_mod._settings_file = self._orig
        self._tmp.cleanup()

    def test_round_trip(self):
        cfg = {**io_mod._defaults(), "quality": 70}
        io_mod.save_settings(cfg)
        self.assertEqual(io_mod.load_settings()["quality"], 70)
        self.assertFalse(self.file.with_name("settings.json.tmp").exists())

    def test_corrupt_file_falls_back_to_defaults(self):
        self.file.write_text("{ not json")
        self.assertEqual(io_mod.load_settings(), io_mod._defaults())

    def test_missing_keys_filled_from_defaults(self):
        self.file.write_text('{"quality": 50}')
        cfg = io_mod.load_settings()
        self.assertEqual(cfg["quality"], 50)
        self.assertEqual(cfg["max_dimension"], io_mod._defaults()["max_dimension"])


class SrgbTests(unittest.TestCase):
    def test_no_profile_is_unconverted(self):
        img = Image.new("RGB", (4, 4), "red")
        _, converted = io_mod.convert_to_srgb(img)
        self.assertFalse(converted)

    def test_profile_is_converted(self):
        from PIL import ImageCms
        img = Image.new("RGB", (4, 4), (200, 50, 50))
        img.info["icc_profile"] = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        _, converted = io_mod.convert_to_srgb(img)
        self.assertTrue(converted)


if __name__ == "__main__":
    unittest.main()
