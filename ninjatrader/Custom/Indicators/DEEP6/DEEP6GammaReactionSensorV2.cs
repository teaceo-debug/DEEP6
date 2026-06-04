// DEEP6 Gamma Reaction Sensor V2 — NT8 indicator.
// Monitors price approaching GDS V2 GEX levels and fires confirmation signals
// when AbsorptionDetector or ExhaustionDetector fires within a proximity band.
//
// Depends on:
//   - DEEP6GammaDecisionSurface.cs (GdsPayload/GdsLevel DTOs in same namespace)
//   - AddOns: AbsorptionDetector, ExhaustionDetector, FootprintBar, SessionContext
//
// JSON source: massive_gex_map_v2.json (same file as DEEP6GammaDecisionSurface)
// Namespace: NinjaTrader.NinjaScript.Indicators.DEEP6

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
// Using aliases disambiguate legacy root-namespace versions (in DEEP6Footprint.cs)
// from the modern ISignalDetector versions in the Detectors subdirectory.
using AbsorptionDetector = NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionDetector;
using AbsorptionConfig   = NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionConfig;
using ExhaustionDetector = NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector;
using ExhaustionConfig   = NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionConfig;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6GammaReactionSensorV2 : Indicator
    {
        #region Fields

        // ---- GDS JSON state (same pattern as GammaDecisionSurface) ----
        private readonly object _sync = new object();
        private Timer _refreshTimer;
        private GdsPayload _payload;
        private GdsAsset _asset;

        // ---- FootprintBar building (same pattern as DEEP6FootprintV7) ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private readonly object _barsLock = new object();
        private readonly HashSet<int> _finalizedBars = new HashSet<int>();
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private long _priorCvd;
        private FootprintBar _priorFinalized;

        // ---- Order flow state (ATR + VolEma — same as V7) ----
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;
        private double _vah = double.NaN;
        private double _val = double.NaN;

        // ---- Detectors (from AddOns) ----
        private readonly AbsorptionDetector _absDetector = new AbsorptionDetector();
        private readonly ExhaustionDetector _exhDetector = new ExhaustionDetector();
        private readonly SessionContext _session = new SessionContext();

        // ---- Per-level state ----
        private LevelState[] _levelStates = new LevelState[0];

        // ---- Fired signal history (persistent chart markers) ----
        private readonly List<GrsSignal> _signals = new List<GrsSignal>();
        private const int MaxSignalHistory = 20;

        // ---- Session reset ----
        private DateTime _lastSessionDate = DateTime.MinValue;

        // ---- SharpDX resources ----
        private SharpDX.Direct2D1.Brush dxDefend, dxDefendFill, dxDefendBand;
        private SharpDX.Direct2D1.Brush dxReject, dxRejectFill, dxRejectBand;
        private SharpDX.Direct2D1.Brush dxAttract, dxAttractFill, dxAttractBand;
        private SharpDX.Direct2D1.Brush dxFlip, dxFlipFill, dxFlipBand;
        private SharpDX.Direct2D1.Brush dxPanel, dxText, dxMuted, dxHalo, dxGreen, dxRed;
        private SharpDX.Direct2D1.Brush dxRiskZone, dxRewardZone, dxEntryZone;
        private SharpDX.Direct2D1.Brush dxStopLine, dxTargetLine, dxGoldBright;
        private SharpDX.Direct2D1.StrokeStyle dxDashedStroke;
        private TextFormat fontPill, fontMono, fontTiny, fontDecision, fontDecisionBold;

        #endregion

        #region Inner Types

        // Per-GDS-level order flow accumulator
        private sealed class LevelState
        {
            public string  Id;
            public double  Price;
            public string  BehaviorState;   // DEFEND / REJECT / ATTRACT / FLIP / OPEN_SPACE
            public string  Tier;            // T1 / T2 / T3
            public string  ActionHint;      // HOLD / FADE / TARGET / WATCH_FOR_FLIP
            public double  ConfidenceScore;
            public string  StructuralSource;

            // Proximity tracking
            public bool    IsActive;
            public int     ActiveSinceBar;
            public double  DeltaAccum;
            public int     AbsorbHits;
            public int     ExhaustHits;

            // Signal cooldown
            public int     LastSignalBar;
            public int     CooldownRemaining;

            // Touch tracking
            public int     TouchCount;          // how many times this level has been within proximity today
        }

        // Fired signal (stored for persistent chart markers + setup rendering)
        private sealed class GrsSignal
        {
            public int    BarIndex;
            public double Price;
            public string LevelId;
            public string BehaviorState;
            public string Kind;        // ABSORB_CONFIRM / EXHAUST_CONFIRM / FLIP_BREAK
            public int    Direction;   // +1 long / -1 short
            public float  Confidence;  // 0.0 – 1.0
            public string Label;
            public DateTime Time;
            public bool   WithRegime;  // aligned with FlashAlpha regime?
            public string VexTag;      // "VEX↑" / "VEX↓" / ""
            public string ChexTag;     // "CHEX↑" / "CHEX↓" / ""

            // Setup geometry (computed by TryFireSignal)
            public double EntryPrice;       // bar.Close at signal fire
            public double LevelPrice;       // the GEX level price (st.Price)
            public double StopPrice;        // structural stop beyond the level
            public double TargetPrice;      // next GEX level in direction of trade
            public double RiskPts;          // |EntryPrice - StopPrice|
            public double RewardPts;        // |TargetPrice - EntryPrice|
            public float  RR;               // RewardPts / RiskPts
            public bool   HasPayoff;        // RR >= MinRR threshold
            public string TargetLevelId;    // id of the target GEX level (or "FALLBACK")
        }

        #endregion

        #region Lifecycle

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description          = "DEEP6 Gamma Reaction Sensor V2 — fires confirmation signals with setup zones, decision rail, structural stop, and target levels at active GDS V2 GEX levels.";
                Name                 = "DEEP6 Gamma Reaction Sensor V2";
                Calculate            = Calculate.OnEachTick;
                IsOverlay            = true;
                IsSuspendedWhileInactive = true;

                JsonFilePath         = @"%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map_v2.json";
                RefreshSeconds       = 2;
                ProximityPoints      = 15.0;
                MinAbsorbHits        = 2;
                DeltaThreshold       = 200.0;
                FlipDeltaThreshold   = 350.0;
                CooldownBars         = 5;
                ShowProximityBands   = true;
                ShowStatusPills      = true;
                ShowSignalMarkers    = true;
                OnlyT1T2             = true;
                MinRR                = 1.5;
                StopAtrMultiplier    = 0.5;
                ShowSetupZones       = true;
                ShowDecisionRail     = true;
            }
            else if (State == State.Historical)
            {
                _session.TickSize = TickSize > 0 ? TickSize : 0.25;
                _refreshTimer = new Timer(ReadSnapshotSafe, null, 500, Math.Max(1, RefreshSeconds) * 1000);
            }
            else if (State == State.Terminated)
            {
                if (_refreshTimer != null) { _refreshTimer.Dispose(); _refreshTimer = null; }
                DisposeDx();
            }
        }

        #endregion

        #region Market Data

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;

            // Session reset at date boundary
            DateTime currentDate = Time[0].Date;
            if (currentDate != _lastSessionDate)
            {
                if (_lastSessionDate != DateTime.MinValue)
                {
                    _priorCvd = 0;
                    _priorFinalized = null;
                    _vah = double.NaN;
                    _val = double.NaN;
                    _absDetector.Reset();
                    _exhDetector.Reset();
                    _session.ResetSession();
                    _session.TickSize = TickSize > 0 ? TickSize : 0.25;
                }
                _lastSessionDate = currentDate;
            }

            // Ensure current bar has a FootprintBar
            if (IsFirstTickOfBar)
            {
                lock (_barsLock)
                {
                    if (!_bars.ContainsKey(CurrentBar))
                        _bars[CurrentBar] = new FootprintBar { BarIndex = CurrentBar };
                }
            }

            // Update proximity activation per level (every tick)
            UpdateLevelProximity();

            // On bar close: finalize previous bar and run detectors
            if (!IsFirstTickOfBar) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            lock (_barsLock) { _bars.TryGetValue(prevIdx, out prev); }
            if (prev != null && !_finalizedBars.Contains(prevIdx))
                FinalizeBarAndDetect(prev, prevIdx);
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (State != State.Realtime && State != State.Historical) return;

            if (e.MarketDataType == MarketDataType.Bid) { _bestBid = e.Price; return; }
            if (e.MarketDataType == MarketDataType.Ask) { _bestAsk = e.Price; return; }
            if (e.MarketDataType != MarketDataType.Last) return;
            if (CurrentBar < 0) return;

            int aggressor;
            if (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;
            else if (!double.IsNaN(_bestBid) && e.Price <= _bestBid) aggressor = 2;
            else aggressor = 0;

            lock (_barsLock)
            {
                FootprintBar bar;
                if (!_bars.TryGetValue(CurrentBar, out bar))
                {
                    bar = new FootprintBar { BarIndex = CurrentBar };
                    _bars[CurrentBar] = bar;
                }
                bar.AddTrade(e.Price, (long)e.Volume, aggressor);
            }

            // Accumulate delta toward active proximity levels
            long signed = aggressor == 1 ? (long)e.Volume : aggressor == 2 ? -(long)e.Volume : 0;
            if (signed != 0)
            {
                LevelState[] states;
                lock (_sync) { states = _levelStates; }
                for (int i = 0; i < states.Length; i++)
                {
                    if (states[i].IsActive)
                        states[i].DeltaAccum += signed;
                }
            }
        }

        #endregion

        #region Detection

        private void FinalizeBarAndDetect(FootprintBar bar, int barIdx)
        {
            _finalizedBars.Add(barIdx);

            // Reconcile OHLC with NT8's authoritative bar values (barIdx = CurrentBar-1, so barsAgo=1)
            int barsAgo = CurrentBar - barIdx;
            if (barsAgo >= 0 && CurrentBar >= barsAgo)
            {
                bar.Open  = Open[barsAgo];
                bar.High  = High[barsAgo];
                bar.Low   = Low[barsAgo];
                bar.Close = Close[barsAgo];
            }

            bar.Finalize(_priorCvd);
            _priorCvd = bar.Cvd;

            // Update ATR
            _atrWindow.Enqueue(bar.BarRange);
            if (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            if (_atrWindow.Count > 0) { double s = 0; foreach (var v in _atrWindow) s += v; _atr = Math.Max(s / _atrWindow.Count, 0.25); }

            // Update VolEma
            _volEma = _volEma == 0 ? bar.TotalVol : _volEma + VolEmaAlpha * (bar.TotalVol - _volEma);

            // Update VAH/VAL
            double tickSz = TickSize > 0 ? TickSize : 0.25;
            var va = FootprintBar.ComputeValueArea(bar, tickSz);
            _vah = va.vah;
            _val = va.val;

            // Update SessionContext
            _session.Atr20    = _atr;
            _session.VolEma20 = _volEma;
            _session.PriorBar = _priorFinalized;
            _session.Vah      = double.IsNaN(_vah) ? (double?)null : _vah;
            _session.Val      = double.IsNaN(_val) ? (double?)null : _val;
            _session.TickSize = tickSz;
            _session.BarsSinceOpen++;
            SessionContext.Push(_session.PriceHistory, bar.Close);
            SessionContext.Push(_session.CvdHistory, bar.Cvd);

            // Run detectors
            var absResults = _absDetector.OnBar(bar, _session);
            var exhResults = _exhDetector.OnBar(bar, _session);

            // Cross-reference against active GDS levels
            LevelState[] states;
            lock (_sync) { states = _levelStates; }
            for (int i = 0; i < states.Length; i++)
            {
                var st = states[i];
                if (!st.IsActive) continue;
                if (OnlyT1T2 && st.Tier == "T3") continue;
                if (st.CooldownRemaining > 0) { st.CooldownRemaining--; continue; }

                // Check absorption signals near this level
                foreach (var r in absResults)
                {
                    double sigPrice = r.Direction < 0 ? bar.High : bar.Low;
                    if (Math.Abs(sigPrice - st.Price) <= ProximityPoints + 5.0)
                        st.AbsorbHits++;
                }

                // Check exhaustion signals near this level
                foreach (var r in exhResults)
                {
                    double sigPrice = r.Direction < 0 ? bar.High : r.Direction > 0 ? bar.Low : bar.Close;
                    if (Math.Abs(sigPrice - st.Price) <= ProximityPoints + 5.0)
                        st.ExhaustHits++;
                }

                // Evaluate fire conditions
                TryFireSignal(st, bar, barIdx);
            }

            _priorFinalized = bar;

            // Trim bar cache (keep last 200 bars)
            if (_bars.Count > 200)
            {
                int oldest = barIdx - 200;
                lock (_barsLock)
                {
                    var stale = new List<int>();
                    foreach (var k in _bars.Keys)
                        if (k < oldest) stale.Add(k);
                    foreach (var k in stale) _bars.Remove(k);
                }
                _finalizedBars.RemoveWhere(k => k < oldest);
            }
        }

        private void TryFireSignal(LevelState st, FootprintBar bar, int barIdx)
        {
            int direction = 0;
            string kind = null;

            if (st.BehaviorState == "DEFEND")
            {
                if (st.DeltaAccum < -DeltaThreshold * 0.3 && st.AbsorbHits >= MinAbsorbHits)
                { direction = +1; kind = "ABSORB_CONFIRM"; }
            }
            else if (st.BehaviorState == "REJECT")
            {
                if (st.DeltaAccum > DeltaThreshold * 0.3 && (st.AbsorbHits >= MinAbsorbHits || st.ExhaustHits >= 1))
                { direction = -1; kind = "EXHAUST_CONFIRM"; }
            }
            else if (st.BehaviorState == "ATTRACT")
            {
                if (Math.Abs(st.DeltaAccum) >= DeltaThreshold)
                { direction = (int)Math.Sign(st.Price - bar.Close); kind = "ABSORB_CONFIRM"; }
            }
            else if (st.BehaviorState == "FLIP")
            {
                if (Math.Abs(st.DeltaAccum) >= FlipDeltaThreshold)
                { direction = (int)Math.Sign(st.DeltaAccum); kind = "FLIP_BREAK"; }
            }

            if (direction == 0 || kind == null) return;

            float tierW = st.Tier == "T1" ? 1.0f : st.Tier == "T2" ? 0.75f : 0.5f;
            float absRatio = st.AbsorbHits > 0 ? Math.Min(st.AbsorbHits / (float)MinAbsorbHits, 1.5f) : 0.5f;
            float confidence = Math.Min((float)st.ConfidenceScore * absRatio * tierW, 1.0f);

            // FlashAlpha context multipliers
            GdsFlashAlpha fa;
            lock (_sync) { fa = _asset != null ? _asset.flashalpha : null; }

            bool withRegime = false;
            string vexTag = "", chexTag = "";

            if (fa != null && fa.health == "live")
            {
                // VEX multiplier: signal in direction of vex_direction gets boost, opposite gets penalty
                bool vexAligned = (direction > 0 && fa.vex_direction == "bullish")
                               || (direction < 0 && fa.vex_direction == "bearish");
                bool vexOpposed = (direction > 0 && fa.vex_direction == "bearish")
                               || (direction < 0 && fa.vex_direction == "bullish");
                float vexMult = vexAligned ? 1.15f : vexOpposed ? 0.85f : 1.0f;

                // CHEX multiplier: signal in direction of chex_direction gets boost
                bool chexAligned = (direction > 0 && fa.chex_direction == "bullish")
                                || (direction < 0 && fa.chex_direction == "bearish");
                bool chexOpposed = (direction > 0 && fa.chex_direction == "bearish")
                                || (direction < 0 && fa.chex_direction == "bullish");
                float chexMult = chexAligned ? 1.08f : chexOpposed ? 0.92f : 1.0f;

                // 0DTE penalty: if 0DTE > 40% of GEX AND after 2pm ET (high 0DTE decay risk)
                float zdteMult = 1.0f;
                if (fa.zero_dte_pct >= 0.40 && DateTime.Now.TimeOfDay.TotalHours >= 14.0)
                    zdteMult = 0.75f;

                confidence = Math.Min(confidence * vexMult * chexMult * zdteMult, 1.0f);
                confidence = Math.Max(confidence, 0.0f);

                // With regime = signal direction aligns with FlashAlpha regime
                bool faRegimePositive = fa.regime != null && fa.regime.Contains("positive");
                withRegime = (direction > 0 && faRegimePositive) || (direction < 0 && !faRegimePositive);
                vexTag  = fa.vex_direction  == "bullish" ? "VEX\u2191" : fa.vex_direction  == "bearish" ? "VEX\u2193" : "";
                chexTag = fa.chex_direction == "bullish" ? "CHEX\u2191" : fa.chex_direction == "bearish" ? "CHEX\u2193" : "";
            }

            // --- Setup geometry ---
            double entryPrice = bar.Close;
            double levelPrice = st.Price;
            double stopPrice  = ComputeStructuralStop(st, direction);
            double riskPts    = Math.Abs(entryPrice - stopPrice);

            string targetLevelId;
            double targetPrice = FindTargetLevel(entryPrice, direction, st.Id, out targetLevelId);
            if (targetPrice <= 0)
            {
                targetPrice    = direction > 0 ? entryPrice + riskPts * 2.0 : entryPrice - riskPts * 2.0;
                targetLevelId  = "FALLBACK";
            }
            double rewardPts  = Math.Abs(targetPrice - entryPrice);
            float  rr         = riskPts > 0 ? (float)(rewardPts / riskPts) : 0f;
            bool   hasPayoff  = rr >= (float)MinRR;

            // Build label with FlashAlpha context
            var labelParts = new List<string> { FormatBehavior(st.BehaviorState), st.Tier };
            if (withRegime) labelParts.Add("\u2713");
            if (!string.IsNullOrEmpty(vexTag))  labelParts.Add(vexTag);
            if (!string.IsNullOrEmpty(chexTag)) labelParts.Add(chexTag);
            if (kind == "FLIP_BREAK") labelParts.Add("FLIP!");
            string label = string.Join("  ", labelParts);

            var sig = new GrsSignal
            {
                BarIndex      = barIdx,
                Price         = entryPrice,
                EntryPrice    = entryPrice,
                LevelPrice    = levelPrice,
                StopPrice     = stopPrice,
                TargetPrice   = targetPrice,
                RiskPts       = riskPts,
                RewardPts     = rewardPts,
                RR            = rr,
                HasPayoff     = hasPayoff,
                TargetLevelId = targetLevelId,
                LevelId       = st.Id,
                BehaviorState = st.BehaviorState,
                Kind          = kind,
                Direction     = direction,
                Confidence    = confidence,
                Label         = label,
                Time          = Time[0],
                WithRegime    = withRegime,
                VexTag        = vexTag,
                ChexTag       = chexTag,
            };

            lock (_sync)
            {
                _signals.Add(sig);
                while (_signals.Count > MaxSignalHistory) _signals.RemoveAt(0);
            }

            // Reset per-level accumulators and set cooldown
            st.DeltaAccum        = 0;
            st.AbsorbHits        = 0;
            st.ExhaustHits       = 0;
            st.LastSignalBar     = barIdx;
            st.CooldownRemaining = CooldownBars;

            RefreshChart();
        }

        private static string FormatBehavior(string behavior)
        {
            switch (behavior ?? "")
            {
                case "DEFEND":  return "DEFEND HOLDS";
                case "REJECT":  return "REJECT ACTIVE";
                case "ATTRACT": return "ATTRACT TARGET";
                case "FLIP":    return "FLIP BREAK";
                default:        return behavior ?? "";
            }
        }

        private double ComputeStructuralStop(LevelState st, int direction)
        {
            double atrBuf = _atr * StopAtrMultiplier;
            switch (st.BehaviorState)
            {
                case "DEFEND":
                    return st.Price - atrBuf;
                case "REJECT":
                    return st.Price + atrBuf;
                case "FLIP":
                    return direction > 0 ? st.Price - _atr * 0.75 : st.Price + _atr * 0.75;
                default:
                    double entry = Close[0];
                    return direction > 0 ? entry - atrBuf : entry + atrBuf;
            }
        }

        private double FindTargetLevel(double entryPrice, int direction, string sourceLevelId, out string targetLevelId)
        {
            targetLevelId = "FALLBACK";
            LevelState[] states;
            lock (_sync) { states = _levelStates; }

            double bestDist = double.MaxValue;
            double bestPrice = 0;

            foreach (var st in states)
            {
                if (st == null || st.Price <= 0) continue;
                if (OnlyT1T2 && st.Tier == "T3") continue;
                if (st.Id == sourceLevelId) continue;

                double dist = direction > 0
                    ? st.Price - entryPrice
                    : entryPrice - st.Price;

                if (dist < 5.0) continue;
                if (dist < bestDist)
                {
                    bestDist   = dist;
                    bestPrice  = st.Price;
                    targetLevelId = st.Id ?? "LEVEL";
                }
            }

            return bestPrice > 0 ? bestPrice : 0;
        }

        private void UpdateLevelProximity()
        {
            if (BarsInProgress != 0 || Bars == null) return;
            double close = Close[0];
            LevelState[] states;
            lock (_sync) { states = _levelStates; }
            for (int i = 0; i < states.Length; i++)
            {
                var st = states[i];
                bool wasActive = st.IsActive;
                st.IsActive = Math.Abs(close - st.Price) <= ProximityPoints;
                if (st.IsActive && !wasActive)
                {
                    st.TouchCount++;
                    st.ActiveSinceBar = CurrentBar;
                    st.DeltaAccum     = 0;
                    st.AbsorbHits     = 0;
                    st.ExhaustHits    = 0;
                }
            }
        }

        #endregion

        #region Data Loading

        private void ReadSnapshotSafe(object state)
        {
            try { ReadSnapshot(); }
            catch (Exception) { /* swallow — timer retries */ }
        }

        private void ReadSnapshot()
        {
            string path = ExpandJsonPath(JsonFilePath);
            if (!File.Exists(path)) return;
            string json;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs)) json = sr.ReadToEnd();
            var serializer = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 };
            GdsPayload next = serializer.Deserialize<GdsPayload>(json);
            GdsAsset match = MatchAsset(next);

            LevelState[] newStates = BuildLevelStates(match);

            lock (_sync) { _payload = next; _asset = match; _levelStates = newStates; }
            RefreshChart();
        }

        private LevelState[] BuildLevelStates(GdsAsset a)
        {
            if (a == null || a.levels == null || a.levels.Count == 0)
                return new LevelState[0];
            var result = new List<LevelState>();
            foreach (var lvl in a.levels)
            {
                if (lvl == null || lvl.price <= 0) continue;
                if (OnlyT1T2 && lvl.tier == "T3") continue;
                result.Add(new LevelState
                {
                    Id              = lvl.id ?? lvl.key ?? "?",
                    Price           = lvl.price,
                    BehaviorState   = lvl.behavior_state ?? "ATTRACT",
                    Tier            = lvl.tier ?? "T3",
                    ActionHint      = lvl.action_hint ?? "",
                    ConfidenceScore = lvl.confidence_score,
                    StructuralSource = lvl.structural_source ?? "",
                });
            }
            return result.ToArray();
        }

        private void RefreshChart()
        {
            if (ChartControl != null)
                ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
        }

        // --- Copied exactly from DEEP6GammaDecisionSurface ---

        private string ExpandJsonPath(string raw)
        {
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string profile = Directory.GetParent(docs) != null ? Directory.GetParent(docs).FullName : docs;
            return (raw ?? string.Empty).Replace("%USERPROFILE%", profile).Replace("%USERPROFILE%\\Documents", docs);
        }

        private GdsAsset MatchAsset(GdsPayload p)
        {
            if (p == null || p.assets == null || p.assets.Count == 0) return null;
            string root = NormalizeRoot(GetInstrumentRoot());
            foreach (var a in p.assets)
                if (a != null && string.Equals(NormalizeRoot(a.futures_root), root, StringComparison.OrdinalIgnoreCase)) return a;
            return p.assets[0];
        }

        private string NormalizeRoot(string root)
        {
            root = (root ?? string.Empty).ToUpperInvariant();
            if (root == "MNQ") return "NQ";
            if (root == "MES") return "ES";
            return root;
        }

        private string GetInstrumentRoot()
        {
            string full = Instrument != null && Instrument.MasterInstrument != null ? Instrument.MasterInstrument.Name : string.Empty;
            if (string.IsNullOrEmpty(full)) return string.Empty;
            int i = full.IndexOf(' ');
            return (i > 0 ? full.Substring(0, i) : full).ToUpperInvariant();
        }

        #endregion

        #region Rendering

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            // Behavior solid brushes (same palette as GammaDecisionSurface)
            dxDefend     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0.82f, 0.73f, 1f));
            dxReject     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.36f, 0.36f, 1f));
            dxAttract    = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 1f));
            dxFlip       = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 1f));

            // Fill brushes for proximity bands (lower alpha)
            dxDefendFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f,    0.82f, 0.73f, 0.12f));
            dxRejectFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f,    0.36f, 0.36f, 0.12f));
            dxAttractFill= new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 0.10f));
            dxFlipFill   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 0.08f));

            // Wider band fills (very low alpha — the proximity activation zone)
            dxDefendBand = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f,    0.82f, 0.73f, 0.06f));
            dxRejectBand = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f,    0.36f, 0.36f, 0.06f));
            dxAttractBand= new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 0.05f));
            dxFlipBand   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 0.04f));

            // UI brushes
            dxPanel  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.06f, 0.06f, 0.08f, 0.92f));
            dxText   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.95f, 0.97f, 1f));
            dxMuted  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.60f, 0.62f, 0.67f, 1f));
            dxHalo   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0f, 0f, 0.85f));
            dxGreen  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.18f, 0.84f, 0.46f, 1f));
            dxRed    = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.30f, 0.30f, 1f));

            // Fonts
            fontPill = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Semibold", 11f);
            fontMono = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
            fontTiny = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f);

            // Setup zone fills
            dxRiskZone   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.30f, 0.30f, 0.08f));
            dxRewardZone = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.18f, 0.84f, 0.46f, 0.08f));
            dxEntryZone  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.95f, 0.97f, 0.12f));

            // SL/TP line colors
            dxStopLine   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.30f, 0.30f, 1f));
            dxTargetLine = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.18f, 0.84f, 0.46f, 1f));
            dxGoldBright = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 1f));

            // Dashed stroke style for SL/TP lines
            try
            {
                var dsp = new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash };
                dxDashedStroke = new SharpDX.Direct2D1.StrokeStyle(NinjaTrader.Core.Globals.D2DFactory, dsp);
            }
            catch { dxDashedStroke = null; }

            // Decision rail fonts
            fontDecision     = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Semibold", 13f);
            fontDecisionBold = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Bold", 15f);
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || ChartPanel == null) return;

            GdsAsset a; LevelState[] states; List<GrsSignal> sigs;
            lock (_sync) { a = _asset; states = _levelStates; sigs = new List<GrsSignal>(_signals); }
            GdsFlashAlpha fa = a != null ? a.flashalpha : null;

            // Layer 1: proximity bands (furthest back)
            if (ShowProximityBands && states.Length > 0)
                DrawProximityBands(states, chartScale);

            // Layer 2: setup zones (risk/reward fills + SL/TP lines) — behind signal markers
            if (ShowSetupZones && sigs.Count > 0)
                DrawSetupZones(sigs, chartScale);

            // Layer 3: signal markers on bars
            if (ShowSignalMarkers && sigs.Count > 0)
                DrawSignalMarkers(sigs, chartScale);

            // Layer 4: decision rail (top-right unified status)
            if (ShowDecisionRail)
                DrawDecisionRail(states, a, sigs, chartScale);

            // Layer 5: status pills (right-edge per-level detail — secondary)
            if (ShowStatusPills && states.Length > 0)
                DrawStatusPills(states, fa, chartScale);
        }

        private void DrawProximityBands(LevelState[] states, ChartScale chartScale)
        {
            float panelX = ChartPanel.X;
            float panelW = ChartPanel.W;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var st in states)
            {
                if (!st.IsActive) continue;
                double hi = st.Price + ProximityPoints;
                double lo = st.Price - ProximityPoints;
                if (hi < minV || lo > maxV) continue;

                SharpDX.Direct2D1.Brush bandBrush = GetBandBrush(st.BehaviorState);
                if (bandBrush == null) continue;

                float yTop = chartScale.GetYByValue(Math.Min(hi, maxV));
                float yBot = chartScale.GetYByValue(Math.Max(lo, minV));
                float bandH = Math.Abs(yBot - yTop);
                if (bandH < 1f) continue;

                RenderTarget.FillRectangle(new RectangleF(panelX, yTop, panelW, bandH), bandBrush);
            }
        }

        private void DrawSignalMarkers(List<GrsSignal> sigs, ChartScale chartScale)
        {
            if (fontTiny == null) return;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var sig in sigs)
            {
                if (sig.Price < minV || sig.Price > maxV) continue;
                float y = chartScale.GetYByValue(sig.Price);
                SharpDX.Direct2D1.Brush brush = sig.Direction > 0 ? dxGreen : dxRed;
                if (brush == null) continue;

                float triSize = sig.Confidence >= 0.75f ? 8f : 5f;
                float cx = ChartPanel.X + ChartPanel.W * 0.85f;

                // Triangle marker (PathGeometry)
                SharpDX.Vector2 tip, baseL, baseR;
                if (sig.Direction > 0)
                {
                    tip   = new SharpDX.Vector2(cx, y + triSize * 2f);
                    baseL = new SharpDX.Vector2(cx - triSize, y + triSize * 3.5f);
                    baseR = new SharpDX.Vector2(cx + triSize, y + triSize * 3.5f);
                }
                else
                {
                    tip   = new SharpDX.Vector2(cx, y - triSize * 2f);
                    baseL = new SharpDX.Vector2(cx - triSize, y - triSize * 3.5f);
                    baseR = new SharpDX.Vector2(cx + triSize, y - triSize * 3.5f);
                }

                using (var geom = new SharpDX.Direct2D1.PathGeometry(NinjaTrader.Core.Globals.D2DFactory))
                {
                    using (var sink = geom.Open())
                    {
                        sink.BeginFigure(tip, FigureBegin.Filled);
                        sink.AddLine(baseL);
                        sink.AddLine(baseR);
                        sink.EndFigure(FigureEnd.Closed);
                        sink.Close();
                    }
                    RenderTarget.FillGeometry(geom, brush);
                }

                // Label text with halo
                string txt = sig.Label;
                float textX = cx + 12f;
                float textY = y - 7f;
                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, txt, fontTiny, 200f, 14f))
                {
                    if (dxHalo != null)
                    {
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX - 1, textY - 1), tl, dxHalo);
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX + 1, textY + 1), tl, dxHalo);
                    }
                    RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX, textY), tl, brush);
                }
            }
        }

        private void DrawSetupZones(List<GrsSignal> sigs, ChartScale chartScale)
        {
            if (!ShowSetupZones || sigs.Count == 0) return;

            // Only draw for the MOST RECENT live signal
            GrsSignal sig = null;
            for (int i = sigs.Count - 1; i >= 0; i--)
            {
                if (CurrentBar - sigs[i].BarIndex <= CooldownBars)
                { sig = sigs[i]; break; }
            }
            if (sig == null || sig.RiskPts <= 0) return;

            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;
            float  panelX = ChartPanel.X;
            float  panelW = ChartPanel.W;

            float yEntry = chartScale.GetYByValue(Math.Max(minV, Math.Min(maxV, sig.EntryPrice)));
            float yStop  = chartScale.GetYByValue(Math.Max(minV, Math.Min(maxV, sig.StopPrice)));
            float yTgt   = chartScale.GetYByValue(Math.Max(minV, Math.Min(maxV, sig.TargetPrice)));

            // Risk zone fill (entry -> stop)
            if (dxRiskZone != null)
            {
                float riskTop = Math.Min(yEntry, yStop);
                float riskBot = Math.Max(yEntry, yStop);
                if (riskBot - riskTop > 1f)
                    RenderTarget.FillRectangle(new RectangleF(panelX, riskTop, panelW, riskBot - riskTop), dxRiskZone);
            }

            // Reward zone fill (entry -> target)
            if (dxRewardZone != null)
            {
                float rewardTop = Math.Min(yEntry, yTgt);
                float rewardBot = Math.Max(yEntry, yTgt);
                if (rewardBot - rewardTop > 1f)
                    RenderTarget.FillRectangle(new RectangleF(panelX, rewardTop, panelW, rewardBot - rewardTop), dxRewardZone);
            }

            // Entry zone fill (+/-2 ticks)
            if (dxEntryZone != null)
            {
                double entryHi = sig.EntryPrice + 2 * TickSize;
                double entryLo = sig.EntryPrice - 2 * TickSize;
                float  ezTop = chartScale.GetYByValue(Math.Max(minV, Math.Min(maxV, entryHi)));
                float  ezBot = chartScale.GetYByValue(Math.Max(minV, Math.Min(maxV, entryLo)));
                if (Math.Abs(ezBot - ezTop) > 1f)
                    RenderTarget.FillRectangle(new RectangleF(panelX, ezTop, panelW, Math.Abs(ezBot - ezTop)), dxEntryZone);
            }

            float labelX = panelX + panelW - 200f;

            // Stop line (dashed red) + label
            if (dxStopLine != null && sig.StopPrice > minV && sig.StopPrice < maxV)
            {
                RenderTarget.DrawLine(
                    new SharpDX.Vector2(panelX, yStop),
                    new SharpDX.Vector2(panelX + panelW - 205f, yStop),
                    dxStopLine, 1.5f, dxDashedStroke);
                string slText = string.Format("STOP  {0:0.00}  ({1:+0.#;-0.#} pts)",
                    sig.StopPrice,
                    sig.Direction > 0 ? -(sig.RiskPts) : sig.RiskPts);
                if (fontMono != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, slText, fontMono, 195f, 14f))
                    {
                        if (dxHalo != null)
                            RenderTarget.DrawTextLayout(new SharpDX.Vector2(labelX - 1, yStop - 15f - 1), tl, dxHalo);
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(labelX, yStop - 15f), tl, dxStopLine);
                    }
            }

            // Target line (dashed green) + label
            if (dxTargetLine != null && sig.TargetPrice > minV && sig.TargetPrice < maxV)
            {
                RenderTarget.DrawLine(
                    new SharpDX.Vector2(panelX, yTgt),
                    new SharpDX.Vector2(panelX + panelW - 205f, yTgt),
                    dxTargetLine, 1.5f, dxDashedStroke);
                string tpLabel = sig.TargetLevelId != null && sig.TargetLevelId != "FALLBACK"
                    ? sig.TargetLevelId.Replace("_", " ").ToUpperInvariant()
                    : "R:R FALLBACK";
                string tpText = string.Format("TARGET  {0:0.00}  (+{1:0.#} pts)  {2}",
                    sig.TargetPrice, sig.RewardPts, tpLabel);
                if (fontMono != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, tpText, fontMono, 195f, 14f))
                    {
                        if (dxHalo != null)
                            RenderTarget.DrawTextLayout(new SharpDX.Vector2(labelX - 1, yTgt + 2f - 1), tl, dxHalo);
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(labelX, yTgt + 2f), tl, dxTargetLine);
                    }
            }
        }

        private void DrawDecisionRail(LevelState[] states, GdsAsset asset, List<GrsSignal> sigs, ChartScale chartScale)
        {
            if (!ShowDecisionRail) return;

            const float railW = 380f;
            const float railH = 52f;
            float railX = ChartPanel.X + ChartPanel.W - railW - 8f;
            float railY = ChartPanel.Y + 26f;

            if (dxPanel == null || fontDecision == null) return;
            RenderTarget.FillRectangle(new RectangleF(railX, railY, railW, railH), dxPanel);

            // Find best active state: most recent LIVE signal > best WATCHING level
            GrsSignal liveSig = null;
            for (int i = sigs.Count - 1; i >= 0; i--)
            {
                if (CurrentBar - sigs[i].BarIndex <= CooldownBars)
                { liveSig = sigs[i]; break; }
            }

            LevelState bestWatching = null;
            int bestScore = 0;
            foreach (var st in states)
            {
                if (!st.IsActive || (OnlyT1T2 && st.Tier == "T3")) continue;
                int score = st.AbsorbHits * 10 + st.ExhaustHits * 5 + (int)(Math.Abs(st.DeltaAccum) / 1000.0);
                if (score > bestScore) { bestScore = score; bestWatching = st; }
            }

            if (liveSig != null)
            {
                // LIVE SETUP state
                SharpDX.Direct2D1.Brush accentBrush = liveSig.Direction > 0 ? dxGreen : dxRed;
                if (accentBrush != null)
                    RenderTarget.FillRectangle(new RectangleF(railX, railY, 4f, railH), accentBrush);

                string dirArrow = liveSig.Direction > 0 ? "\u25B2 LONG" : "\u25BC SHORT";
                string payoffTag = liveSig.HasPayoff ? "" : "  \u26A0 LOW PAYOFF";
                string regTag    = liveSig.WithRegime ? "  \u2713" : "";
                string hero = string.Format("{0}  {1:0.00}{2}{3}", dirArrow, liveSig.EntryPrice, regTag, payoffTag);

                if (fontDecisionBold != null && accentBrush != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, hero, fontDecisionBold, railW - 16f, 20f))
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(railX + 10f, railY + 4f), tl, accentBrush);

                string detail = string.Format("STOP {0:0.00}  \u2192  TARGET {1:0.00}  |  R:R {2:0.0}",
                    liveSig.StopPrice, liveSig.TargetPrice, liveSig.RR);
                if (!string.IsNullOrEmpty(liveSig.VexTag) || !string.IsNullOrEmpty(liveSig.ChexTag))
                    detail += "  |  " + (liveSig.VexTag + " " + liveSig.ChexTag).Trim();

                if (fontMono != null && dxMuted != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, detail, fontMono, railW - 16f, 16f))
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(railX + 10f, railY + 28f), tl, dxMuted);
            }
            else if (bestWatching != null)
            {
                // WATCHING state
                SharpDX.Direct2D1.Brush wBrush = GetBehaviorBrush(bestWatching.BehaviorState) ?? dxMuted;
                if (wBrush != null)
                    RenderTarget.FillRectangle(new RectangleF(railX, railY, 2f, railH), wBrush);

                string wtxt = string.Format("\u25CF WATCHING  {0:0.00}  {1}  {2}",
                    bestWatching.Price,
                    bestWatching.BehaviorState,
                    bestWatching.Tier);
                if (fontDecision != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, wtxt, fontDecision, railW - 16f, 20f))
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(railX + 10f, railY + 4f), tl, wBrush);

                string wprog = string.Format("ABS {0}/{1}  \u03B4{2:+0;-0;0}k  EXH {3}  Touch {4}",
                    bestWatching.AbsorbHits, MinAbsorbHits,
                    (long)(bestWatching.DeltaAccum / 1000),
                    bestWatching.ExhaustHits,
                    bestWatching.TouchCount);
                if (fontMono != null && dxMuted != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, wprog, fontMono, railW - 16f, 16f))
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(railX + 10f, railY + 28f), tl, dxMuted);
            }
            else
            {
                // IDLE state
                string idle = "No active GEX levels in range";
                if (fontDecision != null && dxMuted != null)
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, idle, fontDecision, railW - 16f, 20f))
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(railX + 10f, railY + 16f), tl, dxMuted);
            }
        }

        private void DrawStatusPills(LevelState[] states, GdsFlashAlpha fa, ChartScale chartScale)
        {
            if (fontPill == null || fontMono == null) return;
            float pillRight = ChartPanel.X + ChartPanel.W - 8f;
            const float pillW = 260f;
            const float pillH = 22f;
            const float accLW = 3f;

            var active = new List<LevelState>();
            for (int i = 0; i < states.Length; i++)
            {
                if (states[i].IsActive && (!OnlyT1T2 || states[i].Tier != "T3"))
                    active.Add(states[i]);
            }
            if (active.Count == 0) return;
            active.Sort((a, b) => b.Price.CompareTo(a.Price));

            // Build VEX/CHEX suffix for row1 (shared across all pills)
            string faSuffix = "";
            if (fa != null && fa.health == "live")
            {
                string vt = fa.vex_direction  == "bullish" ? "VEX\u2191" : fa.vex_direction  == "bearish" ? "VEX\u2193" : "";
                string ct = fa.chex_direction == "bullish" ? "CHEX\u2191" : fa.chex_direction == "bearish" ? "CHEX\u2193" : "";
                if (!string.IsNullOrEmpty(vt) || !string.IsNullOrEmpty(ct))
                    faSuffix = "  " + (vt + " " + ct).Trim();
            }

            // Start below GDS regime strip (avoid overlap)
            float startY = ChartPanel.Y + 26f;
            float lastY  = float.MinValue;

            foreach (var st in active)
            {
                float pillY = startY;
                if (lastY != float.MinValue && pillY - lastY < pillH + 2f)
                    pillY = lastY + pillH + 2f;
                lastY = pillY;
                startY = pillY + pillH + 2f;

                float pillX = pillRight - pillW;
                SharpDX.Direct2D1.Brush accentBrush = GetBehaviorBrush(st.BehaviorState);
                if (accentBrush == null) accentBrush = dxText;

                // Pill background
                if (dxPanel != null)
                    RenderTarget.FillRectangle(new RectangleF(pillX, pillY, pillW, pillH), dxPanel);
                // Accent strip
                RenderTarget.FillRectangle(new RectangleF(pillX, pillY, accLW, pillH), accentBrush);

                // Row 1: behavior + tier + source + FlashAlpha VEX/CHEX
                string srcPart = (st.StructuralSource ?? "").Replace("_", " ").ToUpperInvariant();
                if (srcPart.Length > 12) srcPart = srcPart.Substring(0, 12);
                string row1 = string.Format("{0}  {1}  {2}{3}", st.BehaviorState ?? "", st.Tier ?? "", srcPart, faSuffix);

                // Row 2: live delta + absorb/exhaust counters
                double deltaK = st.DeltaAccum / 1000.0;
                string row2 = string.Format("\u03B4{0:+0;-0;0}k  ABS {1}/{2}  EXH {3}",
                    deltaK, st.AbsorbHits, MinAbsorbHits, st.ExhaustHits);

                float textX = pillX + accLW + 4f;
                float row1Y = pillY + 2f;
                float row2Y = pillY + pillH / 2f;
                float textW = pillW - accLW - 6f;
                float halfH = pillH / 2f;

                // Row 1 (bold behavior)
                if (dxHalo != null)
                {
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, row1, fontPill, textW, halfH))
                    {
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX - 1, row1Y - 1), tl, dxHalo);
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX, row1Y), tl, accentBrush);
                    }
                }

                // Row 2 (mono delta/absorb) — green if absorb threshold met
                var row2Brush = st.AbsorbHits >= MinAbsorbHits ? dxGreen : dxMuted;
                if (row2Brush == null) row2Brush = dxMuted;
                if (dxHalo != null)
                {
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, row2, fontMono, textW, halfH))
                    {
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX - 1, row2Y - 1), tl, dxHalo);
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(textX, row2Y), tl, row2Brush);
                    }
                }
            }
        }

        #endregion

        #region Helpers

        private SharpDX.Direct2D1.Brush GetBehaviorBrush(string s)
        {
            switch (s ?? "")
            {
                case "DEFEND":  return dxDefend;
                case "REJECT":  return dxReject;
                case "ATTRACT": return dxAttract;
                case "FLIP":    return dxFlip;
                default:        return dxText;
            }
        }

        private SharpDX.Direct2D1.Brush GetBandBrush(string s)
        {
            switch (s ?? "")
            {
                case "DEFEND":  return dxDefendBand;
                case "REJECT":  return dxRejectBand;
                case "ATTRACT": return dxAttractBand;
                case "FLIP":    return dxFlipBand;
                default:        return null;
            }
        }

        private void DisposeDx()
        {
            DisposeB(ref dxDefend);   DisposeB(ref dxDefendFill);  DisposeB(ref dxDefendBand);
            DisposeB(ref dxReject);   DisposeB(ref dxRejectFill);  DisposeB(ref dxRejectBand);
            DisposeB(ref dxAttract);  DisposeB(ref dxAttractFill); DisposeB(ref dxAttractBand);
            DisposeB(ref dxFlip);     DisposeB(ref dxFlipFill);    DisposeB(ref dxFlipBand);
            DisposeB(ref dxPanel);    DisposeB(ref dxText);        DisposeB(ref dxMuted);
            DisposeB(ref dxHalo);     DisposeB(ref dxGreen);       DisposeB(ref dxRed);
            DisposeB(ref dxRiskZone); DisposeB(ref dxRewardZone);  DisposeB(ref dxEntryZone);
            DisposeB(ref dxStopLine); DisposeB(ref dxTargetLine);  DisposeB(ref dxGoldBright);
            DisposeF(ref fontPill);   DisposeF(ref fontMono);      DisposeF(ref fontTiny);
            DisposeF(ref fontDecision); DisposeF(ref fontDecisionBold);
            if (dxDashedStroke != null) { dxDashedStroke.Dispose(); dxDashedStroke = null; }
        }

        private static void DisposeB(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }
        private static void DisposeF(ref TextFormat f)               { if (f != null) { f.Dispose(); f = null; } }

        #endregion

        #region Properties

        // Group 1 — Data
        [NinjaScriptProperty]
        [Display(Name = "JSON File Path", Order = 1, GroupName = "1. Data")]
        public string JsonFilePath { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Refresh Seconds", Order = 2, GroupName = "1. Data")]
        public int RefreshSeconds { get; set; }

        // Group 2 — Detection
        [NinjaScriptProperty]
        [Display(Name = "Proximity Points", Order = 3, GroupName = "2. Detection")]
        public double ProximityPoints { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Min Absorb Hits", Order = 4, GroupName = "2. Detection")]
        public int MinAbsorbHits { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Delta Threshold", Order = 5, GroupName = "2. Detection")]
        public double DeltaThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Flip Delta Threshold", Order = 6, GroupName = "2. Detection")]
        public double FlipDeltaThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Cooldown Bars", Order = 7, GroupName = "2. Detection")]
        public int CooldownBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Min R:R Ratio", Order = 8, GroupName = "2. Detection")]
        public double MinRR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Stop ATR Multiplier", Order = 9, GroupName = "2. Detection")]
        public double StopAtrMultiplier { get; set; }

        // Group 3 — Display
        [Display(Name = "Show Proximity Bands", Order = 8, GroupName = "3. Display")]
        public bool ShowProximityBands { get; set; }

        [Display(Name = "Show Status Pills", Order = 9, GroupName = "3. Display")]
        public bool ShowStatusPills { get; set; }

        [Display(Name = "Show Signal Markers", Order = 10, GroupName = "3. Display")]
        public bool ShowSignalMarkers { get; set; }

        [Display(Name = "Only T1/T2 Levels", Order = 11, GroupName = "3. Display")]
        public bool OnlyT1T2 { get; set; }

        [Display(Name = "Show Setup Zones", Order = 12, GroupName = "3. Display")]
        public bool ShowSetupZones { get; set; }

        [Display(Name = "Show Decision Rail", Order = 13, GroupName = "3. Display")]
        public bool ShowDecisionRail { get; set; }

        #endregion
    }
}
