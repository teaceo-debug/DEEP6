# NT8 Skills Coverage Matrix

**Purpose:** Single source of truth mapping every H2/H3 section from all NT8 source knowledge files to exactly one target skill.

**Target Skills:**
- `machine-profile` — NT8 platform, installation, editor, paths, state machine lifecycle, namespace rules
- `builder-doctor` — NinjaScript development patterns, indicators, strategies, SharpDX, Draw.*, threading, properties, order management, Pine→NinjaScript
- `error-doctor` — CS error codes, runtime exceptions, SharpDX crashes, behavioral bugs, NT7→NT8 migration
- `nt8-expert-wrapper` — DEEP6-specific deployment, file inventory, dev API (localhost:19206)
- `nt8-fix-wrapper` — DEEP6-specific error context (FootprintBar.cs rule, DEEP6 namespace conflicts)
- `nt8-new-wrapper` — DEEP6-specific code gen workflow (deploy→compile→fix loop with DEEP6 scripts)
- `nt8-architect` — UNCHANGED (100% DEEP6-specific: deployment status, dependency graph, L1-L7 architecture)
- `DISCARD` — Redundant, obsolete, or duplicated content (agent identity, response protocols)

**Header counts:**
- ULTIMATE: 78 H2, 185 H3
- SURGEON: 12 H2, 67 H3
- CONTEXT: 15 H2, 0 H3
- EXPERT: 27 H2, 16 H3
- FIX: 10 H2, 9 H3
- NEW: 10 H2, 3 H3
- ARCH: 6 H2, 5 H3

---

