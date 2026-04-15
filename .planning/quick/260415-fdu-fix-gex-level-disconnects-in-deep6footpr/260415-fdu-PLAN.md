---
phase: 260415-fdu
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
  - ninjatrader/docs/SETUP.md
  - ninjatrader/docs/ARCHITECTURE.md
autonomous: true
requirements:
  - QUICK-260415-fdu
must_haves:
  truths:
    - "GEX fetches run on a 60s background timer, independent of tape activity / OnBarUpdate cadence"
    - "GEX levels stay drawn on the chart during a transient fetch failure (last-good profile survives retries)"
    - "On fetch failure, the next retry occurs in 5s → 15s → 60s (exponential backoff, capped at _gexInterval = 2 min), not after the normal 2-minute interval"
    - "HttpClient tolerates up to 20 paginated pages via a 30s timeout"
    - "MassiveGexClient authenticates successfully against massive.com (Polygon-compatible /v3/snapshot/options/<ticker>) using query-param auth, matching the Python reference implementation in deep6/engines/gex.py"
    - "OnBarUpdate no longer drives the GEX fetch loop; MaybeFetchGex() call site at line 1249 is removed"
    - "Timer is started in State.DataLoaded and disposed in State.Terminated, matching the existing _gexClient/_gexCts lifecycle pattern"
  artifacts:
    - path: "ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs"
      provides: "Background timer-driven GEX fetch with backoff, query-param auth, 30s HTTP timeout, split status tracking"
      contains: "System.Threading.Timer"
    - path: "ninjatrader/docs/SETUP.md"
      provides: "Updated GEX troubleshooting — backoff behavior, query-param auth"
      contains: "60s"
    - path: "ninjatrader/docs/ARCHITECTURE.md"
      provides: "Updated threading model — background timer replaces OnBarUpdate-driven fetch"
      contains: "Timer"
  key_links:
    - from: "State.DataLoaded"
      to: "_gexTimer = new System.Threading.Timer"
      via: "constructor with 0 dueTime and Timeout.Infinite period (manual rescheduling)"
      pattern: "_gexTimer\\s*=\\s*new\\s+System\\.Threading\\.Timer"
    - from: "State.Terminated"
      to: "_gexTimer.Dispose()"
      via: "disposal alongside _gexCts.Cancel() and _gexClient.Dispose()"
      pattern: "_gexTimer[\\s\\S]{0,40}Dispose"
    - from: "MassiveGexClient.FetchAsync"
      to: "massive.com /v3/snapshot/options/<underlying>?apiKey=<key>"
      via: "query-string apiKey parameter (not Authorization: Bearer header)"
      pattern: "apiKey="
---

<objective>
Fix GEX level disconnects in DEEP6Footprint.cs. Three root causes:
(1) GEX fetch is driven by OnBarUpdate — stalls whenever tape slows or bars don't close.
(2) Any transient HTTP failure blanks the chart because _gexStatus and _gexProfile are coupled and the retry doesn't happen for another full 2 min.
(3) The C# MassiveGexClient uses `Authorization: Bearer <key>` — but the Python reference (deep6/engines/gex.py line 197) and the JSON layout (next_url, open_interest, strike_price, underlying_asset.price) prove the API is Polygon.io-compatible and expects `?apiKey=<key>` as a query parameter. This is very likely why fetches are silently returning empty / 401.

Purpose: Keep GEX levels stable and visible on the chart regardless of tape activity or transient network hiccups, and correct the auth style to match the actual massive.com/Polygon API contract.

Output: Modified DEEP6Footprint.cs with (a) a background System.Threading.Timer replacing OnBarUpdate-driven MaybeFetchGex, (b) exponential-backoff retry (5s → 15s → 60s, cap 2 min), (c) split status tracking so last-good profile persists during retries, (d) 30s HTTP timeout + raised connection limit + keep-alive, (e) query-param auth. Updated SETUP.md and ARCHITECTURE.md docs.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
@ninjatrader/docs/SETUP.md
@ninjatrader/docs/ARCHITECTURE.md
@deep6/engines/gex.py

<interfaces>
<!-- Key snippets the executor needs. All line numbers reference DEEP6Footprint.cs. -->

