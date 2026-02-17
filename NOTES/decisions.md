# Decisions Log - Black Frame Detector V2

Track architectural and implementation decisions with context and rationale.

---

## Template

```markdown
### [DEC-XXX] Decision Title
**Date**: YYYY-MM-DD
**Status**: Accepted | Superseded | Deprecated
**Supersedes**: DEC-XXX (if applicable)

**Context**:
- What problem or need prompted this decision

**Options Considered**:
1. **Option A**: Description
   - Pros: ...
   - Cons: ...
2. **Option B**: Description
   - Pros: ...
   - Cons: ...

**Decision**:
- What was chosen and why

**Consequences**:
- What this decision enables or constrains

**Related**: DEC-XXX, ERR-XXX
```

---

## Archived Decisions (Pre-Session)

No archived decisions yet. This is a fresh tracking system.

---

## Current Session Decisions

### [DEC-001] Multi-File Queue-Based Batch Processing
**Date**: 2026-02-04
**Status**: Accepted

**Context**:
- Original app processed one video file at a time
- Users working with multi-file shoots need to analyze many files in one session
- Need drag-and-drop support for fast workflow

**Options Considered**:
1. **Single file (original)**: One file at a time via QLineEdit + Browse
   - Pros: Simple state management
   - Cons: Tedious for batches, no drag-and-drop
2. **Parallel processing**: Multiple ffmpeg processes at once
   - Pros: Faster total time
   - Cons: High CPU/memory, complex process management, unreliable progress tracking
3. **Sequential queue**: Process files one at a time in order
   - Pros: Predictable resource usage, clear progress (1/N, 2/N...), per-file error isolation
   - Cons: Total time is sum of individual times

**Decision**:
- Sequential queue with QListWidget for file management
- Per-file results stored in `all_hits` / `all_ranges` dicts keyed by path
- Scratch vars (`hits`, `ranges`) reset between files
- Failed files marked red and skipped, queue continues

**Consequences**:
- Tables and exports include "File" column
- Cancel mid-queue preserves completed results
- Single file still works identically (queue of 1)
- UI disables file list and buttons during analysis

**Files Modified**:
- `black_frame_detector.py` - All changes in single file

<!-- Add new decisions below this line -->
