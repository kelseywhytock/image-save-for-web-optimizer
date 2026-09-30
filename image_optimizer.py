#!/usr/bin/env python3
"""
Image Optimizer for Web  v1.1.1
- Drop images onto the droplet app to optimize them
- Double-click the app to open settings
"""

import sys
import io
import json
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from PIL import Image, ImageCms, ImageOps

# ── Paths ────────────────────────────────────────────────────────────────────
SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

# Settings live in ~/Library/Application Support so they persist across
# rebuilds and are never inside the app bundle (avoids spurious permission checks)
def _settings_file() -> Path:
    support = Path.home() / "Library" / "Application Support" / "Image Optimizer"
    support.mkdir(parents=True, exist_ok=True)
    return support / "settings.json"

# Desktop path is built lazily so it's never evaluated at import time
def _default_output_dir() -> str:
    return str(Path.home() / "Desktop" / "optimized")


def _defaults() -> dict:
    return {
        "quality":        85,
        "quality_min":    60,
        "max_dimension":  2560,
        "target_kb":      200,
        "convert_png":    True,
        "strip_metadata": True,
        "convert_srgb":   True,
        "progressive":    True,
        "output_dir":     _default_output_dir(),
    }


def load_settings() -> dict:
    settings_file = _settings_file()
    defaults = _defaults()

    # migrate from old locations if present
    old_locations = [
        Path(__file__).parent / "image_optimizer_settings.json",
        Path(__file__).parent / ".image_optimizer_settings.json",
    ]
    for old in old_locations:
        try:
            if old.exists() and not settings_file.exists():
                shutil.copy(old, settings_file)
                break
        except OSError:
            pass

    if settings_file.exists():
        try:
            saved = json.loads(settings_file.read_text())
            return {**defaults, **saved}
        except (OSError, ValueError):
            pass  # unreadable or corrupt settings file: fall back to defaults
    return defaults


def save_settings(cfg: dict):
    """Write settings atomically so a failed write can't leave a corrupt file."""
    target = _settings_file()
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(target)


# ── Image processing ──────────────────────────────────────────────────────────

def convert_to_srgb(img: Image.Image) -> tuple:
    """Returns (image, converted). converted is False if there was no profile or conversion failed."""
    icc = img.info.get("icc_profile")
    if not icc:
        return img, False
    try:
        input_profile  = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        output_profile = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(img, input_profile, output_profile), True
    except (ImageCms.PyCMSError, OSError, ValueError):
        return img, False  # e.g. palette images or a malformed profile


def has_transparency(img: Image.Image) -> bool:
    """Return True if any pixel is not fully opaque."""
    if "transparency" in img.info:  # palette / colour-key transparency
        return True
    if img.mode in ("RGBA", "LA", "PA"):
        return img.getextrema()[-1][0] < 255
    return False