## Current state fields (lines 981-988)
```csharp
// GEX
private MassiveGexClient _gexClient;
private volatile GexProfile _gexProfile;
private DateTime _lastGexFetch = DateTime.MinValue;
private readonly TimeSpan _gexInterval = TimeSpan.FromMinutes(2);
private CancellationTokenSource _gexCts;
// Status string updated through every fetch path; visible at top-right of chart and in NT8 Output Window.
private volatile string _gexStatus = "GEX: idle (no key)";
```

## Current MassiveGexClient ctor (lines 775-789) — currently Bearer-auth
```csharp
public MassiveGexClient(string apiKey, string baseUrl = "https://api.massive.com")
{
    _apiKey = apiKey ?? throw new ArgumentNullException("apiKey");
    _baseUrl = baseUrl.TrimEnd('/');

    ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
    _http = new HttpClient
    {
        BaseAddress = new Uri(_baseUrl),
        Timeout = TimeSpan.FromSeconds(8),
    };
    _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
    _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    _http.DefaultRequestHeaders.UserAgent.ParseAdd("DEEP6-NT8/1.0");
}
```

## Current FetchAsync URL construction (line 798) — needs apiKey query param
```csharp
string url = string.Format("/v3/snapshot/options/{0}?limit=250", underlying);
// ...
if (!string.IsNullOrEmpty(url) && url.StartsWith(_baseUrl)) url = url.Substring(_baseUrl.Length);
```

## Python reference — deep6/engines/gex.py line 195-214 (CONFIRMED query-param auth)
```python
url = f"{self.base_url}/v3/snapshot/options/{self.underlying}"
params = {
    "apiKey": self.api_key,
    "limit": 250,
    "strike_price.gte": spot_price * 0.90,
    "strike_price.lte": spot_price * 1.10,
}
# ...
r = requests.get(url, params=params, timeout=15)
# next_url has other params built in:
params = {"apiKey": self.api_key}
```

## Current DataLoaded GEX init (lines 1068-1081)
```csharp
else if (string.IsNullOrWhiteSpace(GexApiKey)) { ... }
else
{
    _gexClient = new MassiveGexClient(GexApiKey);
    _gexCts = new CancellationTokenSource();
    _gexStatus = "GEX: initializing — first fetch in progress";
    Print("[DEEP6] GEX client initialized. Fetching " + GexUnderlying + " chain from massive.com…");
    _lastGexFetch = DateTime.MinValue;
}
```

## Current Terminated GEX teardown (lines 1094-1102)
```csharp
else if (State == State.Terminated)
{
    if (_gexCts != null) { try { _gexCts.Cancel(); } catch { } }
    if (_gexClient != null) { _gexClient.Dispose(); _gexClient = null; }
    try { if (ChartControl != null) ChartControl.MouseDown -= OnChartTraderMouseDown; } catch { }
    _ctMouseWired = false;
    DisposeDx();
}
```

## Current OnBarUpdate driver (line 1249) — REMOVE
```csharp
// Kick GEX fetch if due.
MaybeFetchGex();
```

## Current MaybeFetchGex (lines 1283-1320) — REPLACE with timer callback
Sets `_lastGexFetch = DateTime.UtcNow` BEFORE the await (line 1287), so a failed or long-running fetch blocks the next attempt for the full 2-minute interval. Must move to AFTER success and add backoff on failure.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix MassiveGexClient auth + timeout + connection limits</name>
  <files>ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs</files>
  <action>
Modify the `MassiveGexClient` class (lines ~769-925) as follows:

1. **Switch auth from Bearer header to query-param `apiKey`** (matches deep6/engines/gex.py line 197 and the Polygon-compatible JSON layout already being parsed in FetchAsync):
   - In the constructor (line 786): REMOVE the line `_http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);`
   - In `FetchAsync` (line 798): change the initial URL from `"/v3/snapshot/options/{0}?limit=250"` to `"/v3/snapshot/options/{0}?limit=250&apiKey={1}"` with `Uri.EscapeDataString(_apiKey)` for the key.
   - IMPORTANT: The pagination path around line 836-837 reuses `nextUrl` directly from the JSON. Polygon's `next_url` already embeds its own apiKey — DO NOT re-append. Matches the Python reference at line 214 (`params = {"apiKey": self.api_key}` only resets on the first call pattern; for Polygon's next_url the key is already baked in). Add a comment confirming this.
   - Add a SINGLE-LINE FALLBACK COMMENT in the ctor: `// NOTE: If massive.com ever returns 401 with query-param auth, swap to DefaultRequestHeaders.Authorization Bearer. Python ref (deep6/engines/gex.py) confirms query-param is correct as of 2026-04-15.`

