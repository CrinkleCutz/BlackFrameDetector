#!/bin/bash
#
# Black Frame Detector - Intel Build Script
# Builds a self-contained macOS .app bundle for Intel (x86_64)
# Can be run on Apple Silicon via Rosetta 2
#
# Usage:
#   ./build-intel.sh                                    # Ad-hoc signing (local use)
#   ./build-intel.sh --sign "Developer ID: Your Name"  # Developer ID signing
#

set -e

# Configuration
APP_NAME="Black Frame Detector"
BUNDLE_NAME="Black Frame Detector.app"
VERSION="1.0.0"
ARCH="x86_64"

# Parse arguments
SIGN_IDENTITY="-"

while [[ $# -gt 0 ]]; do
    case $1 in
        --sign)
            SIGN_IDENTITY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--sign \"Developer ID Application: Name (TEAMID)\"]"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Black Frame Detector Intel Build Script"
echo "============================================"
echo ""
echo "  Target Architecture: x86_64 (Intel)"
echo ""

# Check if running on Apple Silicon
MACHINE_ARCH=$(uname -m)
if [ "$MACHINE_ARCH" = "arm64" ]; then
    echo "  Building on Apple Silicon via Rosetta 2"
    ARCH_PREFIX="arch -x86_64"
else
    echo "  Building natively on Intel"
    ARCH_PREFIX=""
fi
echo ""

# Find a Python that supports x86_64
# System Python is universal binary, Homebrew/Miniconda are usually ARM64-only
echo "Checking x86_64 Python availability..."

PYTHON_CMD=""
for candidate in /usr/bin/python3 /usr/local/bin/python3 python3; do
    if [ -x "$(command -v $candidate)" ]; then
        if $ARCH_PREFIX $candidate --version &> /dev/null 2>&1; then
            PYTHON_CMD="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "ERROR: Cannot find a Python that supports x86_64 mode."
    echo ""
    echo "Your current Python ($(which python3)) is ARM64-only."
    echo "The system Python (/usr/bin/python3) should work if available."
    echo ""
    echo "Options:"
    echo "  1. Use system Python: export PATH=/usr/bin:\$PATH"
    echo "  2. Install universal Python from python.org"
    exit 1
fi

PYTHON_VERSION=$($ARCH_PREFIX $PYTHON_CMD --version 2>&1)
echo "Using: $PYTHON_VERSION (x86_64)"
echo "Binary: $PYTHON_CMD"
echo ""

# Step 1: Create/activate virtual environment for Intel
echo "[1/5] Setting up x86_64 Python virtual environment..."
VENV_DIR=".venv-intel"

if [ ! -d "$VENV_DIR" ]; then
    $ARCH_PREFIX $PYTHON_CMD -m venv "$VENV_DIR"
    echo "  Created new x86_64 virtual environment"
else
    echo "  Using existing x86_64 virtual environment"
fi

source "$VENV_DIR/bin/activate"
echo "  Activated: $(which python)"
echo ""

# Step 2: Install dependencies (under x86_64)
echo "[2/5] Installing Python dependencies (x86_64)..."
$ARCH_PREFIX pip install --upgrade pip -q
$ARCH_PREFIX pip install -r requirements.txt -q
echo "  Installed: PySide6, PyInstaller (x86_64)"
echo ""

# Step 3: Download static FFmpeg binaries for Intel
echo "[3/5] Checking Intel FFmpeg binaries..."
mkdir -p vendor/bin-intel

FFMPEG_PATH="vendor/bin-intel/ffmpeg"
FFPROBE_PATH="vendor/bin-intel/ffprobe"

download_ffmpeg_intel() {
    echo "  Downloading static FFmpeg binaries for Intel..."

    # osxexperts.net Intel builds
    FFMPEG_URL="https://www.osxexperts.net/ffmpeg80intel.zip"
    FFPROBE_URL="https://www.osxexperts.net/ffprobe80intel.zip"

    TEMP_DIR=$(mktemp -d)

    echo "  Downloading ffmpeg (Intel)..."
    if curl -fsSL "$FFMPEG_URL" -o "$TEMP_DIR/ffmpeg.zip"; then
        unzip -o -q "$TEMP_DIR/ffmpeg.zip" -d "$TEMP_DIR"
        FFMPEG_BIN=$(find "$TEMP_DIR" -name "ffmpeg" -type f | head -1)
        if [ -n "$FFMPEG_BIN" ]; then
            cp "$FFMPEG_BIN" "$FFMPEG_PATH"
            chmod +x "$FFMPEG_PATH"
            echo "  Downloaded ffmpeg successfully"
        else
            echo "  ERROR: ffmpeg binary not found in archive"
            rm -rf "$TEMP_DIR"
            return 1
        fi
    else
        echo "  ERROR: Failed to download ffmpeg"
        rm -rf "$TEMP_DIR"
        return 1
    fi

    echo "  Downloading ffprobe (Intel)..."
    if curl -fsSL "$FFPROBE_URL" -o "$TEMP_DIR/ffprobe.zip"; then
        unzip -o -q "$TEMP_DIR/ffprobe.zip" -d "$TEMP_DIR"
        FFPROBE_BIN=$(find "$TEMP_DIR" -name "ffprobe" -type f | head -1)
        if [ -n "$FFPROBE_BIN" ]; then
            cp "$FFPROBE_BIN" "$FFPROBE_PATH"
            chmod +x "$FFPROBE_PATH"
            echo "  Downloaded ffprobe successfully"
        else
            echo "  ERROR: ffprobe binary not found in archive"
            rm -rf "$TEMP_DIR"
            return 1
        fi
    else
        echo "  ERROR: Failed to download ffprobe"
        rm -rf "$TEMP_DIR"
        return 1
    fi

    rm -rf "$TEMP_DIR"
    return 0
}

# Check if we need to download FFmpeg
NEED_DOWNLOAD=false
if [ ! -f "$FFMPEG_PATH" ]; then
    echo "  ffmpeg not found in vendor/bin-intel/"
    NEED_DOWNLOAD=true
elif [ ! -f "$FFPROBE_PATH" ]; then
    echo "  ffprobe not found in vendor/bin-intel/"
    NEED_DOWNLOAD=true
else
    # Verify they are x86_64 binaries
    FFMPEG_ARCH=$(file "$FFMPEG_PATH" | grep -o "arm64\|x86_64" | head -1)
    if [ "$FFMPEG_ARCH" != "x86_64" ]; then
        echo "  WARNING: ffmpeg is not x86_64, re-downloading..."
        NEED_DOWNLOAD=true
    else
        echo "  Using existing x86_64 ffmpeg/ffprobe binaries"
    fi
fi

if [ "$NEED_DOWNLOAD" = true ]; then
    if ! download_ffmpeg_intel; then
        echo ""
        echo "  ============================================"
        echo "  MANUAL DOWNLOAD REQUIRED"
        echo "  ============================================"
        echo "  Could not auto-download Intel FFmpeg binaries."
        echo "  Please manually download static x86_64 builds from:"
        echo ""
        echo "    https://www.osxexperts.net/ffmpeg80intel.zip"
        echo "    https://www.osxexperts.net/ffprobe80intel.zip"
        echo ""
        echo "  Or from: https://evermeet.cx/ffmpeg/"
        echo ""
        echo "  Extract and place the binaries in:"
        echo "    $SCRIPT_DIR/vendor/bin-intel/ffmpeg"
        echo "    $SCRIPT_DIR/vendor/bin-intel/ffprobe"
        echo ""
        echo "  Then re-run this script."
        echo "  ============================================"
        exit 1
    fi
fi

# Verify binaries are executable
chmod +x "$FFMPEG_PATH" "$FFPROBE_PATH"

# Quick sanity check
echo "  Verifying binaries..."
$ARCH_PREFIX "$FFMPEG_PATH" -version | head -1
$ARCH_PREFIX "$FFPROBE_PATH" -version | head -1
echo ""

# Step 4: Run PyInstaller
echo "[4/5] Building application with PyInstaller (x86_64)..."
rm -rf build dist

$ARCH_PREFIX pyinstaller black_frame_detector-intel.spec --noconfirm

if [ ! -d "dist/$BUNDLE_NAME" ]; then
    echo "ERROR: PyInstaller failed to create app bundle"
    exit 1
fi

echo "  Built: dist/$BUNDLE_NAME"
echo ""

# Step 5: Code signing
echo "[5/5] Signing application..."
if [ "$SIGN_IDENTITY" = "-" ]; then
    echo "  Performing ad-hoc signing (local use only)..."
else
    echo "  Signing with: $SIGN_IDENTITY"
fi

# Sign the bundled ffmpeg/ffprobe first
codesign --force --sign "$SIGN_IDENTITY" "dist/$BUNDLE_NAME/Contents/MacOS/bin/ffmpeg" 2>/dev/null || true
codesign --force --sign "$SIGN_IDENTITY" "dist/$BUNDLE_NAME/Contents/MacOS/bin/ffprobe" 2>/dev/null || true

# Sign the entire app bundle
codesign --deep --force --sign "$SIGN_IDENTITY" "dist/$BUNDLE_NAME"

echo "  Signed successfully"
echo ""

# Verify signature
echo "Verifying signature..."
codesign --verify --deep --strict "dist/$BUNDLE_NAME" && echo "  Signature valid" || echo "  WARNING: Signature verification failed"
echo ""

# Summary
echo "============================================"
echo "  Intel Build Complete"
echo "============================================"
echo ""
echo "  App location: dist/$BUNDLE_NAME"
echo "  Architecture: x86_64 (Intel)"
echo ""
echo "  To test (runs via Rosetta on Apple Silicon):"
echo "    open \"dist/$BUNDLE_NAME\""
echo ""
echo "  To create DMG for distribution:"
echo "    ./package_dmg-intel.sh"
echo ""

# Deactivate venv
deactivate
