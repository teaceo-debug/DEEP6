# Common Compile Errors

Last verified: 2026-05-22

Use this file for the high-frequency non-coded errors found in real Pine work.

## Undeclared Identifier

Check in this order:
- typo
- missing namespace (`ta.`, `math.`, `str.`, `request.`)
- scope error: declared inside block, used outside
- version mismatch between old and new Pine syntax

## Cannot Call Function With Argument Type X; Expected Y

Most often this is a qualifier mismatch across `const`, `simple`, and `series`.

Repair pattern:
- inspect the function signature
- replace dynamic inputs with actual `input.*()` or literals where required
- do not assume `int()` or `float()` removes the `series` qualifier

## Mismatched Input / Syntax Spillover

Usually the flagged line is not the true root cause.
Inspect the previous 1–3 lines for:
- missing `)` or `]`
- unclosed string
- broken multiline ternary or function call
- stray comma

## Array / Object Guard Failures

Typical root causes:
- array access before size check
- calling setters on `na` line/label/box/table IDs
- loop bounds derived from empty arrays