2. **Raise HttpClient timeout from 8s to 30s** (line 784): `Timeout = TimeSpan.FromSeconds(30)` — required to tolerate up to 20 paginated pages.

3. **Raise ServicePointManager.DefaultConnectionLimit and enable keep-alive** — add BEFORE the `_http = new HttpClient` line:
   ```csharp
   if (ServicePointManager.DefaultConnectionLimit < 8)
       ServicePointManager.DefaultConnectionLimit = 8;
   ```
   Keep-alive is HTTP/1.1 default for HttpClient; ensure no `Connection: close` is emitted. The existing code already doesn't set Connection header, so no change needed — but add a comment confirming keep-alive is intentional.

Do NOT touch the JSON extraction helpers, GEX math, or pagination logic.
  </action>
  <verify>
    <automated>grep -n "apiKey=" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && grep -n "TimeSpan.FromSeconds(30)" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && ! grep -n "AuthenticationHeaderValue(\"Bearer\"" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && grep -n "DefaultConnectionLimit" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs</automated>
  </verify>
  <done>
- `Authorization: Bearer` header is removed from MassiveGexClient.
- First-page URL carries `?limit=250&apiKey=<escaped>`.
- `next_url` is still followed as-is (pagination unchanged).
- HttpClient.Timeout = 30s.
- DefaultConnectionLimit raised to at least 8.
- File still compiles as valid C# (brace-balanced, no orphaned members).
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Replace OnBarUpdate-driven MaybeFetchGex with background Timer + backoff + split status</name>
  <files>ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs</files>
  <behavior>
- Timer fires every 60s regardless of OnBarUpdate / tape activity.
- On fetch success: `_gexProfile` updated, `_gexLastSuccess` set to DateTime.UtcNow, `_gexFailCount` reset to 0, next timer tick scheduled at 60s (or `_gexInterval` if shorter).
- On fetch failure: `_gexProfile` UNCHANGED (last-good levels stay drawn), `_gexFailCount` incremented, next timer tick scheduled at 5s (first failure), 15s (second), 60s (third), capped at `_gexInterval` (2 min) thereafter.
- `_gexStatus` is split into two fields: `_gexLastSuccessStatus` (sticky — e.g., "GEX: 42 levels @ 13:45") and `_gexRetryStatus` (transient — e.g., "retry in 15s after error: HttpRequestException"). The render layer concatenates them so the user sees both: levels stayed drawn AND a retry is in flight.
- Timer is started in State.DataLoaded (same block as _gexClient init, lines 1074-1081).
- Timer is disposed in State.Terminated (same block as _gexCts.Cancel, lines 1094-1102).
- `MaybeFetchGex()` call at line 1249 in OnBarUpdate is REMOVED — timer is the sole driver.
  </behavior>
  <action>
1. **Update state fields (lines 981-988)**:
   - KEEP `_gexClient`, `_gexProfile`, `_gexCts`, `_gexInterval`.
   - REMOVE `_lastGexFetch` (replaced by timer internal scheduling).
   - ADD:
     ```csharp
     private System.Threading.Timer _gexTimer;
     private int _gexFailCount;                    // consecutive failures, resets on success
     private DateTime _gexLastSuccess = DateTime.MinValue;
     private volatile string _gexLastSuccessStatus = "GEX: idle (no key)";  // sticky — never cleared on failure
     private volatile string _gexRetryStatus = string.Empty;                // transient — set during retry, cleared on success
     private readonly object _gexTimerLock = new object();
     ```
   - REPLACE the `_gexStatus` field with a computed property:
     ```csharp
     private string _gexStatus
     {
         get
         {
             var s = _gexLastSuccessStatus ?? string.Empty;
             var r = _gexRetryStatus ?? string.Empty;
             return string.IsNullOrEmpty(r) ? s : s + "  [" + r + "]";
         }
     }
     ```
     (The setter is no longer needed; all existing assignments in the file that previously wrote `_gexStatus = "..."` must be rewritten to assign to either `_gexLastSuccessStatus` or `_gexRetryStatus`. Audit: lines 988 (initializer → move to field initializer on `_gexLastSuccessStatus`), 1066, 1070, 1077, 1294, 1305, 1310, 1316. For the fetch-path writes inside the new timer callback, use `_gexLastSuccessStatus` on success and `_gexRetryStatus` on failure.)

