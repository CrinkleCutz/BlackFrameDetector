# NOTES Directory

Development tracking documents for Black Frame Detector V2.

## Files

| File | Purpose |
|------|---------|
| `errors.md` | Errors encountered (with status tracking) |
| `fixes.md` | Solutions that worked (reusable patterns) |
| `decisions.md` | Architecture and implementation decisions |

---

## Workflow

### BEFORE Starting Any Task
1. Read `errors.md` - Check for active (Open) issues
2. Read `fixes.md` - Review recent solutions and patterns
3. Read `decisions.md` - Understand past decisions

### WHEN You Encounter an Error
1. **Immediately** log in `errors.md`:
   - Date, component, exact error message
   - Status: Open
2. Cross-reference any related previous issues (ERR-XXX)

### AFTER Fixing an Issue
1. Document solution in `fixes.md`:
   - Problem description and link to error (ERR-XXX)
   - Exact solution/code that worked
   - Reusable pattern for future
2. Update error status to Fixed in `errors.md`

### FOR Important Decisions
1. Log in `decisions.md`:
   - What was decided and why
   - Alternatives considered
   - Expected trade-offs

---

## Quick Reference

| Situation | Action |
|-----------|--------|
| Starting work | Read all three files |
| Hit an error | Log in errors.md (Open) |
| Fixed something | Log in fixes.md, update errors.md (Fixed) |
| Made a choice | Log in decisions.md |

---

*Last updated: February 2026*