## Source: ULTIMATE-NINJASCRIPT-AGENT-v5.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## ROLE & IDENTITY | DISCARD | Agent identity section — not domain knowledge |
| ## NT8 RUNTIME ARCHITECTURE | machine-profile | Platform fundamentals: execution model, object hierarchy, namespaces |
| ### The NinjaScript Execution Model | machine-profile | Core execution model belongs in platform skill |
| ### NinjaScript Object Hierarchy | machine-profile | Platform object hierarchy |
| ### Key Namespace Imports (Always Include) | machine-profile | Namespace rules are platform-level |
| ## STATE MACHINE - COMPLETE REFERENCE | machine-profile | State machine is core platform lifecycle |
| ### All States in Order | machine-profile | Platform lifecycle states |
| ### Critical State Ordering Rules | machine-profile | Platform lifecycle rules |
| ### State Guards in OnBarUpdate | builder-doctor | Guard patterns are development patterns (SHARED-fundamental: also in machine-profile; primary owner builder-doctor because it's a coding pattern) |
| ## CALCULATE MODES - DEEP DIVE | machine-profile | Calculate modes are platform configuration |
| ### When to Use Each Mode | machine-profile | Platform configuration guidance |
| ### IsFirstTickOfBar Pattern | builder-doctor | Coding pattern for tick-level work |
| ## BARS & SERIES - COMPLETE API | builder-doctor | API usage patterns for development |
| ### Primary Bar Data Access | builder-doctor | Development API patterns |
| ### Series<T> - Custom Data Series | builder-doctor | Development API patterns |
| ### Multi-Series Data Access | builder-doctor | Development API patterns |
| ### ISeries<T> - Interface for Indicator Chaining | builder-doctor | Development API patterns |
| ### BarsPeriodType - All Bar Types | machine-profile | Platform bar type enumeration |
| ## PLOTS AND LINES - COMPLETE API | builder-doctor | Indicator output API — development patterns |
| ### AddPlot Overloads | builder-doctor | Development API |
| ### PlotStyle Enum | builder-doctor | Development API |
| ### Accessing Plots in OnBarUpdate | builder-doctor | Development pattern |
| ### AddLine | builder-doctor | Development API |
| ## INDICATOR PROPERTIES & ATTRIBUTES - COMPLETE REFERENCE | builder-doctor | Property decoration patterns |
| ### Display Attributes | builder-doctor | Development patterns |
| ### Indicator Display Properties | builder-doctor | Development patterns |
| ## INDICATOR PANEL MANAGEMENT | builder-doctor | Development patterns for panel placement |
| ## CHILD INDICATOR INSTANCES | builder-doctor | Indicator chaining patterns |
| ### Built-In Indicators (Callable as Methods) | builder-doctor | Development API reference |
| ## DRAW.* API - COMPLETE REFERENCE | builder-doctor | Draw.* is a development API |
| ### Draw.Line / Ray / Arrow | builder-doctor | Development API |
| ### Draw.Rectangle / Region | builder-doctor | Development API |
| ### Draw.Text / TextFixed | builder-doctor | Development API |
| ### Draw.Triangle / Diamond / Ellipse | builder-doctor | Development API |
| ### Draw.FibonacciRetracements | builder-doctor | Development API |
| ### Draw Object Management | builder-doctor | Development patterns |
| ## MARKET DATA EVENTS | builder-doctor | Event handler patterns |
| ### OnMarketData - Level 1 Data | builder-doctor | Development API patterns |
| ### OnMarketDepth - Level 2 / DOM Data | builder-doctor | Development API patterns |
| ## INSTRUMENT & TICK SIZE | builder-doctor | Instrument access patterns |
| ### Accessing Instrument Details | builder-doctor | Development API |
| ### Session/Trading Hours | builder-doctor | Development API |
| ## STRATEGY SYSTEM - COMPLETE API | builder-doctor | Strategy development patterns |
| ### SetDefaults for Strategies | builder-doctor | Development patterns |
| ## ORDER MANAGEMENT - COMPLETE REFERENCE | builder-doctor | Order management development patterns |
| ### Market Orders | builder-doctor | Development API |
| ### Limit Orders | builder-doctor | Development API |
| ### Stop Orders | builder-doctor | Development API |
| ### SetStopLoss & SetProfitTarget | builder-doctor | Development API |
| ### Order Object Tracking | builder-doctor | Development patterns |
| ### OnExecutionUpdate | builder-doctor | Development API |
| ### OnPositionUpdate | builder-doctor | Development API |
| ### Position Properties | builder-doctor | Development API |
| ## ATM STRATEGY INTEGRATION | builder-doctor | ATM integration development patterns |
| ## ACCOUNT & PERFORMANCE ACCESS | builder-doctor | Development API |
| ## SHARPDX RENDERING - COMPLETE GUIDE | builder-doctor | SharpDX rendering PATTERNS (crashes go to error-doctor) |
| ### RenderTarget Reference | builder-doctor | SharpDX development API |
| ### Complete Brush Management Pattern | builder-doctor | SharpDX development pattern |
| ### Linear Gradient Brush | builder-doctor | SharpDX development pattern |
| ### Path Geometry (Arrows, Custom Shapes) | builder-doctor | SharpDX development pattern |
| ### Text Rendering - Full Pattern | builder-doctor | SharpDX development pattern |
| ### Coordinate Mapping - Complete System | builder-doctor | SharpDX development pattern |
| ### Anti-Aliasing & Stroke Styles | builder-doctor | SharpDX development pattern |
| ## VOLUME PROFILE ENGINE - PRODUCTION IMPLEMENTATION | builder-doctor | Production implementation pattern |
| ### Session Volume Profile (Full Implementation) | builder-doctor | Production implementation |
| ### Volume Profile SharpDX Renderer | builder-doctor | SharpDX rendering pattern |
| ## CVD ENGINE (CUMULATIVE VOLUME DELTA) | builder-doctor | Order flow engine implementation |
| ## FOOTPRINT CHART ENGINE | builder-doctor | Footprint engine implementation |
| ## ICT METHODOLOGY - COMPLETE IMPLEMENTATIONS | builder-doctor | ICT pattern implementations |
| ### PO3 / AMD Session Box Engine | builder-doctor | ICT implementation |
| ### FVG Engine - Production Grade | builder-doctor | ICT implementation |
| ### Order Block Detection - Full Implementation | builder-doctor | ICT implementation |
| ### BOS / ChoCH - Structural Analysis Engine | builder-doctor | ICT implementation |
| ### VWAP with Standard Deviation Bands | builder-doctor | Indicator implementation |
| ### Liquidity Pool / Equal Highs-Lows Detection | builder-doctor | ICT implementation |
| ## SESSIONS & TIME - COMPLETE UTILITIES | builder-doctor | Session/time utility patterns |
| ## RISK MANAGEMENT ENGINE | builder-doctor | Risk management implementation |
| ### Prop Firm Daily Loss Limit Guard | builder-doctor | Risk management pattern |
| ### Dynamic Position Sizing | builder-doctor | Risk management pattern |
| ## WPF / UI INTEGRATION | builder-doctor | WPF integration patterns |
| ### Adding Custom WPF Control to ChartTrader | builder-doctor | WPF development pattern |
| ### ForceRefresh Pattern | builder-doctor | Development pattern |
| ## OPTIMIZATION & BACKTESTING | builder-doctor | Strategy optimization patterns |
| ### Strategy Optimizer Properties | builder-doctor | Development API |
| ### Walk-Forward Optimization | builder-doctor | Development pattern |
| ## COMMON PATTERNS & RECIPES | builder-doctor | Development recipes |
| ### Bar Color Override | builder-doctor | Development pattern |
| ### Alert System | builder-doctor | Development pattern |
| ### CrossAbove / CrossBelow | builder-doctor | Development pattern |
| ### Rising / Falling | builder-doctor | Development pattern |
| ### Previous Session High/Low | builder-doctor | Development pattern |
| ### Pre-Market Range (CBDR/NWOG) | builder-doctor | Development pattern |
| ## DEBUGGING GUIDE - COMPREHENSIVE | error-doctor | Debugging belongs in error-doctor |
| ### NinjaScript Compile Errors | error-doctor | Compile error guidance |
| ### Runtime Debugging Patterns | error-doctor | Runtime debugging |
| ### Common Logic Bugs | error-doctor | Logic bug patterns |
| ## COMPLETE PROPERTY ATTRIBUTE REFERENCE | builder-doctor | Property attribute reference |
| ## INSTRUMENT SPECIFICATIONS REFERENCE | machine-profile | Platform instrument specs |
| ### NQ (Nasdaq-100 E-mini) | machine-profile | Instrument spec |
| ### MNQ (Micro Nasdaq-100) | machine-profile | Instrument spec |
| ### ES (S&P 500 E-mini) | machine-profile | Instrument spec |
| ### MES (Micro S&P 500) | machine-profile | Instrument spec |
| ### RTY (Russell 2000 E-mini) | machine-profile | Instrument spec |
| ### CL (Crude Oil) | machine-profile | Instrument spec |
| ### GC (Gold) | machine-profile | Instrument spec |
| ## FULL FILE STRUCTURE TEMPLATES | builder-doctor | Code templates for development |
| ### Complete Indicator Template | builder-doctor | Code template |
| ## RESPONSE PROTOCOL | DISCARD | Agent response protocol — not domain knowledge |
| ### Step 1 - Requirements Clarification (if ambiguous) | DISCARD | Agent protocol |
| ### Step 2 - Architecture Note | DISCARD | Agent protocol |
| ### Step 3 - Complete Code Output | DISCARD | Agent protocol |
| ### Step 4 - Usage Notes | DISCARD | Agent protocol |
| ### NEVER: | DISCARD | Agent protocol |
| ## WHAT IS A FOOTPRINT CHART | builder-doctor | Footprint fundamentals for development |
| ### Why Footprint Matters for NQ/Futures Trading | builder-doctor | Domain context for development |
| ### Data Requirements | builder-doctor | Data requirements for footprint development |
| ## CORE DATA MODEL | builder-doctor | Footprint data model for development |
| ### FootprintCell - Atomic Unit | builder-doctor | Data model |
| ### FootprintBar - Complete Bar Data | builder-doctor | Data model |
| ## TICK CLASSIFICATION - BID VS ASK | builder-doctor | Tick classification implementation |
| ### Method 1: True Aggressor Classification (Rithmic/Best) | builder-doctor | Implementation method |
| ### Method 2: Tick Direction Heuristic (Universal) | builder-doctor | Implementation method |
| ### Method 3: Quote Comparison (More Accurate) | builder-doctor | Implementation method |
| ### Why Classification Matters | builder-doctor | Domain context |
| ## IMBALANCE DETECTION - COMPLETE THEORY | builder-doctor | Imbalance detection implementation |
| ### What Is an Imbalance? | builder-doctor | Domain theory for implementation |
| ### Diagonal Comparison Logic | builder-doctor | Implementation logic |
| ### Complete Imbalance Engine | builder-doctor | Full implementation |
| ## STACKED IMBALANCES - DEEP DIVE | builder-doctor | Stacked imbalance implementation |
| ### What Stacked Imbalances Tell You | builder-doctor | Domain context |
| ### Stacked Imbalance Zone Logic | builder-doctor | Implementation logic |
| ## DELTA ANALYSIS - COMPLETE | builder-doctor | Delta analysis implementation |
| ### Bar Delta | builder-doctor | Implementation |
| ### Delta Divergence - The Most Important Footprint Signal | builder-doctor | Signal implementation |
| ### Cumulative Delta (CVD) | builder-doctor | CVD implementation |
| ### Delta Exhaustion | builder-doctor | Signal implementation |
| ## ABSORPTION - THEORY & DETECTION | builder-doctor | Absorption detection implementation |
| ### Visual Signature of Absorption | builder-doctor | Domain context |
| ### Absorption Detector | builder-doctor | Implementation |
| ## ICEBERG ORDER DETECTION | builder-doctor | Iceberg detection implementation |
| ### Iceberg Fingerprint in Footprint | builder-doctor | Domain context |
| ### Iceberg Detector | builder-doctor | Implementation |
| ## FOOTPRINT PATTERNS ENCYCLOPEDIA | builder-doctor | Pattern reference for development |
| ### 1. Bullish Reversal Patterns | builder-doctor | Pattern reference |
| ### 2. Bearish Reversal Patterns | builder-doctor | Pattern reference |
| ### 3. Continuation Patterns | builder-doctor | Pattern reference |
| ### 4. High-Probability Entry Setups (ICT + Footprint Confluence) | builder-doctor | Pattern reference |
| ## FOOTPRINT RENDERER - PRODUCTION SHARPDX | builder-doctor | SharpDX rendering implementation |
| ### Complete Footprint Rendering Engine | builder-doctor | Full implementation |
| ## COMPLETE FOOTPRINT INDICATOR - FULL IMPLEMENTATION | builder-doctor | Complete indicator implementation |
| ## FOOTPRINT + STRATEGY INTEGRATION | builder-doctor | Strategy integration patterns |
| ### Using Footprint Signals in an AutoTrader | builder-doctor | Integration pattern |
| ## FOOTPRINT READING GUIDE - NQ SPECIFIC | builder-doctor | NQ-specific reading guide for development context |
| ### NQ Volume Context (2024-2025 Normal Ranges) | builder-doctor | Domain context |
| ### Time-of-Day Footprint Characteristics | builder-doctor | Domain context |
| ### What to Look for on NQ | builder-doctor | Domain context |
| ## COMPETITIVE LANDSCAPE - KNOW EVERY COMPETITOR | builder-doctor | Competitor analysis for feature parity |
| ### MZpack (mzFootprint) - The European Benchmark | builder-doctor | Competitor reference |
| ### TradeDevils (TDU FootPrint) - The UX King | builder-doctor | Competitor reference |
| ### ninZa (Order Flow Presentation v2) - The No-Tick-Replay Innovator | builder-doctor | Competitor reference |
| ### ClusterDelta - The DPOC & Iceberg Specialist | builder-doctor | Competitor reference |
| ### ICF Trading - The Quad-Mode Institutional Workflow | builder-doctor | Competitor reference |
| ### Hameral - The Alerts & Telegram Integration Pioneer | builder-doctor | Competitor reference |
| ## COMPLETE SIGNAL CATALOG - ALL 40+ FOOTPRINT SIGNALS | builder-doctor | Signal catalog for implementation |
| ### Category 1: Delta Signals (11 Core) | builder-doctor | Signal reference |
| ### Category 2: POC Signals (6 Core) | builder-doctor | Signal reference |
| ### Category 3: Value Area Signals (4 Core) | builder-doctor | Signal reference |
| ### Category 4: Imbalance Signals (9 Types) | builder-doctor | Signal reference |
| ### Category 5: Absorption & Iceberg Signals | builder-doctor | Signal reference |
| ### Category 6: Market Structure Signals (from orderflow) | builder-doctor | Signal reference |
| ## DELTA RATE - MZ'S MOST UNDERRATED METRIC | builder-doctor | Advanced metric implementation |
| ## ALL DISPLAY MODES - COMPLETE UI SYSTEM | builder-doctor | UI system implementation |
| ### The 16-Combination Two-Sided System (MZ-style) | builder-doctor | UI implementation |
| ### Color Themes (6-Theme System) | builder-doctor | UI implementation |
| ### Cluster Scale Normalization (MZpack-style) | builder-doctor | Implementation pattern |
| ### Saturation Color Mode | builder-doctor | Implementation pattern |
| ## BAR STATISTICS TABLE - COMPLETE IMPLEMENTATION | builder-doctor | Statistics table implementation |
| ## TAPE STRIP / BIG TRADE OVERLAY | builder-doctor | Overlay implementation |
| ## ON-CHART SETTINGS MENU (NO-RELOAD UI) | builder-doctor | UI implementation pattern |
| ### 14 Layout Templates (TradeDevils-style) | builder-doctor | UI templates |
| ## ALL 11 TRADEDEVILS DELTA SIGNALS - COMPLETE IMPLEMENTATIONS | builder-doctor | Signal implementations |
| ### Signal Letter System | builder-doctor | Signal system implementation |
| ## POC SYSTEM - COMPLETE | builder-doctor | POC system implementation |
| ### All POC Signal Implementations | builder-doctor | Signal implementations |
| ## VALUE AREA SIGNALS - COMPLETE | builder-doctor | Value area signal implementations |
| ## AUTOMATIC S/R ZONE ENGINE (MZpack-style) | builder-doctor | S/R zone engine implementation |
| ## TICK AGGREGATION SYSTEM | builder-doctor | Tick aggregation implementation |
| ## TAPE RECONSTRUCTION ENGINE | builder-doctor | Tape reconstruction implementation |
| ## 2D DELTA ENGINE (ninZa-style) | builder-doctor | 2D delta engine implementation |
| ## FOOTPRINT ALERT SYSTEM - COMPLETE | builder-doctor | Alert system implementation |
| ## FOOTPRINT STRATEGY API - 101 PLOTS SYSTEM | builder-doctor | Strategy API implementation |
| ## PERFORMANCE OPTIMIZATION - PRODUCTION GRADE | builder-doctor | Performance optimization patterns |
| ### Memory Management for Long Sessions | builder-doctor | Performance pattern |
| ### Render Culling - Only Render What's Visible | builder-doctor | Performance pattern |
| ## FOOTPRINT + ICT CONFLUENCE MATRIX | builder-doctor | Confluence matrix for development |
| ## COMPLETE FOOTPRINT READING WORKFLOW | builder-doctor | Reading workflow for development context |
| ### Step 1 - Orient to the Bar's Story | builder-doctor | Workflow step |
| ### Step 2 - POC Analysis | builder-doctor | Workflow step |
| ### Step 3 - Value Area Analysis | builder-doctor | Workflow step |
| ### Step 4 - Imbalance Scan | builder-doctor | Workflow step |
| ### Step 5 - Absorption & Iceberg Check | builder-doctor | Workflow step |
| ### Step 6 - Multi-Bar Pattern Recognition | builder-doctor | Workflow step |
| ## PART I: THE THEORETICAL FOUNDATION - WHY FOOTPRINT WORKS | builder-doctor | Academic theory supporting implementation decisions |
| ### 1. Kyle (1985) - The Informed Trader Model | builder-doctor | Academic foundation |
| ### 2. Glosten-Milgrom (1985) - The Bid-Ask Spread Decomposition | builder-doctor | Academic foundation |
| ### 3. Hasbrouck (1991) - Information Content of Trades | builder-doctor | Academic foundation |
| ### 4. Easley, Lopez de Prado, O'Hara (2012) - VPIN: Flow Toxicity | builder-doctor | Academic foundation |
| ### 5. Cont, Kukanov, Stoikov (2014) - Multi-Level Order Flow Imbalance | builder-doctor | Academic foundation |
| ### 6. Market Auction Theory (Steidlmayer 1984, Dalton 2007) - The Theoretical Bridge | builder-doctor | Academic foundation |
| ### 7. Lee-Ready (1991) - The Tick Classification Algorithm | builder-doctor | Academic foundation |
| ### 8. The Square Root Market Impact Law | builder-doctor | Academic foundation |
| ### 9. Order Book Resilience - The Replenishment Rate | builder-doctor | Academic foundation |
| ## PART II: THE PSYCHOLOGY OF ORDER FLOW | builder-doctor | Behavioral context for development |
| ### Behavioral Finance Layer - Why Footprint Patterns Are Persistent | builder-doctor | Domain context |
| ## PART III: ADVANCED QUANTITATIVE FOOTPRINT METRICS | builder-doctor | Advanced metrics implementation |
| ### 1. Amihud (2002) Illiquidity Ratio - Adapted for Footprint | builder-doctor | Metric implementation |
| ### 2. Tick Volume Entropy - Measuring Order Flow Randomness | builder-doctor | Metric implementation |
| ### 3. Realized Volatility via Tick Data - Garman-Klass Estimator | builder-doctor | Metric implementation |
| ### 4. Price Impact Regression - Footprint's Theoretical Anchor | builder-doctor | Metric implementation |
| ## PART IV: ADVANCED FOOTPRINT PATTERNS FROM RESEARCH | builder-doctor | Advanced pattern implementations |
| ### The "Effort vs Result" Analysis (Volume Spread Analysis) | builder-doctor | Pattern implementation |
| ### Single Prints - Market Profile in Footprint | builder-doctor | Pattern implementation |
| ## PART V: FOOTPRINT READING - THE FULL PRACTITIONER REFERENCE | builder-doctor | Practitioner reference for development context |
| ### Contextual Reading Rules - The Market Environment First | builder-doctor | Domain context |
| ### The 5 Footprint "Market States" and Their Trading Rules | builder-doctor | Domain context |
| ### The Complete Pre-Trade Checklist (Every Footprint Trade) | builder-doctor | Domain context |
| ## PART VI: FOOTPRINT AGENT RESPONSE PROTOCOL | DISCARD | Agent response protocol — not domain knowledge |
| ### Step 1 - Establish the theoretical context | DISCARD | Agent protocol |
| ### Step 2 - Data requirements | DISCARD | Agent protocol |
| ### Step 3 - Complete implementation | DISCARD | Agent protocol |
| ### Step 4 - Performance specs | DISCARD | Agent protocol |
| ### Step 5 - Academic annotation in code | DISCARD | Agent protocol |
| ## SECTION I: THE COMPLETE BOOK LIBRARY | builder-doctor | Reference library for domain knowledge |
| ### Tier 1 - Essential Foundational Works | builder-doctor | Book references |
| ### Tier 2 - Essential Practitioner Works | builder-doctor | Book references |
| ### Tier 3 - Deep Specialist Works | builder-doctor | Book references |
| ## SECTION II: COMPLETE PLATFORM INTELLIGENCE MATRIX | builder-doctor | Competitor platform analysis |
| ### 1. Sierra Chart - "Numbers Bars" Ecosystem | builder-doctor | Competitor platform reference |
| ### 2. ATAS - The Feature King (400+ Footprint Variations) | builder-doctor | Competitor platform reference |
| ### 3. Jigsaw Trading - The DOM Mastery Platform | builder-doctor | Competitor platform reference |
| ### 4. Bookmap - The Liquidity Heatmap Pioneer | builder-doctor | Competitor platform reference |
| ### 5. Quantower - "Cluster Charts" & DOM Surface | builder-doctor | Competitor platform reference |
| ### 6. VolFix - Institutional-Grade Cluster Analysis | builder-doctor | Competitor platform reference |
| ## SECTION III: WYCKOFF / VSA COMPLETE IMPLEMENTATION | builder-doctor | Wyckoff/VSA implementation |
| ### Wyckoff's Three Laws - NinjaScript Formalization | builder-doctor | Implementation |
| ### Complete Wyckoff Schematic Detection | builder-doctor | Implementation |
| ### VSA Bar Classifier - All 12 VSA Bar Types | builder-doctor | Implementation |
| ## SECTION IV: WEIS WAVE - ADVANCED WAVE VOLUME ENGINE | builder-doctor | Weis Wave implementation |
| ## SECTION V: ALTERNATIVE BAR TYPES - ADVANCED | builder-doctor | Alternative bar type implementations |
| ### Information-Driven Bars (Lopez de Prado) | builder-doctor | Implementation |
| ## SECTION VI: GAMMA EXPOSURE (GEX) - OPTIONS-DRIVEN ORDER FLOW | builder-doctor | GEX integration implementation |
| ## SECTION VII: COMPLETE STRATEGY BIBLE | builder-doctor | Strategy implementations |
| ### STRATEGY 1: The Institutional Entry Protocol (IEP) | builder-doctor | Strategy implementation |
| ### STRATEGY 2: The Stacked Zone Fade | builder-doctor | Strategy implementation |
| ### STRATEGY 3: Delta Slingshot Auto-Entry | builder-doctor | Strategy implementation |
| ### STRATEGY 4: ICT Silver Bullet + Footprint Confluence | builder-doctor | Strategy implementation |
| ### STRATEGY 5: POC Migration Trend Follow | builder-doctor | Strategy implementation |
| ## SECTION VIII: PERFORMANCE & MEMORY ARCHITECTURE FOR PRODUCTION | builder-doctor | Production performance patterns |
| ### The Complete NinjaScript Memory Architecture for a Pro Footprint Suite | builder-doctor | Performance architecture |
| ## SECTION IX: THE ULTIMATE RESPONSE PROTOCOL | DISCARD | Agent response protocol |
| ### Response Protocol - Tiered by Complexity | DISCARD | Agent protocol |
| ### Code Quality Standards (NON-NEGOTIABLE) | builder-doctor | Code quality standards belong in builder-doctor |
| ### The Encyclopedia of Everything You Know | DISCARD | Agent identity section |

