# Notes System Documentation

## What It Does

The Notes system is a markdown-based development knowledge base that tracks three things across sessions:

1. **Errors** (`NOTES/errors.md`) -- Bugs, crashes, and unexpected behavior encountered during development. Each error gets a unique ID (ERR-001, ERR-002, ...) and a status (Open, Fixed, Workaround).

2. **Fixes** (`NOTES/fixes.md`) -- Solutions that worked, with code examples and reusable patterns. Each fix gets a unique ID (FIX-001, FIX-002, ...) and cross-references the error it solved.

3. **Decisions** (`NOTES/decisions.md`) -- Architecture and implementation choices with rationale. Each decision gets a unique ID (DEC-001, DEC-002, ...) and records what alternatives were considered and why one was chosen.

The system ensures that knowledge isn't lost between sessions. When Claude Code starts a new task, it reads these files first to avoid repeating mistakes and to stay consistent with past decisions.

## Files

```
BlackFrameDetector_v2/
├── .clinerules              # Tells Claude Code to check NOTES/ before every task
├── CLAUDE.md                # Project context (references NOTES/)
├── NOTES-SYSTEM.md          # This file
└── NOTES/
    ├── readme.md            # Workflow instructions and quick reference
    ├── errors.md            # Error tracking log
    ├── fixes.md             # Solution and pattern log
    └── decisions.md         # Decision log
```

## Where Notes Are Stored

All notes live in the `NOTES/` directory as plain markdown files. No database, no special tooling -- just text files that are easy to read, search, and version control.

## How to Use It

### Before Starting Work

Read all three files to understand current state:

```
NOTES/errors.md      -- Any open issues?
NOTES/fixes.md       -- Recent patterns to reuse?
NOTES/decisions.md   -- Past decisions to respect?
```

### Adding an Error

When you hit a bug or unexpected behavior, add to `NOTES/errors.md`:

```markdown
### [ERR-001] Progress bar shows wrong percentage
**Date**: 2026-02-04
**Component**: black_frame_detector.py
**Severity**: Medium
**Status**: Open

**Symptoms**:
- Progress bar jumps to 100% immediately when analysis starts

**Root Cause**:
- ffmpeg's out_time_ms field is in microseconds, not milliseconds

**Fix Applied**:
- (none yet)

**Lesson Learned**:
- (to be filled when fixed)
```

### Adding a Fix

When you solve the error, add to `NOTES/fixes.md` and update the error status:

```markdown
### [FIX-001] Correct progress bar time unit
**Date**: 2026-02-04
**Related Error**: ERR-001
**Component**: black_frame_detector.py

**Problem**:
- Progress bar jumped to 100% immediately

**Solution**:
- Divide out_time_ms by 1,000,000 instead of 1,000

**Code**:
```python
# Before
dur_ms = int(self.video_duration_s * 1_000)
frac = out_time_ms / dur_ms

# After
dur_us = int(self.video_duration_s * 1_000_000)
frac = out_time_us / dur_us
```

**Why It Works**:
- Despite the name, ffmpeg's out_time_ms outputs microseconds

**Reusable Pattern**:
- Always verify units in ffmpeg progress output fields
```

Then update ERR-001's status from `Open` to `Fixed`.

### Adding a Decision

When making an architecture or design choice, add to `NOTES/decisions.md`:

```markdown
### [DEC-001] Multi-file batch processing over single-file
**Date**: 2026-02-04
**Status**: Accepted

**Context**:
- Users need to analyze multiple video files from a shoot

**Options Considered**:
1. **Single file (original)**: One file at a time
   - Pros: Simple
   - Cons: Tedious for large batches
2. **Queue-based batch**: Process files sequentially with shared results
   - Pros: Handles batches, preserves per-file results
   - Cons: More complex state management

**Decision**:
- Queue-based batch processing with per-file results stored in dicts

**Consequences**:
- Tables and exports now include a "file" column
- Queue can be cancelled mid-run with partial results preserved
```

### ID Numbering

IDs are sequential within each file:
- Errors: ERR-001, ERR-002, ERR-003, ...
- Fixes: FIX-001, FIX-002, FIX-003, ...
- Decisions: DEC-001, DEC-002, DEC-003, ...

Cross-reference between files using these IDs (e.g., "**Related Error**: ERR-003").

### Status Values

**Errors**: Open | Fixed | Workaround
**Decisions**: Accepted | Superseded | Deprecated

When a decision is replaced by a newer one, mark the old one as `Superseded` and add `**Supersedes**: DEC-XXX` to the new one.

## Enforcement

The `.clinerules` file instructs Claude Code to read all three NOTES files before starting any task. This ensures continuity across sessions.
