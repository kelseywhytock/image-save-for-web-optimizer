#!/bin/bash
# Image Optimizer installer (v1.1.3)
#
# Downloads the prebuilt app from this repo with curl, verifies its SHA-256,
# and installs it. Files fetched with curl never get the browser quarantine
# flag, so macOS does not show "Apple could not verify ... is free of malware".
#
# Safety:
#   - downloads only from github.com/kelseywhytock/image-save-for-web-optimizer
#   - refuses to install if the zip does not match the checksum below
#   - only writes Image Optimizer.app (and a temp dir it removes on exit)
#   - needs no sudo
#
# Usage:
#   bash install.sh
#   INSTALL_DIR="$HOME/Applications" bash install.sh   # custom location

set -euo pipefail

ZIP_URL="https://raw.githubusercontent.com/kelseywhytock/image-save-for-web-optimizer/main/releases/ImageOptimizer-1.1.3.zip"
ZIP_SHA256="8f01bc00f5ad281680359ad641689aa468c2949aac9d4783e31fc47bd85f2e67"
APP_NAME="Image Optimizer.app"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This app is macOS only." >&2
  exit 1
fi

# Default to /Applications, fall back to ~/Applications if it isn't writable.
INSTALL_DIR="${INSTALL_DIR:-/Applications}"
if [ ! -w "$INSTALL_DIR" ]; then
  INSTALL_DIR="$HOME/Applications"
  mkdir -p "$INSTALL_DIR"
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "Downloading Image Optimizer..."
curl -fL --progress-bar -o "$WORK_DIR/app.zip" "$ZIP_URL"

echo "Verifying checksum..."
ACTUAL_SHA256="$(shasum -a 256 "$WORK_DIR/app.zip" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$ZIP_SHA256" ]; then
  echo "Checksum mismatch, not installing." >&2
  echo "  expected: $ZIP_SHA256" >&2
  echo "  actual:   $ACTUAL_SHA256" >&2
  exit 1
fi

echo "Unpacking..."
ditto -x -k "$WORK_DIR/app.zip" "$WORK_DIR/unpacked"
if [ ! -d "$WORK_DIR/unpacked/$APP_NAME" ]; then
  echo "Unexpected zip contents, not installing." >&2
  exit 1
fi

if [ -d "$INSTALL_DIR/$APP_NAME" ]; then
  echo "Replacing existing $INSTALL_DIR/$APP_NAME"
  rm -rf "$INSTALL_DIR/$APP_NAME"
fi
ditto "$WORK_DIR/unpacked/$APP_NAME" "$INSTALL_DIR/$APP_NAME"

# Clear any quarantine flag (a no-op for curl downloads, kept for safety).
xattr -dr com.apple.quarantine "$INSTALL_DIR/$APP_NAME" 2>/dev/null || true

codesign --verify --deep --strict "$INSTALL_DIR/$APP_NAME"

echo
echo "Installed: $INSTALL_DIR/$APP_NAME"
echo "Drop images onto it, or right-click it > Make Alias."