---

## Source: ninjascript-error-surgeon-v2.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## IDENTITY & OPERATING PROTOCOL | DISCARD | Agent identity — not domain knowledge |
| ## MASTER ERROR INDEX - FIND YOUR ERROR IN SECONDS | error-doctor | Quick-lookup error index — core error-doctor content |
| ## TIER 1: COMPILE ERRORS - COMPLETE DATABASE | error-doctor | Compile error database |
| ### CS0019 - Operator Cannot Be Applied to These Operands | error-doctor | CS error code |
| ### CS0029 - Cannot Implicitly Convert Type | error-doctor | CS error code |
| ### CS0100 - Parameter Name Already Defined | error-doctor | CS error code |
| ### CS0101 - Namespace Contains Duplicate Type Definition | error-doctor | CS error code |
| ### CS0103 - Name Does Not Exist in Current Context (5 Root Causes) | error-doctor | CS error code |
| ### CS0106 - Modifier Not Valid for This Item | error-doctor | CS error code |
| ### CS0111 - Type Already Defines a Member with Same Parameter Types | error-doctor | CS error code |
| ### CS0117 - Does Not Contain a Definition For (Wrong Member) | error-doctor | CS error code |
| ### CS0118 - Is a Namespace But Is Used Like a Type / Missing Assembly | error-doctor | CS error code |
| ### CS0120 - Object Reference Required for Non-Static Member | error-doctor | CS error code |
| ### CS0128 - Local Variable Already Defined in This Scope | error-doctor | CS error code |
| ### CS0131 - Left Side of Assignment Must Be a Variable, Property, or Indexer | error-doctor | CS error code |
| ### CS0161 - Not All Code Paths Return a Value | error-doctor | CS error code |
| ### CS0163 - Control Cannot Fall Through from One Case to Another | error-doctor | CS error code |
| ### CS0165 - Use of Possibly Unassigned Variable | error-doctor | CS error code |
| ### CS0168 - Variable Declared But Never Used (Warning) | error-doctor | CS error code |
| ### CS0173 - Cannot Determine Type of Conditional Expression | error-doctor | CS error code |
| ### CS0200 - Property Cannot Be Assigned (Read-Only) | error-doctor | CS error code |
| ### CS0229 - Ambiguity Between Members | error-doctor | CS error code |
| ### CS0246 - Type or Namespace Not Found (**DEEP TREATMENT** - Most Common Error) | error-doctor | CS error code — most critical |
| ### CS0260 - Missing Partial Modifier on Declaration | error-doctor | CS error code |
| ### CS0266 - Cannot Implicitly Convert (Explicit Cast Needed) | error-doctor | CS error code |
| ### CS0305 - Generic Type Requires Type Arguments | error-doctor | CS error code |
| ### CS0428 - Cannot Convert Method Group to Non-Delegate Type | error-doctor | CS error code |
| ### CS1501 - Method Has No Overload Taking N Arguments (**MASTER REFERENCE**) | error-doctor | CS error code |
| ### CS1502 / CS1503 - Wrong Argument Type | error-doctor | CS error code |
| ### CS1520 - Class, Struct, or Interface Expected | error-doctor | CS error code |
| ### CS1612 - Cannot Modify Return Value (Struct by Value) | error-doctor | CS error code |
| ## TIER 2: RUNTIME ERROR DATABASE | error-doctor | Runtime error database |
| ### RT-001: "Error on bar -1: You are accessing an invalid index" | error-doctor | Runtime error |
| ### RT-002: "Index Was Outside the Bounds of the Array" | error-doctor | Runtime error |
| ### RT-003: "Collection Was Modified; Enumeration Operation May Not Execute" | error-doctor | Runtime error |
| ### RT-004: "Object Reference Not Set to an Instance of an Object" (NullReferenceException) | error-doctor | Runtime error |
| ### RT-005: Strategy Halted - Generic | error-doctor | Runtime error |
| ### RT-006: EventHandlerBarsUpdate Null Reference | error-doctor | Runtime error |
| ### RT-007: "The Process Cannot Access the File - Being Used by Another Process" | error-doctor | Runtime error |
| ### RT-008: Order Rejected - Wrong Side of Market | error-doctor | Runtime error |
| ### RT-009: "An Order Has Been Ignored Since Order Was Submitted Before BarsRequiredToTrade Had Been Met" | error-doctor | Runtime error |
| ### RT-010: OnOrderUpdate / OnExecutionUpdate Never Called | error-doctor | Runtime error |
| ### RT-011: Orders Not Submitted in Historical Mode | error-doctor | Runtime error |
| ### RT-012: MaximumBarsLookBack TwoHundredFiftySix - Index Out of Range > 256 Bars Back | error-doctor | Runtime error |
| ### RT-013: Series Values Set on Wrong BarsInProgress (SharkIndicators Pattern) | error-doctor | Runtime error |
| ### RT-014: Divide By Zero / Infinity / NaN in Calculations | error-doctor | Runtime error |
| ### RT-015: InvalidCastException - Database Corruption | error-doctor | Runtime error |
| ### RT-016: StackOverflowException | error-doctor | Runtime error |
| ### RT-017: Positions Not Closed When Strategy Errors | error-doctor | Runtime error |
| ## TIER 3: SHARPDX ERROR DATABASE | error-doctor | SharpDX crash database |
| ### SDX-001: D2DERR_WRONG_FACTORY (HRESULT 0x88990012) | error-doctor | SharpDX crash |
| ### SDX-002: D2DERR_PUSH_POP_UNBALANCED (HRESULT 0x88990016) | error-doctor | SharpDX crash |
| ### SDX-003: D2DERR_WRONG_STATE (HRESULT 0x88990001) | error-doctor | SharpDX crash |
| ### SDX-004: "Cannot Access a Disposed Object" | error-doctor | SharpDX crash |
| ### SDX-008: Brush Not Frozen - WPF Threading Error | error-doctor | SharpDX crash |
| ### SDX-009: "An Item with the Same Key Has Already Been Added" (Draw.* Tag Collision) | error-doctor | SharpDX crash |
| ## TIER 4: BEHAVIORAL / LOGIC ERROR DATABASE | error-doctor | Behavioral bug database |
| ### LG-001: Look-Ahead Bias - Strategy Works in Backtest but Fails Live | error-doctor | Behavioral bug |
| ### LG-002: BarsInProgress Double-Processing | error-doctor | Behavioral bug |
| ### LG-003: No Plot Output / NaN Values on Chart | error-doctor | Behavioral bug |
| ### LG-004: UniqueEntries Silently Blocking Orders | error-doctor | Behavioral bug |
| ### LG-007: Static Variable Threading Corruption (Chart Rendering Failed) | error-doctor | Behavioral bug |
| ### LG-008: "Collection Was Modified" - The foreach Trap | error-doctor | Behavioral bug |
| ### LG-009: Series Values Disappearing > 256 Bars Back | error-doctor | Behavioral bug |
| ## TIER 5: NT7 → NT8 MIGRATION ERROR DATABASE | error-doctor | NT7→NT8 migration errors |
| ### MIG-001 + MIG-002 + MIG-003: OnOrderUpdate / OnExecutionUpdate Signature Changes | error-doctor | Migration error |
| ### MIG-004: Brushes Are Now WPF (System.Windows.Media), Not GDI+ (System.Drawing) | error-doctor | Migration error |
| ## TIER 6: STATE MACHINE ERROR DATABASE | error-doctor | State machine errors (SHARED-fundamental: state machine basics in machine-profile; errors go to error-doctor) |
| ### SM-001: Complete State Machine Law (The Definitive Reference) | error-doctor | State machine error patterns |
| ## TIER 7: ENVIRONMENT ERROR DATABASE | error-doctor | Environment errors |
| ### ENV-004: Microsoft OneDrive Path Issues (2023-2024 Top Issue) | error-doctor | Environment error |
| ### ENV-005: NT8 Database Corruption Fix | error-doctor | Environment error |
| ### ENV-006: MaximumBarsLookBack Locked by Third-Party Indicator | error-doctor | Environment error |
| ### ENV-007: IsValidDataPoint Throws Instead of Returning False | error-doctor | Environment error |
| ### ENV-008: NinjaScript Utilization Monitor - Finding Performance Bottlenecks | error-doctor | Performance debugging |
| ## TIER 8: THE SELF-DEBUGGING ARSENAL | error-doctor | Debugging tools and techniques |
| ### The Nuclear Debugging Strategy - Find Any Error in Minutes | error-doctor | Debugging technique |
| ## MASTER QUICK-FIX CHEAT SHEET | error-doctor | Quick-fix reference |
| ## RESPONSE FORMAT - ALWAYS USE THIS | DISCARD | Agent response format — not domain knowledge |

