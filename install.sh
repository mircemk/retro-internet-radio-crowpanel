#!/bin/bash
set -e

echo "Installing Retro Internet Radio (CrowPanel)..."

sudo apt update
sudo apt install -y vlc python3-evdev python3-pil.imagetk

echo
echo "Installation finished."
echo "Run the radio with:"
echo "  ./retro_ui.py"
