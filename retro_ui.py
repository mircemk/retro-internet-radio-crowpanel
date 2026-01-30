#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import tkinter as tk
from PIL import Image, ImageTk
from evdev import InputDevice, ecodes
import signal
import sys
import time

# ---------------- Paths ----------------
STATIONS_FILE = "/home/pi/radio/stations.txt"

SCALE_IMAGES = [
    "/home/pi/radio/scale1.jpg",
    "/home/pi/radio/scale2.jpg",
    "/home/pi/radio/scale3.jpg",
]
scale_idx = 0

# --------------- UI tuning -------------
LEFT_MARGIN = 80
RIGHT_MARGIN = 80
WHEEL_DEBOUNCE = 0.12  # seconds

# Touch zones (pixels)
EDGE_PX = 80          # right edge strip width (~1cm)
EXIT_BOX_PX = 80      # top-left square size
VOL_BAR_PX = 80       # bottom strip height (~1cm)

# Center zone for background switching
CENTER_ZONE_W = 220   # half-width
CENTER_ZONE_H = 140   # half-height

# Station text font size (top-right)
STATION_FONT_SIZE = 16  # set 10..12 if you want smaller

# ---------------------------------------
vlc_proc = None
playing = False
last_wheel_ts = 0.0

root = None
canvas = None
bg_item = None
photo = None
img = None
W = H = 0
pointer = None
vol_text = None
station_text = None
dev = None

# --------------- Helpers ---------------
def detect_mouse():
    cands = sorted(glob.glob("/dev/input/by-id/*-event-mouse"))
    if not cands:
        raise SystemExit("No *-event-mouse found in /dev/input/by-id/")
    return cands[0]

def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def pactl_exists():
    return shutil.which("pactl") is not None

def amixer_exists():
    return shutil.which("amixer") is not None

def set_volume(percent: int):
    percent = max(0, min(100, int(percent)))

    # Preferred (PipeWire/PulseAudio)
    if pactl_exists():
        run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        return True

    # Fallback (ALSA mixers; depends on device)
    if amixer_exists():
        for ctl in ("Master", "PCM", "Speaker"):
            r = run(["amixer", "sset", ctl, f"{percent}%"])
            if r.returncode == 0:
                return True

    return False

# ------------ VLC control --------------
def stop_vlc():
    global vlc_proc, playing
    if vlc_proc is None:
        playing = False
        return
    try:
        vlc_proc.terminate()
        try:
            vlc_proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            vlc_proc.kill()
    except Exception:
        pass
    vlc_proc = None
    playing = False