---

## Source: ninjatrader/ninjascript-ai-context.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## Runtime Constraints | machine-profile | Platform runtime constraints (C# version, .NET version, forbidden patterns) |
| ## Namespace Rules | machine-profile | Platform namespace rules |
| ## Class Hierarchy | machine-profile | Platform class hierarchy |
| ## FORBIDDEN - Do NOT generate these | builder-doctor | Forbidden C# patterns are development constraints (SHARED-fundamental: also in machine-profile; primary owner builder-doctor as coding guidance) |
| ## Mandatory State Machine | machine-profile | State machine is platform lifecycle |
| ## OnBarUpdate - Always Guard with CurrentBar | builder-doctor | Guard pattern is a development pattern |
| ## Property Decoration (Parameters Visible to User) | builder-doctor | Property decoration is a development pattern |
| ## Built-in Indicators (Call These - Do Not Reimplement) | builder-doctor | Built-in indicator reference for development |
| ## Drawing Objects (NT8 Style - All via Draw.* Static Class) | builder-doctor | Draw.* usage patterns |
| ## Thread Safety | builder-doctor | Thread safety is a development concern |
| ## Multi-Series (Watching Multiple Instruments or Timeframes) | builder-doctor | Multi-series development patterns |
| ## Strategy Order Methods (Strategy Class Only) | builder-doctor | Strategy development patterns |
| ## Key DEEP6 Project Gotchas | nt8-expert-wrapper | DEEP6-specific gotchas — routes to expert wrapper |
| ## Minimal Working Indicator Template | builder-doctor | Code template for development |
| ## Quick Reference: What to Check Before Submitting Generated Code | builder-doctor | Pre-submission checklist for development |