def flatten_on_white(img: Image.Image) -> Image.Image:
    """Composite any transparency over white and return an RGB image (for JPEG output)."""
    if "transparency" in img.info or img.mode in ("RGBA", "LA", "PA"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if img.mode not in ("RGB", "L", "CMYK"):
        return img.convert("RGB")
    return img


def resize_if_needed(img: Image.Image, max_dim: int) -> Image.Image:
    if max_dim <= 0:
        return img
    w, h = img.size
    if w <= max_dim and h <= max_dim:
        return img
    ratio = min(max_dim / w, max_dim / h)
    return img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    out = directory / f"{stem}{suffix}"
    counter = 1
    while out.exists():
        out = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return out


def save_jpg(img: Image.Image, out_path: Path, cfg: dict, meta: dict) -> int:
    img = flatten_on_white(img)
    target  = cfg["target_kb"] * 1024
    quality = cfg["quality"]
    # The floor can never be above the starting quality, or nothing would be saved
    floor   = min(cfg["quality_min"], quality)
    save_kwargs = dict(format="JPEG", optimize=True, progressive=cfg["progressive"], **meta)
    while True:
        img.save(out_path, quality=quality, **save_kwargs)
        if target <= 0 or quality <= floor or out_path.stat().st_size <= target:
            break
        quality = max(quality - 5, floor)
    return out_path.stat().st_size


def save_png(img: Image.Image, out_path: Path, meta: dict) -> int:
    img.save(out_path, "PNG", optimize=True, **meta)
    return out_path.stat().st_size


def optimize_image(src: Path, cfg: dict) -> dict:
    """Returns a result dict: {ok, name, message}"""
    suffix = src.suffix.lower()
    if suffix not in SUPPORTED:
        return {"ok": False, "name": src.name, "message": "unsupported format"}

    try:
        with Image.open(src) as opened:
            opened.load()
            # Bake EXIF orientation into the pixels. Output files never carry the
            # orientation tag, so skipping this would leave phone photos sideways.
            img = ImageOps.exif_transpose(opened)
    except Exception as e:
        return {"ok": False, "name": src.name, "message": str(e)}

    original_size = src.stat().st_size

    try:
        exif = img.getexif()
        icc  = img.info.get("icc_profile")
        # Transparency info is needed to decide PNG vs JPG and to write PNGs
        transparency = {"transparency": img.info["transparency"]} if "transparency" in img.info else {}

        if cfg["convert_srgb"]:
            img, converted = convert_to_srgb(img)
            if converted:
                icc = None  # pixels are now sRGB, no profile needed

        img = resize_if_needed(img, cfg["max_dimension"])
        img.info = transparency  # drop everything else so nothing leaks into the output

        # Pillow only writes metadata that is passed to save() explicitly
        meta = {}
        if not cfg["strip_metadata"]:
            if len(exif):
                meta["exif"] = exif
            if icc:
                meta["icc_profile"] = icc

        keep_png = suffix == ".png" and (not cfg["convert_png"] or has_transparency(img))
        out_dir  = Path(cfg["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = None
        try:
            if keep_png:
                out_path   = unique_path(out_dir, src.stem, ".png")
                final_size = save_png(img, out_path, meta)
                fmt = "PNG"
            else:
                out_path   = unique_path(out_dir, src.stem, ".jpg")
                final_size = save_jpg(img, out_path, cfg, meta)
                fmt = "JPG"
        except Exception:
            # Don't leave a half-written file in the output folder
            if out_path is not None:
                out_path.unlink(missing_ok=True)
            raise

    except Exception as e:
        return {"ok": False, "name": src.name, "message": str(e)}

    saved_pct   = int((1 - final_size / original_size) * 100) if original_size else 0
    original_kb = original_size // 1024
    final_kb    = final_size // 1024
    over        = " ⚠ over target" if cfg["target_kb"] > 0 and final_size > cfg["target_kb"] * 1024 else ""

    return {
        "ok":      True,
        "name":    src.name,
        "message": f"[{fmt}] {original_kb} KB → {final_kb} KB ({saved_pct}% smaller){over}",
    }


# ── Collect files (recursive) ─────────────────────────────────────────────────

def collect_files(paths: list) -> list:
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            # rglob walks all nested subfolders
            files.extend(
                f for f in sorted(path.rglob("*"))
                if f.is_file() and f.suffix.lower() in SUPPORTED
            )
        elif path.is_file() and path.suffix.lower() in SUPPORTED:
            files.append(path)
    return files


# ── Confirm window ────────────────────────────────────────────────────────────

def show_confirm_window(files: list, cfg: dict) -> bool:
    root = tk.Tk()
    root.title("Image Optimizer")
    root.resizable(False, False)

    style = ttk.Style()
    style.theme_use("aqua")

    confirmed = tk.BooleanVar(value=False)

    out_dir   = Path(cfg["output_dir"])
    out_label = str(out_dir).replace(str(Path.home()), "~")
    n = len(files)

    ttk.Label(root, text=f"{n} image{'s' if n != 1 else ''} ready to optimize",
              font=("SF Pro Display", 15, "bold")).pack(pady=(22, 2))
    ttk.Label(root, text=f"→ {out_label}/",
              foreground="#888", font=("SF Pro", 11)).pack(pady=(0, 14))

    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=20, pady=(0, 10))

    dim_label  = f"{cfg['max_dimension']}px max" if cfg["max_dimension"] > 0 else "no resize"
    size_label = f"{cfg['target_kb']} KB max"    if cfg["target_kb"] > 0    else "no size limit"
    png_label  = "PNG→JPG"    if cfg["convert_png"]    else "keep PNG"
    meta_label = "strip meta" if cfg["strip_metadata"] else "keep meta"

    summary = f"Quality {cfg['quality']}  ·  {dim_label}  ·  {size_label}  ·  {png_label}  ·  {meta_label}"
    ttk.Label(root, text=summary, foreground="#aaa", font=("SF Pro", 10)).pack(pady=(0, 6))
    ttk.Label(root, text="Double-click the app to change settings",
              foreground="#ccc", font=("SF Pro", 9)).pack(pady=(0, 16))

    def on_go():
        confirmed.set(True)
        root.destroy()

    def on_cancel():
        confirmed.set(False)
        root.destroy()

    btn_w, btn_h, btn_r = 280, 52, 12
    canvas = tk.Canvas(root, width=btn_w, height=btn_h,
                       highlightthickness=0, bg=root.cget("bg"), cursor="pointinghand")
    canvas.pack(pady=(0, 10))

    def _draw_btn(color):
        canvas.delete("all")
        canvas.create_rectangle(btn_r, 0, btn_w - btn_r, btn_h, fill=color, outline="")
        canvas.create_rectangle(0, btn_r, btn_w, btn_h - btn_r, fill=color, outline="")
        for dx, dy in [(0, 0), (btn_w - 2*btn_r, 0), (0, btn_h - 2*btn_r), (btn_w - 2*btn_r, btn_h - 2*btn_r)]:
            canvas.create_oval(dx, dy, dx + 2*btn_r, dy + 2*btn_r, fill=color, outline="")
        canvas.create_text(btn_w // 2, btn_h // 2, text="Optimize Now",
                           fill="white", font=("SF Pro Display", 17, "bold"))

    _draw_btn("#E8720C")
    canvas.bind("<Enter>",           lambda e: _draw_btn("#FF8C2A"))
    canvas.bind("<Leave>",           lambda e: _draw_btn("#E8720C"))
    canvas.bind("<Button-1>",        lambda e: _draw_btn("#C45C00"))
    canvas.bind("<ButtonRelease-1>", lambda e: on_go())

    cancel_lbl = tk.Label(root, text="Cancel", fg="#888", bg=root.cget("bg"),
                          font=("SF Pro", 11), cursor="pointinghand")
    cancel_lbl.pack(pady=(0, 18))
    cancel_lbl.bind("<Button-1>", lambda e: on_cancel())

    root.protocol("WM_DELETE_WINDOW", on_cancel)

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    rw, rh = root.winfo_reqwidth(), root.winfo_reqheight()
    root.geometry(f"{max(rw, 340)}x{rh}+{(sw - max(rw, 340))//2}+{(sh - rh)//2}")

    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.focus_force()

    root.mainloop()
    return confirmed.get()


# ── Progress window ───────────────────────────────────────────────────────────

def show_progress_and_run(files: list, cfg: dict) -> list:
    """Shows a live progress window while processing. Returns list of result dicts."""
    results = []

    root = tk.Tk()
    root.title("Image Optimizer")
    root.resizable(False, False)

    style = ttk.Style()
    style.theme_use("aqua")

    n = len(files)

    ttk.Label(root, text="Optimizing…",
              font=("SF Pro Display", 15, "bold")).pack(pady=(22, 4))

    progress_var = tk.DoubleVar(value=0)
    bar = ttk.Progressbar(root, variable=progress_var, maximum=n, length=300, mode="determinate")
    bar.pack(padx=30, pady=(4, 6))

    count_lbl = tk.Label(root, text=f"0 of {n}", fg="#888", bg=root.cget("bg"),
                         font=("SF Pro", 11))
    count_lbl.pack()

    file_lbl = tk.Label(root, text="", fg="#aaa", bg=root.cget("bg"),
                        font=("SF Pro", 10), wraplength=300)
    file_lbl.pack(pady=(2, 20))

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    rw, rh = max(root.winfo_reqwidth(), 360), root.winfo_reqheight()
    root.geometry(f"{rw}x{rh}+{(sw - rw)//2}+{(sh - rh)//2}")

    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.focus_force()

    # Tk is not thread-safe: the worker only posts messages, the main thread updates widgets
    messages = queue.Queue()

    def worker():
        for i, f in enumerate(files):
            messages.put(("start", i, f.name))
            results.append(optimize_image(f, cfg))
            messages.put(("done", i + 1, None))
        messages.put(("finished", None, None))

    def poll():
        try:
            while True:
                kind, i, name = messages.get_nowait()
                if kind == "start":
                    file_lbl.config(text=name)
                    count_lbl.config(text=f"{i + 1} of {n}")
                elif kind == "done":
                    progress_var.set(i)
                else:
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(50, poll)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    root.after(50, poll)

    root.mainloop()
    t.join()
    return results


# ── Done window ───────────────────────────────────────────────────────────────

def show_done_window(results: list, out_dir: Path):
    ok_count  = sum(1 for r in results if r["ok"])
    errors    = [r for r in results if not r["ok"]]
    has_errors = bool(errors)

    root = tk.Tk()
    root.title("Image Optimizer")
    root.resizable(False, False)

    style = ttk.Style()
    style.theme_use("aqua")

    out_label = str(out_dir).replace(str(Path.home()), "~")

    if has_errors:
        icon_text  = "⚠ Completed with errors"
        icon_color = "#E8720C"
    else:
        icon_text  = "✓ Done"
        icon_color = "#4CAF50"

    ttk.Label(root, text=icon_text,
              font=("SF Pro Display", 20, "bold"), foreground=icon_color).pack(pady=(24, 4))
    ttk.Label(root, text=f"{ok_count} image{'s' if ok_count != 1 else ''} optimized",
              font=("SF Pro", 13), foreground="#555").pack()
    ttk.Label(root, text=f"Saved to {out_label}/",
              font=("SF Pro", 11), foreground="#aaa").pack(pady=(3, 0))

    if has_errors:
        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=20, pady=(14, 8))
        ttk.Label(root, text=f"{len(errors)} file{'s' if len(errors) != 1 else ''} could not be processed:",
                  font=("SF Pro", 11, "bold"), foreground="#cc3333").pack(padx=20, anchor="w")

        err_frame = ttk.Frame(root)
        err_frame.pack(fill="x", padx=20, pady=(4, 0))

        sb = ttk.Scrollbar(err_frame, orient="vertical")
        sb.pack(side="right", fill="y")
        err_box = tk.Text(err_frame, height=min(len(errors), 5), font=("Menlo", 10),
                          yscrollcommand=sb.set, wrap="word", relief="flat",
                          bg="#2a2a2a", fg="#ff8888", padx=6, pady=4)
        err_box.pack(fill="x")
        sb.config(command=err_box.yview)

        for r in errors:
            err_box.insert("end", f"• {r['name']}: {r['message']}\n")
        err_box.config(state="disabled")

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    rw = max(root.winfo_reqwidth(), 320)
    rh = root.winfo_reqheight() + 20
    root.geometry(f"{rw}x{rh}+{(sw - rw)//2}+{(sh - rh)//2}")

    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))

    # Auto-close after 1s if no errors, otherwise stay open until dismissed
    if not has_errors:
        root.after(1000, root.destroy)
    else:
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=(12, 16))
        ttk.Button(btn_frame, text="Close", command=root.destroy, width=12).pack()

    root.mainloop()


