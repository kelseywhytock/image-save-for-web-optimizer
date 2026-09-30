# Image Save for Web Optimizer

A Mac droplet app for batch-optimizing images for web use. Drop images onto the app icon to compress, resize, and convert them — no Photoshop required.

---

## How to Use

### Optimize images
Drag one or more image files (or a folder) onto **Image Optimizer.app**.

A confirmation window appears showing how many images are queued and your current settings. Click **Optimize Now** to process, or **Cancel** to abort.

When complete, a brief success notice auto-closes after 1 second. If any file failed, the notice stays open and lists the errors. Optimized files are saved to your configured output folder (default: `~/Desktop/optimized/`).

### Change settings
**Double-click** Image Optimizer.app to open the Settings window.

### Quick access
Drag Image Optimizer.app to your **Dock** so you can drop images onto it without navigating to the folder each time.

---

## Supported Formats

| Format | Input | Output |
|--------|-------|--------|
| JPEG / JPG | ✓ | JPG |
| PNG | ✓ | JPG (opaque) or PNG (transparent) |
| GIF | ✓ (first frame only) | JPG |
| BMP | ✓ | JPG |
| TIFF / TIF | ✓ | JPG |
| WebP | ✓ | JPG |

---

## Settings Reference

### JPEG Quality `(default: 85)`
Controls the compression quality for saved JPEGs on a scale of 30–100. Higher values produce larger files with more detail. 85 is a good balance for web use.

### Min Quality Floor `(default: 60)`
When a file size target is set, the optimizer reduces quality in steps of 5 to hit the target. This is the lowest quality it will ever go — it won't compress further even if the file is still over target.

### Max Dimension `(default: 2560px)`
If an image is wider or taller than this value, it is scaled down proportionally. Set to **No limit** to skip resizing entirely.

| Option | Use case |
|--------|----------|
| 800px | Thumbnails, small UI images |
| 1200px | Blog images, content images |
| 1920px | Full-width web images |
| 2560px | Retina / high-DPI displays |
| 3840px | 4K displays |
| No limit | Print or archival quality |

### Max File Size `(default: 200 KB)`
The optimizer will reduce JPEG quality in steps until the file is at or under this size. It stops at the **Min Quality Floor** even if the file is still over target (flagged with ⚠). Set to **No limit** to skip size targeting.

### Convert opaque PNGs to JPG `(default: on)`
PNGs with no transparency are converted to JPEG for much smaller file sizes. PNGs with transparency (any pixel with alpha < 255) are always kept as PNG regardless of this setting. Any transparency in other formats (e.g. GIF, WebP) is flattened onto a white background when saved as JPG.

### Strip metadata `(default: on)`
Removes all EXIF, GPS, camera, and copyright metadata from output files. Recommended for web — metadata adds file size and can contain location data you may not want to share. When turned off, EXIF data is kept, along with the original color profile unless **Convert color profile to sRGB** replaced it. Photo orientation is always applied to the pixels, so images are never saved sideways either way.

### Convert color profile to sRGB `(default: on)`
Converts images with non-sRGB color profiles (e.g. Adobe RGB, ProPhoto RGB) to sRGB. Recommended — browsers assume sRGB and colors can appear washed out or oversaturated without this.

### Progressive JPEG encoding `(default: on)`
Saves JPEGs in progressive format, which loads top-to-bottom in a blurry-to-sharp manner in browsers instead of showing nothing until fully downloaded. Slightly smaller files, better perceived load performance.

### Output Folder `(default: ~/Desktop/optimized/)`
The folder where all optimized images are saved. Click **Choose…** to pick a different location. The folder is created automatically if it doesn't exist.

---

## Output Behavior

- Original files are **never modified**
- If a file with the same name already exists in the output folder, a counter suffix is added (e.g. `photo_1.jpg`, `photo_2.jpg`)
- Output format is always JPG unless the image has transparency, in which case it stays PNG

---

## File Locations

| File | Purpose |
|------|---------|
| `dist/Image Optimizer.app` | The built app — drag images onto this, or move to Applications / Dock |
| `image_optimizer.py` | The Python source script |
| `tests/test_image_optimizer.py` | Unit tests for the image processing pipeline |
| `requirements.txt` | Python dependencies |
| `~/Library/Application Support/Image Optimizer/settings.json` | Your saved settings (auto-created on first save, outside the repo and the app bundle) |
| `setup.py` | py2app build configuration |
| `AppIcon.icns` | App icon used by the build (generated from `app_icon_1024.png`) |
| `app_icon_1024.png` | Source artwork for the icon |

> `dist/` is not committed. Build it yourself as described below.

> The `dist/Image Optimizer.app` bundle is fully self-contained. You can move it anywhere — to your Dock, Applications folder, or Desktop — independently of the source files.

---

## Building the App

If you modify `image_optimizer.py` and need to rebuild:

```bash
cd Image-Save-for-Web-Optimizer
pip install -r requirements.txt
rm -rf build dist
python3 setup.py py2app
codesign --deep --force --sign "-" "dist/Image Optimizer.app"
```

The rebuilt app will appear in `dist/Image Optimizer.app`.

---

## macOS Permissions

The app declares access to your Documents folder only. For images you drop onto the app from Desktop or Downloads, macOS grants access to those files implicitly. If you choose an output folder in a protected location, macOS may ask for permission the first time the app writes there. Allow it once and macOS remembers.

If you are not prompted and the app can't read your files, go to **System Settings → Privacy & Security → Files and Folders** and ensure Image Optimizer has access to the relevant folders.

---

## Running the tests

```bash
python3 -m unittest discover tests
```

---

## Requirements

- macOS
- Python 3 with Tk support (developed and tested with the python.org 3.13 build)
- Dependencies in `requirements.txt`: Pillow and py2app (only needed to build the app)
- Very large images: Pillow refuses to open images above its decompression-bomb limit (roughly 179 megapixels). Those files are listed as errors in the results window.

---

## License

Copyright 2026 Kelsey Whytock. Licensed under the [PolyForm Strict License 1.0.0](LICENSE). The source is public so you can read it, but you may not distribute it or make changes or new works based on it. Noncommercial use is permitted.