---

## Source: .claude/skills/nt8-expert/knowledge.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## Verified Paths (this machine) | nt8-expert-wrapper | DEEP6-specific machine paths |
| ## NT8 Folder Rules | nt8-expert-wrapper | DEEP6-specific folder rules |
| ## Deploy Flow (manual or scripted) | nt8-expert-wrapper | DEEP6-specific deployment flow |
| ## Triggering Compilation | nt8-expert-wrapper | DEEP6-specific compile trigger methods |
| ### Method 1: UI Automation (SendKeys) - PREFERRED | nt8-expert-wrapper | DEEP6-specific compile method |
| ### Method 2: File watcher trigger | nt8-expert-wrapper | DEEP6-specific compile method |
| ### Method 3: Tools menu sequence | nt8-expert-wrapper | DEEP6-specific compile method |
| ### NT8 Keyboard Shortcuts (in NinjaScript Editor) | machine-profile | Universal NT8 keyboard shortcuts (SHARED-fundamental: also useful in machine-profile; primary owner machine-profile as platform knowledge) |
| ## Adding Indicator to a Chart | nt8-expert-wrapper | DEEP6-specific workflow |
| ### Via NT8 UI: | nt8-expert-wrapper | DEEP6-specific workflow step |
| ### Via UI Automation script: | nt8-expert-wrapper | DEEP6-specific automation |
| ## Adding Strategy to a Chart | nt8-expert-wrapper | DEEP6-specific workflow |
| ### Via NT8 UI: | nt8-expert-wrapper | DEEP6-specific workflow step |
| ## NT8 Control Center Navigation | machine-profile | Universal NT8 UI navigation (SHARED-fundamental: primary owner machine-profile) |
| ## Common NT8 Compile Errors and Fixes | nt8-fix-wrapper | DEEP6-specific error context (quick reference in DEEP6 context) |
| ## NinjaScript Namespace Rules | machine-profile | Universal namespace rules (SHARED-fundamental: primary owner machine-profile) |
| ## NT8 Data Flow for DEEP6 | nt8-expert-wrapper | DEEP6-specific data flow |
| ## NT8 Connection Types | machine-profile | Universal NT8 connection types |
| ## DEEP6-Specific Files | nt8-expert-wrapper | DEEP6 file inventory |
| ## NT8 Log Locations | nt8-expert-wrapper | DEEP6-specific log paths |
| ## Playback / DB Corruption Troubleshooting (April 2026) | error-doctor | Error troubleshooting — routes to error-doctor |
| ## Checking Compile Errors Without NT8 UI | nt8-fix-wrapper | DEEP6-specific error checking workflow |
| ## NT8 Window Management (PowerShell) | nt8-expert-wrapper | DEEP6-specific PowerShell automation |
| ## SendKeys Reference (for UI automation) | nt8-expert-wrapper | DEEP6-specific automation reference |
| ## NT8 Version Info (this machine) | nt8-expert-wrapper | DEEP6-specific machine state |
| ## Important NT8 Constraints | machine-profile | Universal NT8 constraints |
| ## Compile Success/Failure Detection (NEW - April 2026) | nt8-fix-wrapper | DEEP6-specific compile detection |
| ### Detection Strategy | nt8-fix-wrapper | DEEP6-specific detection strategy |
| ### Scripts | nt8-fix-wrapper | DEEP6-specific scripts |
| ## GEXCommand / JSON-backed Indicator Troubleshooting (April 2026) | nt8-fix-wrapper | DEEP6-specific indicator troubleshooting |
| ## VS 2022 Integration (NEW) | nt8-expert-wrapper | DEEP6-specific VS integration |
| ## F5 on Chart = In-Place Reload (NEW) | nt8-expert-wrapper | DEEP6-specific workflow shortcut |
| ## ninjatrader-autodocs MCP (NEW) | nt8-expert-wrapper | DEEP6-specific MCP tooling |
| ## AI Code Generation Workflow (NEW) | nt8-new-wrapper | DEEP6-specific code gen workflow |
| ## UIAutomation Error Reading (VERIFIED - April 2026) | nt8-fix-wrapper | DEEP6-specific error reading automation |
| ### Working PowerShell code (tested and verified): | nt8-fix-wrapper | DEEP6-specific verified script |
| ### NT8 window discovery: | nt8-expert-wrapper | DEEP6-specific window discovery |
| ## Critical Lessons (April 2026 Session) | nt8-expert-wrapper | DEEP6-specific lessons learned |
| ### Deploy bug -- -Target AddOns deploys everything recursively | nt8-expert-wrapper | DEEP6-specific deploy bug |
| ### Enum placement rule (CRITICAL) | builder-doctor | Universal NinjaScript rule (SHARED-fundamental: primary owner builder-doctor) |
| ### Truncated filenames from bad deploy | nt8-expert-wrapper | DEEP6-specific deploy issue |
| ### Pre-existing compile failure detection | nt8-fix-wrapper | DEEP6-specific detection |
| ### Compile success detection timing | nt8-fix-wrapper | DEEP6-specific timing |

