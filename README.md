# Black Frame Detector

A macOS application for detecting black or near-black frames in video files.

## Features

- Detect black frames in video files with adjustable sensitivity
- **Multi-file batch processing** -- add multiple files or entire folders at once
- **Drag-and-drop** -- drop files or folders onto the window to add them
- **Per-file status lines** -- see results for each file as it completes, right below the progress bar
- Support for common video formats (MP4, MOV, MKV, M4V, AVI, MTS, M2TS, WEBM, WMV, FLV, TS, VOB, MPG, MPEG)
- Support for popular codecs (H.264, H.265/HEVC, ProRes, DNxHD)
- Works with SD, HD (720p/1080p), and UHD (4K) resolutions
- Real-time progress with ETA countdown showing current file and queue position
- Group consecutive black frames into ranges
- Export results to CSV or JSON with per-file identification
- Faster than real-time analysis on most content

## Installation

### From GitHub Releases (Recommended)

1. Go to the [Releases](../../releases) page
2. Download the `.dmg` file for your architecture (ARM64 for Apple Silicon, x86_64 for Intel)
3. Double-click the DMG to mount it
4. Drag "Black Frame Detector" to Applications
5. **First launch**: Right-click the app → "Open" → Click "Open" in the dialog

After the first launch, the app will open normally.

> If no release is available yet, see [Building from Source](#building-from-source) below.

### Requirements

- macOS 10.15 (Catalina) or later for Intel Macs
- macOS 11.0 (Big Sur) or later for Apple Silicon Macs
- Apple Silicon (M1/M2/M3/M4) or Intel processor

## Usage

1. Add video files using any of these methods:
   - Click **Add Files...** to select one or more video files
   - Click **Add Folder...** to scan a folder (including subfolders) for videos
   - **Drag and drop** files or folders directly onto the application window
2. Adjust detection settings if needed:
   - **Detection Mode**: Standard (recommended) or Strict
   - **Black Threshold**: Higher = more lenient (default: 32)
   - **Pixel Blackness**: Lower = more lenient (default: 98%)
   - **Min Run Length**: Minimum consecutive frames to report as a range
3. Click **Start Analysis** -- files are processed sequentially with progress shown as `[1/N]`
4. Watch per-file results appear below the progress bar as each file completes
5. View detailed results in the Frames or Ranges tab (each row shows which file it belongs to)
6. Export results using the CSV/JSON buttons (exports include a "file" column)

### Detection Modes

| Mode | Threshold | Amount | Use Case |
|------|-----------|--------|----------|
| Standard | 32 | 98% | Most compressed video (H.264, H.265) |
| Strict | 0 | 100% | Uncompressed or exact black detection |

## Building from Source

### Prerequisites

- Python 3.11+
- macOS with Apple Silicon

### Build Steps (Apple Silicon)

```bash
# Clone or download the project
cd BlackFrameDetector

# Make scripts executable
chmod +x build.sh package_dmg.sh

# Build the app (downloads ffmpeg automatically)
./build.sh

# Create distributable DMG
./package_dmg.sh
```

The built app will be at `dist/Black Frame Detector.app`
The DMG will be at `dist/BlackFrameDetector-3.0.0-arm64.dmg`

### Build Steps (Intel)

Building for Intel Macs can be done on Apple Silicon via Rosetta 2:

```bash
# Make Intel scripts executable
chmod +x build-intel.sh package_dmg-intel.sh

# Build the Intel version (uses Rosetta 2)
./build-intel.sh

# Create distributable DMG
./package_dmg-intel.sh
```

The Intel DMG will be at `dist/BlackFrameDetector-3.0.0-x86_64.dmg`

### Developer ID Signing (Optional)

For distribution without Gatekeeper warnings:

```bash
# Build with Developer ID
./build.sh --sign "Developer ID Application: Your Name (TEAMID)"

# Create and notarize DMG
./package_dmg.sh
xcrun notarytool submit "dist/BlackFrameDetector-3.0.0-arm64.dmg" \
    --keychain-profile "notary" --wait
xcrun stapler staple "dist/BlackFrameDetector-3.0.0-arm64.dmg"
```

## Project Structure

```
BlackFrameDetector/
├── black_frame_detector.py         # Main application
├── black_frame_detector.spec       # PyInstaller config (ARM64)
├── black_frame_detector-intel.spec # PyInstaller config (Intel)
├── build.sh                        # ARM64 build script
├── build-intel.sh                  # Intel build script
├── package_dmg.sh                  # ARM64 DMG creation
├── package_dmg-intel.sh            # Intel DMG creation
├── requirements.txt                # Python dependencies
├── logo.png                        # Application logo
├── logo2.png                       # Banner background image
├── LICENSES.txt                    # Third-party licenses
├── CLAUDE.md                       # Claude Code context
├── README.md                       # This file
├── NOTES/                          # Development tracking
└── vendor/
    ├── bin/                        # ARM64 ffmpeg/ffprobe
    └── bin-intel/                  # Intel ffmpeg/ffprobe
```

## Technical Details

- Built with Python and PySide6 (Qt for Python)
- Uses FFmpeg's `blackframe` filter for detection
- Packaged with PyInstaller for standalone distribution
- Bundles static ARM64 FFmpeg binaries (no dependencies required)

## License

This application bundles FFmpeg which is licensed under the GPL. See `LICENSES.txt` for details.

## Troubleshooting

### App won't open ("damaged" or "unidentified developer")

Right-click the app → "Open" → Click "Open" in the security dialog.

### No black frames detected

Try lowering the detection sensitivity:
- Increase **Black Threshold** (e.g., 40-50)
- Decrease **Pixel Blackness** (e.g., 95%)

### Analysis seems stuck

The progress bar shows accurate progress with ETA. Large or high-resolution files may take longer. You can click **Cancel** at any time.
