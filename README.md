Fullscreen retro-style internet radio for Raspberry Pi + CrowPanel industrial touch display (1280×720).

## Features
- Fullscreen retro radio scale + moving pointer
- VLC streaming (HTTPS-friendly)
- USB mouse / rotary encoder (mouse-compatible)
- Touch zones:
  - Top-left corner: Exit
  - Right edge (top half): Next station
  - Right edge (bottom half): Previous station
  - Bottom strip: Volume (slide)
  - Center tap: Switch background (scale1/2/3)

## Hardware tested
- Elecrow Pi Terminal / CrowPanel (CM4) industrial touch panel
- 1280×720 display

## Install (fresh OS)
```bash
sudo apt update
sudo apt install -y vlc python3-evdev python3-pil.imagetk
git clone https://github.com/mircemk/retro-internet-radio-crowpanel.git
cd retro-internet-radio-crowpanel
chmod +x retro_ui.py
./retro_ui.py