2. **Replace `MaybeFetchGex` (lines 1283-1320) with two methods:**

   ```csharp
   // Timer callback — runs on a ThreadPool thread, NEVER on NT data/chart threads.
   // Must not touch Draw.*, RenderTarget, or NT collections; only _gexProfile (volatile) and status strings (volatile).
   private void GexTimerTick(object state)
   {
       // Re-entrance guard: if a previous fetch is still in flight, skip this tick.
       if (!System.Threading.Monitor.TryEnter(_gexTimerLock)) return;
       try
       {
           var client = _gexClient;
           if (client == null) return;
           var ctsTok = _gexCts == null ? CancellationToken.None : _gexCts.Token;
           if (ctsTok.IsCancellationRequested) return;
           var underlying = GexUnderlying;

           _gexRetryStatus = "fetching " + underlying + "…";
           Print("[DEEP6] GEX fetch start: " + underlying + " @ " + DateTime.Now.ToString("HH:mm:ss"));

           // Fire and wait for this tick's fetch to complete before scheduling next one.
           try
           {
               var profile = client.FetchAsync(underlying, ctsTok).GetAwaiter().GetResult();
               if (profile != null && profile.Levels.Count > 0)
                   OnGexFetchSuccess(profile);
               else
                   OnGexFetchFailure(new InvalidOperationException("empty response (check API key, plan, underlying)"));
           }
           catch (OperationCanceledException) { /* shutdown — stay silent */ }
           catch (Exception ex) { OnGexFetchFailure(ex); }
       }
       finally
       {
           System.Threading.Monitor.Exit(_gexTimerLock);
           ScheduleNextGexTick();
       }
   }

   private void OnGexFetchSuccess(GexProfile profile)
   {
       _gexProfile = profile;
       _gexLastSuccess = DateTime.UtcNow;
       _gexFailCount = 0;
       _gexLastSuccessStatus = "GEX: " + profile.Levels.Count + " levels @ " + DateTime.Now.ToString("HH:mm");
       _gexRetryStatus = string.Empty;  // clear transient banner
       Print("[DEEP6] GEX OK: " + profile.Levels.Count + " levels, spot " + profile.Spot.ToString("F2") + ", flip " + profile.GammaFlip.ToString("F2"));
   }

   private void OnGexFetchFailure(Exception ex)
   {
       _gexFailCount++;
       // DO NOT clear _gexProfile — keep last-good levels drawn.
       var delay = ComputeGexRetryDelay(_gexFailCount);
       _gexRetryStatus = "retry in " + ((int)delay.TotalSeconds) + "s after " + ex.GetType().Name;
       Print("[DEEP6] GEX EXCEPTION (#" + _gexFailCount + "): " + ex.GetType().Name + " — " + ex.Message + ". Retrying in " + (int)delay.TotalSeconds + "s.");
   }

   // 5s → 15s → 60s → 120s (cap = _gexInterval).
   private TimeSpan ComputeGexRetryDelay(int failCount)
   {
       if (failCount <= 0) return TimeSpan.FromSeconds(60);
       switch (failCount)
       {
           case 1: return TimeSpan.FromSeconds(5);
           case 2: return TimeSpan.FromSeconds(15);
           case 3: return TimeSpan.FromSeconds(60);
           default: return _gexInterval;  // 2 min cap
       }
   }

   private void ScheduleNextGexTick()
   {
       if (_gexTimer == null) return;
       try
       {
           var next = _gexFailCount == 0 ? TimeSpan.FromSeconds(60) : ComputeGexRetryDelay(_gexFailCount);
           _gexTimer.Change(next, System.Threading.Timeout.InfiniteTimeSpan);
       }
       catch (ObjectDisposedException) { /* shutting down */ }
   }
   ```

3. **Update State.DataLoaded (lines 1074-1081)** — after `_gexCts = new CancellationTokenSource();`, add:
   ```csharp
   _gexFailCount = 0;
   _gexLastSuccessStatus = "GEX: initializing — first fetch in progress";
   _gexRetryStatus = string.Empty;
   // Fire first fetch immediately (dueTime=0), then each tick self-schedules via ScheduleNextGexTick.
   _gexTimer = new System.Threading.Timer(GexTimerTick, null, TimeSpan.Zero, System.Threading.Timeout.InfiniteTimeSpan);
   ```