---

## Source: .claude/skills/nt8-fix/knowledge.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## NT8 NinjaScript Compile Environment | nt8-fix-wrapper | DEEP6-specific compile environment context |
| ## CS Error Quick Reference | nt8-fix-wrapper | DEEP6-specific quick reference (full treatment in error-doctor) |
| ## NT8-Specific API Pitfalls | nt8-fix-wrapper | DEEP6-specific API pitfall context |
| ### `volatile` fields | nt8-fix-wrapper | DEEP6-specific pitfall |
| ### Threading from indicator to UI | nt8-fix-wrapper | DEEP6-specific threading pitfall |
| ### `OnBarUpdate()` - always check `CurrentBar` before indexing | nt8-fix-wrapper | DEEP6-specific guard pattern reminder |
| ### Series access - `[0]` is current bar, `[1]` is one bar ago | nt8-fix-wrapper | DEEP6-specific series access reminder |
| ### `AddDataSeries` - must be called in `OnStateChange` / `State.SetDefaults` or `State.Configure` | nt8-fix-wrapper | DEEP6-specific API constraint |
| ### Namespace rules | nt8-fix-wrapper | DEEP6-specific namespace context |
| ## Duplicate Type / CS0101 | nt8-fix-wrapper | DEEP6-specific CS0101 context (full treatment in error-doctor) |
| ## Compile Success/Failure Detection | nt8-fix-wrapper | DEEP6-specific detection workflow |
| ## Fix Workflow (AI Loop) | nt8-fix-wrapper | DEEP6-specific fix loop workflow |
| ## Common NinjaScript Patterns for DEEP6 Indicators | nt8-fix-wrapper | DEEP6-specific patterns |
| ### Indicator shell | nt8-fix-wrapper | DEEP6-specific indicator shell |
| ### Drawing on chart (use `Draw.*` helpers) | nt8-fix-wrapper | DEEP6-specific drawing reminder |
| ### `OnRender` for custom pixel-level drawing | nt8-fix-wrapper | DEEP6-specific rendering reminder |
| ## NT8 File Paths (this machine) | nt8-fix-wrapper | DEEP6-specific file paths |
| ## DEEP6 File Inventory | nt8-fix-wrapper | DEEP6-specific file inventory |
| ## Escalation Checklist | nt8-fix-wrapper | DEEP6-specific escalation workflow |

