# Changelog

## [Unreleased] - 2026-10-16
No code changes. Docs only: `README.md`.

### Fixed
- **The built `dist/Image Optimizer.app` had an invalid code signature** (`a sealed resource is missing or invalid`): a `Resources/__pycache__/` folder had been written into the bundle after signing, by launching the app. An unsigned-looking or quarantined app is not accepted as a drop target by Finder, so a colleague's dropped files just sat on top of the icon. Removed the folder, re-signed ad hoc, verified with `codesign --verify --deep --strict`, and re-zipped with `ditto` to `dist/ImageOptimizer.zip`. `dist/` is gitignored, so this is a local build fix.

### Changed
- README: removed the "right-click > Open once" Gatekeeper workaround, which macOS 15+ ignores, and documented **System Settings > Privacy & Security > Open Anyway** plus the `xattr` command. Cause: a downloaded copy of the ad-hoc-signed, un-notarized app showed "Apple could not verify ... is free of malware".

### Added
- `install.sh`: one-line installer (`curl ... | bash`). Downloads `releases/ImageOptimizer-1.1.3.zip` with curl, verifies the pinned SHA-256, installs to `/Applications` (falls back to `~/Applications`, no sudo), and clears quarantine. Rationale: browser downloads of the ad-hoc-signed, un-notarized app trigger Gatekeeper's "could not verify" warning; curl downloads are not quarantined. Tested into a temp dir: installs, passes `codesign --verify`, no quarantine xattr, and a wrong checksum aborts with nothing installed. **When rebuilding the zip, update `ZIP_SHA256` and the version in `ZIP_URL` in `install.sh`.**
- `releases/ImageOptimizer-1.1.3.zip`: the prebuilt, ad-hoc-signed app (32 MB, made with `ditto -c -k --keepParent`), committed so the repo ships a usable app. Each future rebuild adds another ~32 MB to history if committed; consider moving to GitHub Releases if versions accumulate.
- README: "Getting the App" section for non-developers; file table lists the zip.
- README: "Sharing with a Colleague" section (zip, quarantine, alias steps, drop-troubleshooting) and a warning not to launch the built bundle before zipping it.

## [1.1.3] - 2026-09-30
Files: `image_optimizer.py v1.1.3`, `setup.py v1.1.3`.

### Fixed
- **Dropping an image sometimes opened Settings instead of the confirm window.** On a cold launch the open-document event arrives about 0.6 s after Tk starts (measured 0.62-0.65 s over three launches), but `_wait_for_dropped_files()` only waited 300 ms. It now waits up to 2 s and stops 100 ms after files arrive, so drops are not slowed down. Double-clicking the app now shows Settings after up to 2 s instead of 0.3 s.

## [1.1.2] - 2026-09-30
Files: `image_optimizer.py v1.1.2`, `setup.py v1.1.2`, `requirements.txt`.

### Fixed
- **The built app crashed on launch** (`-[NSApplication macOSVersion]: unrecognized selector`, SIGABRT) on macOS 26 with the bundled Tk 8.6.16, both when dropping files and when double-clicking. The drop handler created a plain `NSApplication` through PyObjC before Tk started, so Tk's own application class was never installed and Tk crashed while resolving its first color. Dropped files are now received through Tk's `::tk::mac::OpenDocument` hook on a hidden root window, so Tk owns the application object. Verified by building in a clean virtualenv and dropping an image on the bundle: the confirm window opens and Tk receives the path.

### Removed
- `pyobjc-framework-Cocoa` from `requirements.txt`, and `_run_with_apple_events()` from `image_optimizer.py`. Nothing imports PyObjC any more. Replaced by `_wait_for_dropped_files()`.

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