def start_station(url: str):
    global vlc_proc, playing
    stop_vlc()
    vlc_proc = subprocess.Popen(
        ["vlc", "-I", "dummy", "--no-video", "--quiet", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    playing = True

def cleanup_and_exit(*_):
    stop_vlc()
    try:
        dev.ungrab()
    except Exception:
        pass
    try:
        root.overrideredirect(False)
        root.attributes("-topmost", False)
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass
    sys.exit(0)

# -------- Stations parsing -------------
def parse_station_line(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Format: Name | URL
    if "|" in line:
        name, url = [x.strip() for x in line.split("|", 1)]
        if url:
            return (name if name else url, url)

    # Fallback: only URL -> short name from hostname
    url = line
    short = url
    try:
        short = short.split("://", 1)[-1]
        short = short.split("/", 1)[0]
        short = short.split(":", 1)[0]
    except Exception:
        pass
    return (short, url)

stations = []
with open(STATIONS_FILE, encoding="utf-8") as f:
    for l in f:
        item = parse_station_line(l)
        if item:
            stations.append(item)

if not stations:
    raise SystemExit("stations.txt is empty")

# ------------- Tk window ---------------
root = tk.Tk()
root.title("Retro Internet Radio")

# TRUE fullscreen over desktop panel
root.attributes("-topmost", True)
root.overrideredirect(True)
root.update_idletasks()
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
root.geometry(f"{sw}x{sh}+0+0")

# Exit keys
root.focus_force()
root.bind_all("<Escape>", cleanup_and_exit)
root.bind_all("q", cleanup_and_exit)
root.bind_all("Q", cleanup_and_exit)

root.protocol("WM_DELETE_WINDOW", cleanup_and_exit)
signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ------------- Canvas + BG -------------
canvas = tk.Canvas(root, highlightthickness=0)
canvas.pack()

img = Image.open(SCALE_IMAGES[scale_idx])
W, H = img.size
photo = ImageTk.PhotoImage(img)

bg_item = canvas.create_image(0, 0, anchor="nw", image=photo)
canvas.config(width=W, height=H)
canvas.focus_set()

def load_bg(path: str):
    # IMPORTANT: keep reference to photo, otherwise white screen
    global img, photo, W, H
    img = Image.open(path)
    W, H = img.size
    photo = ImageTk.PhotoImage(img)
    canvas.itemconfigure(bg_item, image=photo)

def next_bg():
    global scale_idx
    scale_idx = (scale_idx + 1) % len(SCALE_IMAGES)
    load_bg(SCALE_IMAGES[scale_idx])

# -------------- Pointer ----------------
def idx_to_x(i: int) -> int:
    if len(stations) == 1:
        return W // 2
    span = (W - LEFT_MARGIN - RIGHT_MARGIN)
    return int(LEFT_MARGIN + (span * i) / (len(stations) - 1))

idx = 0
pointer = canvas.create_line(idx_to_x(idx), 0, idx_to_x(idx), H, width=4, fill="red")

def set_pointer(i: int):
    global idx
    idx = i % len(stations)
    x = idx_to_x(idx)
    canvas.coords(pointer, x, 0, x, H)

# --------------- HUD -------------------
vol_text = canvas.create_text(
    12, H-4,
    anchor="sw",
    text="VOL",
    fill="yellow",
    font=("DejaVu Sans", 12)
)
def show_vol(p):
    canvas.itemconfigure(vol_text, text=f"VOL: {p}%")

station_text = canvas.create_text(
    W-12, 12,
    anchor="ne",
    text="",
    fill="yellow",
    font=("DejaVu Sans", STATION_FONT_SIZE)
)
def show_station(name: str):
    canvas.itemconfigure(station_text, text=name)

# -------- Volume touch mapping ----------
def x_to_vol(x):
    return int(round((max(0, min(W, x)) / float(W)) * 100))

def handle_volume_touch(x):
    p = x_to_vol(x)
    if set_volume(p):
        show_vol(p)

# -------- Station controls --------------
def next_station():
    set_pointer(idx + 1)
    show_station(stations[idx][0])
    start_station(stations[idx][1])

def prev_station():
    set_pointer(idx - 1)
    show_station(stations[idx][0])
    start_station(stations[idx][1])

def toggle_play():
    global playing
    if playing:
        stop_vlc()
    else:
        show_station(stations[idx][0])
        start_station(stations[idx][1])

# ---- TOUCH HANDLER (Tk click/drag) ----
def on_touch_press(event):
    x, y = event.x, event.y

    # Bottom strip => volume
    if y >= (H - VOL_BAR_PX):
        handle_volume_touch(x)
        return

    # Top-left square => exit
    if x <= EXIT_BOX_PX and y <= EXIT_BOX_PX:
        cleanup_and_exit()
        return

    # Right edge strip: top half = next, bottom half = prev
    if x >= (W - EDGE_PX):
        if y < (H / 2):
            next_station()
        else:
            prev_station()
        return

    # Center tap => change background
    cx, cy = W / 2, H / 2
    if abs(x - cx) <= CENTER_ZONE_W and abs(y - cy) <= CENTER_ZONE_H:
        next_bg()
        return

def on_touch_drag(event):
    x, y = event.x, event.y
    if y >= (H - VOL_BAR_PX):
        handle_volume_touch(x)

canvas.bind("<Button-1>", on_touch_press)
canvas.bind("<B1-Motion>", on_touch_drag)

# ------------- Input device -------------
dev = InputDevice(detect_mouse())
dev.grab()

# Make evdev FD non-blocking (avoid set_blocking() compatibility issues)
try:
    os.set_blocking(dev.fd, False)
except Exception:
    pass

# Start first station immediately
show_station(stations[idx][0])
start_station(stations[idx][1])

def poll_input():
    global last_wheel_ts
    now = time.time()
    try:
        for e in dev.read():
            if e.type == ecodes.EV_REL and e.code == ecodes.REL_WHEEL:
                if now - last_wheel_ts < WHEEL_DEBOUNCE:
                    continue
                last_wheel_ts = now
                if e.value > 0:
                    next_station()
                else:
                    prev_station()

            elif e.type == ecodes.EV_KEY:
                if e.code == ecodes.BTN_LEFT and e.value == 1:
                    toggle_play()
                elif e.code == ecodes.BTN_RIGHT and e.value == 1:
                    cleanup_and_exit()

    except BlockingIOError:
        pass
    except OSError:
        pass

    root.after(10, poll_input)

poll_input()
root.mainloop()