# ── Run optimizer ─────────────────────────────────────────────────────────────

def run_optimizer(paths: list):
    cfg   = load_settings()
    files = collect_files(paths)

    if not files:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Image Optimizer", "No supported image files found.")
        root.destroy()
        return

    if not show_confirm_window(files, cfg):
        return

    results = show_progress_and_run(files, cfg)
    show_done_window(results, Path(cfg["output_dir"]))


# ── Settings UI ───────────────────────────────────────────────────────────────

def show_settings_window():
    from tkinter import filedialog

    cfg = load_settings()

    root = tk.Tk()
    root.title("Image Optimizer — Settings")
    root.resizable(False, False)

    style = ttk.Style()
    style.theme_use("aqua")

    ttk.Label(root, text="Image Optimizer", font=("SF Pro Display", 18, "bold")).pack(pady=(20, 2))
    ttk.Label(root, text="Settings for web image optimization", foreground="#666").pack(pady=(0, 16))
    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=16, pady=(0, 12))

    frame = ttk.Frame(root)
    frame.pack(fill="x", padx=16)
    frame.columnconfigure(1, weight=1)

    def grid_row(label_text, widget_factory, row_idx):
        ttk.Label(frame, text=label_text, width=22, anchor="w").grid(
            row=row_idx, column=0, sticky="w", pady=5)
        w = widget_factory(frame)
        w.grid(row=row_idx, column=1, sticky="ew", padx=(8, 0), pady=5)
        return w

    # JPEG quality
    quality_var = tk.IntVar(value=cfg["quality"])
    quality_lbl = ttk.Label(frame, textvariable=quality_var, width=4)
    grid_row("JPEG quality:", lambda p: ttk.Scale(
        p, from_=30, to=100, variable=quality_var, orient="horizontal",
        command=lambda v: quality_var.set(int(float(v)))), 0)
    quality_lbl.grid(row=0, column=2, padx=(6, 0), pady=5)

    # Min quality floor
    quality_min_var = tk.IntVar(value=cfg["quality_min"])
    quality_min_lbl = ttk.Label(frame, textvariable=quality_min_var, width=4)
    grid_row("Min quality floor:", lambda p: ttk.Scale(
        p, from_=20, to=85, variable=quality_min_var, orient="horizontal",
        command=lambda v: quality_min_var.set(int(float(v)))), 1)
    quality_min_lbl.grid(row=1, column=2, padx=(6, 0), pady=5)

    # Max dimension
    max_dim_var = tk.StringVar()
    def make_dim(parent):
        opts = ["No limit", "800", "1200", "1920", "2560", "3840"]
        vals = ["0",        "800", "1200", "1920", "2560", "3840"]
        combo = ttk.Combobox(parent, values=opts, width=12, state="readonly")
        cur = str(cfg["max_dimension"])
        combo.current(vals.index(cur) if cur in vals else 4)
        max_dim_var.set(vals[combo.current()])
        combo.bind("<<ComboboxSelected>>", lambda e: max_dim_var.set(vals[combo.current()]))
        return combo
    grid_row("Max dimension:", make_dim, 2)

    # Target KB
    target_kb_var = tk.StringVar()
    def make_target(parent):
        opts = ["No limit", "100 KB", "150 KB", "200 KB", "300 KB", "500 KB"]
        vals = ["0",        "100",    "150",    "200",    "300",    "500"]
        combo = ttk.Combobox(parent, values=opts, width=12, state="readonly")
        cur = str(cfg["target_kb"])
        combo.current(vals.index(cur) if cur in vals else 3)
        target_kb_var.set(vals[combo.current()])
        combo.bind("<<ComboboxSelected>>", lambda e: target_kb_var.set(vals[combo.current()]))
        return combo
    grid_row("Max file size:", make_target, 3)

    ttk.Separator(frame, orient="horizontal").grid(
        row=4, column=0, columnspan=3, sticky="ew", pady=10)

    convert_png_var  = tk.BooleanVar(value=cfg["convert_png"])
    strip_meta_var   = tk.BooleanVar(value=cfg["strip_metadata"])
    convert_srgb_var = tk.BooleanVar(value=cfg["convert_srgb"])
    progressive_var  = tk.BooleanVar(value=cfg["progressive"])
    for text, var, r in [
        ("Convert opaque PNGs to JPG",   convert_png_var,  5),
        ("Strip metadata (EXIF/GPS)",     strip_meta_var,   6),
        ("Convert color profile to sRGB", convert_srgb_var, 7),
        ("Progressive JPEG encoding",     progressive_var,  8),
    ]:
        ttk.Checkbutton(frame, text=text, variable=var).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=3)

    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=16, pady=(12, 10))

    output_dir_var = tk.StringVar(value=cfg["output_dir"])

    def _short(path_str):
        return path_str.replace(str(Path.home()), "~")

    folder_outer = ttk.Frame(root)
    folder_outer.pack(fill="x", padx=16, pady=(0, 8))

    ttk.Label(folder_outer, text="Output folder:", foreground="#888",
              font=("SF Pro", 11), anchor="w").pack(side="left")

    path_label = tk.Label(folder_outer, text=_short(cfg["output_dir"]),
                          fg="#cccccc", bg="#333333",
                          font=("SF Pro", 11), anchor="w", padx=4)
    path_label.pack(side="left", padx=(6, 8), fill="x", expand=True)

    def choose_folder():
        chosen = filedialog.askdirectory(
            title="Choose Output Folder",
            initialdir=output_dir_var.get(),
            mustexist=False,
        )
        if chosen:
            output_dir_var.set(chosen)
            path_label.config(text=_short(chosen))

    ttk.Button(folder_outer, text="Choose…", command=choose_folder, width=9).pack(side="right")

    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=16, pady=(6, 0))

    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=(10, 20))

    def on_save():
        new_cfg = {
            "quality":        quality_var.get(),
            "quality_min":    quality_min_var.get(),
            "max_dimension":  int(max_dim_var.get()),
            "target_kb":      int(target_kb_var.get()),
            "convert_png":    convert_png_var.get(),
            "strip_metadata": strip_meta_var.get(),
            "convert_srgb":   convert_srgb_var.get(),
            "progressive":    progressive_var.get(),
            "output_dir":     output_dir_var.get(),
        }
        try:
            save_settings(new_cfg)
        except OSError as e:
            messagebox.showerror("Image Optimizer", f"Could not save settings:\n{e}")
            return
        messagebox.showinfo("Saved", "Settings saved! They'll apply the next time you drop images.")
        root.destroy()

    def on_reset():
        try:
            save_settings(_defaults())
        except OSError as e:
            messagebox.showerror("Image Optimizer", f"Could not reset settings:\n{e}")
            return
        messagebox.showinfo("Reset", "Settings reset to defaults.")
        root.destroy()
        show_settings_window()

    ttk.Button(btn_frame, text="Save Settings",  command=on_save,  width=16).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="Reset Defaults", command=on_reset, width=16).pack(side="left", padx=6)

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"460x{root.winfo_reqheight()}+{(sw - 460)//2}+{(sh - root.winfo_reqheight())//2}")

    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.focus_force()

    root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

