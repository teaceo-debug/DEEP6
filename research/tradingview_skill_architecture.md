# TradingView/Pine Script Skill Architecture Proposal

**Research Date**: May 22, 2026  
**Scope**: Full surface area of TradingView development requiring expert guidance  
**Outcome**: Recommended skill split with rationale and coverage map

## EXECUTIVE SUMMARY

TradingView Pine Script development spans 12 major domains with distinct expertise requirements. Current skills cover builder + error fixing, but leave significant gaps in:

1. Machine profile (platform knowledge, editor behavior, compilation, limits)
2. Strategy/backtesting operator (Strategy Tester, broker emulator, optimization)
3. Alert/webhook specialist (payload design, relay platforms, automation)
4. Publishing/deployment (moderation rules, library management, versioning)
5. Repainting diagnostics (detection, prevention, testing methodology)

Recommended Architecture: 7 specialized skills with clear ownership and no overlap.

## PROPOSED SKILL SPLIT

### 1. tradingview-machine-profile (NEW)
Purpose: Platform knowledge base - TradingView environment, editor, compiler, limits
Triggers: "Install TradingView", "Pine Editor", "compile", "limits", "token count"

Coverage:
- TradingView installation, workspace, file system
- Pine Editor features: syntax highlighting, autocomplete, parameter hints, annotations
- Compilation: 2-minute limit, token counting (100K per script, 1M for libraries), 5MB request size
- Error/warning system: CE/RE/CW codes, runtime vs compile-time errors
- Script limits: plot count (64 max), drawing limits, memory (RE10139), buffer (RE10143)
- Execution model: bar-by-bar, realtime vs historical, state persistence
- Version support: v3/v4/v5/v6 availability, auto-converter behavior
- Pine Logs: log.info/warning/error for debugging
- Pine Profiler: runtime performance analysis
- Account plan features: free vs Pro vs Premium vs Ultimate

Load FIRST before any TradingView task - establishes platform constraints and capabilities.

### 2. tradingview-pinescript-language-reference (NEW)
Purpose: Pine Script language fundamentals - types, operators, syntax, execution
Triggers: "Pine Script syntax", "type system", "UDT", "variable declaration", "operator", "scope"

Coverage:
- Type system: fundamental types, value types, reference types, UDTs
- Collections: arrays, matrices, maps with full API
- User-defined types (UDTs): definition, instantiation, fields, shallow/deep copy
- Operators: arithmetic, comparison, logical, ternary, history-referencing []
- Variable declarations: single, tuple, var keyword, qualifiers
- Control flow: if/switch/for/while/break/continue
- Functions: user-defined, methods, parameter types, return types
- Scoping: global, local, function scope rules
- Execution model: bar-by-bar evaluation, realtime vs historical behavior
- Built-in variables: open, high, low, close, volume, time, bar_index, barstate.*
- Namespaces: ta.*, math.*, str.*, color.*, syminfo.*
- v5 vs v6 differences: lazy evaluation, bool na removal, dynamic requests

Scope: Language only - NOT builder patterns, NOT error fixing, NOT strategy logic.

### 3. tradingview-pinescript-builder-doctor (EXISTING - REFOCUS)
Purpose: Indicator/strategy/library code generation and architecture
Triggers: "Build me a Pine Script", "Build indicator", "Build strategy", "Create library"

Coverage:
- Indicator architecture: declaration, inputs, plots, hlines, fills
- Strategy architecture: declaration, entry/exit logic, position management, order types
- Library architecture: export, UDTs, functions, annotations, versioning
- Technical analysis patterns: moving averages, oscillators, trend detection, confluence
- Drawing patterns: lines, labels, boxes, polylines, tables
- Multi-timeframe patterns: request.security() design, lookahead prevention, dynamic requests
- Alert patterns: alert(), alertcondition(), alert_message formatting
- Non-repainting patterns: barstate.isconfirmed, confirmed data only, HTF safety
- Input design: input types, defaults, ranges, tooltips
- Performance patterns: minimize request.security(), consolidate with tuples, var keyword usage
- Code organization: functions, libraries, UDTs for reusability

Scope: Building new scripts from scratch or concept - NOT error fixing, NOT platform limits.

### 4. tradingview-pinescript-error-doctor (EXISTING - REFOCUS)
Purpose: Compile/runtime error diagnosis and fixing
Triggers: "Fix Pine error", "won't compile", "runtime error", "CE/RE/CW code"

Coverage:
- Compilation errors: CE10101 (bool condition), syntax errors, type mismatches
- Runtime errors: RE10139 (memory), RE10143 (buffer), array bounds, na handling
- Compiler warnings: CW10003 (function scope), deprecated features, v5 to v6 migration issues
- Error diagnosis: reading error messages, identifying root cause, locating problematic code
- Common fixes: type casting, scope correction, buffer sizing, memory optimization
- v5 to v6 migration errors: dynamic_requests, bool na, color changes, transp removal
- Repainting detection: identifying unconfirmed bar usage, HTF lookahead, intrabar conditions
- Performance errors: loop timeouts, memory limits, excessive request.security() calls

Scope: Fixing broken code - NOT building new scripts, NOT platform knowledge.

### 5. tradingview-strategy-backtesting-operator (NEW)
Purpose: Strategy development, backtesting, optimization, and live execution
Triggers: "Backtest", "Strategy Tester", "broker emulator", "optimize strategy", "Bar Magnifier"

