# Black Frame Detector - Claude Code Context

## Project Overview

A macOS desktop application for detecting black or near-black frames in video files using FFmpeg's blackframe filter. Built with Python/PySide6 and packaged as a self-contained .app for Apple Silicon Macs.

## Development Notes

Check `NOTES/` directory before starting any task:
- `NOTES/errors.md` - Error tracking with status (Open/Fixed)
- `NOTES/fixes.md` - Solutions and reusable patterns
- `NOTES/decisions.md` - Architecture and implementation decisions

See `NOTES/readme.md` for full workflow instructions.

## Key Files

| File | Purpose |
|------|---------|
| `black_frame_detector.py` | Main application source (single-file PySide6 GUI) |
| `black_frame_detector.spec` | PyInstaller configuration for ARM64 builds |
| `black_frame_detector-intel.spec` | PyInstaller configuration for Intel (x86_64) builds |
| `build.sh` | ARM64 build script (venv, deps, PyInstaller, codesigning) |
| `build-intel.sh` | Intel build script (uses Rosetta 2 on Apple Silicon) |
| `package_dmg.sh` | Creates ARM64 DMG with drag-to-Applications layout |
| `package_dmg-intel.sh` | Creates Intel DMG for distribution |
| `requirements.txt` | Python dependencies (PySide6, PyInstaller) |
| `LICENSES.txt` | FFmpeg GPL and Qt LGPL license notices |
| `logo.png` | Application logo (displayed in UI header) |
| `vendor/bin/` | Static ARM64 ffmpeg/ffprobe binaries (downloaded by build.sh) |
| `vendor/bin-intel/` | Static x86_64 ffmpeg/ffprobe binaries (downloaded by build-intel.sh) |

## Architecture

### FFmpeg Integration
- Uses `QProcess` for non-blocking subprocess execution
- Parses `blackframe` filter output from stderr via regex
- Progress tracking via `-progress pipe:1` (outputs to stdout in microseconds, not milliseconds)
- Forces `format=yuv420p` before blackframe filter for consistent results across codecs

### Key Design Decisions
1. **CPU-only decoding**: Hardware acceleration (videotoolbox) was removed because it breaks blackframe detection and is actually slower for this use case
2. **Static ffmpeg binaries**: Uses truly static ARM64 builds from osxexperts.net (Homebrew builds have dynamic library dependencies)
3. **Default thresholds**: threshold=32, amount=98% (more lenient than original spec to catch real-world black frames)
4. **Min run length**: Default 1 frame (detects single black frames)
5. **Sequential queue processing**: Multi-file batch processes files one at a time for predictable resource usage and per-file error isolation (see DEC-001)

### UI Components
- Header: Title ("Black Frame Detector"), info text, logo
- File selection: QListWidget with Add Files, Add Folder, Remove Selected, Clear All buttons; supports drag-and-drop of files and folders
- Detection settings: Mode (Standard/Strict), threshold, amount, range grouping
- Progress bar: Shows `[X/Y] filename` prefix with percentage + ETA countdown
- Results: Tabbed view (Frames / Ranges) with "File" as first column; export buttons for CSV/JSON

## Build Process

### Apple Silicon (ARM64) - Primary
```bash
./build.sh                    # Ad-hoc signing (local/team use)
./build.sh --sign "Dev ID"    # Developer ID signing
./package_dmg.sh              # Create DMG for distribution
```

### Intel (x86_64) - Secondary
```bash
./build-intel.sh              # Builds via Rosetta 2 on Apple Silicon
./build-intel.sh --sign "Dev ID"
./package_dmg-intel.sh        # Creates BlackFrameDetector-1.0.0-x86_64.dmg
```

The Intel build uses:
- Separate venv (`.venv-intel`) with x86_64 Python packages
- Intel FFmpeg binaries in `vendor/bin-intel/`
- `black_frame_detector-intel.spec` with `target_arch='x86_64'`
- System Python (`/usr/bin/python3`) which is a universal binary

Build script automatically:
1. Creates Python venv
2. Installs PySide6 + PyInstaller
3. Downloads static ffmpeg/ffprobe if not present
4. Runs PyInstaller with spec file
5. Codesigns the app bundle

## Common Issues & Solutions

### Progress bar jumps to 100% immediately
- **Cause**: ffmpeg's `out_time_ms` is actually in microseconds
- **Fix**: Divide by 1,000,000 instead of 1,000

### Black frames not detected
- **Cause**: Hardware acceleration interferes with blackframe filter
- **Fix**: Always use CPU decoding (no `-hwaccel` flag)

### Thresholds too strict
- **Cause**: Compressed video rarely has true RGB(0,0,0) black
- **Fix**: Use threshold=32, amount=98% as defaults

### App won't open on other Macs
- **Cause**: Gatekeeper blocks unsigned apps
- **Fix**: Right-click → Open, or use Developer ID signing + notarization

## Testing

Test video should include:
- 1 second of black (multiple frames)
- 2 frames of black
- 1 frame of black

All three should be detected with default settings.
