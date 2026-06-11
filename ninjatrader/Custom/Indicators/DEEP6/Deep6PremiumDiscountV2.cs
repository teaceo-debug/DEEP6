//==============================================================================================
//  DEEP6 PREMIUM/DISCOUNT MATRIX v2.1 — FULL SYSTEM, SELF-CONTAINED IN NINJATRADER 8
//----------------------------------------------------------------------------------------------
//  v2.1 incorporates a four-way independent audit (platform / quant methodology / concurrency /
//  adversarial bug hunt). Material changes vs v2.0:
//   * MaximumBarsLookBack.Infinite — v2.0's 256-bar Series limit silently aborted calibration.
//   * Live lifecycle gated to State.Realtime; posteriors are no longer triple-counted
//     (historical replay + seed + reload). Persistence now stores LIVE deltas only and the
//     historical seed is rebuilt fresh each load — sample counts can no longer self-inflate.
//   * Correct asymmetric breakeven: each cell ledgers its target/stop distances and gates on
//     p* = S̄/(T̄+S̄) + haircut instead of the (wrong) flat 0.5 + haircut.
//   * MOMO regime fixed: FOLLOW now requires evidence that fades LOSE (Hi90 < p* − haircut);
//     v2.0 activated FOLLOW on evidence fades win and pointed the bias the wrong way.
//   * Honest IS/OOS: bands / anchor race / IBS are fit on the OLDER half only; the posterior
//     seed replays the recent half. Anchor race uses non-overlapping 60-bar windows and must
//     beat the runner-up by 2pp or VWAP stays the default.
//   * One trial per touch episode (re-arm at mid-range) — kills autocorrelated trial chains.
//   * Intrabar stop test (High/Low), ambiguous bars scored as losses; per-TF stop horizon
//     (sigma scaled to 240/1380/6900 min) and per-TF timeouts (x1/x6/x30).
//   * GEX regime: prior-session lookup (no same-day EOD look-ahead), |net| below the 20th
//     percentile = genuine FLIP (stand aside), UW HTTP errors surfaced not swallowed,
//     net==0 no longer mapped to MOMO. History fetch is awaited before calibration.
//   * Per-instrument state/telemetry files, atomic state writes; EWMA/vol series seed
//     correctly (no zero-poisoned warm-up) and session-gap returns no longer spike the vol.
//   * OU half-life skips session-straddling pairs; IBS verdict requires |t| >= 2.
//
//  ENGINES (all in-platform)
//   E1 ANCHORS      Range EQ, session VWAP, session POC, EWMA mean. Anchor race on the
//                   older half of history; winner becomes the live attractor line.
//   E2 LOCATION     Range percentile per TF (H4/Daily/Weekly swing ranges). Pullback bands
//                   are empirical quantiles (q60–q85) fit per regime on the older half.
//   E3 REGIME GATE  GEX sign (UW / FlashAlpha) with FLIP band, ER-proxy fallback (LOCAL).
//   E4 POSTERIORS   Beta(2,2) hit-rate per (TF x regime) cell + payoff ledger (T̄, S̄).
//                   Seeded from the recent half each load; live deltas persisted per
//                   instrument to Documents\NinjaTrader 8\Deep6PD. Cells render SHADOW until
//                   n >= MinSamples AND the posterior bound clears the cell's own p*.
//   E5 EXECUTION    Rolling OU half-life of (log price − anchor), session-aware.
//   E6 TELEMETRY    signals_<key>.csv (live only) + calibration_report_<key>.txt.
//
//  INSTALL
//   Already placed in bin\Custom\Indicators\DEEP6. Open NinjaScript Editor → F5 to compile.
//   Add to an NQ chart (1–5 min) with AT LEAST 1 year of data (Days to load: 365+).
//
//  HONEST LIMITS — read this
//   * Chronological split-half validation, not CPCV/DSR/PBO. Treat LIVE cells as
//     "locally validated", not institutionally validated.
//   * The posterior seed reconstructs H4/D/W structure from primary-series pivots
//     (k = SwingStrength x 3/9/21) — a faster proxy for the live HTF ranges. Seeded and
//     live trials are aligned in logic (same arming, barriers, timeouts, TargetSigma)
//     but not in range scale; weight LIVE counts over seed counts mentally.
//   * GEX regime uses NDX/QQQ index-options dealer positioning as the NQ proxy.
//   * VERIFY the UW put_gamma sign convention once against their dashboard on a known
//     negative-GEX date; if UW reports put gamma as a positive magnitude, net = call+put
//     is wrong and the regime tags invert exactly when they matter.
//   * The UW token is stored in plaintext in workspace/template XML.
//   * Beta CI is a normal approximation (fine for n >= ~30).
//==============================================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using Media = System.Windows.Media;
using D2D   = SharpDX.Direct2D1;
using DW    = SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript
{
    // namespace-scope (NOT class-nested): NT's code generator emits this type UNQUALIFIED in the
    // MarketAnalyzerColumns and Strategies wrapper namespaces, which only resolve parent namespaces
    public enum Deep6DashboardCorner { TopRight, TopLeft, BottomRight, BottomLeft }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class Deep6PremiumDiscountV2 : Indicator
    {
        #region Types
        private class SwingPoint { public double Price; public DateTime Time; }

        private class DealingRange
        {
            public bool Valid; public double High, Low; public DateTime AnchorTime; public bool BullLeg;
            public double Range  { get { return High - Low; } }
            public double Eq     { get { return Low + 0.5 * (High - Low); } }
        }

        private class PosteriorCell
        {
            public double Alpha = 2, Beta = 2;          // Beta(2,2) prior, seed + live
            public double SumT, SumS; public int PayN;  // payoff ledger: |target-entry|, |entry-stop|
            public double LiveAlpha, LiveBeta;          // live-resolved deltas (the only persisted part)
            public double LiveSumT, LiveSumS; public int LivePayN;
            public int LiveN;
            public double N      { get { return Alpha + Beta - 4; } }
            public double Mean   { get { return Alpha / (Alpha + Beta); } }
            public double Sd     { get { double s = Alpha + Beta; return Math.Sqrt(Alpha * Beta / (s * s * (s + 1))); } }
            public double Lo90   { get { return Math.Max(0, Mean - 1.645 * Sd); } }
            public double Hi90   { get { return Math.Min(1, Mean + 1.645 * Sd); } }
            // asymmetric-payoff breakeven hit rate: p* = S̄ / (T̄ + S̄); 0.5 until payoffs observed
            public double PStar0 { get { return PayN > 0 && SumT + SumS > 0 ? SumS / (SumT + SumS) : 0.5; } }
        }

        private class LiveSignal
        {
            public int Tf; public int Regime; public bool IsLong;
            public double Entry, Target, Stop; public int BarOpened; public DateTime Opened;
        }

        private class PersistedState
        {
            public Dictionary<string, double[]> Cells = new Dictionary<string, double[]>(); // key -> [liveA,liveB,liveN,liveSumT,liveSumS,livePayN]
            public string CalibratedThrough = "";
            public string FirstLiveOpen = "";   // seed replay stops here: those episodes are already in the live deltas
        }

        #endregion

        #region Fields
        private const int TfCount = 3;                                   // 0=H4 1=Daily 2=Weekly
        private static readonly string[] TfTags = { "H4", "D", "W" };
        private static readonly int[] TfHorizonMin = { 240, 1380, 6900 };// stop-sigma horizon per TF (minutes)
        private static readonly int[] TfTimeoutFac = { 1, 6, 30 };       // TimeoutBars multiplier per TF
        private const int RegimeCount = 3;                               // 0=+GEX/calm 1=flip/unknown 2=-GEX/stressed
        private static readonly string[] RegimeTags = { "REVERT", "FLIP", "MOMO" };

        private SwingPoint[] lastHigh, lastLow;
        private DealingRange[] ranges;

        // anchors
        private double sessVwapPv, sessVwapVol, sessionVwap = double.NaN;
        private Dictionary<double, double> pocHist = new Dictionary<double, double>();
        private double sessionPoc = double.NaN, pocBestVol = -1;
        private Series<double> ewmaMean, realizedVol, anchorSeries;

        // regime
        private volatile int gexSign = 0;                 // -1/0/+1 live
        private volatile bool gexLiveValid;               // a live GEX value has actually been fetched
        private DateTime lastGexPoll = DateTime.MinValue;
        private Dictionary<DateTime, int> gexHistory = new Dictionary<DateTime, int>(); // session date -> sign (-1/0/+1, 0 = flip band)
        private volatile bool gexHistoryLoaded;
        private double gexAbsEps;                         // |net| below this = FLIP (20th pct of history)
        private string gexStatusText = "GEX: OFF";
        private volatile int lastRegime = 1;              // cached for OnRender / public API
        private Task histTask;
        private static readonly HttpClient http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };

        // posteriors / lifecycle
        private PosteriorCell[,] cells;                   // [tf, regime]
        private LiveSignal[] active;                      // one per TF
        private bool[] armed;                             // one trial per touch episode: re-arm at mid-range
        private DateTime firstLiveOpen = DateTime.MaxValue;
        private string stateDir, stateFile, signalsFile, reportFile;
        private DateTime lastPersist = DateTime.MinValue;

        // calibration
        private bool calibrated;
        private readonly List<double> retraceDepths = new List<double>();
        private readonly List<KeyValuePair<DateTime, double>> retraceTimed = new List<KeyValuePair<DateTime, double>>(); // regime-tagged at calibration
        private double[] bandQ60 = new double[RegimeCount], bandQ85 = new double[RegimeCount];
        private readonly List<double>[] pullbackByRegime = new List<double>[RegimeCount];
        private string anchorWinner = "VWAP";
        private double anchorIcVwap, anchorIcEq, anchorIcEwma;
        private readonly List<double[]> icSamples = new List<double[]>(); // [zVwap,zEq,zEwma,barIdx]

        // daily IBS (session approximation)
        private double dayHi = double.MinValue, dayLo = double.MaxValue, dayClose = double.NaN, prevDayClose = double.NaN;
        private readonly List<double[]> ibsSamples = new List<double[]>(); // [ibs, nextRet]
        private double pendingIbs = double.NaN;

        // half-life (NaN entries mark session boundaries; straddling pairs are excluded)
        private readonly List<double> spreadBuf = new List<double>();
        private double halfLifeMin = double.NaN;

        private Series<double> compositeBias;
        private double lastBias;                          // dashboard copy — OnRender must not index series by barsAgo

        // cached device-independent render resources (created lazily, disposed in Terminated)
        private DW.TextFormat fmtS, fmtH;
        private D2D.StrokeStyle ssDash, ssDot;
        #endregion

        #region State machine
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description              = "DEEP6 Premium/Discount v2.1 — regime-gated, posterior-driven PD system, fully in-platform.";
                Name                     = "Deep6PremiumDiscountV2";
                Calculate                = Calculate.OnBarClose;     // lifecycle integrity > tick repainting
                IsOverlay                = true;
                DisplayInDataBox         = false;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = false;                    // GEX polling continues while tab inactive
                MaximumBarsLookBack      = MaximumBarsLookBack.Infinite; // calibration indexes Series deep into history

                SwingStrength   = 5;
                MinSamples      = 100;
                CostHaircutPct  = 2.0;
                TargetSigma     = 0.0;     // 0 = range EQ; >0 = entry + k*sigma toward anchor
                StopSigma       = 2.0;
                TimeoutBars     = 240;     // base (H4); Daily x6, Weekly x30
                ZoneOpacity     = 20;
                PollSeconds     = 120;

                UwToken         = "";
                UwTicker        = "NDX";
                FlashAlphaUrl   = "";
                FlashAlphaJsonPath = "net_gex";

                ShowDashboard   = true;
                DashboardPos    = Deep6DashboardCorner.TopRight;
                ShowLabels      = true;

                PremiumBrush  = new Media.SolidColorBrush(Media.Color.FromRgb(0xFF, 0x47, 0x57));
                DiscountBrush = new Media.SolidColorBrush(Media.Color.FromRgb(0x2E, 0xD5, 0x73));
                EqBrush       = new Media.SolidColorBrush(Media.Color.FromRgb(0xFF, 0xA5, 0x02));
                BandBrush     = new Media.SolidColorBrush(Media.Color.FromRgb(0xA5, 0x5E, 0xEA));
                AnchorBrush   = new Media.SolidColorBrush(Media.Color.FromRgb(0x22, 0xD3, 0xEE));
                TextBrush     = new Media.SolidColorBrush(Media.Color.FromRgb(0xEA, 0xEE, 0xF5));
                PremiumBrush.Freeze(); DiscountBrush.Freeze(); EqBrush.Freeze();
                BandBrush.Freeze(); AnchorBrush.Freeze(); TextBrush.Freeze();
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 240);   // BIP 1 → H4
                AddDataSeries(BarsPeriodType.Day,     1);    // BIP 2 → Daily
                AddDataSeries(BarsPeriodType.Week,    1);    // BIP 3 → Weekly
            }
            else if (State == State.DataLoaded)
            {
                lastHigh = new SwingPoint[TfCount + 1]; lastLow = new SwingPoint[TfCount + 1];
                ranges   = new DealingRange[TfCount];
                for (int i = 0; i < TfCount; i++) ranges[i] = new DealingRange();

                cells  = new PosteriorCell[TfCount, RegimeCount];
                for (int t = 0; t < TfCount; t++) for (int r = 0; r < RegimeCount; r++) cells[t, r] = new PosteriorCell();
                active = new LiveSignal[TfCount];
                armed  = new bool[TfCount];
                for (int r = 0; r < RegimeCount; r++) pullbackByRegime[r] = new List<double>();

                ewmaMean      = new Series<double>(this);
                realizedVol   = new Series<double>(this);
                anchorSeries  = new Series<double>(this);
                compositeBias = new Series<double>(this);

                stateDir = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "Deep6PD");
                Directory.CreateDirectory(stateDir);
                string key  = Instrument.MasterInstrument.Name + "_" + BarsPeriod.Value + BarsPeriod.BarsPeriodType;
                stateFile   = Path.Combine(stateDir, "state_" + key + ".json");
                signalsFile = Path.Combine(stateDir, "signals_" + key + ".csv");
                reportFile  = Path.Combine(stateDir, "calibration_report_" + key + ".txt");
                LoadState();

                if (!string.IsNullOrWhiteSpace(UwToken))
                    histTask = Task.Run(() => FetchUwGexHistory());  // daily history for regime-tagging calibration
            }
            else if (State == State.Transition)
            {
                try { RunCalibration(); }                    // historical pass done → fit bands, race anchors, seed posteriors
                catch (Exception ex) { Print("Deep6PDv2: calibration failed at transition: " + Msg(ex)); }
            }
            else if (State == State.Terminated)
            {
                if (cells != null) SaveState();
                foreach (IDisposable d in new IDisposable[] { fmtS, fmtH, ssDash, ssDot })
                    if (d != null) d.Dispose();
                fmtS = fmtH = null; ssDash = ssDot = null;
            }
        }
        #endregion

        #region Bar update
        protected override void OnBarUpdate()
        {
            int bip = BarsInProgress;

            if (bip >= 1 && bip <= TfCount)                  // HTF swing ranges
            {
                UpdateSwingsAndRange(bip);
                return;
            }
            if (bip != 0 || CurrentBar < 20) return;

            // calibrate at the end of the historical pass even with no realtime connection
            if (!calibrated && State == State.Historical && CurrentBar >= Bars.Count - 2)
                try { RunCalibration(); } catch (Exception ex) { calibrated = true; Print("Deep6PDv2: calibration failed: " + Msg(ex)); }

            // ---------------- session anchors ----------------
            bool newSession = Bars.IsFirstBarOfSession;
            if (newSession)
            {
                // finalize previous day's IBS sample (older half only — calibration must stay OOS to the seed)
                if (dayHi > dayLo && !double.IsNaN(prevDayClose) && !double.IsNaN(pendingIbs)
                    && State == State.Historical && CurrentBar < Bars.Count / 2)
                    ibsSamples.Add(new[] { pendingIbs, Math.Log(dayClose / prevDayClose) });
                if (dayHi > dayLo)
                {
                    pendingIbs   = (dayClose - dayLo) / (dayHi - dayLo);
                    prevDayClose = dayClose;
                }
                sessVwapPv = sessVwapVol = 0;
                pocHist.Clear(); pocBestVol = -1; sessionPoc = double.NaN;
                dayHi = double.MinValue; dayLo = double.MaxValue;
                spreadBuf.Add(double.NaN);                   // session marker: half-life skips straddling pairs
            }
            double v = Math.Max(Volume[0], 1);
            sessVwapPv  += Close[0] * v; sessVwapVol += v;
            sessionVwap  = sessVwapPv / sessVwapVol;
            double bw = TickSize * 20;                       // POC bucket: ~5 pts on NQ, scales with any instrument
            double bucket = Instrument.MasterInstrument.RoundToTickSize(Math.Round(Close[0] / bw) * bw);
            double bv; pocHist.TryGetValue(bucket, out bv); bv += v; pocHist[bucket] = bv;
            if (bv > pocBestVol) { pocBestVol = bv; sessionPoc = bucket; }
            dayHi = Math.Max(dayHi, High[0]); dayLo = Math.Min(dayLo, Low[0]); dayClose = Close[0];

            // ---------------- statistical series ----------------
            // the CurrentBar<20 gate means bar 20 is the first processed bar: seed from price, not from 0
            ewmaMean[0] = !ewmaMean.IsValidDataPoint(1) || ewmaMean[1] <= 0
                        ? Close[0]
                        : ewmaMean[1] + 2.0 / (390 + 1) * (Close[0] - ewmaMean[1]);
            double r1 = Math.Log(Close[0] / Close[1]);
            if (newSession)
                realizedVol[0] = realizedVol.IsValidDataPoint(1) && realizedVol[1] > 0 ? realizedVol[1] : 0; // a gap return never seeds or updates the vol EWMA
            else
            {
                double prevVar = !realizedVol.IsValidDataPoint(1) || realizedVol[1] <= 0 ? r1 * r1 : realizedVol[1] * realizedVol[1];
                realizedVol[0] = Math.Sqrt(prevVar + 2.0 / (390 + 1) * (r1 * r1 - prevVar));
            }
            double pmin = BarsPeriod.BarsPeriodType == BarsPeriodType.Minute ? BarsPeriod.Value : 1;

            anchorSeries[0] = anchorWinner == "EQ" && ranges[1].Valid ? ranges[1].Eq
                            : anchorWinner == "EWMA" ? ewmaMean[0]
                            : anchorWinner == "POC" && !double.IsNaN(sessionPoc) ? sessionPoc
                            : double.IsNaN(sessionVwap) ? ewmaMean[0] : sessionVwap;

            // half-life buffer (log spread to anchor)
            if (anchorSeries[0] > 0)
            {
                spreadBuf.Add(Math.Log(Close[0] / anchorSeries[0]));
                if (spreadBuf.Count > 1950) spreadBuf.RemoveAt(0);
                if (CurrentBar % 60 == 0 && spreadBuf.Count > 300) halfLifeMin = EstimateHalfLife(spreadBuf);
            }

            // anchor horse-race samples: OLDER half only, non-overlapping 60-bar forward windows
            if (State == State.Historical && CurrentBar > 400 && CurrentBar < Bars.Count / 2
                && CurrentBar % 60 == 0 && ranges[1].Valid && realizedVol[0] > 0 && !double.IsNaN(sessionPoc))
            {
                double vol = Math.Max(realizedVol[0], 1e-6);
                icSamples.Add(new[]
                {
                    -(Math.Log(Close[0] / Math.Max(sessionVwap, 1e-9))) / vol,
                    -(Math.Log(Close[0] / Math.Max(ranges[1].Eq, 1e-9))) / vol,
                    -(Math.Log(Close[0] / Math.Max(ewmaMean[0], 1e-9))) / vol,
                    -(Math.Log(Close[0] / Math.Max(sessionPoc, 1e-9))) / vol,
                    CurrentBar  // fwd filled later via close lookback in calibration
                });
            }

            // ---------------- regime ----------------
            int regime = CurrentRegime(Time[0]);
            lastRegime = regime;

            // ---------------- live GEX poll ----------------
            if (State == State.Realtime && (DateTime.UtcNow - lastGexPoll).TotalSeconds > PollSeconds)
            {
                lastGexPoll = DateTime.UtcNow;
                Task.Run(() => PollLiveGex());
            }

            // ---------------- signal lifecycle (LIVE ONLY — historical evidence comes from the seed) ----------------
            if (State == State.Realtime)
            {
                for (int tf = 0; tf < TfCount; tf++)
                {
                    DealingRange rg = ranges[tf];
                    if (!rg.Valid || rg.Range <= 0) continue;
                    double loc = (Close[0] - rg.Low) / rg.Range;
                    if (loc > 0.25 && loc < 0.75) armed[tf] = true;   // new touch episode only after mid-range revisit

                    LiveSignal s = active[tf];
                    if (s != null)
                    {
                        // intrabar stop test; a bar that touches both barriers scores as a loss (conservative)
                        bool loss = s.IsLong ? Low[0] <= s.Stop : High[0] >= s.Stop;
                        bool win  = !loss && (s.IsLong ? Close[0] >= s.Target : Close[0] <= s.Target);
                        bool timo = !loss && !win && CurrentBar - s.BarOpened >= TimeoutBars * TfTimeoutFac[tf];
                        if (win || loss || timo)
                        {
                            ResolveSignal(tf, s, win, loss ? "STOP" : timo ? "TIMEOUT" : "TARGET");
                            active[tf] = null;
                        }
                    }
                    else if (regime != 1 && armed[tf])          // FLIP/unknown → stand aside, no counting
                    {
                        bool discountTouch = loc <= 0.10;
                        bool premiumTouch  = loc >= 0.90;
                        if (discountTouch || premiumTouch)
                        {
                            bool isLong = discountTouch;
                            double sigTf = Math.Max(realizedVol[0] * Close[0] * Math.Sqrt(TfHorizonMin[tf] / pmin), TickSize * 4);
                            double tgt  = TargetSigma > 0
                                ? Close[0] + (isLong ? 1 : -1) * TargetSigma * sigTf
                                : rg.Eq;
                            var sig = new LiveSignal
                            {
                                Tf = tf, Regime = regime, IsLong = isLong,
                                Entry = Close[0], Target = tgt,
                                Stop  = Close[0] - (isLong ? 1 : -1) * StopSigma * sigTf,
                                BarOpened = CurrentBar, Opened = Time[0]
                            };
                            active[tf] = sig;
                            armed[tf] = false;
                            if (firstLiveOpen == DateTime.MaxValue) firstLiveOpen = Time[0];
                            LogSignal("OPEN", tf, regime, sig, "");
                        }
                    }
                }
            }

            // ---------------- composite (regime-conditional, same gate as the dashboard) ----------------
            double num = 0, den = 0, hc = CostHaircutPct / 100.0;
            for (int tf = 0; tf < TfCount; tf++)
            {
                DealingRange rg = ranges[tf];
                if (!rg.Valid || rg.Range <= 0 || regime == 1) continue;
                PosteriorCell c = cells[tf, regime];
                if (c.N < MinSamples) continue;
                double p0  = c.PStar0;
                double pos = Math.Max(-1, Math.Min(1, (Close[0] - rg.Eq) / (0.5 * rg.Range)));
                double w = 0, dirSign = 0;
                if (regime == 0 && c.Lo90 > p0 + hc)      { w = (c.Mean - p0 - hc) * 4; dirSign = -1; } // fade the extreme
                else if (regime == 2 && c.Hi90 < p0 - hc) { w = (p0 - hc - c.Mean) * 4; dirSign = 1;  } // follow it
                if (w <= 0) continue;
                num += dirSign * pos * w;
                den += w;
            }
            compositeBias[0] = den > 0 ? 100 * num / den : 0;
            lastBias = compositeBias[0];

            if (State == State.Realtime && (DateTime.UtcNow - lastPersist).TotalMinutes > 10)
            {
                lastPersist = DateTime.UtcNow; SaveState();
            }
        }

        private void UpdateSwingsAndRange(int bip)
        {
            int k = bip == 3 ? Math.Max(2, SwingStrength - 2) : SwingStrength;
            if (CurrentBars[bip] < 2 * k + 2) return;
            int c = k + 1;
            bool isHigh = true, isLow = true;
            double ph = Highs[bip][c], pl = Lows[bip][c];
            for (int j = 1; j <= k && (isHigh || isLow); j++)
            {
                if (Highs[bip][c - j] > ph || Highs[bip][c + j] > ph) isHigh = false;
                if (Lows[bip][c - j]  < pl || Lows[bip][c + j]  < pl) isLow  = false;
            }
            int tf = bip - 1;
            bool rebuilt = false;
            if (isHigh) { lastHigh[bip] = new SwingPoint { Price = ph, Time = Times[bip][c] }; rebuilt = true; }
            if (isLow)  { lastLow[bip]  = new SwingPoint { Price = pl, Time = Times[bip][c] }; rebuilt = true; }
            if (rebuilt && lastHigh[bip] != null && lastLow[bip] != null && lastHigh[bip].Price > lastLow[bip].Price)
            {
                DealingRange r = ranges[tf];
                // record completed pullback depth at range turnover (older half only — IS for the seed)
                if (r.Valid && State == State.Historical && r.Range > 0
                    && CurrentBars[0] > 0 && CurrentBars[0] < BarsArray[0].Count / 2)
                {
                    double depth = r.BullLeg
                        ? (r.High - Math.Min(lastLow[bip].Price, r.High)) / r.Range
                        : (Math.Max(lastHigh[bip].Price, r.Low) - r.Low) / r.Range;
                    if (depth > 0 && depth < 2) { retraceDepths.Add(depth); retraceTimed.Add(new KeyValuePair<DateTime, double>(Times[bip][0], depth)); }
                }
                // swap in a fully-built range: OnRender reads ranges[tf] concurrently (ref assignment is atomic)
                ranges[tf] = new DealingRange
                {
                    Valid = true, High = lastHigh[bip].Price, Low = lastLow[bip].Price,
                    AnchorTime = lastHigh[bip].Time < lastLow[bip].Time ? lastHigh[bip].Time : lastLow[bip].Time,
                    BullLeg = lastHigh[bip].Time > lastLow[bip].Time
                };
            }
        }
        #endregion

        #region Regime
        private int CurrentRegime(DateTime barTime)
        {
            // live poll first; else GEX history (covers the gap between load and first poll);
            // else the LOCAL trend-efficiency proxy
            if (State != State.Historical && gexLiveValid)
                return gexSign > 0 ? 0 : gexSign < 0 ? 2 : 1;
            if (gexHistoryLoaded)
            {
                var gh = gexHistory;                         // local copy: map is swapped by background task
                // only the PRIOR session's EOD GEX is knowable intraday — lag the lookup
                DateTime d = barTime.Date.AddDays(-1);
                for (int b = 0; b < 5; b++, d = d.AddDays(-1))
                {
                    int s;
                    if (gh.TryGetValue(d, out s)) return s > 0 ? 0 : s < 0 ? 2 : 1;
                }
            }
            return LocalRegime(0);
        }

        // trend-efficiency proxy on the primary series (LOCAL fallback when no GEX feed)
        private int LocalRegime(int barsAgo)
        {
            int cb = CurrentBars[0];
            if (cb - barsAgo < 121 || cb < 0) return 1;
            double net = Math.Abs(Closes[0][barsAgo] - Closes[0][barsAgo + 120]);
            double path = 0;
            for (int i = 1; i <= 120; i++) path += Math.Abs(Closes[0][barsAgo + i - 1] - Closes[0][barsAgo + i]);
            double er = path > 0 ? net / path : 0;
            return er > 0.35 ? 2 : 0;
        }
        #endregion

        #region GEX REST
        private static string Msg(Exception ex)
        {
            var a = ex as AggregateException;
            return a != null && a.InnerException != null ? a.InnerException.Message : ex.Message;
        }

        private static double ToD(object o)
        {
            if (o == null) return double.NaN;
            if (o is double)  return (double)o;
            if (o is decimal) return (double)(decimal)o;
            if (o is int)     return (int)o;
            if (o is long)    return (long)o;
            double parsed;
            return double.TryParse(Convert.ToString(o, CultureInfo.InvariantCulture),
                NumberStyles.Float, CultureInfo.InvariantCulture, out parsed) ? parsed : double.NaN;
        }

        private Dictionary<string, object>[] UwGreekExposureRows()
        {
            var req = new HttpRequestMessage(HttpMethod.Get,
                string.Format("https://api.unusualwhales.com/api/stock/{0}/greek-exposure", UwTicker));
            req.Headers.Add("Authorization", "Bearer " + UwToken);
            req.Headers.Add("Accept", "application/json");
            using (var resp = http.SendAsync(req).Result)
            {
                string body = resp.Content.ReadAsStringAsync().Result;
                if (!resp.IsSuccessStatusCode)
                    throw new Exception("UW HTTP " + (int)resp.StatusCode + ": " + body.Substring(0, Math.Min(body.Length, 160)));
                var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
                var root = js.DeserializeObject(body) as Dictionary<string, object>;
                object dataObj; object[] data = root != null && root.TryGetValue("data", out dataObj) ? dataObj as object[] : null;
                return data == null ? new Dictionary<string, object>[0]
                                    : data.Select(x => x as Dictionary<string, object>).Where(x => x != null).ToArray();
            }
        }

        private static double NetGamma(Dictionary<string, object> row)
        {
            return ToD(row.ContainsKey("call_gamma") ? row["call_gamma"] : null)
                 + ToD(row.ContainsKey("put_gamma")  ? row["put_gamma"]  : null);
        }

        private void PollLiveGex()
        {
            try
            {
                if (!string.IsNullOrWhiteSpace(FlashAlphaUrl))
                {
                    string body = http.GetStringAsync(FlashAlphaUrl).Result;
                    object node = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.DeserializeObject(body);
                    foreach (string part in FlashAlphaJsonPath.Split('.'))
                    {
                        var d = node as Dictionary<string, object>;
                        if (d == null || !d.TryGetValue(part, out node)) { node = null; break; }
                    }
                    double g = ToD(node);
                    if (!double.IsNaN(g))
                    {
                        gexSign = g > 0 ? 1 : g < 0 ? -1 : 0;
                        gexLiveValid = true;
                        gexStatusText = string.Format("GEX {0} (FlashAlpha)", gexSign > 0 ? "+" : gexSign < 0 ? "-" : "FLIP");
                        return;
                    }
                }
                if (!string.IsNullOrWhiteSpace(UwToken))
                {
                    var rows = UwGreekExposureRows();
                    if (rows.Length > 0)
                    {
                        var last = rows.OrderBy(x => Convert.ToString(x.ContainsKey("date") ? x["date"] : "")).Last();
                        double net = NetGamma(last);
                        if (!double.IsNaN(net))
                        {
                            double eps = gexAbsEps;
                            gexSign = net > eps ? 1 : net < -eps ? -1 : 0;
                            gexLiveValid = true;
                            gexStatusText = string.Format("GEX {0} ({1} UW)", gexSign > 0 ? "+" : gexSign < 0 ? "-" : "FLIP", UwTicker);
                            return;
                        }
                    }
                }
                gexStatusText = "GEX: LOCAL proxy (no API configured)";
            }
            catch (Exception ex)
            {
                gexStatusText = "GEX: LOCAL (fetch failed)";
                Print("Deep6PDv2 GEX poll error: " + Msg(ex));
            }
        }

        private void FetchUwGexHistory()
        {
            try
            {
                var rows = new List<KeyValuePair<DateTime, double>>();
                foreach (var r in UwGreekExposureRows())
                {
                    double net = NetGamma(r);
                    DateTime d;
                    if (!double.IsNaN(net) && r.ContainsKey("date")
                        && DateTime.TryParseExact(Convert.ToString(r["date"]), "yyyy-MM-dd",
                            CultureInfo.InvariantCulture, DateTimeStyles.None, out d))
                        rows.Add(new KeyValuePair<DateTime, double>(d, net));
                }
                // FLIP band: |net| below the 20th percentile = dealer positioning too small to trust either way
                double eps = 0;
                if (rows.Count >= 20)
                {
                    double[] abs = rows.Select(x => Math.Abs(x.Value)).OrderBy(x => x).ToArray();
                    eps = abs[(int)(0.2 * (abs.Length - 1))];
                }
                var map = new Dictionary<DateTime, int>();
                foreach (var kv in rows) map[kv.Key] = kv.Value > eps ? 1 : kv.Value < -eps ? -1 : 0;
                gexAbsEps = eps;
                gexHistory = map; gexHistoryLoaded = map.Count > 0;
                Print(string.Format("Deep6PDv2: UW GEX history loaded — {0} sessions, FLIP band |net| < {1:E2}.", map.Count, eps));
            }
            catch (Exception ex) { Print("Deep6PDv2: UW GEX history failed (" + Msg(ex) + ") — calibration uses LOCAL regime proxy."); }
        }
        #endregion

        #region Calibration (runs once, at the end of the historical pass)
        private void RunCalibration()
        {
            int cb = CurrentBars[0];
            if (calibrated || cb < 500) { calibrated = true; return; }
            calibrated = true;

            // regime tagging for the seed needs the GEX history; wait briefly if it is still in flight
            if (histTask != null) try { histTask.Wait(10000); } catch { }

            var rep = new List<string> { "DEEP6 PD v2.1 — IN-PLATFORM CALIBRATION  " + DateTime.Now, new string('=', 64) };
            rep.Add(string.Format("Split: bands/race/IBS fit on bars 0..{0} (older half); posterior seed replays bars {0}..{1} (recent half).", cb / 2, cb));
            rep.Add(gexHistoryLoaded ? "Regime source: UW GEX history (prior-session lookup)." : "Regime source: LOCAL trend-efficiency proxy (no GEX history).");

            // regime-tag the pullback samples now, AFTER the history wait — one consistent regime
            // source for the whole fit (tagging per-bar raced the async GEX fetch)
            for (int r0 = 0; r0 < RegimeCount; r0++) pullbackByRegime[r0].Clear();
            foreach (var kv in retraceTimed)
            {
                int idx = Bars.GetBar(kv.Key);
                if (idx < 0) continue;
                pullbackByRegime[HistRegime(Math.Max(1, cb - idx))].Add(kv.Value);
            }

            // ---- G1: retracement distribution vs 61.8-79 claim ----
            if (retraceDepths.Count > 100)
            {
                double[] d = retraceDepths.Where(x => x > 0.1 && x < 1.5).ToArray();
                double inOte  = d.Count(x => x >= 0.618 && x <= 0.79) / (double)d.Length;
                double expect = (0.79 - 0.618) / 1.4;
                rep.Add(string.Format("G1 retracements: n={0}  mass(61.8-79)={1:P1}  uniform-expect={2:P1}  ratio={3:F2}  -> {4}",
                    d.Length, inOte, expect, inOte / expect, inOte / expect > 1.15 ? "fib band kept" : "fib band REJECTED -> empirical bands"));
                rep.Add("    note: depths are sampled at range turnover (completed pullbacks only) — survivorship-conditioned.");
            }
            // regime-conditional empirical pullback bands (q60/q85), fallback to pooled
            double[] pooled = retraceDepths.Where(x => x > 0 && x < 1.2).OrderBy(x => x).ToArray();
            for (int r = 0; r < RegimeCount; r++)
            {
                double[] src = pullbackByRegime[r].Count > 60 ? pullbackByRegime[r].Where(x => x > 0 && x < 1.2).OrderBy(x => x).ToArray() : pooled;
                if (src.Length > 20)
                {
                    bandQ60[r] = src[(int)(0.60 * (src.Length - 1))];
                    bandQ85[r] = src[(int)(0.85 * (src.Length - 1))];
                    rep.Add(string.Format("   band[{0}]: q60={1:P0} q85={2:P0} depth (n={3})", RegimeTags[r], bandQ60[r], bandQ85[r], src.Length));
                }
                else { bandQ60[r] = 0.55; bandQ85[r] = 0.74; }
            }

            // ---- G5: anchor horse race (sign agreement, NON-OVERLAPPING 60-bar fwd windows, older half) ----
            if (icSamples.Count > 100)
            {
                int n = 0; double aV = 0, aE = 0, aW = 0, aP = 0;
                foreach (double[] s in icSamples)
                {
                    int bar = (int)s[4];
                    if (bar + 60 > cb) continue;
                    double fwd = Math.Log(Closes[0][cb - (bar + 60)] / Closes[0][cb - bar]);
                    n++;
                    aV += Math.Sign(s[0]) == Math.Sign(fwd) ? 1 : 0;
                    aE += Math.Sign(s[1]) == Math.Sign(fwd) ? 1 : 0;
                    aW += Math.Sign(s[2]) == Math.Sign(fwd) ? 1 : 0;
                    aP += Math.Sign(s[3]) == Math.Sign(fwd) ? 1 : 0;
                }
                if (n > 60)
                {
                    anchorIcVwap = aV / n; anchorIcEq = aE / n; anchorIcEwma = aW / n;
                    double[] rates = { anchorIcVwap, anchorIcEq, anchorIcEwma, aP / n };
                    string[] names = { "VWAP", "EQ", "EWMA", "POC" };
                    int bi = 0; for (int i = 1; i < rates.Length; i++) if (rates[i] > rates[bi]) bi = i;
                    double runnerUp = rates.Where((x, i) => i != bi).Max();
                    bool decisive = rates[bi] - runnerUp >= 0.02;   // must beat runner-up by 2pp on independent windows
                    anchorWinner = decisive ? names[bi] : "VWAP";
                    rep.Add(string.Format("G5 anchor race (independent 60-bar windows, n={0}): VWAP={1:P1} EQ={2:P1} EWMA={3:P1} POC={4:P1} -> {5}",
                        n, rates[0], rates[1], rates[2], rates[3],
                        decisive ? "winner " + names[bi] : "inconclusive (margin < 2pp) -> default VWAP"));
                }
            }

            // ---- G3: IBS quintiles with significance ----
            if (ibsSamples.Count > 200)
            {
                var sorted = ibsSamples.OrderBy(x => x[0]).ToList();
                int q = sorted.Count / 5;
                double[] q1 = sorted.Take(q).Select(x => x[1]).ToArray();
                double[] q5 = sorted.Skip(4 * q).Select(x => x[1]).ToArray();
                double m1 = q1.Average(), m5 = q5.Average();
                double v1 = q1.Sum(x => (x - m1) * (x - m1)) / Math.Max(1, q1.Length - 1);
                double v5 = q5.Sum(x => (x - m5) * (x - m5)) / Math.Max(1, q5.Length - 1);
                double se = Math.Sqrt(v1 / q1.Length + v5 / q5.Length);
                double t  = se > 0 ? (m1 - m5) / se : 0;
                rep.Add(string.Format("G3 IBS (ETH session, not RTH): n={0} days  Q1={1:F1}bps  Q5={2:F1}bps  spread={3:F1}bps  t={4:F2}  -> {5}",
                    sorted.Count, m1 * 1e4, m5 * 1e4, (m1 - m5) * 1e4, t,
                    Math.Abs(t) < 2 ? "inconclusive (|t|<2)" : m1 - m5 > 0 ? "reversion confirmed" : "momentum, not reversion"));
            }

            // ---- G2/G4 seed: replay lifecycle over the RECENT half with regime tags ----
            SeedPosteriorsFromHistory(rep);

            // per-cell asymmetric breakeven
            double hc = CostHaircutPct / 100.0;
            for (int t2 = 0; t2 < TfCount; t2++)
                for (int r2 = 0; r2 < RegimeCount; r2++)
                {
                    PosteriorCell c = cells[t2, r2];
                    if (c.PayN > 0)
                        rep.Add(string.Format("   p*[{0}|{1}] = {2:P1} (+{3:P1} haircut)  T~{4:F1}pts S~{5:F1}pts  n={6}  P(rev)={7:P1} [{8:P1}-{9:P1}]",
                            TfTags[t2], RegimeTags[r2], c.PStar0, hc, c.SumT / c.PayN, c.SumS / c.PayN, (int)c.N, c.Mean, c.Lo90, c.Hi90));
                }

            rep.Add(new string('=', 64));
            rep.Add("Cells below MinSamples or failing their own p* gate render SHADOW.");
            rep.Add("REMINDER: split-half chronological validation, not CPCV — see spec G7. Seed uses primary-series proxy pivots (HONEST LIMITS).");
            foreach (string line in rep) Print(line);
            try { File.WriteAllLines(reportFile, rep); } catch { }
        }

        private void SeedPosteriorsFromHistory(List<string> rep)
        {
            // Replays the live lifecycle bar-by-bar over the RECENT half of chart history (the half
            // no calibration artifact was fit on). Range structure is reconstructed from primary-
            // series pivots (k = SwingStrength x 3/9/21 proxies H4/D/W) — coarse but causal: the
            // pivot window starts at barsAgo i+1, so a pivot becomes known exactly one bar after
            // its window completes, matching the live confirmation delay. Arming, intrabar stops,
            // TargetSigma, per-TF sigma horizon and timeouts all match the live path.
            int cb = CurrentBars[0];
            int half = cb / 2;
            int[] kfac = { 3, 9, 21 };
            double pmin = BarsPeriod.BarsPeriodType == BarsPeriodType.Minute ? BarsPeriod.Value : 1;
            int seeded = 0, wins = 0;
            for (int tf = 0; tf < TfCount; tf++)
            {
                int k = SwingStrength * kfac[tf];
                int tmo = TimeoutBars * TfTimeoutFac[tf];
                double rngHi = double.NaN, rngLo = double.NaN;
                int dir = 0; double entry = 0, tgt = 0, stp = 0; int openedBar = -1; int regAt = 0;
                double lastH = double.NaN, lastL = double.NaN;
                bool arm = false;
                for (int i = half; i >= 1; i--)
                {
                    if (Times[0][i] >= firstLiveOpen) break; // episodes from here on are already counted in the live deltas
                    int c = i + k + 1;                       // pivot center: window c±k ends at barsAgo i+1 → known at bar i
                    if (c + k <= cb)
                    {
                        bool isH = true, isL = true;
                        double ph = Highs[0][c], pl = Lows[0][c];
                        for (int j = 1; j <= k && (isH || isL); j++)
                        {
                            if (Highs[0][c + j] > ph || Highs[0][c - j] > ph) isH = false;
                            if (Lows[0][c + j]  < pl || Lows[0][c - j]  < pl) isL = false;
                        }
                        if (isH) lastH = ph;
                        if (isL) lastL = pl;
                        if (!double.IsNaN(lastH) && !double.IsNaN(lastL) && lastH > lastL) { rngHi = lastH; rngLo = lastL; }
                    }
                    if (double.IsNaN(rngHi) || rngHi <= rngLo) continue;
                    double close = Closes[0][i];
                    double loc = (close - rngLo) / (rngHi - rngLo);
                    if (loc > 0.25 && loc < 0.75) arm = true;
                    double sig = Math.Max(realizedVol.IsValidDataPoint(i) ? realizedVol[i] : 0.0006, 1e-6)
                               * close * Math.Sqrt(TfHorizonMin[tf] / pmin);

                    if (openedBar < 0 && arm && (loc <= 0.10 || loc >= 0.90))
                    {
                        dir = loc <= 0.10 ? 1 : -1;
                        regAt = HistRegime(i);
                        if (regAt == 1) continue;
                        entry = close;
                        tgt = TargetSigma > 0 ? close + dir * TargetSigma * sig : rngLo + 0.5 * (rngHi - rngLo);
                        stp = close - dir * StopSigma * sig;
                        openedBar = i;
                        arm = false;
                    }
                    else if (openedBar > 0)
                    {
                        bool loss = dir > 0 ? Lows[0][i] <= stp : Highs[0][i] >= stp;   // intrabar, loss-first
                        bool win  = !loss && (dir > 0 ? close >= tgt : close <= tgt);
                        bool timo = !loss && !win && openedBar - i >= tmo;
                        if (win || loss || timo)
                        {
                            PosteriorCell cell = cells[tf, regAt];
                            cell.Alpha += win ? 1 : 0;
                            cell.Beta  += win ? 0 : 1;
                            cell.SumT += Math.Abs(tgt - entry); cell.SumS += Math.Abs(entry - stp); cell.PayN++;
                            seeded++; wins += win ? 1 : 0;
                            openedBar = -1;
                        }
                    }
                }
            }
            rep.Add(string.Format("G2/G4 seed (recent half): {0} signals resolved, raw hit {1:P1}; per-cell posteriors updated.", seeded, seeded > 0 ? wins / (double)seeded : 0));
        }

        private int HistRegime(int barsAgo)
        {
            if (gexHistoryLoaded)
            {
                var gh = gexHistory;
                DateTime d = Times[0][barsAgo].Date.AddDays(-1);     // prior-session lookup, same as live
                for (int b = 0; b < 5; b++, d = d.AddDays(-1))
                {
                    int s;
                    if (gh.TryGetValue(d, out s)) return s > 0 ? 0 : s < 0 ? 2 : 1;
                }
            }
            return LocalRegime(barsAgo);
        }

        private double EstimateHalfLife(List<double> s)
        {
            var xs = new List<double>(); var ys = new List<double>();
            for (int i = 0; i + 1 < s.Count; i++)
            {
                if (double.IsNaN(s[i]) || double.IsNaN(s[i + 1])) continue;   // skip session-straddling pairs
                xs.Add(s[i]); ys.Add(s[i + 1] - s[i]);
            }
            int n = xs.Count;
            if (n < 200) return double.NaN;
            double mx = 0, my = 0;
            for (int i = 0; i < n; i++) { mx += xs[i]; my += ys[i]; }
            mx /= n; my /= n;
            double cov = 0, var = 0;
            for (int i = 0; i < n; i++) { cov += (xs[i] - mx) * (ys[i] - my); var += (xs[i] - mx) * (xs[i] - mx); }
            if (var <= 0) return double.NaN;
            double kappa = -(cov / var);
            return kappa > 1e-6 ? Math.Log(2) / kappa * (BarsPeriod.BarsPeriodType == BarsPeriodType.Minute ? BarsPeriod.Value : 1) : double.NaN;
        }
        #endregion

        #region Lifecycle helpers / persistence / telemetry
        private void ResolveSignal(int tf, LiveSignal s, bool win, string how)
        {
            PosteriorCell c = cells[tf, s.Regime];
            double tt = Math.Abs(s.Target - s.Entry), ss = Math.Abs(s.Entry - s.Stop);
            c.Alpha += win ? 1 : 0; c.Beta += win ? 0 : 1;
            c.SumT += tt; c.SumS += ss; c.PayN++;
            c.LiveAlpha += win ? 1 : 0; c.LiveBeta += win ? 0 : 1; c.LiveN++;
            c.LiveSumT += tt; c.LiveSumS += ss; c.LivePayN++;
            LogSignal("CLOSE", tf, s.Regime, s, how + (win ? "/WIN" : "/LOSS"));
            if (State == State.Realtime)
                Alert("d6v2_" + tf + "_" + CurrentBar, Priority.Medium,
                    string.Format("DEEP6 PDv2: {0} {1} cell resolved {2} — P(rev) now {3:P0} [{4:P0}-{5:P0}] n={6}",
                        TfTags[tf], RegimeTags[s.Regime], how, c.Mean, c.Lo90, c.Hi90, (int)c.N),
                    Path.Combine(NinjaTrader.Core.Globals.InstallDir, "sounds", "Alert2.wav"), 10, Media.Brushes.Black, Media.Brushes.White);
        }

        private void LogSignal(string evt, int tf, int regime, LiveSignal s, string note)
        {
            try
            {
                bool head = !File.Exists(signalsFile);
                using (var w = new StreamWriter(signalsFile, true))
                {
                    if (head) w.WriteLine("utc,evt,tf,regime,dir,entry,target,stop,note");
                    w.WriteLine(string.Format(CultureInfo.InvariantCulture, "{0:o},{1},{2},{3},{4},{5},{6},{7},{8}",
                        DateTime.UtcNow, evt, TfTags[tf], RegimeTags[regime], s.IsLong ? "L" : "S", s.Entry, s.Target, s.Stop, note));
                }
            }
            catch { }
        }

        private void SaveState()
        {
            try
            {
                // persist LIVE deltas only — the historical seed is rebuilt fresh on every load,
                // so reloads can never compound evidence (v2.0 inflated n on every restart)
                var ps = new PersistedState
                {
                    CalibratedThrough = DateTime.UtcNow.ToString("o"),
                    FirstLiveOpen = firstLiveOpen == DateTime.MaxValue ? "" : firstLiveOpen.ToString("o")
                };
                for (int t = 0; t < TfCount; t++)
                    for (int r = 0; r < RegimeCount; r++)
                    {
                        PosteriorCell c = cells[t, r];
                        ps.Cells[TfTags[t] + "|" + RegimeTags[r]] =
                            new[] { c.LiveAlpha, c.LiveBeta, (double)c.LiveN, c.LiveSumT, c.LiveSumS, (double)c.LivePayN };
                    }
                string tmp = stateFile + ".tmp";
                File.WriteAllText(tmp, new JavaScriptSerializer().Serialize(ps));
                if (File.Exists(stateFile)) File.Replace(tmp, stateFile, null);
                else File.Move(tmp, stateFile);
            }
            catch (Exception ex) { Print("Deep6PDv2 save failed: " + Msg(ex)); }
        }

        private void LoadState()
        {
            try
            {
                if (!File.Exists(stateFile)) return;
                var ps = new JavaScriptSerializer().Deserialize<PersistedState>(File.ReadAllText(stateFile));
                if (ps == null || ps.Cells == null) return;
                DateTime flo;
                if (!string.IsNullOrEmpty(ps.FirstLiveOpen)
                    && DateTime.TryParse(ps.FirstLiveOpen, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out flo))
                    firstLiveOpen = flo;
                for (int t = 0; t < TfCount; t++)
                    for (int r = 0; r < RegimeCount; r++)
                    {
                        double[] v;
                        if (!ps.Cells.TryGetValue(TfTags[t] + "|" + RegimeTags[r], out v) || v == null || v.Length < 6) continue;
                        PosteriorCell c = cells[t, r];
                        c.LiveAlpha = v[0]; c.LiveBeta = v[1]; c.LiveN = (int)v[2];
                        c.LiveSumT = v[3]; c.LiveSumS = v[4]; c.LivePayN = (int)v[5];
                        c.Alpha += v[0]; c.Beta += v[1];
                        c.SumT += v[3]; c.SumS += v[4]; c.PayN += (int)v[5];
                    }
                Print("Deep6PDv2: live posterior deltas restored from " + stateFile);
            }
            catch (Exception ex) { Print("Deep6PDv2 load failed: " + Msg(ex)); }
        }
        #endregion

        #region Rendering
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (Bars == null || ChartBars == null || RenderTarget == null || IsInHitTest) return;

            float pl = ChartPanel.X, pr = ChartPanel.X + ChartPanel.W, pt = ChartPanel.Y, pb = ChartPanel.Y + ChartPanel.H;
            int regime = lastRegime;                          // cached on the data thread — no series reads per frame
            float mute = regime == 2 ? 0.45f : regime == 1 ? 0.3f : 1f;
            float zoneA = Math.Max(0.02f, Math.Min(0.6f, ZoneOpacity / 100f)) * mute;

            if (fmtS == null)  fmtS = new DW.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", DW.FontWeight.Normal, DW.FontStyle.Normal, 10f);
            if (fmtH == null)  fmtH = new DW.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", DW.FontWeight.Bold, DW.FontStyle.Normal, 11.5f);
            if (ssDash == null) ssDash = new D2D.StrokeStyle(NinjaTrader.Core.Globals.D2DFactory, new D2D.StrokeStyleProperties { DashStyle = D2D.DashStyle.Dash });
            if (ssDot == null)  ssDot  = new D2D.StrokeStyle(NinjaTrader.Core.Globals.D2DFactory, new D2D.StrokeStyleProperties { DashStyle = D2D.DashStyle.Dot });

            D2D.SolidColorBrush txt = null, dim = null, prem = null, disc = null, eqB = null, band = null, anch = null, bg = null, edge = null;
            try
            {
                txt  = Solid(TextBrush, 1f);   dim = Solid(TextBrush, 0.5f);
                prem = Solid(PremiumBrush, .85f); disc = Solid(DiscountBrush, .85f);
                eqB  = Solid(EqBrush, .95f);  band = Solid(BandBrush, .9f); anch = Solid(AnchorBrush, .95f);
                bg   = new D2D.SolidColorBrush(RenderTarget, new Color4(0.055f, 0.065f, 0.095f, 0.93f));
                edge = new D2D.SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 0.10f));

                // zones + EQ + empirical band per TF
                for (int tf = 0; tf < TfCount; tf++)
                {
                    DealingRange r = ranges == null ? null : ranges[tf];
                    if (r == null || !r.Valid || r.Range <= 0) continue;
                    float x1 = chartControl.GetXByTime(r.AnchorTime); if (x1 < pl || float.IsNaN(x1)) x1 = pl;
                    float yH = chartScale.GetYByValue(r.High), yL = chartScale.GetYByValue(r.Low), yE = chartScale.GetYByValue(r.Eq);
                    Grad(x1, yH, pr, yE, C4(PremiumBrush, zoneA), C4(PremiumBrush, 0.012f));
                    Grad(x1, yE, pr, yL, C4(DiscountBrush, 0.012f), C4(DiscountBrush, zoneA));
                    RenderTarget.DrawLine(new Vector2(x1, yH), new Vector2(pr, yH), prem, 1.4f);
                    RenderTarget.DrawLine(new Vector2(x1, yL), new Vector2(pr, yL), disc, 1.4f);
                    RenderTarget.DrawLine(new Vector2(x1, yE), new Vector2(pr, yE), eqB, 1.5f, ssDash);

                    double q60 = bandQ60[regime] > 0 ? bandQ60[regime] : 0.55, q85 = bandQ85[regime] > 0 ? bandQ85[regime] : 0.74;
                    double bTop = r.BullLeg ? r.High - q60 * r.Range : r.Low + q85 * r.Range;
                    double bBot = r.BullLeg ? r.High - q85 * r.Range : r.Low + q60 * r.Range;
                    float yT = chartScale.GetYByValue(Math.Max(bTop, bBot)), yB2 = chartScale.GetYByValue(Math.Min(bTop, bBot));
                    using (var f = new D2D.SolidColorBrush(RenderTarget, C4(BandBrush, Math.Min(0.4f, zoneA + 0.08f))))
                        RenderTarget.FillRectangle(new RectangleF(x1, yT, pr - x1, yB2 - yT), f);
                    RenderTarget.DrawLine(new Vector2(x1, yT), new Vector2(pr, yT), band, 1f, ssDot);
                    RenderTarget.DrawLine(new Vector2(x1, yB2), new Vector2(pr, yB2), band, 1f, ssDot);

                    if (ShowLabels)
                    {
                        TagR(string.Format("{0} HI {1:F2}", TfTags[tf], r.High), pr, yH, fmtS, prem);
                        TagR(string.Format("{0} EQ {1:F2}", TfTags[tf], r.Eq), pr, yE, fmtS, eqB);
                        TagR(string.Format("{0} LO {1:F2}", TfTags[tf], r.Low), pr, yL, fmtS, disc);
                        TagR(string.Format("EMP BAND q60-q85 [{0}]", RegimeTags[regime]), pr, yT, fmtS, band);
                    }
                }

                // anchor line (winner) across visible bars — absolute-index access only:
                // barsAgo indexing in OnRender resolves against whichever series processed last
                // (e.g. the 4-bar Weekly) and throws out-of-range
                if (anchorSeries != null)
                {
                    int last = Math.Min(ChartBars.ToIndex, ChartBars.Bars.Count - 1);
                    float prevX = float.NaN, prevY = float.NaN; double lastVal = double.NaN;
                    for (int idx = Math.Max(ChartBars.FromIndex, 0); idx <= last; idx++)
                    {
                        if (!anchorSeries.IsValidDataPointAt(idx)) { prevX = float.NaN; continue; }
                        double val = anchorSeries.GetValueAt(idx);
                        if (val <= 0) { prevX = float.NaN; continue; }
                        float x = chartControl.GetXByBarIndex(ChartBars, idx);
                        float y = chartScale.GetYByValue(val);
                        if (!float.IsNaN(prevX)) RenderTarget.DrawLine(new Vector2(prevX, prevY), new Vector2(x, y), anch, 1.6f);
                        prevX = x; prevY = y; lastVal = val;
                    }
                    if (ShowLabels && !double.IsNaN(lastVal))
                        TagR(string.Format("ANCHOR {0} {1:F2} (race winner)", anchorWinner, lastVal), pr, chartScale.GetYByValue(lastVal), fmtS, anch);
                }

                if (ShowDashboard && cells != null) Dashboard(regime, pl, pr, pt, pb, fmtH, fmtS, txt, dim, prem, disc, eqB, anch, bg, edge);
            }
            finally
            {
                foreach (IDisposable d in new IDisposable[] { txt, dim, prem, disc, eqB, band, anch, bg, edge })
                    if (d != null) d.Dispose();
            }
        }

        private void Dashboard(int regime, float pl, float pr, float pt, float pb,
            DW.TextFormat fH, DW.TextFormat fS, D2D.SolidColorBrush txt, D2D.SolidColorBrush dim,
            D2D.SolidColorBrush prem, D2D.SolidColorBrush disc, D2D.SolidColorBrush eqB, D2D.SolidColorBrush anch,
            D2D.SolidColorBrush bg, D2D.SolidColorBrush edge)
        {
            float w = 318f, rowH = 19f, h = 30f + 18f + 16f + TfCount * rowH + 56f;
            float x = DashboardPos == Deep6DashboardCorner.TopLeft || DashboardPos == Deep6DashboardCorner.BottomLeft ? pl + 12f : pr - w - 12f;
            float y = DashboardPos == Deep6DashboardCorner.BottomLeft || DashboardPos == Deep6DashboardCorner.BottomRight ? pb - h - 12f : pt + 12f;

            var rr = new D2D.RoundedRectangle { Rect = new RectangleF(x, y, w, h), RadiusX = 7f, RadiusY = 7f };
            RenderTarget.FillRoundedRectangle(rr, bg);
            RenderTarget.DrawRoundedRectangle(rr, edge, 1f);

            Cell("DEEP6 PREMIUM / DISCOUNT v2.1", x + 10, y + 6, w - 20, fH, txt);
            string verdict = regime == 0 ? "MEAN-REVERT REGIME" : regime == 2 ? "MOMENTUM REGIME" : "STAND ASIDE";
            D2D.SolidColorBrush vb = regime == 0 ? disc : regime == 2 ? prem : eqB;
            Cell(gexStatusText + "  ·  " + verdict, x + 10, y + 26, w - 20, fS, vb);

            float ry = y + 46;
            Cell("TF", x + 10, ry, 26, fS, dim); Cell("P(rev) 90% CI", x + 40, ry, 110, fS, dim);
            Cell("n / p*", x + 152, ry, 52, fS, dim); Cell("t1/2", x + 206, ry, 44, fS, dim); Cell("ACTION", x + 254, ry, 60, fS, dim);
            ry += 16;
            double hc = CostHaircutPct / 100.0;
            for (int tf = 0; tf < TfCount; tf++)
            {
                PosteriorCell c = cells[tf, regime];
                double p0 = c.PStar0;
                // FADE needs proof fading beats its own breakeven; FOLLOW needs proof fading FAILS it
                bool ok = regime == 0 ? c.Lo90 > p0 + hc : regime == 2 && c.Hi90 < p0 - hc;
                bool shadow = c.N < MinSamples || !ok;
                string act = regime == 1 ? "—" : shadow ? "SHADOW" : regime == 0 ? "FADE" : "FOLLOW";
                D2D.SolidColorBrush ab = shadow || regime == 1 ? dim : regime == 0 ? disc : prem;
                Cell(TfTags[tf], x + 10, ry, 26, fS, txt);
                Cell(c.N < 5 ? "collecting…" : string.Format("{0:P0} [{1:P0}-{2:P0}]", c.Mean, c.Lo90, c.Hi90), x + 40, ry, 110, fS, shadow ? dim : txt);
                Cell(string.Format("{0}/{1:P0}", (int)c.N, p0), x + 152, ry, 54, fS, dim);
                Cell(tf == 0 && !double.IsNaN(halfLifeMin) ? string.Format("{0:F0}m", halfLifeMin) : "—", x + 206, ry, 44, fS, dim);
                Cell(act, x + 254, ry, 60, fS, ab);
                ry += rowH;
            }

            // gauge (lastBias is a plain field — never index a Series from OnRender)
            double score = lastBias;
            float gx = x + 12, gw = w - 24, gy = ry + 8, gh = 9;
            using (var track = new D2D.SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 0.08f)))
                RenderTarget.FillRectangle(new RectangleF(gx, gy, gw, gh), track);
            float cx = gx + gw / 2f;
            RenderTarget.DrawLine(new Vector2(cx, gy - 2), new Vector2(cx, gy + gh + 2), dim, 1f);
            float fw = (float)(Math.Min(100, Math.Abs(score)) / 100.0 * gw / 2f);
            RenderTarget.FillRectangle(new RectangleF(score >= 0 ? cx : cx - fw, gy, fw, gh), score >= 0 ? disc : prem);
            Cell(regime == 1 ? "GAUGE SUPPRESSED — NO ACTIVE CELLS"
                : string.Format("BIAS {0:+0;-0;0}  ·  live deltas persisted  ·  anchor {1}", score, anchorWinner),
                gx, gy + gh + 5, gw, fS, regime == 1 ? eqB : txt);
        }

        private D2D.SolidColorBrush Solid(Media.Brush b, float a) { return new D2D.SolidColorBrush(RenderTarget, C4(b, a)); }
        private static Color4 C4(Media.Brush b, float a)
        {
            var s = b as Media.SolidColorBrush; var c = s != null ? s.Color : Media.Colors.Gray;
            return new Color4(c.R / 255f, c.G / 255f, c.B / 255f, a);
        }
        private void Grad(float x1, float yT, float x2, float yB, Color4 cT, Color4 cB)
        {
            var stops = new[] { new D2D.GradientStop { Position = 0f, Color = cT }, new D2D.GradientStop { Position = 1f, Color = cB } };
            using (var gsc = new D2D.GradientStopCollection(RenderTarget, stops))
            using (var lgb = new D2D.LinearGradientBrush(RenderTarget,
                new D2D.LinearGradientBrushProperties { StartPoint = new Vector2(x1, yT), EndPoint = new Vector2(x1, yB) }, gsc))
                RenderTarget.FillRectangle(new RectangleF(x1, yT, x2 - x1, yB - yT), lgb);
        }
        private void TagR(string t, float xR, float yv, DW.TextFormat f, D2D.Brush b)
        {
            using (var tl = new DW.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, t, f, 420f, 20f))
                RenderTarget.DrawTextLayout(new Vector2(xR - tl.Metrics.Width - 8f, yv - tl.Metrics.Height - 2f), tl, b);
        }
        private void Cell(string t, float x, float yv, float w, DW.TextFormat f, D2D.Brush b)
        {
            using (var tl = new DW.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, t, f, w, 18f))
                RenderTarget.DrawTextLayout(new Vector2(x, yv), tl, b);
        }
        #endregion

        #region Public API
        [Browsable(false)] [XmlIgnore] public Series<double> CompositeBias { get { return compositeBias; } }
        public double PRev(int tf) { return cells != null && tf >= 0 && tf < TfCount ? cells[tf, lastRegime].Mean : double.NaN; }
        public double PRevLo90(int tf) { return cells != null && tf >= 0 && tf < TfCount ? cells[tf, lastRegime].Lo90 : double.NaN; }
        public double PStarOf(int tf) { return cells != null && tf >= 0 && tf < TfCount ? cells[tf, lastRegime].PStar0 : double.NaN; }
        public int RegimeCode() { return lastRegime; }
        public double HalfLifeMinutes() { return halfLifeMin; }
        #endregion

        #region Properties
        [NinjaScriptProperty] [Range(2, 25)]
        [Display(Name = "Swing strength", Order = 1, GroupName = "01. Engine")]
        public int SwingStrength { get; set; }

        [NinjaScriptProperty] [Range(20, 1000)]
        [Display(Name = "Min samples to leave SHADOW", Order = 2, GroupName = "01. Engine")]
        public int MinSamples { get; set; }

        [NinjaScriptProperty] [Range(0, 10)]
        [Display(Name = "Cost haircut over p* (%)", Description = "Posterior bound must clear the cell's asymmetric breakeven p* by this margin.", Order = 3, GroupName = "01. Engine")]
        public double CostHaircutPct { get; set; }

        [NinjaScriptProperty] [Range(0, 5)]
        [Display(Name = "Target (sigma, 0 = range EQ)", Order = 4, GroupName = "02. Lifecycle")]
        public double TargetSigma { get; set; }

        [NinjaScriptProperty] [Range(0.5, 8)]
        [Display(Name = "Stop (sigma, per-TF horizon)", Order = 5, GroupName = "02. Lifecycle")]
        public double StopSigma { get; set; }

        [NinjaScriptProperty] [Range(20, 2000)]
        [Display(Name = "Timeout (bars, H4 base; D x6, W x30)", Order = 6, GroupName = "02. Lifecycle")]
        public int TimeoutBars { get; set; }

        [NinjaScriptProperty] [Range(30, 3600)]
        [Display(Name = "GEX poll seconds", Order = 1, GroupName = "04. Data APIs")]
        public int PollSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Unusual Whales API token", Order = 2, GroupName = "04. Data APIs")]
        public string UwToken { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "UW ticker (NDX/QQQ/SPX)", Order = 3, GroupName = "04. Data APIs")]
        public string UwTicker { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "FlashAlpha live URL (optional)", Order = 4, GroupName = "04. Data APIs")]
        public string FlashAlphaUrl { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "FlashAlpha JSON path to net gamma", Order = 5, GroupName = "04. Data APIs")]
        public string FlashAlphaJsonPath { get; set; }

        [NinjaScriptProperty] [Range(2, 60)]
        [Display(Name = "Zone opacity (%)", Order = 1, GroupName = "03. Visuals")]
        public int ZoneOpacity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show dashboard", Order = 2, GroupName = "03. Visuals")]
        public bool ShowDashboard { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Dashboard position", Order = 3, GroupName = "03. Visuals")]
        public Deep6DashboardCorner DashboardPos { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show labels", Order = 4, GroupName = "03. Visuals")]
        public bool ShowLabels { get; set; }

        [XmlIgnore] [Display(Name = "Premium color", Order = 5, GroupName = "03. Visuals")]
        public Media.Brush PremiumBrush { get; set; }
        [Browsable(false)] public string PremiumBrushSerialize { get { return Serialize.BrushToString(PremiumBrush); } set { PremiumBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Discount color", Order = 6, GroupName = "03. Visuals")]
        public Media.Brush DiscountBrush { get; set; }
        [Browsable(false)] public string DiscountBrushSerialize { get { return Serialize.BrushToString(DiscountBrush); } set { DiscountBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Equilibrium color", Order = 7, GroupName = "03. Visuals")]
        public Media.Brush EqBrush { get; set; }
        [Browsable(false)] public string EqBrushSerialize { get { return Serialize.BrushToString(EqBrush); } set { EqBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Empirical band color", Order = 8, GroupName = "03. Visuals")]
        public Media.Brush BandBrush { get; set; }
        [Browsable(false)] public string BandBrushSerialize { get { return Serialize.BrushToString(BandBrush); } set { BandBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Anchor color", Order = 9, GroupName = "03. Visuals")]
        public Media.Brush AnchorBrush { get; set; }
        [Browsable(false)] public string AnchorBrushSerialize { get { return Serialize.BrushToString(AnchorBrush); } set { AnchorBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Text color", Order = 10, GroupName = "03. Visuals")]
        public Media.Brush TextBrush { get; set; }
        [Browsable(false)] public string TextBrushSerialize { get { return Serialize.BrushToString(TextBrush); } set { TextBrush = Serialize.StringToBrush(value); } }
        #endregion
    }
}