Coverage:
- Strategy Tester: Performance Summary, Properties, List of Trades tabs
- Broker emulator: fill assumptions, slippage, commission, margin, pyramiding
- Backtesting modes: regular, Deep Backtesting (Premium+), Bar Magnifier (Premium+)
- Bar Replay: extending historical data, multi-dataset testing
- Order management: strategy.entry(), strategy.exit(), strategy.close(), strategy.order()
- Order types: market, limit, stop, stop-limit with fill logic
- Position tracking: strategy.position_size, strategy.opentrades, strategy.closedtrades
- Execution modes: calc_on_every_tick vs bar close, process_orders_on_close
- Backtesting vs live divergence: identifying causes, realistic simulation
- Parameter optimization: input ranges, sweep methodology, curve fitting avoidance
- Risk management: position sizing, stop-loss, take-profit, trailing stops
- Performance metrics: win rate, drawdown, Sharpe ratio, profit factor interpretation
- Realistic backtesting: slippage, commission, spread, fill price assumptions

Scope: Strategy testing and optimization - NOT indicator building, NOT language syntax.

### 6. tradingview-alerts-webhooks-operator (NEW)
Purpose: Alert design, webhook automation, and live execution pipelines
Triggers: "Alert", "webhook", "automate", "TradersPost", "Ontology", "alert payload", "JSON"

Coverage:
- Alert types: alert(), alertcondition(), alert_message parameter
- Alert frequency: alert.freq_once_per_bar_close, 15 triggers per 3 minutes limit
- Webhook configuration: URL setup, TradingView IP allowlist, ports 80/443 only
- Payload design: JSON formatting, placeholder substitution
- Webhook delivery: latency expectations (1-5s normal, 45+ during volatility), retry logic
- Relay platforms: TradersPost, Ontology Trading, PineConnector, Alertatron, WunderTrading
- Broker API integration: mapping webhook payload to broker order fields
- Security: secret token validation, HTTPS requirement, no credentials in payload
- Testing: webhook preview, payload validation, dry-run on paper trading
- Idempotency: duplicate signal prevention, position state tracking
- Live execution: order placement, fill confirmation, error handling
- Monitoring: webhook delivery status, alert log inspection, signal verification

Scope: Alerts and automation - NOT strategy logic, NOT indicator building.

### 7. tradingview-publishing-library-manager (NEW)
Purpose: Script publishing, library management, moderation, and community standards
Triggers: "Publish", "library", "moderation", "reuse rules", "vendor", "invite-only"

Coverage:
- Publication types: public vs private, open-source vs protected vs invite-only
- Publishing workflow: description, tags, visibility, access mode, submission
- Script Publishing Rules: no spam, no misleading titles, no repainting, no external links
- Moderation process: criteria, rejection reasons, appeals, PineCoders contact
- Library management: export, import, versioning, namespace, annotations
- Library reuse rules: credit original author, meaningful improvements, open-source requirement
- Vendor Requirements: for invite-only (paid) scripts, compliance checklist
- Code reuse: open-source reuse criteria, license selection, attribution
- Library versioning: explicit version in import, update process, backward compatibility
- Community Scripts: searchable repository, 150,000+ published, filtering by likes/date/performance
- Publication immutability: can't change description/visibility/mode after publish
- Updates: code updates with release notes, chart replacement
- Tips for authors: open-source benefits, learning from community, quality standards
- Compiler annotations: @description, @enum, @type, @field, @function, @param, @returns

Scope: Publishing and library ecosystem - NOT code building, NOT error fixing.

## COVERAGE MAP

Domain          | Skill                              | Coverage
Platform        | machine-profile                    | Editor, compiler, limits, execution model, account features
Language        | language-reference                 | Types, operators, syntax, scoping, execution, namespaces
Building        | builder-doctor                     | Indicators, strategies, libraries, patterns, architecture
Errors          | error-doctor                       | Compile/runtime errors, warnings, diagnostics, fixes
Strategy        | backtesting-operator               | Strategy Tester, broker emulator, optimization, risk management
Alerts          | alerts-webhooks-operator           | Alerts, webhooks, payloads, relay platforms, live execution
Publishing      | publishing-library-manager         | Publishing, libraries, moderation, reuse rules, community

## EVIDENCE SOURCES

Official Documentation:
- Pine Script User Manual: https://my.tradingview.com/pine-script-docs/
- Pine Script v6 Reference: https://www.tradingview.com/pine-script-reference/v6/
- Release Notes (Jan 2026): https://tradingview.com/pine-script-docs/release-notes/
- Strategy Tester Guide: https://www.tradingview.com/support/solutions/43000562362-what-are-strategies-backtesting-and-forward-testing/
- Webhook Configuration: https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
- Publishing Rules: https://www.tradingview.com/support/solutions/43000549935-tips-for-script-authors/
- Script Moderation: https://www.tradingview.com/support/solutions/43000549905-script-moderation-on-tradingview/

Community Resources:
- GitHub Examples: Corbanistan/Trading-Pinescript-v6, chris-c-thomas/CT-Pine-Scripts, damianpitt/capital41-indicators
- Repainting Research: GrandAlgo (2026-02-26), Jayadev Rana (2026-04-06), Pineify (2026-01-31)
- Webhook Automation: Ontology Trading (2026-04-14), CodeReindeer (2026-04-11), BotJockie (2026-04-16)
- Strategy Alerts: Lune Trading (2026-05-01), TradersPost (2026-04-15)

## SUCCESS CRITERIA

Coverage: All 12 domains covered by at least one skill
No Overlap: Each skill has distinct ownership, no duplicate coverage
Routing: User can be routed to correct skill based on question type
Evidence: All claims backed by official docs or GitHub permalinks
Completeness: Skill can answer 95%+ of questions in its domain without cross-referencing
Clarity: Skill boundaries are clear and unambiguous

## NEXT STEPS

1. Review this proposal with Hermes and stakeholders
2. Prioritize implementation (Phase 1 foundation skills first)
3. Create skill templates with knowledge.md structure
4. Populate with evidence from official docs + GitHub
5. Test routing with sample questions
6. Iterate based on real usage patterns
