#!/bin/bash
#
# Black Frame Detector - DMG Packaging Script
# Creates a distributable DMG with a professional layout
#
# Requires: brew install create-dmg
#

set -e

# Configuration
APP_NAME="Black Frame Detector"
BUNDLE_NAME="Black Frame Detector.app"
VERSION="3.0.0"
DMG_NAME="BlackFrameDetector-${VERSION}-arm64.dmg"
VOLUME_NAME="Black Frame Detector"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Black Frame Detector DMG Packager"
echo "============================================"
echo ""

# Check if app exists
if [ ! -d "dist/$BUNDLE_NAME" ]; then
    echo "ERROR: App not found at dist/$BUNDLE_NAME"
    echo "Please run ./build.sh first"
    exit 1
fi

# Check for create-dmg
if ! command -v create-dmg &> /dev/null; then
    echo "create-dmg not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install create-dmg
    else
        echo "ERROR: Homebrew not installed."
        echo "Please install create-dmg manually:"
        echo "  brew install create-dmg"
        exit 1
    fi
fi

# Remove old DMG if exists
if [ -f "dist/$DMG_NAME" ]; then
    echo "Removing existing DMG..."
    rm "dist/$DMG_NAME"
fi

# Copy license file to dist for inclusion
if [ -f "LICENSES.txt" ]; then
    cp "LICENSES.txt" "dist/"
fi

echo "Creating DMG..."
echo ""

# Create DMG with professional layout
create-dmg \
    --volname "$VOLUME_NAME" \
    --volicon "dist/$BUNDLE_NAME/Contents/Resources/AppIcon.icns" 2>/dev/null || true \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "$BUNDLE_NAME" 140 190 \
    --hide-extension "$BUNDLE_NAME" \
    --app-drop-link 460 190 \
    --no-internet-enable \
    "dist/$DMG_NAME" \
    "dist/$BUNDLE_NAME"

# Note: If the above fails due to no icon, try simpler version
if [ ! -f "dist/$DMG_NAME" ]; then
    echo "Trying simplified DMG creation..."
    create-dmg \
        --volname "$VOLUME_NAME" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "$BUNDLE_NAME" 140 190 \
        --hide-extension "$BUNDLE_NAME" \
        --app-drop-link 460 190 \
        --no-internet-enable \
        "dist/$DMG_NAME" \
        "dist/$BUNDLE_NAME"
fi

if [ -f "dist/$DMG_NAME" ]; then
    echo ""
    echo "============================================"
    echo "  DMG Created Successfully"
    echo "============================================"
    echo ""
    echo "  DMG: dist/$DMG_NAME"
    echo "  Size: $(du -h "dist/$DMG_NAME" | cut -f1)"
    echo ""
    echo "  To notarize the DMG (after app notarization):"
    echo "    xcrun notarytool submit \"dist/$DMG_NAME\" \\"
    echo "        --keychain-profile \"notary\" --wait"
    echo "    xcrun stapler staple \"dist/$DMG_NAME\""
    echo ""
else
    echo ""
    echo "ERROR: Failed to create DMG"
    echo ""
    echo "Falling back to simple ZIP archive..."
    cd dist
    zip -r "BlackFrameDetector-${VERSION}-arm64.zip" "$BUNDLE_NAME"
    cd ..
    echo "Created: dist/BlackFrameDetector-${VERSION}-arm64.zip"
fi
