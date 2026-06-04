# Trading Knowledge Center

Invoke this skill when the user asks you to:
- What is [trading concept]?
- Find strategies for [condition]
- What does DEEP6 signal [X] detect?
- How do I find NinjaTrader strategies?
- Document this trade setup
- What academic research supports [pattern]?
- Explain [order flow concept]

## Skill Entry Point

Load `knowledge.md` in this directory first. Then identify the query domain,
load the relevant domain file, and answer with references.

## Workflow

1. Read `knowledge.md` as the master index.
2. Identify the query domain.
3. Load the relevant domain, catalog, or reference file.
4. Answer using the indexed source files and absolute paths.
5. If multiple domains apply, use the minimum set of files needed.

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\`
