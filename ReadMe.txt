Prompt

Build a macOS desktop application called Black Frame Detector that lets a user select a video file and detect frames that are “black” (or near-black) using an FFmpeg-based approach. The target inputs are primarily H.264 or H.265 videos in common containers (MP4/MOV/MKV), at 1080p and UHD, and the analysis should run faster than real time when possible.

Core functionality

Provide a simple, modern, clean GUI (macOS-friendly) with:

A Browse… button to select a video file.

A prominent Start Analysis button and a Cancel option while running.

A progress indicator (determinate if duration is known; indeterminate if not).

A results view showing detected black frames with:

Frame number

Timestamp (HH:MM:SS.mmm)

% blackness (percentage of pixels classified as black)

Optionally compute and show black ranges by grouping consecutive black frames into runs (start/end frame, start/end time, length).

Export options:

Frames CSV / Frames JSON

Ranges CSV / Ranges JSON (if ranges enabled)

Detection specifics

Use FFmpeg for decode + analysis, specifically the blackframe filter.

Treat “pure black” pragmatically for compressed video:

Expose user controls for:

threshold (luma threshold below which a pixel is considered black; 0–50)

amount (percent of pixels that must be black; 90.00–100.00%)

Provide two presets:

Standard (practical for H.264): default threshold around 16, amount around 99.90

Strict (near-exact): threshold 0, amount 100.00

Force a consistent pixel format before analysis for reliability on 10-bit or odd formats:

e.g., include format=yuv420p (or equivalent) ahead of blackframe.

Include a Decode Acceleration option:

Default to videotoolbox on macOS.

Allow auto and none.

If hardware decode fails, auto-fallback once to CPU decode (none) and continue.

Implementation requirements

Implement as a single-file Python GUI app using PySide6 (Qt).

Run FFmpeg via a subprocess mechanism (e.g., Qt QProcess) and:

Parse FFmpeg output safely using buffered line parsing (avoid losing partial lines).

Batch UI updates for performance (avoid inserting table rows one-by-one under heavy hit counts).

Must remain responsive during scan; never freeze the UI thread.

Packaging and distribution requirements (Apple Silicon)

Package as a self-contained macOS .app that coworkers can run by double-clicking:

Coworkers must not need to install Python, PySide6, FFmpeg, or any dependencies.

The app must run on Apple Silicon (arm64) Macs.

Use PyInstaller to build the .app.

Bundle ffmpeg and ffprobe binaries inside the app, and ensure the app calls the bundled binaries when frozen (not relying on PATH).

Homebrew paths on Apple Silicon are typically:

/opt/homebrew/bin/ffmpeg

/opt/homebrew/bin/ffprobe

Provide a repeatable build procedure:

Create a venv, install dependencies, run PyInstaller with --windowed, and include --add-binary to embed ffmpeg/ffprobe (e.g., into a bin/ folder inside the bundle).

Improve end-user experience for Gatekeeper:

At minimum, perform ad-hoc codesigning (codesign --deep --sign -) as part of the build output.

If available, support Developer ID signing + notarization for frictionless opening on coworker machines.

Recommend distribution via a DMG (drag app to /Applications) or ZIP.

Include required license notices for bundled FFmpeg (LGPL/GPL depending on the build).

Deliverables

The complete Python source file.

The exact PyInstaller build command(s) for Apple Silicon.

Optional: a minimal packaging script that builds, signs, and creates a DMG/ZIP suitable for sharing with coworkers.