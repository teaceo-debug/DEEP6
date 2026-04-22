# NT8 DEEP6 Architecture Explorer

Invoke this skill when the user:
- Asks about file dependencies or "what depends on what"
- Gets CS0234/CS0246 errors about missing types or namespaces
- Wants to know what's deployed and working vs broken
- Plans a new file and needs to know what types already exist
- Asks "what's broken?", "why can't X compile?", "where is type Y defined?"
- Wants a map of the DEEP6 codebase

## Entry Point

1. Load `architecture.md` from this directory — current deployment state and dependency graph
2. For specific file questions: read the actual file being asked about
3. For missing types: cross-reference `architecture.md` "Missing Type Inventory" section

## Workflow

1. **Load** `architecture.md` to get the current architecture snapshot
2. **Answer** the specific question using the map + any file reads needed
3. **For broken deps**: describe exactly what types need to be created and in which namespace
4. **For new file planning**: check existing namespaces to avoid conflicts (CS0101)
5. **For fixing**: hand off to nt8-fix skill with the specific file + error info

## Base path: `C:\Users\Tea\DEEP6`
## NT8 Custom: `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\`
