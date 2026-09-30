# Changelog

## [1.1.1] - 2026-09-30
Pre-review cleanup. Files: `image_optimizer.py v1.1.1`, `setup.py v1.1.1`.

### Fixed
- **`.gitignore` was listed in 1.1.0 but never created.** It now exists and excludes `build/`, `dist/`, the legacy Automator `Image Optimizer.app/`, `__pycache__/`, editor files and local settings, so generated artifacts (~230 MB) can't be committed by accident.
- Removed the stale `image_optimizer_settings.json`, which held a personal absolute path. The app reads `~/Library/Application Support/Image Optimizer/settings.json`.
- `save_settings()` now writes atomically (temp file + replace), and the Settings window shows an error dialog instead of failing silently if saving or resetting fails.
- A failed save in `optimize_image()` now deletes the partially written output file rather than leaving it in the output folder.
- README: success notice closes after 1 second (not ~2), build instructions use the real directory name, and the permissions section matches `setup.py` (Documents only declared).
- `_run_with_apple_events()` docstring now states the PyObjC fallback accurately.

- **The built app had no custom icon.** `setup.py` had `iconfile: None`, so py2app used the generic Python icon. It now uses `AppIcon.icns`, generated from `app_icon_1024.png` with `sips` + `iconutil`. Both files are committed. Verified by building in a clean virtualenv: the bundle contains the icon and PyObjC's `AppKit`.

### Changed
- `requirements.txt` now has version bounds (`Pillow>=10,<13`, `pyobjc-framework-Cocoa>=10`, `py2app>=0.28`).
- README documents Pillow's decompression-bomb limit for very large images.

### Added
- 10 more tests (20 total) covering `unique_path` collisions, recursive `collect_files`, unsupported and corrupt inputs, partial-output cleanup, settings round-trip and corrupt-file fallback, and sRGB conversion.

## [1.1.0] - 2026-09-30
First public release. Files: `image_optimizer.py v1.1.0`, `setup.py v1.1.0`.

### Fixed
- **Reset Defaults crashed** with a `NameError` (`DEFAULTS` was never defined). It now uses `_defaults()`.
- **Save failed when JPEG quality was below the min quality floor.** The two sliders are independent, so the quality loop could run zero times and no file was written. The floor is now capped at the starting quality and at least one save always happens.
- **Phone photos came out sideways.** EXIF orientation is now applied to the pixels before metadata is dropped.
- **Palette images (GIF, 8-bit PNG) could get wrong colors.** The metadata strip rebuilt the image with `Image.new` + `putdata`, which discards the palette and is slow on large images. It no longer rebuilds the image.
- **"Strip metadata" had no effect when turned off.** Pillow only writes EXIF/ICC data that is passed to `save()`. Turning it off now keeps EXIF and, if the image was not converted to sRGB, the ICC profile.
- **PNG transparency handling disagreed with the README.** Previously an image needed more than 1% transparent pixels to stay PNG, and smaller transparent areas turned black in the JPG. Any non-opaque pixel now keeps the PNG, and transparency in other formats is flattened onto white. Palette PNGs with a `tRNS` chunk no longer raise a `TypeError`.
- Source file handles are now closed after loading.
- Resize can no longer produce a 0 px dimension on extreme aspect ratios.
- Broad `except Exception: pass` blocks narrowed to the errors they are meant to handle.
- Progress window no longer updates Tk widgets from the worker thread; it uses a queue polled by the main thread.
- Corrected a stale auto-close comment (1 s, not 2.5 s) and removed an unused `threading.Event`.

### Changed
- `CFBundleIdentifier` is now `com.kelseywhytock.image-optimizer`, so the bundle ID matches the author's personal name. Apps built from this version get a new identity, so macOS treats them as a different app and re-asks for folder permissions once.
- `convert_to_srgb()` now returns `(image, converted)`.
- `README.md`: corrected the settings file location, removed the hard-coded Python path, documented GIF first-frame behavior, transparency flattening, and metadata behavior.

### Added
- `tests/test_image_optimizer.py` (10 unit tests; run with `python3 -m unittest discover tests`). Seven of them fail against the pre-fix code.
- `LICENSE` (PolyForm Strict 1.0.0: source is public, but no modification, no redistribution, noncommercial use only; MIT was rejected because it permits both), `.gitignore`, `requirements.txt` (adds `pyobjc-framework-Cocoa`, which the drag-and-drop handler imports).