def _filter_py2app_args(args):
    """Strip py2app/macOS internal flags that aren't file paths."""
    skip_next = False
    result = []
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("-psn", "-NSDocumentRevisionsDebugMode") or a.startswith("-psn_"):
            continue
        if a.startswith("-") and not Path(a).exists():
            skip_next = True
            continue
        result.append(a)
    return result


def _run_with_apple_events():
    """
    Handle file drops via Apple Events (open document events).
    macOS sends dropped files as odoc Apple Events rather than argv
    when argv_emulation is off. We install a handler, wait briefly,
    then fall back to settings if nothing arrives. If PyObjC isn't
    installed, fall back to plain argv handling.
    """
    try:
        from AppKit import NSApplication, NSObject
        from Foundation import NSTimer
        import objc

        dropped_paths = []
        timer_fired = []

        class AppDelegate(NSObject):
            def applicationDidFinishLaunching_(self, notif):
                # Give Apple Events 0.3s to arrive before falling back to settings
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.3, self, b"timerFired:", None, False
                )

            def application_openFiles_(self, app, filenames):
                dropped_paths.extend(filenames)
                app.replyToOpenOrPrint_(0)  # NSApplicationDelegateReplySuccess

            def timerFired_(self, timer):
                timer_fired.append(True)
                NSApplication.sharedApplication().stop_(None)

        app = NSApplication.sharedApplication()
        delegate = AppDelegate.alloc().init()
        app.setDelegate_(delegate)
        app.run()

        if dropped_paths:
            run_optimizer(dropped_paths)
        else:
            show_settings_window()

    except ImportError:
        # AppKit not available (running outside .app bundle)
        args = _filter_py2app_args(sys.argv[1:])
        if args:
            run_optimizer(args)
        else:
            show_settings_window()


if __name__ == "__main__":
    args = _filter_py2app_args(sys.argv[1:])
    if args:
        # Called with file args directly (e.g. from terminal)
        run_optimizer(args)
    else:
        # Launched by macOS (double-click or drop) — use Apple Events
        _run_with_apple_events()