---

## Source: .claude/skills/nt8-new/knowledge.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## Mandatory File Structure (in order) | nt8-new-wrapper | DEEP6-specific mandatory file structure |
| ## OnStateChange - Mandatory Pattern | nt8-new-wrapper | DEEP6-specific state change pattern |
| ## OnBarUpdate - Mandatory Guard Pattern | nt8-new-wrapper | DEEP6-specific guard pattern |
| ## Property Decoration Pattern | nt8-new-wrapper | DEEP6-specific property decoration |
| ### Numeric / bool properties: | nt8-new-wrapper | DEEP6-specific property pattern |
| ### Brush/Color (requires serialization pair): | nt8-new-wrapper | DEEP6-specific property pattern |
| ### Enum property (enum MUST be at global namespace): | nt8-new-wrapper | DEEP6-specific enum placement rule |
| ## Built-In Series (use, don't reimplement) | nt8-new-wrapper | DEEP6-specific series reference |
| ## Draw.* Methods | nt8-new-wrapper | DEEP6-specific Draw.* reference |
| ## FORBIDDEN Patterns (compile errors) | nt8-new-wrapper | DEEP6-specific forbidden patterns |
| ## SharpDX Custom Rendering (advanced) | nt8-new-wrapper | DEEP6-specific SharpDX guidance |
| ## DEEP6 Namespace Conventions | nt8-new-wrapper | DEEP6-specific namespace conventions |
| ## Pre-Generation Checklist | nt8-new-wrapper | DEEP6-specific pre-generation checklist |

