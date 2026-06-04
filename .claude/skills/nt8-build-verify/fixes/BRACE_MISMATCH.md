# BRACE_MISMATCH — Unmatched braces or region directives

## Pattern
```
error CS1513: } expected
error CS1514: { expected
error CS1022: Type or namespace definition, or end-of-file expected
error CS0116: A namespace cannot directly contain members such as fields or methods
```
These errors often appear together and point to a location far from the actual mismatch.

## Root Causes (ordered by likelihood)
1. A closing `}` was deleted or never written, leaving a method, class, or namespace block open
2. An extra `{` was inserted (e.g., copy-paste of a block that already had its opening brace)
3. `#region` / `#endregion` imbalance — a `#region` was added without a matching `#endregion`, or vice versa (this doesn't cause a compile error but causes editor folding issues and can mask real brace errors)
4. A `using` block's `}` was removed, leaving the enclosed code at the wrong nesting level

## Fix Strategies

### Strategy 1: Count braces per scope level
- **Detect**: The compiler error points to a line near the end of the file, or to a line that looks syntactically correct. This is the classic sign of a brace mismatch earlier in the file.
- **Lookup**: Count opening `{` and closing `}` in the file. They must be equal. A quick count:
  ```powershell
  $src = Get-Content "path\to\File.cs" -Raw
  $open  = ($src.ToCharArray() | Where-Object { $_ -eq '{' }).Count
  $close = ($src.ToCharArray() | Where-Object { $_ -eq '}' }).Count
  Write-Host "Open: $open  Close: $close  Delta: $($open - $close)"
  ```
- **Fix**: If `open > close`, a `}` is missing. If `close > open`, there's an extra `}`. Locate the mismatch by scanning from the top, tracking depth. Insert or remove the brace at the correct location.
- **Verify**: After the fix, `open == close` and the file compiles without CS1513/CS1514.

### Strategy 2: Locate the mismatch by depth tracking
- **Detect**: The brace count is off by 1 or 2. The error line number is near the end of the file.
- **Lookup**: Walk the file line by line, maintaining a depth counter. Increment on `{`, decrement on `}`. The first line where depth goes negative (extra `}`) or the last line where depth is non-zero (missing `}`) is the mismatch site.
- **Fix**: Insert the missing `}` at the end of the block that was left open, or remove the extra `}` at the line where depth went negative.
- **Verify**: Depth reaches exactly 0 at the last line of the file.

```
Depth tracking example:
  namespace N {          // depth: 1
    public class C {     // depth: 2
      void M() {         // depth: 3
        if (x) {         // depth: 4
        }                // depth: 3
      // Missing }       // depth stays 3 — mismatch!
    }                    // depth: 2 (closes class, but method was never closed)
  }                      // depth: 1 (closes namespace)
                         // EOF at depth 1 — CS1513: } expected
```

### Strategy 3: Region/endregion imbalance
- **Detect**: The file uses `#region` / `#endregion` directives and the editor shows folding errors, or a `#endregion` appears without a matching `#region` (or vice versa).
- **Lookup**: Count `#region` and `#endregion` occurrences. They must be equal and properly nested.
  ```powershell
  Select-String -Path "File.cs" -Pattern "#region|#endregion"
  ```
- **Fix**: Add the missing `#endregion` at the end of the region block, or remove the orphaned `#endregion`. Region directives don't affect compilation but their imbalance can hide real brace errors in the editor.
- **Verify**: `#region` count equals `#endregion` count. The file compiles cleanly.

### Strategy 4: Copy-paste introduced duplicate opening brace
- **Detect**: A block of code was pasted and the paste included the opening `{` of the block, but the destination already had an opening `{` for that scope. The result is an extra `{` that opens a nested scope where none was intended.
- **Lookup**: Look for two consecutive `{` on adjacent lines without any code between them, or a `{` immediately after a method signature that already has a `{` on the same line.
- **Fix**: Remove the extra `{` and its matching `}` (which will be somewhere later in the file, closing the unintended nested scope).
- **Verify**: The method or block has exactly one opening and one closing brace.

## NT8-Specific Notes

- NT8 indicators and strategies have a fixed nesting structure: `namespace { class { method { } } }`. Any deviation from 3 levels of nesting (for a simple method) is suspicious.
- `OnStateChange`, `OnBarUpdate`, and `OnRender` are the most common sites for brace mismatches because they contain nested `if (State == ...)` blocks.
- After a brace fix, always run `nt8-ai-loop.ps1` to confirm the compile succeeds. Brace errors cascade — fixing one may reveal another.

## Example Fix

```diff
  protected override void OnStateChange()
  {
      if (State == State.SetDefaults)
      {
          Name = "DEEP6Footprint";
          Description = "Footprint chart renderer";
      }
      else if (State == State.DataLoaded)
      {
          _bidSeries = new Series<double>(this);
          _askSeries = new Series<double>(this);
-     // Missing closing brace for DataLoaded block — CS1513 fires at end of file
+     }
  }
```