4. **Update State.Terminated (lines 1094-1102)** — add timer disposal BEFORE the _gexCts.Cancel call so no new tick can start after cancellation:
   ```csharp
   if (_gexTimer != null) { try { _gexTimer.Dispose(); } catch { } _gexTimer = null; }
   if (_gexCts != null) { try { _gexCts.Cancel(); } catch { } }
   if (_gexClient != null) { _gexClient.Dispose(); _gexClient = null; }
   ```

5. **Remove `MaybeFetchGex()` call from OnBarUpdate** (line 1249 and the preceding comment `// Kick GEX fetch if due.`). The timer is now the sole driver.

6. **Remove the old `MaybeFetchGex()` method body** (lines 1283-1320) entirely — it's replaced by the new timer methods above.

7. **Audit every reference to `_lastGexFetch` and `_gexStatus` setter** — since `_gexStatus` is now a read-only computed property, any remaining assignment like `_gexStatus = "..."` will fail to compile. Rewrite each to target either `_gexLastSuccessStatus` (for success/steady state) or `_gexRetryStatus` (for transient errors). Expected sites: line 988 initializer, 1066, 1070, 1077, and any inside the old MaybeFetchGex (being deleted).
  </action>
  <verify>
    <automated>grep -n "System.Threading.Timer" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && grep -n "GexTimerTick" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && grep -n "ScheduleNextGexTick" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && grep -n "_gexLastSuccessStatus\|_gexRetryStatus" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && ! grep -n "MaybeFetchGex" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && ! grep -n "_lastGexFetch" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs</automated>
  </verify>
  <done>
- `System.Threading.Timer _gexTimer` field exists and is initialized in State.DataLoaded with dueTime=0, period=Infinite (self-rescheduling).
- `_gexTimer.Dispose()` is called in State.Terminated BEFORE `_gexCts.Cancel()`.
- `MaybeFetchGex` method is deleted; its call site in OnBarUpdate is removed.
- `_lastGexFetch` field is deleted.
- `_gexFailCount`, `_gexLastSuccess`, `_gexLastSuccessStatus`, `_gexRetryStatus`, `_gexTimerLock` fields exist.
- `ComputeGexRetryDelay` returns 5s/15s/60s/120s (cap) for failCount 1/2/3/4+.
- On failure, `_gexProfile` is NOT cleared (last-good persists).
- Re-entrance guarded via `Monitor.TryEnter(_gexTimerLock)`.
- File compiles as valid C# — run `dotnet build` is NOT available (NinjaScript compiles inside NT8 via F5), so verification is static: bracket balance, no `_gexStatus = ` writes remain, no orphaned `MaybeFetchGex` refs.
  </done>
</task>

<task type="auto">
  <name>Task 3: Update SETUP.md and ARCHITECTURE.md for new GEX behavior</name>
  <files>ninjatrader/docs/SETUP.md, ninjatrader/docs/ARCHITECTURE.md</files>
  <action>
