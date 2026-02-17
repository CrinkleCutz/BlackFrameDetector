#!/bin/bash
#
# Black Frame Detector - Build Script
# Builds a self-contained macOS .app bundle for Apple Silicon (arm64)
#
# Usage:
#   ./build.sh                                    # Ad-hoc signing (local use)
#   ./build.sh --sign "Developer ID: Your Name"  # Developer ID signing
#   ./build.sh --sign "Developer ID: Your Name" --notarize  # Full notarization
#

set -e

# Configuration
APP_NAME="Black Frame Detector"
BUNDLE_NAME="Black Frame Detector.app"
VERSION="3.0.0"

# Parse arguments
SIGN_IDENTITY="-"
NOTARIZE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --sign)
            SIGN_IDENTITY="$2"
            shift 2
            ;;
        --notarize)
            NOTARIZE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--sign \"Developer ID Application: Name (TEAMID)\"] [--notarize]"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Black Frame Detector Build Script"
echo "============================================"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not found."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "Using: $PYTHON_VERSION"
echo ""

# Step 1: Create/activate virtual environment
echo "[1/5] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  Created new virtual environment"
else
    echo "  Using existing virtual environment"
fi

source .venv/bin/activate
echo "  Activated: $(which python)"
echo ""

# Step 2: Install dependencies
echo "[2/5] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Installed: PySide6, PyInstaller"
echo ""

# Step 3: Download static FFmpeg binaries
echo "[3/5] Checking FFmpeg binaries..."
mkdir -p vendor/bin

FFMPEG_PATH="vendor/bin/ffmpeg"
FFPROBE_PATH="vendor/bin/ffprobe"

download_ffmpeg() {
    echo "  Downloading static FFmpeg binaries for ARM64..."

    # Primary source: osxexperts.net (static builds)
    FFMPEG_URL="https://www.osxexperts.net/ffmpeg80arm.zip"
    FFPROBE_URL="https://www.osxexperts.net/ffprobe80arm.zip"

    # Alternative source (fallback): Martin Riedl's builds
    # FFMPEG_URL="https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"

    TEMP_DIR=$(mktemp -d)

    echo "  Downloading ffmpeg..."
    if curl -fsSL "$FFMPEG_URL" -o "$TEMP_DIR/ffmpeg.zip"; then
        unzip -o -q "$TEMP_DIR/ffmpeg.zip" -d "$TEMP_DIR"
        # Find the ffmpeg binary (might be in root or subdirectory)
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

    echo "  Downloading ffprobe..."
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
    echo "  ffmpeg not found in vendor/bin/"
    NEED_DOWNLOAD=true
elif [ ! -f "$FFPROBE_PATH" ]; then
    echo "  ffprobe not found in vendor/bin/"
    NEED_DOWNLOAD=true
else
    # Verify they are ARM64 binaries
    FFMPEG_ARCH=$(file "$FFMPEG_PATH" | grep -o "arm64\|x86_64" | head -1)
    if [ "$FFMPEG_ARCH" != "arm64" ]; then
        echo "  WARNING: ffmpeg is not ARM64, re-downloading..."
        NEED_DOWNLOAD=true
    else
        echo "  Using existing ARM64 ffmpeg/ffprobe binaries"
    fi
fi

if [ "$NEED_DOWNLOAD" = true ]; then
    if ! download_ffmpeg; then
        echo ""
        echo "  ============================================"
        echo "  MANUAL DOWNLOAD REQUIRED"
        echo "  ============================================"
        echo "  Could not auto-download FFmpeg binaries."
        echo "  Please manually download static ARM64 builds from:"
        echo ""
        echo "    https://www.osxexperts.net/ffmpeg80arm.zip"
        echo "    https://www.osxexperts.net/ffprobe80arm.zip"
        echo ""
        echo "  Or from: https://ffmpeg.martin-riedl.de"
        echo ""
        echo "  Extract and place the binaries in:"
        echo "    $SCRIPT_DIR/vendor/bin/ffmpeg"
        echo "    $SCRIPT_DIR/vendor/bin/ffprobe"
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
"$FFMPEG_PATH" -version | head -1
"$FFPROBE_PATH" -version | head -1
echo ""

# Step 4: Run PyInstaller
echo "[4/5] Building application with PyInstaller..."
rm -rf build dist

pyinstaller black_frame_detector.spec --noconfirm

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

# Notarization (if requested)
if [ "$NOTARIZE" = true ] && [ "$SIGN_IDENTITY" != "-" ]; then
    echo "============================================"
    echo "  Notarization"
    echo "============================================"
    echo ""
    echo "To notarize the app, run:"
    echo ""
    echo "  # First, create a ZIP for notarization:"
    echo "  ditto -c -k --keepParent \"dist/$BUNDLE_NAME\" \"dist/BlackFrameDetector-notarize.zip\""
    echo ""
    echo "  # Submit for notarization:"
    echo "  xcrun notarytool submit \"dist/BlackFrameDetector-notarize.zip\" \\"
    echo "      --keychain-profile \"notary\" --wait"
    echo ""
    echo "  # Staple the ticket to the app:"
    echo "  xcrun stapler staple \"dist/$BUNDLE_NAME\""
    echo ""
    echo "  Note: You must first store your credentials with:"
    echo "  xcrun notarytool store-credentials \"notary\" \\"
    echo "      --apple-id \"your@email.com\" \\"
    echo "      --team-id \"XXXXXXXXXX\" \\"
    echo "      --password \"app-specific-password\""
    echo ""
fi

# Summary
echo "============================================"
echo "  Build Complete"
echo "============================================"
echo ""
echo "  App location: dist/$BUNDLE_NAME"
echo ""
echo "  To test:"
echo "    open \"dist/$BUNDLE_NAME\""
echo ""
echo "  To create DMG for distribution:"
echo "    ./package_dmg.sh"
echo ""

# Deactivate venv
deactivate