---

## Source: .claude/skills/nt8-architect/architecture.md

| Section | Target | Rationale |
|---------|--------|-----------|
| ## Current NT8 Deployment (compiles successfully as of 2026-04-20 00:00) | nt8-architect | 100% DEEP6-specific deployment state |
| ### Indicators\DEEP6\ | nt8-architect | DEEP6-specific indicator inventory |
| ### AddOns\DEEP6\ | nt8-architect | DEEP6-specific addon inventory |
| ### AddOns\NinjaAIBridge\ | nt8-architect | DEEP6-specific addon inventory |
| ### Indicators\AIBridge\ | nt8-architect | DEEP6-specific indicator inventory |
| ### AddOns\DEEP6\ (stub implementations - all compiling) | nt8-architect | DEEP6-specific stub state |
| ## NT8 Compile Rules (Quick Reference) | nt8-architect | DEEP6-specific compile rules in architecture context |
| ## Dependency Graph | nt8-architect | DEEP6-specific dependency graph |
| ## HTTP Dev API (localhost:19206) | nt8-architect | DEEP6-specific dev API |
| ## DEEP6Footprint.cs Restoration - COMPLETED 2026-04-20 | nt8-architect | DEEP6-specific restoration record |
| ## DEEP6Signal.cs Architecture (L1-L7) | nt8-architect | DEEP6-specific L1-L7 architecture |

---

## Summary Statistics

| Target | H2 Sections | H3 Sections | Total |
|--------|-------------|-------------|-------|
| machine-profile | 18 | 22 | 40 |
| builder-doctor | 57 | 148 | 205 |
| error-doctor | 11 | 67 | 78 |
| nt8-expert-wrapper | 18 | 12 | 30 |
| nt8-fix-wrapper | 12 | 7 | 19 |
| nt8-new-wrapper | 10 | 3 | 13 |
| nt8-architect | 6 | 5 | 11 |
| DISCARD | 14 | 8 | 22 |
| **TOTAL** | **146** | **272** | **418** |

## SHARED-fundamental Notes

Sections marked SHARED-fundamental have meaningful overlap across skills. The primary owner is listed in the Target column. Secondary references are noted here:

| Section | Primary Owner | Secondary Reference | Note |
|---------|--------------|---------------------|------|
| State Guards in OnBarUpdate | builder-doctor | machine-profile | Guard patterns are coding patterns; state machine basics stay in machine-profile |
| FORBIDDEN C# patterns | builder-doctor | machine-profile | Coding constraints; platform context in machine-profile |
| NT8 Keyboard Shortcuts | machine-profile | nt8-expert-wrapper | Universal shortcuts; DEEP6 context in expert-wrapper |
| NT8 Control Center Navigation | machine-profile | nt8-expert-wrapper | Universal UI; DEEP6 workflow in expert-wrapper |
| NinjaScript Namespace Rules | machine-profile | nt8-fix-wrapper, nt8-new-wrapper | Universal rules; DEEP6-specific application in wrappers |
| Enum placement rule (CRITICAL) | builder-doctor | nt8-new-wrapper | Universal NinjaScript rule; DEEP6 application in new-wrapper |
| State Machine Error Database (SM-001) | error-doctor | machine-profile | Error patterns go to error-doctor; state machine basics in machine-profile |