1. **SETUP.md** — replace the "GEX levels don't appear" troubleshooting block (lines ~73-77) with:
   ```markdown
   **"GEX levels don't appear"**
   - Verify API key is populated and `ShowGexLevels` is true.
   - First fetch runs immediately at chart load. Subsequent fetches run every **60s on a background timer** — independent of tape activity. If tape is frozen, GEX still updates.
   - On transient network failure, levels **stay drawn** (last-good profile). Retry schedule: 5s → 15s → 60s → 2 min cap.
   - Check the NT8 Output window (New → Output Window) for `[DEEP6] GEX EXCEPTION (#N)` messages — N is the consecutive failure count.
   - Confirm massive.com plan covers real-time (or delayed, acceptable for GEX) options chain snapshots.
   - Auth: the indicator uses **query-param** auth (`?apiKey=<key>`), matching massive.com's Polygon.io-compatible API. If your plan requires Bearer-header auth instead, see the `MassiveGexClient` ctor comment in DEEP6Footprint.cs for the one-line switch.
   ```

2. **ARCHITECTURE.md** — update the data-flow diagram and threading table:
   - Replace the line `└─ MaybeFetchGex (every 2 min)` in the OnBarUpdate branch (line ~32) with a blank line or comment noting the timer drives GEX independently.
   - Add a new branch under "Data flow" (before the `Task.Run` block, around line 40):
     ```
     System.Threading.Timer (60s) ─── GexTimerTick ──► MassiveGexClient.FetchAsync
                                            │
                                            ├─ success → _gexProfile (volatile), _gexFailCount=0, reschedule 60s
                                            └─ failure → _gexProfile UNCHANGED, backoff 5s→15s→60s→120s cap
     ```
   - In the threading-model table (lines ~50-54), REMOVE the old `Task.Run (async FetchAsync)` row and ADD:
     | Background timer | `GexTimerTick` (ThreadPool) | HTTP + volatile writes only. Touch no NT APIs. Re-entrance guarded by Monitor. Writes `_gexProfile`, `_gexLastSuccessStatus`, `_gexRetryStatus`. |
   - Under "Failure modes" (lines ~97-), update `**GEX fetch fails**` to:
     `**GEX fetch fails** → _gexProfile UNCHANGED (last-good levels keep rendering). Retry runs on exponential backoff (5s/15s/60s/cap 2min). _gexRetryStatus banner shows countdown to next attempt.`
  </action>
  <verify>
    <automated>grep -n "60s on a background timer\|query-param" ninjatrader/docs/SETUP.md && grep -n "GexTimerTick\|backoff" ninjatrader/docs/ARCHITECTURE.md</automated>
  </verify>
  <done>
- SETUP.md troubleshooting block mentions 60s background timer, backoff schedule (5s→15s→60s→2min), last-good persistence, and query-param auth.
- ARCHITECTURE.md data-flow diagram shows Timer → GexTimerTick branch.
- ARCHITECTURE.md threading table has an entry for the background timer.
- ARCHITECTURE.md failure-modes section states last-good levels stay rendered during retries.
  </done>
</task>

</tasks>

<verification>
Manual compile check inside NT8 (F5 in NinjaScript Editor) must succeed — this is the only real compiler for NinjaScript. Static checks before handing to user:

1. No references to `MaybeFetchGex` anywhere in DEEP6Footprint.cs.
2. No references to `_lastGexFetch` anywhere.
3. No assignments to `_gexStatus` (it's now a read-only property).
4. No `Authorization: Bearer` header on MassiveGexClient's _http.
5. First-page URL includes `&apiKey=`.
6. HttpClient.Timeout = 30s.
7. `_gexTimer` is created in State.DataLoaded and disposed in State.Terminated.
8. Brace balance sanity check: `awk '{for(i=1;i<=length($0);i++){c=substr($0,i,1);if(c=="{")b++;if(c=="}")b--}}END{print b}' ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` should print 0.

Runtime verification (user, after F5 compile succeeds in NT8):
1. Open any NQ chart with the indicator attached, massive.com API key populated.
2. Within 1-2 seconds of chart load, Output Window should show `[DEEP6] GEX fetch start` followed by either `[DEEP6] GEX OK: N levels` (success path) or `[DEEP6] GEX EXCEPTION (#1)` with a specific error.
3. If exception path: next retry happens in ~5s (visible in Output Window as another `GEX fetch start`), then ~15s, then ~60s. Levels on chart stay drawn from any previously-successful fetch.
4. Let chart idle with no tape activity for >60s — verify a new `GEX fetch start` appears in Output Window. This confirms the timer is independent of OnBarUpdate.
5. If auth fails with 401 despite query-param: flip to Bearer via the fallback comment in MassiveGexClient ctor.
</verification>

<success_criteria>
- GEX fetches occur every 60s regardless of tape activity (timer-driven, not bar-driven).
- Transient fetch failures do NOT clear levels from the chart.
- Backoff schedule is 5s → 15s → 60s → 120s cap.
- HttpClient tolerates 20 paginated pages via 30s timeout.
- Auth uses `?apiKey=<key>` query parameter (matching deep6/engines/gex.py and Polygon.io convention).
- NT8 F5 compile succeeds with zero errors.
- SETUP.md and ARCHITECTURE.md accurately describe the new behavior.
</success_criteria>

<output>
After completion, create `.planning/quick/260415-fdu-fix-gex-level-disconnects-in-deep6footpr/260415-fdu-SUMMARY.md`
</output>
