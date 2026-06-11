//==============================================================================================
//  DEEP6 PREMIUM/DISCOUNT MATRIX v3.0 — PHASE 0 (build-out plan r2)
//----------------------------------------------------------------------------------------------
//  Shell only. All pure logic lives in AddOns\Deep6PD\Deep6Core.cs / Deep6Persistence.cs
//  (no NinjaTrader or SharpDX types there — enforced by the offline test project).
//
//  PHASE 0 CHANGES vs the reviewed v2 baseline
//   1. Class renamed Deep6PremiumDiscountV3; state moves to Deep6PD\v3\, keyed per
//      instrument+period; v2 files are never touched.
//   2. POC bucket configurable via PocBucketTicks (the /5.0 NQ literal is gone).
//   3. All horizons minute-denominated (TimeoutMinutes, EWMA half-life, sigma horizon,
//      ER lookback, half-life cadence). The indicator HARD-GATES to Minute-type primary
//      bars: barsPerMinute is undefined on Tick/Range/Renko, so anything else prints an
//      error and disables the engine. This is the documented choice from plan r2 §3/P0.3.
//   4. Secrets: UwToken / FlashAlphaUrl are no longer NinjaScriptProperties and are never
//      serialized; they load from Documents\NinjaTrader 8\Deep6PD\credentials.json.
//   5. One SHADOW predicate (Deep6PD.Core.ShadowRule) shared by composite + dashboard.
//   6. TrackBreak stub deleted.
//   7. Render resources cached: device brushes in OnRenderTargetChanged, TextFormats in
//      DataLoaded, StrokeStyles once, TextLayouts keyed to the dashboard snapshot
//      generation (rebuilt once per bar, reused across mouse-move frames). Debug
//      allocation counters assert nothing is created after the second frame of a
//      generation.
//   8. SaveState guarded: never writes unless calibration completed this session or
//      state was restored.
//   9. Calibration buffers released after RunCalibration; the seed replay runs over
//      local array copies (no NT series indexer churn), stopwatch-timed per phase with
//      a <3s budget printed in the report.
//  QA substrate: IClock (bar time drives trading logic; wall UTC only for GEX age and
//  bookkeeping), IGexProvider (live HTTP / file fixture / off), OfflineMode hard-fails
//  any HTTP attempt, FailureRegistry replaces silent catches, SignalId on every CSV row.
//
//  v2's honest-limits block still applies: this measures, it does not promise edge.
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
using System.Xml.Serialization;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
using SharpDX;
using Deep6PD.Core;
using Media = System.Windows.Media;
using D2D   = SharpDX.Direct2D1;
using DW    = SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// Top-level (not nested) on purpose: the NT 8.1 wrapper generator emits nested-enum
	// parameters unqualified when the enum name collides with another top-level type in
	// this namespace (UWDarkPoolCore.cs declares Deep6DashCorner). A unique top-level
	// name sidesteps both the collision and the generator quirk.
	public enum Deep6DashCorner { TopRight, TopLeft, BottomRight, BottomLeft }

	public class Deep6PremiumDiscountV3 : Indicator
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
			public double Alpha = 2, Beta = 2;          // Beta(2,2) prior
			public int LiveN;                           // live-resolved count (subset of total n)
			public double N      { get { return Alpha + Beta - 4; } }
			public double Mean   { get { return Alpha / (Alpha + Beta); } }
			public double Sd     { get { double s = Alpha + Beta; return Math.Sqrt(Alpha * Beta / (s * s * (s + 1))); } }
			public double Lo90   { get { return Math.Max(0, Mean - 1.645 * Sd); } }
			public double Hi90   { get { return Math.Min(1, Mean + 1.645 * Sd); } }
		}

		private class LiveSignal
		{
			public string SignalId;
			public int Tf; public int Regime; public bool IsLong;
			public double Entry, Target, Stop; public int BarOpened; public DateTime Opened;
		}

		private enum GexMode { Off, Local, Live }
		#endregion

		#region Fields
		private const string CodeVersion = "3.0.0-p0";

		private const int TfCount = 3;                                   // 0=H4 1=Daily 2=Weekly
		private static readonly string[] TfTags = { "H4", "D", "W" };
		private const int RegimeCount = 3;                               // 0=+GEX/calm 1=flip/unknown 2=-GEX/stressed
		private static readonly string[] RegimeTags = { "REVERT", "FLIP", "MOMO" };

		private SwingPoint[] lastHigh, lastLow;
		private DealingRange[] ranges;

		// anchors
		private double sessVwapPv, sessVwapVol, sessionVwap = double.NaN;
		private Dictionary<double, double> pocHist = new Dictionary<double, double>();
		private double sessionPoc = double.NaN, pocBestVol = -1;
		private DateTime currentSessionDate = DateTime.MinValue;
		private Series<double> ewmaMean, realizedVol, anchorSeries;

		// regime
		private volatile int gexSign = 0;                 // -1/0/+1 live
		private GexMode gexMode = GexMode.Off;
		private DateTime lastGexPoll = DateTime.MinValue;            // WALL clock domain
		private Dictionary<DateTime, int> gexHistory = new Dictionary<DateTime, int>(); // session date -> sign
		private volatile bool gexHistoryLoaded;
		private volatile string gexStatusText = "GEX: OFF";
		private Task gexHistoryTask;
		private bool restoredState;
		private int lastRegimeCode = 1;
		private static readonly HttpClient http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };

		// QA substrate (plan r2 Phase 0.10-0.15)
		private ManualClock clock;
		private FailureRegistry failures;
		private PhaseTimer calTimer;
		private IGexProvider offlineGexProvider;          // fixture or Off; live HTTP stays in this shell
		private StatePersistence statePersistence;
		private bool disabledWrongBarType;
		private bool calibrationCompletedThisSession;
		private long memAfterDataLoaded;

		// minute-denominated horizons (set in DataLoaded; primary is hard-gated to Minute type)
		private double minutesPerBar = 1;
		private int timeoutBarsEffective = 240;
		private int erLookbackBars = 120;
		private int hourBars = 60;
		private int spreadCapBars = 1950;
		private double sigmaHorizonBars = 30;
		private double ewmaBars = 390;

		// posteriors / lifecycle
		private PosteriorCell[,] cells;                   // [tf, regime]
		private LiveSignal[] active;                      // one per TF
		private string stateDir, stateFile, signalsFile, reportFile, credentialsFile;
		private string instrumentKey = "";
		private DateTime lastPersist = DateTime.MinValue;            // WALL clock domain (bookkeeping only)
		private string uwToken = "", flashAlphaUrl = "";

		// calibration
		private bool calibrated;
		private readonly List<double> retraceDepths = new List<double>();
		private double[] bandQ60 = new double[RegimeCount], bandQ85 = new double[RegimeCount];
		private readonly List<double>[] pullbackByRegime = new List<double>[RegimeCount];
		private string anchorWinner = "VWAP";
		private double anchorIcVwap, anchorIcEq, anchorIcEwma, anchorIcPoc;
		private readonly List<double[]> icSamples = new List<double[]>(); // [zVwap,zEq,zEwma,zPoc,bar]

		// daily IBS (RTH approximation by session)
		private double dayHi = double.MinValue, dayLo = double.MaxValue, dayClose = double.NaN, prevDayClose = double.NaN;
		private readonly List<double[]> ibsSamples = new List<double[]>(); // [ibs, nextRet]
		private double pendingIbs = double.NaN;

		// half-life
		private readonly List<double> spreadBuf = new List<double>();
		private double halfLifeMin = double.NaN;

		private Series<double> compositeBias;
		private SessionIterator sessionIterator;

		// ---- render resources (Phase 0.7 caching discipline) ----
		// device-independent: created on first render / lazily, disposed in Terminated
		private DW.TextFormat fmtSmall, fmtHead;
		private D2D.StrokeStyle strokeDash, strokeDot;
		// device-dependent: created in OnRenderTargetChanged(non-null), disposed on null + Terminated
		private D2D.SolidColorBrush brTxt, brDim, brPrem, brDisc, brEq, brBand, brAnchor, brBg, brEdge, brTrack, brBandFill;
		private D2D.GradientStopCollection gscPrem, gscDisc;
		private D2D.LinearGradientBrush lgbPrem, lgbDisc;
		// TextLayout cache keyed to dashboard generation
		private readonly Dictionary<string, DW.TextLayout> layoutCache = new Dictionary<string, DW.TextLayout>();
		private int dashGeneration, layoutCacheGeneration = -1;
		private int framesAtGeneration, layoutCreatesThisFrame, deviceBrushCreates;
		private readonly System.Diagnostics.Stopwatch renderWatch = new System.Diagnostics.Stopwatch();
		private double renderMsAccum; private int renderFrames;
		#endregion

		#region State machine
		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description              = "DEEP6 Premium/Discount v3 Phase 0 — regime-gated, posterior-driven PD system. Pure logic in AddOns\\Deep6PD.";
				Name                     = "Deep6PremiumDiscountV3";
				Calculate                = Calculate.OnBarClose;     // lifecycle integrity > tick repainting
				IsOverlay                = true;
				DisplayInDataBox         = false;
				PaintPriceMarkers        = false;
				IsSuspendedWhileInactive = false;                    // GEX polling continues

				SwingStrength   = 5;
				MinSamples      = 100;
				CostHaircutPct  = 2.0;
				PocBucketTicks  = 20;      // 20 ticks = 5.00 pts on NQ — preserves v2 behavior there, portable elsewhere
				TargetSigma     = 0.0;     // 0 = anchor touch; >0 = entry + k*sigma toward anchor
				StopSigma       = 2.0;
				TimeoutMinutes  = 240;     // was 240 BARS on a 1-min chart; now honest minutes on any minute period
				ZoneOpacity     = 20;
				PollSeconds     = 120;

				UwTicker        = "NDX";
				FlashAlphaJsonPath = "net_gex";
				UwToken         = "";      // loaded from credentials.json — never a NinjaScriptProperty
				FlashAlphaUrl   = "";

				OfflineMode     = false;
				DebugPerf       = false;

				ShowDashboard   = true;
				DashboardPos    = Deep6DashCorner.TopRight;
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
				// NO execution series — live first-touch arrives via OnMarketData in Phase 3 (plan r2 #1).
			}
			else if (State == State.DataLoaded)
			{
				clock    = new ManualClock(null);
				failures = new FailureRegistry(5);
				calTimer = new PhaseTimer();

				// ---- hard gate: minute-type primary only (plan r2 Phase 0.3) ----
				if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute)
				{
					disabledWrongBarType = true;
					Print(string.Format(
						"Deep6PDv3 ERROR: primary series must be Minute-type (got {0}). Horizons are minute-denominated; " +
						"barsPerMinute is undefined on Tick/Range/Renko. Indicator disabled on this chart.",
						BarsPeriod.BarsPeriodType));
					return;
				}

				minutesPerBar        = Math.Max(1, BarsPeriod.Value);
				timeoutBarsEffective = Math.Max(1, (int)Math.Round(TimeoutMinutes / minutesPerBar));
				erLookbackBars       = Math.Max(10, (int)Math.Round(120.0 / minutesPerBar));
				hourBars             = Math.Max(1, (int)Math.Round(60.0 / minutesPerBar));
				spreadCapBars        = Math.Max(300, (int)Math.Round(1950.0 / minutesPerBar));
				sigmaHorizonBars     = Math.Max(1.0, 30.0 / minutesPerBar);
				ewmaBars             = Math.Max(2.0, 390.0 / minutesPerBar);

				lastHigh = new SwingPoint[TfCount + 1]; lastLow = new SwingPoint[TfCount + 1];
				ranges   = new DealingRange[TfCount];
				for (int i = 0; i < TfCount; i++) ranges[i] = new DealingRange();

				cells  = new PosteriorCell[TfCount, RegimeCount];
				for (int t = 0; t < TfCount; t++) for (int r = 0; r < RegimeCount; r++) cells[t, r] = new PosteriorCell();
				active = new LiveSignal[TfCount];
				for (int r = 0; r < RegimeCount; r++) pullbackByRegime[r] = new List<double>();

				sessionIterator = new SessionIterator(Bars);
				ewmaMean      = new Series<double>(this);
				realizedVol   = new Series<double>(this);
				anchorSeries  = new Series<double>(this);
				compositeBias = new Series<double>(this);

				// ---- v3 state directory; v2 files never touched (plan r2 Phase 0.1) ----
				string rootDir = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "Deep6PD");
				stateDir = Path.Combine(rootDir, "v3");
				Directory.CreateDirectory(stateDir);
				instrumentKey   = Instrument.MasterInstrument.Name + "_" + BarsPeriod.Value + "m";
				stateFile       = Path.Combine(stateDir, "state_" + instrumentKey + ".json");
				signalsFile     = Path.Combine(stateDir, "signals_v3_" + instrumentKey + ".csv");
				reportFile      = Path.Combine(stateDir, "calibration_report_" + instrumentKey + ".txt");
				credentialsFile = Path.Combine(rootDir, "credentials.json");
				statePersistence = new StatePersistence(PrintWrapper);

				// ---- secrets from credentials.json, never workspace XML (plan r2 Phase 0.4) ----
				CredentialsDto creds; string credErr;
				if (CredentialStore.TryLoad(credentialsFile, out creds, out credErr))
				{
					uwToken = creds.UwToken; flashAlphaUrl = creds.FlashAlphaUrl;
				}
				else
				{
					try { CredentialStore.WriteTemplateIfMissing(credentialsFile); }
					catch (Exception ex) { failures.Report("Credentials", ex.Message, clock.UtcWall); }
					Print("Deep6PDv3: " + credErr + " — GEX runs in LOCAL/OFF mode until credentials.json is filled in.");
				}
				// programmatic override path (tests / hosted use); the file wins when present
				if (uwToken.Length == 0 && !string.IsNullOrWhiteSpace(UwToken)) uwToken = UwToken;
				if (flashAlphaUrl.Length == 0 && !string.IsNullOrWhiteSpace(FlashAlphaUrl)) flashAlphaUrl = FlashAlphaUrl;

				LoadState();

				// ---- GEX provider selection (plan r2 Phase 0.12) ----
				if (OfflineMode)
				{
					string fixturePath = Path.Combine(stateDir, "gex_fixture_" + UwTicker + ".json");
					if (File.Exists(fixturePath))
					{
						offlineGexProvider = new FileFixtureGexProvider(fixturePath);
						Dictionary<DateTime, int> hist; string gexErr;
						if (offlineGexProvider.TryGetHistory(clock.UtcWall, out hist, out gexErr))
						{
							gexHistory = hist; gexHistoryLoaded = true;
							gexStatusText = string.Format("GEX: OFFLINE FIXTURE ({0} sessions)", hist.Count);
						}
						else
						{
							failures.Report("GexFixture", gexErr, clock.UtcWall);
							gexStatusText = "GEX: OFFLINE (fixture unreadable)";
						}
					}
					else
					{
						offlineGexProvider = new OffGexProvider();
						gexStatusText = "GEX: OFFLINE (no fixture — OFF)";
					}
				}
				else if (!string.IsNullOrWhiteSpace(uwToken))
				{
					gexHistoryTask = Task.Run(new Action(FetchUwGexHistory));    // daily history for regime-tagging calibration
				}

				memAfterDataLoaded = GC.GetTotalMemory(false);
			}
			else if (State == State.Transition)
			{
				if (disabledWrongBarType) return;

				// Give the optional UW history task one bounded chance to finish before calibration,
				// otherwise historical regime labels silently fall back to LOCAL mode.
				if (gexHistoryTask != null && !gexHistoryTask.IsCompleted)
				{
					try { gexHistoryTask.Wait(TimeSpan.FromSeconds(8)); }
					catch (Exception ex) { failures.Report("GexHistory", "wait failed: " + ex.Message, clock.UtcWall); }
				}
				RunCalibration();
				for (int i = 0; active != null && i < active.Length; i++) active[i] = null;
			}
			else if (State == State.Terminated)
			{
				SaveState();
				DisposeDeviceResources();
				DisposeDeviceIndependentResources();
			}
		}

		private void PrintWrapper(string s) { Print(s); }

		// SaveState guard (plan r2 Phase 0.8): an instance that has not completed calibration
		// this session and did not restore prior state must never write statistical state.
		private bool MayPersist { get { return !disabledWrongBarType && (calibrationCompletedThisSession || restoredState); } }
		#endregion

		#region Bar update
		protected override void OnBarUpdate()
		{
			if (disabledWrongBarType) return;

			int bip = BarsInProgress;

			if (bip >= 1 && bip <= TfCount)                  // HTF swing ranges
			{
				UpdateSwingsAndRange(bip);
				return;
			}
			if (bip != 0 || CurrentBar < 20) return;
			for (int i = 1; i <= TfCount; i++) if (CurrentBars[i] < 0) return;

			clock.SetBarTime(Time[0]);                       // ALL trading-logic time = exchange bar time

			// ---------------- session anchors ----------------
			DateTime sess = sessionIterator.GetTradingDayEndLocal(Time[0]).Date;
			if (sess != currentSessionDate)
			{
				// finalize previous day's IBS sample
				if (dayHi > dayLo && !double.IsNaN(prevDayClose) && !double.IsNaN(pendingIbs))
					ibsSamples.Add(new[] { pendingIbs, Math.Log(dayClose / prevDayClose) });
				if (dayHi > dayLo)
				{
					pendingIbs   = (dayClose - dayLo) / (dayHi - dayLo);
					prevDayClose = dayClose;
				}
				currentSessionDate = sess;
				sessVwapPv = sessVwapVol = 0;
				pocHist.Clear(); pocBestVol = -1; sessionPoc = double.NaN;
				dayHi = double.MinValue; dayLo = double.MaxValue;

				// OfflineMode: refresh the fixture reading once per session roll (no HTTP ever)
				if (OfflineMode && offlineGexProvider != null)
				{
					GexReading reading; string gerr;
					if (offlineGexProvider.TryGetLatest(clock.UtcWall, out reading, out gerr))
						gexSign = reading.Sign;
				}
			}
			double v = Math.Max(Volume[0], 1);
			sessVwapPv  += Close[0] * v; sessVwapVol += v;
			sessionVwap  = sessVwapPv / sessVwapVol;

			// configurable POC bucket (plan r2 Phase 0.2): PocBucketTicks * TickSize wide
			double bucketSize = Math.Max(TickSize, PocBucketTicks * TickSize);
			double bucket = Instrument.MasterInstrument.RoundToTickSize(Math.Round(Close[0] / bucketSize) * bucketSize);
			double bv; pocHist.TryGetValue(bucket, out bv); bv += v; pocHist[bucket] = bv;
			if (bv > pocBestVol) { pocBestVol = bv; sessionPoc = bucket; }
			dayHi = Math.Max(dayHi, High[0]); dayLo = Math.Min(dayLo, Low[0]); dayClose = Close[0];

			// ---------------- statistical series (minute-denominated horizons) ----------------
			double ewmaAlpha = 2.0 / (ewmaBars + 1);
			ewmaMean[0]    = CurrentBar < 1 ? Close[0] : ewmaMean[1] + ewmaAlpha * (Close[0] - ewmaMean[1]);
			double r1      = Math.Log(Close[0] / Close[1]);
			double prevVar = CurrentBar < 2 ? r1 * r1 : realizedVol[1] * realizedVol[1];
			realizedVol[0] = Math.Sqrt(prevVar + ewmaAlpha * (r1 * r1 - prevVar));
			double sigmaPx = Math.Max(realizedVol[0] * Close[0] * Math.Sqrt(sigmaHorizonBars), TickSize * 4); // ~30-min sigma in points

			anchorSeries[0] = anchorWinner == "EQ" && ranges[1].Valid ? ranges[1].Eq
			                : anchorWinner == "EWMA" ? ewmaMean[0]
			                : anchorWinner == "POC" && !double.IsNaN(sessionPoc) ? sessionPoc
			                : double.IsNaN(sessionVwap) ? ewmaMean[0] : sessionVwap;

			// half-life buffer (log spread to anchor)
			if (anchorSeries[0] > 0)
			{
				spreadBuf.Add(Math.Log(Close[0] / anchorSeries[0]));
				if (spreadBuf.Count > spreadCapBars) spreadBuf.RemoveAt(0);
				if (CurrentBar % hourBars == 0 && spreadBuf.Count > 300) halfLifeMin = EstimateHalfLife(spreadBuf);
			}

			// anchor horse-race samples during the historical pass
			if (State == State.Historical && CurrentBar > 400 && ranges[1].Valid && realizedVol[0] > 0)
			{
				double vol = Math.Max(realizedVol[0], 1e-6);
				icSamples.Add(new[]
				{
					-(Math.Log(Close[0] / Math.Max(sessionVwap, 1e-9))) / vol,
					-(Math.Log(Close[0] / Math.Max(ranges[1].Eq, 1e-9))) / vol,
					-(Math.Log(Close[0] / Math.Max(ewmaMean[0], 1e-9))) / vol,
					-(Math.Log(Close[0] / Math.Max(double.IsNaN(sessionPoc) ? sessionVwap : sessionPoc, 1e-9))) / vol,
					CurrentBar
				});
			}

			// ---------------- regime ----------------
			int regime = CurrentRegime();
			lastRegimeCode = regime;

			// ---------------- live GEX poll (wall-clock domain; OfflineMode never polls) ----------------
			if (State == State.Realtime && !OfflineMode && (clock.UtcWall - lastGexPoll).TotalSeconds > PollSeconds)
			{
				lastGexPoll = clock.UtcWall;
				Task.Run(new Action(PollLiveGex));
			}

			if (State == State.Realtime)
			{
				// ---------------- signal lifecycle ----------------
				for (int tf = 0; tf < TfCount; tf++)
				{
					DealingRange rg = ranges[tf];
					if (!rg.Valid || rg.Range <= 0) continue;
					double loc = (Close[0] - rg.Low) / rg.Range;

					LiveSignal s = active[tf];
					if (s != null)
					{
						// single source of truth for touch tests: Deep6PD.Core.SignalTape
						TapeResult tr = SignalTape.EvaluateBar(Open[0], High[0], Low[0], Close[0], s.IsLong, s.Target, s.Stop);
						bool timo = CurrentBar - s.BarOpened >= timeoutBarsEffective;
						if (tr.Exit != TapeExit.None || timo)
						{
							bool win = tr.Exit == TapeExit.Target;
							string how = tr.Exit == TapeExit.Stop ? "STOP" : tr.Exit == TapeExit.Target ? "TARGET" : "TIMEOUT";
							double exitPx = tr.Exit != TapeExit.None ? tr.ExitPrice : Close[0];
							ResolveSignal(tf, s, win, how, exitPx, tr.Ambiguous);
							active[tf] = null;
						}
					}
					else if (regime != 1)                       // FLIP/unknown → stand aside, no counting
					{
						bool discountTouch = loc <= 0.10;
						bool premiumTouch  = loc >= 0.90;
						if (discountTouch || premiumTouch)
						{
							bool isLong = regime == 2 ? premiumTouch : discountTouch; // REVERT fades; MOMO follows.
							double tgt  = TargetForSignal(rg, regime, isLong, Close[0], sigmaPx);
							var sig = new LiveSignal
							{
								SignalId = Guid.NewGuid().ToString("N"),
								Tf = tf, Regime = regime, IsLong = isLong,
								Entry = Close[0], Target = tgt,
								Stop  = Close[0] - (isLong ? 1 : -1) * StopSigma * sigmaPx,
								BarOpened = CurrentBar, Opened = Time[0]
							};
							active[tf] = sig;
							LogSignal("OPEN", tf, regime, sig, double.NaN, "", false, "");
						}
					}
				}
			}

			// ---------------- composite (regime-conditional; SHADOW predicate unified) ----------------
			double breakeven = Breakeven();
			double num = 0, den = 0;
			for (int tf = 0; tf < TfCount; tf++)
			{
				DealingRange rg = ranges[tf];
				if (!rg.Valid || rg.Range <= 0) continue;
				PosteriorCell c = cells[tf, regime];
				if (ShadowRule.IsShadow(c.N, MinSamples, c.Lo90, breakeven)) continue; // same rule as dashboard
				double pos = Math.Max(-1, Math.Min(1, (Close[0] - rg.Eq) / (0.5 * rg.Range)));
				double edge = c.Mean - 0.5;
				double w = Math.Max(0, edge) * 4;
				num += (regime == 2 ? pos : -pos) * w;
				den += w;
			}
			compositeBias[0] = den > 0 ? 100 * num / den * (regime == 1 ? 0 : 1) : 0;

			if (State == State.Realtime && MayPersist && (clock.UtcWall - lastPersist).TotalMinutes > 10)
			{
				lastPersist = clock.UtcWall; SaveState();
			}

			dashGeneration++;        // dashboard inputs change once per primary bar close
		}

		private double Breakeven() { return 0.5 + CostHaircutPct / 100.0; }

		private void UpdateSwingsAndRange(int bip)
		{
			int k = bip == 3 ? Math.Max(2, SwingStrength - 2) : SwingStrength;
			if (CurrentBars[bip] < 2 * k + 1) return;
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
				if (r.Valid && State == State.Historical && r.Range > 0)
				{
					double depth = r.BullLeg
						? (r.High - Math.Min(lastLow[bip].Price, r.High)) / r.Range
						: (Math.Max(lastHigh[bip].Price, r.Low) - r.Low) / r.Range;
					if (depth > 0 && depth < 2) { retraceDepths.Add(depth); pullbackByRegime[CurrentRegime()].Add(depth); }
				}
				r.Valid = true; r.High = lastHigh[bip].Price; r.Low = lastLow[bip].Price;
				r.AnchorTime = lastHigh[bip].Time < lastLow[bip].Time ? lastHigh[bip].Time : lastLow[bip].Time;
				r.BullLeg = lastHigh[bip].Time > lastLow[bip].Time;
			}
			// TrackBreak stub deleted (plan r2 Phase 0.6)
		}
		#endregion

		#region Regime
		private int CurrentRegime()
		{
			int sign = 0;
			if (State == State.Historical)
			{
				DateTime d = Time[0].Date;
				if (gexHistoryLoaded && gexHistory.ContainsKey(d)) sign = gexHistory[d];
			}
			else sign = gexSign;

			if (sign == 0)
			{
				// LOCAL fallback: trend-efficiency proxy over ~120 minutes — strong directional + high vol = MOMO
				if (CurrentBar < erLookbackBars) return 1;
				int lb = Math.Min(erLookbackBars, CurrentBar);
				double net = Math.Abs(Close[0] - Close[lb]);
				double path = 0;
				for (int i = 1; i <= lb; i++) path += Math.Abs(Close[i - 1] - Close[i]);
				double er = path > 0 ? net / path : 0;
				return er > 0.35 ? 2 : 0;
			}
			return sign > 0 ? 0 : 2;
		}
		#endregion

		#region GEX REST
		private void PollLiveGex()
		{
			// hard-fail guard (plan r2 Phase 0.12): Playback/offline must never reach HTTP
			if (OfflineMode)
			{
				failures.Report("GexHttp", "HTTP poll attempted while OfflineMode=true — blocked", DateTime.UtcNow);
				return;
			}
			try
			{
				if (!string.IsNullOrWhiteSpace(flashAlphaUrl))
				{
					string body = http.GetStringAsync(flashAlphaUrl).Result;
					JToken tok = JToken.Parse(body).SelectToken(FlashAlphaJsonPath);
					if (tok != null)
					{
						double g = tok.Value<double>();
						gexSign = g > 0 ? 1 : g < 0 ? -1 : 0;
						gexMode = GexMode.Live;
						gexStatusText = string.Format("GEX {0} (FlashAlpha)", gexSign > 0 ? "+" : gexSign < 0 ? "−" : "0");
						return;
					}
				}
				if (!string.IsNullOrWhiteSpace(uwToken))
				{
					var req = new HttpRequestMessage(HttpMethod.Get,
						string.Format("https://api.unusualwhales.com/api/stock/{0}/greek-exposure", UwTicker));
					req.Headers.Add("Authorization", "Bearer " + uwToken);
					req.Headers.Add("Accept", "application/json");
					string body = http.SendAsync(req).Result.Content.ReadAsStringAsync().Result;
					JArray data = (JArray)JObject.Parse(body)["data"];
					if (data != null && data.Count > 0)
					{
						JToken last = data.OrderBy(x => (string)x["date"]).Last();
						double net = last.Value<double>("call_gamma") + last.Value<double>("put_gamma");
						gexSign = net > 0 ? 1 : -1;
						gexMode = GexMode.Live;
						gexStatusText = string.Format("GEX {0} ({1} UW)", gexSign > 0 ? "+" : "−", UwTicker);
						return;
					}
				}
				gexMode = GexMode.Local;
				gexStatusText = "GEX: LOCAL proxy (no API configured)";
			}
			catch (Exception ex)
			{
				gexMode = GexMode.Local;
				gexStatusText = "GEX: LOCAL (fetch failed)";
				if (failures.Report("GexHttp", ex.Message, DateTime.UtcNow))
					Print("Deep6PDv3 GEX poll error: " + ex.Message);
			}
		}

		private void FetchUwGexHistory()
		{
			if (OfflineMode)
			{
				failures.Report("GexHttp", "history fetch attempted while OfflineMode=true — blocked", DateTime.UtcNow);
				return;
			}
			try
			{
				var req = new HttpRequestMessage(HttpMethod.Get,
					string.Format("https://api.unusualwhales.com/api/stock/{0}/greek-exposure", UwTicker));
				req.Headers.Add("Authorization", "Bearer " + uwToken);
				req.Headers.Add("Accept", "application/json");
				string body = http.SendAsync(req).Result.Content.ReadAsStringAsync().Result;
				JArray data = (JArray)JObject.Parse(body)["data"];
				var map = new Dictionary<DateTime, int>();
				foreach (JToken r in data)
				{
					double net = r.Value<double>("call_gamma") + r.Value<double>("put_gamma");
					map[DateTime.ParseExact((string)r["date"], "yyyy-MM-dd", CultureInfo.InvariantCulture)] = net > 0 ? 1 : -1;
				}
				gexHistory = map; gexHistoryLoaded = true;
				Print(string.Format("Deep6PDv3: UW GEX history loaded — {0} sessions for regime tagging.", map.Count));
			}
			catch (Exception ex)
			{
				if (failures.Report("GexHistory", ex.Message, DateTime.UtcNow))
					Print("Deep6PDv3: UW GEX history failed (" + ex.Message + ") — calibration uses LOCAL regime proxy.");
			}
		}
		#endregion

		#region Calibration (runs at Historical → Realtime transition)
		private void RunCalibration()
		{
			if (calibrated || CurrentBar < 500) { calibrated = true; return; }
			calibrated = true;
			var rep = new List<string>
			{
				"DEEP6 PD v3 (Phase 0) — IN-PLATFORM CALIBRATION  " + clock.ExchangeBarTime.ToString("o", CultureInfo.InvariantCulture),
				new string('=', 64)
			};

			// ---- measurement harness (plan r2 Phase 0.13): copy bars to local arrays ONCE ----
			calTimer.Start("array copy");
			int n = CurrentBar + 1;
			double[] op = new double[n], hi = new double[n], lo = new double[n], cl = new double[n], rv = new double[n];
			DateTime[] tm = new DateTime[n];
			for (int idx = 0; idx < n; idx++)
			{
				op[idx] = Open.GetValueAt(idx);  hi[idx] = High.GetValueAt(idx);
				lo[idx] = Low.GetValueAt(idx);   cl[idx] = Close.GetValueAt(idx);
				rv[idx] = realizedVol.IsValidDataPointAt(idx) ? realizedVol.GetValueAt(idx) : 0.0006;
				tm[idx] = Time.GetValueAt(idx);
			}

			// ---- G1: retracement distribution vs 61.8–79 claim ----
			calTimer.Start("bands");
			if (retraceDepths.Count > 100)
			{
				double[] d = retraceDepths.Where(x => x > 0.1 && x < 1.5).ToArray();
				double inOte  = d.Count(x => x >= 0.618 && x <= 0.79) / (double)d.Length;
				double expect = (0.79 - 0.618) / 1.4;
				rep.Add(string.Format("G1 retracements: n={0}  mass(61.8–79)={1:P1}  uniform-expect={2:P1}  ratio={3:F2}  → {4}",
					d.Length, inOte, expect, inOte / expect, inOte / expect > 1.15 ? "fib band kept" : "fib band REJECTED → empirical bands"));
			}
			double[] pooled = retraceDepths.Where(x => x > 0 && x < 1.2).OrderBy(x => x).ToArray();
			for (int r = 0; r < RegimeCount; r++)
			{
				double[] src = pullbackByRegime[r].Count > 60 ? pullbackByRegime[r].OrderBy(x => x).ToArray() : pooled;
				if (src.Length > 20)
				{
					bandQ60[r] = src[(int)(0.60 * (src.Length - 1))];
					bandQ85[r] = src[(int)(0.85 * (src.Length - 1))];
					rep.Add(string.Format("   band[{0}]: q60={1:P0} q85={2:P0} depth (n={3})", RegimeTags[r], bandQ60[r], bandQ85[r], src.Length));
				}
				else { bandQ60[r] = 0.55; bandQ85[r] = 0.74; }
			}

			// ---- G5: anchor horse race (sign agreement on ~60-minute forward) ----
			calTimer.Start("anchor race");
			int fwdBars = Math.Max(1, (int)Math.Round(60.0 / minutesPerBar));
			if (icSamples.Count > 2000)
			{
				int cnt = 0; double aV = 0, aE = 0, aW = 0, aP = 0;
				foreach (double[] s in icSamples)
				{
					int bar = (int)s[4];
					if (bar + fwdBars > n - 1) continue;
					double fwd = Math.Log(cl[bar + fwdBars] / cl[bar]);
					cnt++;
					aV += Math.Sign(s[0]) == Math.Sign(fwd) ? 1 : 0;
					aE += Math.Sign(s[1]) == Math.Sign(fwd) ? 1 : 0;
					aW += Math.Sign(s[2]) == Math.Sign(fwd) ? 1 : 0;
					aP += Math.Sign(s[3]) == Math.Sign(fwd) ? 1 : 0;
				}
				if (cnt > 500)
				{
					anchorIcVwap = aV / cnt; anchorIcEq = aE / cnt; anchorIcEwma = aW / cnt; anchorIcPoc = aP / cnt;
					anchorWinner = anchorIcVwap >= anchorIcEq && anchorIcVwap >= anchorIcEwma && anchorIcVwap >= anchorIcPoc ? "VWAP"
					             : anchorIcEq >= anchorIcEwma && anchorIcEq >= anchorIcPoc ? "EQ"
					             : anchorIcEwma >= anchorIcPoc ? "EWMA" : "POC";
					rep.Add(string.Format("G5 anchor race (sign-hit on {0}-bar fwd, n={1}): VWAP={2:P1} EQ={3:P1} EWMA={4:P1} POC={5:P1} → winner {6}",
						fwdBars, cnt, anchorIcVwap, anchorIcEq, anchorIcEwma, anchorIcPoc, anchorWinner));
				}
			}

			// ---- G3: IBS quintiles ----
			calTimer.Start("ibs");
			if (ibsSamples.Count > 200)
			{
				var sorted = ibsSamples.OrderBy(x => x[0]).ToList();
				int q = sorted.Count / 5;
				double lo5 = sorted.Take(q).Average(x => x[1]) * 1e4;
				double hi5 = sorted.Skip(4 * q).Average(x => x[1]) * 1e4;
				rep.Add(string.Format("G3 IBS: n={0} days  Q1 next-day={1:F1}bps  Q5={2:F1}bps  spread={3:F1}bps  → {4}",
					sorted.Count, lo5, hi5, lo5 - hi5, lo5 - hi5 > 0 ? "reversion confirmed" : "NO IBS effect in this sample"));
			}

			// ---- G2/G4 seed: replay lifecycle over OOS half with regime tags ----
			calTimer.Start("seed replay");
			if (!restoredState)
				SeedPosteriorsFromHistory(rep, op, hi, lo, cl, rv, tm);
			else
				rep.Add("G2/G4 OOS seed skipped because posterior state was restored; delete the v3 state file to force a fresh seed.");
			calTimer.Stop();

			// ---- measurement report (plan r2 Phase 0.13: numbers on day one) ----
			long memNow = GC.GetTotalMemory(false);
			rep.Add(new string('-', 64));
			rep.AddRange(calTimer.ReportLines("CALIBRATION TIMING (budget: < 3000 ms total)"));
			if (calTimer.TotalMs >= 3000)
				rep.Add("   *** OVER BUDGET — investigate before adding phases ***");
			rep.Add(string.Format(CultureInfo.InvariantCulture,
				"MEASUREMENT: primary bars={0}  H4 bars={1}  Daily bars={2}  Weekly bars={3}  icSamples={4}",
				CurrentBar + 1, CurrentBars[1] + 1, CurrentBars[2] + 1, CurrentBars[3] + 1, icSamples.Count));
			rep.Add(string.Format(CultureInfo.InvariantCulture,
				"MEASUREMENT: managed memory now {0:F1} MB (delta vs DataLoaded {1:+0.0;-0.0} MB)",
				memNow / 1048576.0, (memNow - memAfterDataLoaded) / 1048576.0));

			rep.Add(new string('=', 64));
			rep.Add("Cells below MinSamples or below breakeven render SHADOW (single predicate, Core.ShadowRule).");
			rep.Add("REMINDER: this is chronological IS/OOS, not CPCV — see plan r2 §8.");
			foreach (string line in rep) Print(line);
			try { File.WriteAllLines(reportFile, rep); }
			catch (Exception ex) { failures.Report("Report", ex.Message, clock.UtcWall); }

			// ---- release calibration buffers (plan r2 Phase 0.9) ----
			icSamples.Clear();      icSamples.TrimExcess();
			retraceDepths.Clear();  retraceDepths.TrimExcess();
			ibsSamples.Clear();     ibsSamples.TrimExcess();
			for (int r = 0; r < RegimeCount; r++) { pullbackByRegime[r].Clear(); pullbackByRegime[r].TrimExcess(); }

			calibrationCompletedThisSession = true;
			dashGeneration++;
		}

		private void SeedPosteriorsFromHistory(List<string> rep,
			double[] op, double[] hi, double[] lo, double[] cl, double[] rv, DateTime[] tm)
		{
			// Replays the live lifecycle over the RECENT half of the chart history on local
			// array copies (plan r2 #17 — no NT series indexer churn). Range states are
			// reconstructed from primary-series pivots (k = SwingStrength*3/9/21 proxies the
			// H4/Daily/Weekly structure) — coarse but identical logic to live, and only the
			// recent-half counts seed the posteriors.
			int n = cl.Length;
			int half = n / 2;
			int[] kfac = { 3, 9, 21 };
			double sqrtSigmaBars = Math.Sqrt(sigmaHorizonBars);
			int seeded = 0, wins = 0;
			for (int tf = 0; tf < TfCount; tf++)
			{
				int k = SwingStrength * kfac[tf];
				double rngHi = double.NaN, rngLo = double.NaN;
				int dir = 0; double tgt = 0, stp = 0; int openedIdx = -1; int regAt = 0;
				double lastH = double.NaN, lastL = double.NaN;
				for (int idx = half; idx <= n - 2; idx++)
				{
					if (idx - k >= 0 && idx + k <= n - 2)
					{
						bool isH = true, isL = true;
						for (int j = 1; j <= k && (isH || isL); j++)
						{
							if (hi[idx - j] > hi[idx] || hi[idx + j] > hi[idx]) isH = false;
							if (lo[idx - j] < lo[idx] || lo[idx + j] < lo[idx]) isL = false;
						}
						if (isH) lastH = hi[idx];
						if (isL) lastL = lo[idx];
						if (!double.IsNaN(lastH) && !double.IsNaN(lastL) && lastH > lastL) { rngHi = lastH; rngLo = lastL; }
					}
					if (double.IsNaN(rngHi) || rngHi <= rngLo) continue;
					double loc = (cl[idx] - rngLo) / (rngHi - rngLo);
					double sig = Math.Max(rv[idx], 1e-6) * cl[idx] * sqrtSigmaBars;

					if (openedIdx < 0 && (loc <= 0.10 || loc >= 0.90))
					{
						bool discountTouch = loc <= 0.10;
						bool premiumTouch  = loc >= 0.90;
						regAt = HistRegimeAt(idx, cl, tm);
						if (regAt == 1) continue;
						dir = regAt == 2 ? (premiumTouch ? 1 : -1) : (discountTouch ? 1 : -1);
						double entry = cl[idx];
						tgt = TargetSigma > 0 ? entry + dir * TargetSigma * sig
						                    : regAt == 2 ? (dir > 0 ? rngHi : rngLo) : rngLo + 0.5 * (rngHi - rngLo);
						stp = entry - dir * StopSigma * sig;
						openedIdx = idx;
					}
					else if (openedIdx >= 0)
					{
						TapeResult tr = SignalTape.EvaluateBar(op[idx], hi[idx], lo[idx], cl[idx], dir > 0, tgt, stp);
						bool timo = idx - openedIdx >= timeoutBarsEffective;
						if (tr.Exit != TapeExit.None || timo)
						{
							bool win = tr.Exit == TapeExit.Target;
							cells[tf, regAt].Alpha += win ? 1 : 0;
							cells[tf, regAt].Beta  += win ? 0 : 1;
							seeded++; wins += win ? 1 : 0;
							openedIdx = -1;
						}
					}
				}
			}
			rep.Add(string.Format("G2/G4 OOS seed: {0} historical signals resolved, raw hit {1:P1}; per-cell posteriors updated.",
				seeded, seeded > 0 ? wins / (double)seeded : 0));
		}

		private int HistRegimeAt(int idx, double[] cl, DateTime[] tm)
		{
			DateTime d = tm[idx].Date;
			if (gexHistoryLoaded && gexHistory.ContainsKey(d)) return gexHistory[d] > 0 ? 0 : 2;
			if (idx < erLookbackBars) return 1;
			int lb = Math.Min(erLookbackBars, idx);
			double net = Math.Abs(cl[idx] - cl[idx - lb]);
			double path = 0;
			for (int i = idx - lb + 1; i <= idx; i++) path += Math.Abs(cl[i] - cl[i - 1]);
			double er = path > 0 ? net / path : 0;
			return er > 0.35 ? 2 : 0;
		}

		private double EstimateHalfLife(List<double> s)
		{
			int n = s.Count - 1;
			double mx = 0, my = 0;
			for (int i = 0; i < n; i++) { mx += s[i]; my += s[i + 1] - s[i]; }
			mx /= n; my /= n;
			double cov = 0, var = 0;
			for (int i = 0; i < n; i++) { cov += (s[i] - mx) * (s[i + 1] - s[i] - my); var += (s[i] - mx) * (s[i] - mx); }
			if (var <= 0) return double.NaN;
			double kappa = -(cov / var);
			return kappa > 1e-6 ? Math.Log(2) / kappa * minutesPerBar : double.NaN;
		}
		#endregion

		#region Lifecycle helpers / persistence / telemetry
		private double TargetForSignal(DealingRange rg, int regime, bool isLong, double entry, double sigmaPx)
		{
			if (TargetSigma > 0)
				return entry + (isLong ? 1 : -1) * TargetSigma * sigmaPx;
			return regime == 2 ? (isLong ? rg.High : rg.Low) : rg.Eq;
		}

		private void ResolveSignal(int tf, LiveSignal s, bool win, string how, double exitPrice, bool ambiguous)
		{
			PosteriorCell c = cells[tf, s.Regime];
			c.Alpha += win ? 1 : 0; c.Beta += win ? 0 : 1; c.LiveN++;
			LogSignal("CLOSE", tf, s.Regime, s, exitPrice, how, ambiguous, win ? "WIN" : "LOSS");
			if (State == State.Realtime)
			{
				Alert("d6v3_" + tf + "_" + CurrentBar, Priority.Medium,
					string.Format("DEEP6 PDv3: {0} {1} cell resolved {2} — P(edge) now {3:P0} [{4:P0}–{5:P0}] n={6}",
						TfTags[tf], RegimeTags[s.Regime], how, c.Mean, c.Lo90, c.Hi90, (int)c.N),
					NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert2.wav", 10, Media.Brushes.Black, Media.Brushes.White);
				if (MayPersist) SaveState();   // persist-on-resolve bounds reconnect loss to zero resolved samples
			}
		}

		private void LogSignal(string evt, int tf, int regime, LiveSignal s, double exitPrice, string exitReason, bool ambiguous, string note)
		{
			try
			{
				bool head = !File.Exists(signalsFile);
				using (var w = new StreamWriter(signalsFile, true))
				{
					if (head)
					{
						w.WriteLine(SignalsCsvSchema.CommentLine);
						w.WriteLine(SignalsCsvSchema.Header);
					}
					w.WriteLine(SignalsCsvSchema.FormatRow(
						s.SignalId, clock.UtcWall, clock.ExchangeBarTime, CodeVersion,
						Instrument.MasterInstrument.Name, BarsPeriod.Value + "m",
						evt, TfTags[tf], RegimeTags[regime], s.IsLong ? "L" : "S",
						s.Entry, s.Target, s.Stop, exitPrice, exitReason, ambiguous, note));
					w.Flush();
				}
			}
			catch (Exception ex)
			{
				if (failures.Report("Telemetry", ex.Message, clock.UtcWall))
					Print("Deep6PDv3 signals csv write failed: " + ex.Message);
			}
		}

		private void SaveState()
		{
			if (!MayPersist || statePersistence == null) return;   // plan r2 Phase 0.8
			var dto = new PersistedStateDto
			{
				CodeVersion = CodeVersion,
				CalibratedThroughUtc = (clock != null ? clock.UtcWall : DateTime.UtcNow).ToString("o", CultureInfo.InvariantCulture)
			};
			for (int t = 0; t < TfCount; t++)
				for (int r = 0; r < RegimeCount; r++)
					dto.Cells[TfTags[t] + "|" + RegimeTags[r]] = new[] { cells[t, r].Alpha, cells[t, r].Beta, (double)cells[t, r].LiveN };
			string err;
			if (!statePersistence.TrySave(stateFile, dto, out err))
				failures.Report("StateSave", err, clock != null ? clock.UtcWall : DateTime.UtcNow);
		}

		private void LoadState()
		{
			PersistedStateDto dto; string err;
			if (!statePersistence.TryLoad(stateFile, out dto, out err))
			{
				if (err != "no state file")
					Print("Deep6PDv3: state load failed (" + err + ") — starting fresh; bad file left in place for inspection.");
				return;
			}
			for (int t = 0; t < TfCount; t++)
				for (int r = 0; r < RegimeCount; r++)
				{
					double[] v;
					if (dto.Cells.TryGetValue(TfTags[t] + "|" + RegimeTags[r], out v) && v.Length >= 3)
					{ cells[t, r].Alpha = v[0]; cells[t, r].Beta = v[1]; cells[t, r].LiveN = (int)v[2]; }
				}
			restoredState = true;
			Print("Deep6PDv3: posterior state restored from " + stateFile);
		}
		#endregion

		#region Rendering
		public override void OnRenderTargetChanged()
		{
			// dispose-on-null + recreate-on-non-null; idempotent across repeated cycles (plan r2 Phase 0.7)
			DisposeDeviceResources();
			if (RenderTarget == null) return;

			brTxt      = MakeSolid(TextBrush, 1f);
			brDim      = MakeSolid(TextBrush, 0.5f);
			brPrem     = MakeSolid(PremiumBrush, 0.85f);
			brDisc     = MakeSolid(DiscountBrush, 0.85f);
			brEq       = MakeSolid(EqBrush, 0.95f);
			brBand     = MakeSolid(BandBrush, 0.9f);
			brAnchor   = MakeSolid(AnchorBrush, 0.95f);
			brBandFill = MakeSolid(BandBrush, 1f);                  // opacity mutated per frame
			brBg       = new D2D.SolidColorBrush(RenderTarget, new Color4(0.055f, 0.065f, 0.095f, 0.93f));
			brEdge     = new D2D.SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 0.10f));
			brTrack    = new D2D.SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 0.08f));
			deviceBrushCreates += 11;

			// gradient stops per palette, created once per render target; brush opacity carries zone alpha
			gscPrem = new D2D.GradientStopCollection(RenderTarget, new[]
			{
				new D2D.GradientStop { Position = 0f, Color = C4(PremiumBrush, 1f) },
				new D2D.GradientStop { Position = 1f, Color = C4(PremiumBrush, 0.03f) }
			});
			gscDisc = new D2D.GradientStopCollection(RenderTarget, new[]
			{
				new D2D.GradientStop { Position = 0f, Color = C4(DiscountBrush, 0.03f) },
				new D2D.GradientStop { Position = 1f, Color = C4(DiscountBrush, 1f) }
			});
			lgbPrem = new D2D.LinearGradientBrush(RenderTarget,
				new D2D.LinearGradientBrushProperties { StartPoint = new Vector2(0, 0), EndPoint = new Vector2(0, 1) }, gscPrem);
			lgbDisc = new D2D.LinearGradientBrush(RenderTarget,
				new D2D.LinearGradientBrushProperties { StartPoint = new Vector2(0, 0), EndPoint = new Vector2(0, 1) }, gscDisc);
		}

		private D2D.SolidColorBrush MakeSolid(Media.Brush b, float a)
		{
			return new D2D.SolidColorBrush(RenderTarget, C4(b, a));
		}

		private void DisposeDeviceResources()
		{
			IDisposable[] all =
			{
				brTxt, brDim, brPrem, brDisc, brEq, brBand, brAnchor, brBg, brEdge, brTrack, brBandFill,
				lgbPrem, lgbDisc, gscPrem, gscDisc
			};
			foreach (IDisposable d in all) if (d != null) d.Dispose();
			brTxt = brDim = brPrem = brDisc = brEq = brBand = brAnchor = brBg = brEdge = brTrack = brBandFill = null;
			lgbPrem = lgbDisc = null; gscPrem = gscDisc = null;
			DisposeLayoutCache();
		}

		private void DisposeDeviceIndependentResources()
		{
			if (fmtSmall != null)   { fmtSmall.Dispose();   fmtSmall = null; }
			if (fmtHead != null)    { fmtHead.Dispose();    fmtHead = null; }
			if (strokeDash != null) { strokeDash.Dispose(); strokeDash = null; }
			if (strokeDot != null)  { strokeDot.Dispose();  strokeDot = null; }
		}

		private void DisposeLayoutCache()
		{
			foreach (DW.TextLayout tl in layoutCache.Values) tl.Dispose();
			layoutCache.Clear();
			layoutCacheGeneration = -1;
		}

		private void EnsureDeviceIndependentResources()
		{
			if (fmtSmall == null)
				fmtSmall = new DW.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", DW.FontWeight.Normal, DW.FontStyle.Normal, 10f);
			if (fmtHead == null)
				fmtHead = new DW.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", DW.FontWeight.Bold, DW.FontStyle.Normal, 11.5f);
			if (strokeDash == null)
				strokeDash = new D2D.StrokeStyle(NinjaTrader.Core.Globals.D2DFactory, new D2D.StrokeStyleProperties { DashStyle = D2D.DashStyle.Dash });
			if (strokeDot == null)
				strokeDot = new D2D.StrokeStyle(NinjaTrader.Core.Globals.D2DFactory, new D2D.StrokeStyleProperties { DashStyle = D2D.DashStyle.Dot });
		}

		/// <summary>
		/// TextLayouts cached keyed to the dashboard generation: rebuilt once per new bar,
		/// reused across every mouse-move frame (plan r2 Phase 0.7).
		/// </summary>
		private DW.TextLayout GetLayout(string key, string text, DW.TextFormat fmt, float w, float h)
		{
			if (layoutCacheGeneration != dashGeneration)
			{
				DisposeLayoutCache();
				layoutCacheGeneration = dashGeneration;
				framesAtGeneration = 0;
			}
			DW.TextLayout lay;
			if (!layoutCache.TryGetValue(key, out lay))
			{
				lay = new DW.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, fmt, w, h);
				layoutCache[key] = lay;
				layoutCreatesThisFrame++;
			}
			return lay;
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (disabledWrongBarType || Bars == null || ChartBars == null || RenderTarget == null || IsInHitTest) return;
			if (brTxt == null) return;            // device resources not built yet

			if (DebugPerf) renderWatch.Restart();
			EnsureDeviceIndependentResources();
			layoutCreatesThisFrame = 0;

			float pl = ChartPanel.X, pr = ChartPanel.X + ChartPanel.W, pt = ChartPanel.Y, pb = ChartPanel.Y + ChartPanel.H;
			int regime = CurrentBar > 0 ? lastRegimeCode : 1;
			float mute = regime == 2 ? 0.45f : regime == 1 ? 0.3f : 1f;
			float zoneA = Math.Max(0.02f, Math.Min(0.6f, ZoneOpacity / 100f)) * mute;

			// zones + EQ + empirical band per TF
			for (int tf = 0; tf < TfCount; tf++)
			{
				DealingRange r = ranges[tf];
				if (!r.Valid || r.Range <= 0) continue;
				float x1 = chartControl.GetXByTime(r.AnchorTime); if (x1 < pl || float.IsNaN(x1)) x1 = pl;
				float yH = chartScale.GetYByValue(r.High), yL = chartScale.GetYByValue(r.Low), yE = chartScale.GetYByValue(r.Eq);

				lgbPrem.StartPoint = new Vector2(x1, yH); lgbPrem.EndPoint = new Vector2(x1, yE);
				lgbPrem.Opacity = zoneA;
				RenderTarget.FillRectangle(new RectangleF(x1, yH, pr - x1, yE - yH), lgbPrem);
				lgbDisc.StartPoint = new Vector2(x1, yE); lgbDisc.EndPoint = new Vector2(x1, yL);
				lgbDisc.Opacity = zoneA;
				RenderTarget.FillRectangle(new RectangleF(x1, yE, pr - x1, yL - yE), lgbDisc);

				RenderTarget.DrawLine(new Vector2(x1, yH), new Vector2(pr, yH), brPrem, 1.4f);
				RenderTarget.DrawLine(new Vector2(x1, yL), new Vector2(pr, yL), brDisc, 1.4f);
				RenderTarget.DrawLine(new Vector2(x1, yE), new Vector2(pr, yE), brEq, 1.5f, strokeDash);

				double q60 = bandQ60[regime] > 0 ? bandQ60[regime] : 0.55, q85 = bandQ85[regime] > 0 ? bandQ85[regime] : 0.74;
				double bTop = r.BullLeg ? r.High - q60 * r.Range : r.Low + q85 * r.Range;
				double bBot = r.BullLeg ? r.High - q85 * r.Range : r.Low + q60 * r.Range;
				float yT = chartScale.GetYByValue(Math.Max(bTop, bBot)), yB2 = chartScale.GetYByValue(Math.Min(bTop, bBot));
				brBandFill.Opacity = Math.Min(0.4f, zoneA + 0.08f);
				RenderTarget.FillRectangle(new RectangleF(x1, yT, pr - x1, yB2 - yT), brBandFill);
				RenderTarget.DrawLine(new Vector2(x1, yT), new Vector2(pr, yT), brBand, 1f, strokeDot);
				RenderTarget.DrawLine(new Vector2(x1, yB2), new Vector2(pr, yB2), brBand, 1f, strokeDot);

				if (ShowLabels)
				{
					TagR("tag." + tf + ".hi", string.Format("{0} HI {1:F2}", TfTags[tf], r.High), pr, yH, fmtSmall, brPrem);
					TagR("tag." + tf + ".eq", string.Format("{0} EQ {1:F2}", TfTags[tf], r.Eq), pr, yE, fmtSmall, brEq);
					TagR("tag." + tf + ".lo", string.Format("{0} LO {1:F2}", TfTags[tf], r.Low), pr, yL, fmtSmall, brDisc);
					TagR("tag." + tf + ".band", string.Format("EMP BAND q60–q85 [{0}]", RegimeTags[regime]), pr, yT, fmtSmall, brBand);
				}
			}

			// anchor line (winner) across visible bars — absolute index access only
			if (CurrentBar > 1)
			{
				int from = Math.Max(ChartBars.FromIndex, 1);
				float prevX = float.NaN, prevY = float.NaN;
				for (int idx = from; idx <= ChartBars.ToIndex; idx++)
				{
					if (!anchorSeries.IsValidDataPointAt(idx)) continue;
					float xx = chartControl.GetXByBarIndex(ChartBars, idx);
					float yy = chartScale.GetYByValue(anchorSeries.GetValueAt(idx));
					if (!float.IsNaN(prevX)) RenderTarget.DrawLine(new Vector2(prevX, prevY), new Vector2(xx, yy), brAnchor, 1.6f);
					prevX = xx; prevY = yy;
				}
				if (ShowLabels && anchorSeries.IsValidDataPointAt(CurrentBar))
					TagR("tag.anchor", string.Format("ANCHOR {0} {1:F2} (race winner)", anchorWinner, anchorSeries.GetValueAt(CurrentBar)),
						pr, chartScale.GetYByValue(anchorSeries.GetValueAt(CurrentBar)), fmtSmall, brAnchor);
			}

			if (ShowDashboard) Dashboard(regime, pl, pr, pt, pb);

			// allocation discipline (Phase 0 acceptance): after the second frame at one
			// generation, nothing new may be created
			framesAtGeneration++;
			if (framesAtGeneration > 2 && layoutCreatesThisFrame > 0)
			{
				if (failures.Report("RenderAlloc",
					layoutCreatesThisFrame + " TextLayouts created on frame " + framesAtGeneration + " of one generation",
					DateTime.UtcNow) && DebugPerf)
					Print("Deep6PDv3 RENDER ALLOC WARNING: layouts created after second frame of a generation.");
			}

			if (DebugPerf)
			{
				renderWatch.Stop();
				renderMsAccum += renderWatch.Elapsed.TotalMilliseconds; renderFrames++;
				if (renderFrames >= 300)
				{
					Print(string.Format(CultureInfo.InvariantCulture,
						"Deep6PDv3 render: {0} frames avg {1:F2} ms, device brush creates total {2}",
						renderFrames, renderMsAccum / renderFrames, deviceBrushCreates));
					renderMsAccum = 0; renderFrames = 0;
				}
			}
		}

		private void Dashboard(int regime, float pl, float pr, float pt, float pb)
		{
			float w = 318f, rowH = 19f, h = 30f + 18f + 16f + TfCount * rowH + 56f;
			float x = DashboardPos == Deep6DashCorner.TopLeft || DashboardPos == Deep6DashCorner.BottomLeft ? pl + 12f : pr - w - 12f;
			float y = DashboardPos == Deep6DashCorner.BottomLeft || DashboardPos == Deep6DashCorner.BottomRight ? pb - h - 12f : pt + 12f;

			var rr = new D2D.RoundedRectangle { Rect = new RectangleF(x, y, w, h), RadiusX = 7f, RadiusY = 7f };
			RenderTarget.FillRoundedRectangle(rr, brBg);
			RenderTarget.DrawRoundedRectangle(rr, brEdge, 1f);

			Cell("d.title", "DEEP6 PREMIUM / DISCOUNT v3 [P0]", x + 10, y + 6, w - 20, fmtHead, brTxt);
			string verdict = regime == 0 ? "MEAN-REVERT REGIME" : regime == 2 ? "MOMENTUM — PD READS INVERT" : "STAND ASIDE";
			D2D.SolidColorBrush vb = regime == 0 ? brDisc : regime == 2 ? brPrem : brEq;
			Cell("d.status", gexStatusText + "  ·  " + verdict, x + 10, y + 26, w - 20, fmtSmall, vb);

			float ry = y + 46;
			Cell("d.h.tf", "TF", x + 10, ry, 26, fmtSmall, brDim); Cell("d.h.ci", "P(edge) 90% CI", x + 40, ry, 110, fmtSmall, brDim);
			Cell("d.h.n", "n", x + 152, ry, 50, fmtSmall, brDim); Cell("d.h.hl", "t½", x + 206, ry, 44, fmtSmall, brDim); Cell("d.h.act", "ACTION", x + 254, ry, 60, fmtSmall, brDim);
			ry += 16;
			double breakeven = Breakeven();
			for (int tf = 0; tf < TfCount; tf++)
			{
				PosteriorCell c = cells[tf, regime];
				bool shadow = ShadowRule.IsShadow(c.N, MinSamples, c.Lo90, breakeven);   // SAME predicate as composite
				string act = regime == 1 ? "—" : shadow ? "SHADOW" : regime == 0 ? "FADE" : "FOLLOW";
				D2D.SolidColorBrush ab = shadow || regime == 1 ? brDim : regime == 0 ? brDisc : brPrem;
				Cell("d.r" + tf + ".tf", TfTags[tf], x + 10, ry, 26, fmtSmall, brTxt);
				Cell("d.r" + tf + ".ci", c.N < 5 ? "collecting…" : string.Format("{0:P0} [{1:P0}–{2:P0}]", c.Mean, c.Lo90, c.Hi90), x + 40, ry, 110, fmtSmall, shadow ? brDim : brTxt);
				Cell("d.r" + tf + ".n", string.Format("n={0}/{1}L", (int)c.N, c.LiveN), x + 152, ry, 54, fmtSmall, brDim);
				Cell("d.r" + tf + ".hl", tf == 0 && !double.IsNaN(halfLifeMin) ? string.Format("{0:F0}m", halfLifeMin) : "—", x + 206, ry, 44, fmtSmall, brDim);
				Cell("d.r" + tf + ".act", act, x + 254, ry, 60, fmtSmall, ab);
				ry += rowH;
			}

			// gauge (cut in Phase 5 per plan; kept for Phase 0 parity)
			double score = compositeBias.IsValidDataPoint(0) ? compositeBias[0] : 0;
			float gx = x + 12, gw = w - 24, gy = ry + 8, gh = 9;
			RenderTarget.FillRectangle(new RectangleF(gx, gy, gw, gh), brTrack);
			float cx = gx + gw / 2f;
			RenderTarget.DrawLine(new Vector2(cx, gy - 2), new Vector2(cx, gy + gh + 2), brDim, 1f);
			float fw = (float)(Math.Abs(score) / 100.0 * gw / 2f);
			RenderTarget.FillRectangle(new RectangleF(score >= 0 ? cx : cx - fw, gy, fw, gh), score >= 0 ? brDisc : brPrem);
			Cell("d.gauge", regime == 1 ? "GAUGE SUPPRESSED — NO ACTIVE CELLS"
				: string.Format("BIAS {0:+0;-0;0}  ·  anchor {1}  ·  fails {2}", score, anchorWinner, failures.TotalCount),
				gx, gy + gh + 5, gw, fmtSmall, regime == 1 ? brEq : brTxt);
		}

		private static Color4 C4(Media.Brush b, float a)
		{
			var s = b as Media.SolidColorBrush; var c = s != null ? s.Color : Media.Colors.Gray;
			return new Color4(c.R / 255f, c.G / 255f, c.B / 255f, a);
		}

		private void TagR(string key, string t, float xR, float yv, DW.TextFormat f, D2D.Brush b)
		{
			DW.TextLayout tl = GetLayout(key, t, f, 420f, 20f);
			RenderTarget.DrawTextLayout(new Vector2(xR - tl.Metrics.Width - 8f, yv - tl.Metrics.Height - 2f), tl, b);
		}

		private void Cell(string key, string t, float x, float yv, float w, DW.TextFormat f, D2D.Brush b)
		{
			DW.TextLayout tl = GetLayout(key, t, f, w, 18f);
			RenderTarget.DrawTextLayout(new Vector2(x, yv), tl, b);
		}
		#endregion

		#region Public API
		[Browsable(false)] [XmlIgnore] public Series<double> CompositeBias { get { return compositeBias; } }
		public double PRev(int tf) { int r = CurrentBar > 0 ? lastRegimeCode : 1; return tf >= 0 && tf < TfCount ? cells[tf, r].Mean : double.NaN; }
		public double PRevLo90(int tf) { int r = CurrentBar > 0 ? lastRegimeCode : 1; return tf >= 0 && tf < TfCount ? cells[tf, r].Lo90 : double.NaN; }
		public int RegimeCode() { return CurrentBar > 0 ? lastRegimeCode : 1; }
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
		[Display(Name = "Cost haircut over 50% (%)", Description = "Posterior lower bound must clear 50% + this.", Order = 3, GroupName = "01. Engine")]
		public double CostHaircutPct { get; set; }

		[NinjaScriptProperty] [Range(1, 400)]
		[Display(Name = "POC bucket (ticks)", Description = "Volume-at-price bucket width in ticks (was hardcoded 5.0 pts for NQ).", Order = 4, GroupName = "01. Engine")]
		public int PocBucketTicks { get; set; }

		[NinjaScriptProperty] [Range(0, 5)]
		[Display(Name = "Target (sigma, 0 = anchor touch)", Order = 1, GroupName = "02. Lifecycle")]
		public double TargetSigma { get; set; }

		[NinjaScriptProperty] [Range(0.5, 8)]
		[Display(Name = "Stop (sigma)", Order = 2, GroupName = "02. Lifecycle")]
		public double StopSigma { get; set; }

		[NinjaScriptProperty] [Range(20, 20000)]
		[Display(Name = "Timeout (minutes)", Description = "Signal lifetime in MINUTES — identical behavior on any minute-period chart.", Order = 3, GroupName = "02. Lifecycle")]
		public int TimeoutMinutes { get; set; }

		[NinjaScriptProperty] [Range(30, 3600)]
		[Display(Name = "GEX poll seconds", Order = 1, GroupName = "04. Data APIs")]
		public int PollSeconds { get; set; }

		// SECRETS — deliberately NOT [NinjaScriptProperty], NOT serialized, NOT browsable.
		// Loaded from Documents\NinjaTrader 8\Deep6PD\credentials.json (plan r2 Phase 0.4).
		[Browsable(false)] [XmlIgnore]
		public string UwToken { get; set; }

		[Browsable(false)] [XmlIgnore]
		public string FlashAlphaUrl { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "UW ticker (NDX/QQQ/SPX)", Order = 2, GroupName = "04. Data APIs")]
		public string UwTicker { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "FlashAlpha JSON path to net gamma", Order = 3, GroupName = "04. Data APIs")]
		public string FlashAlphaJsonPath { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Offline mode (no HTTP ever; GEX from fixture)", Description = "Playback/QA: blocks all HTTP and reads gex_fixture_<ticker>.json from Deep6PD\\v3.", Order = 1, GroupName = "05. QA")]
		public bool OfflineMode { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Debug perf counters", Order = 2, GroupName = "05. QA")]
		public bool DebugPerf { get; set; }

		[NinjaScriptProperty] [Range(2, 60)]
		[Display(Name = "Zone opacity (%)", Order = 1, GroupName = "03. Visuals")]
		public int ZoneOpacity { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show dashboard", Order = 2, GroupName = "03. Visuals")]
		public bool ShowDashboard { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Dashboard position", Order = 3, GroupName = "03. Visuals")]
		public Deep6DashCorner DashboardPos { get; set; }

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

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private Deep6PremiumDiscountV3[] cacheDeep6PremiumDiscountV3;
		public Deep6PremiumDiscountV3 Deep6PremiumDiscountV3(int swingStrength, int minSamples, double costHaircutPct, int pocBucketTicks, double targetSigma, double stopSigma, int timeoutMinutes, int pollSeconds, string uwTicker, string flashAlphaJsonPath, bool offlineMode, bool debugPerf, int zoneOpacity, bool showDashboard, Deep6DashCorner dashboardPos, bool showLabels)
		{
			return Deep6PremiumDiscountV3(Input, swingStrength, minSamples, costHaircutPct, pocBucketTicks, targetSigma, stopSigma, timeoutMinutes, pollSeconds, uwTicker, flashAlphaJsonPath, offlineMode, debugPerf, zoneOpacity, showDashboard, dashboardPos, showLabels);
		}

		public Deep6PremiumDiscountV3 Deep6PremiumDiscountV3(ISeries<double> input, int swingStrength, int minSamples, double costHaircutPct, int pocBucketTicks, double targetSigma, double stopSigma, int timeoutMinutes, int pollSeconds, string uwTicker, string flashAlphaJsonPath, bool offlineMode, bool debugPerf, int zoneOpacity, bool showDashboard, Deep6DashCorner dashboardPos, bool showLabels)
		{
			if (cacheDeep6PremiumDiscountV3 != null)
				for (int idx = 0; idx < cacheDeep6PremiumDiscountV3.Length; idx++)
					if (cacheDeep6PremiumDiscountV3[idx] != null && cacheDeep6PremiumDiscountV3[idx].SwingStrength == swingStrength && cacheDeep6PremiumDiscountV3[idx].MinSamples == minSamples && cacheDeep6PremiumDiscountV3[idx].CostHaircutPct == costHaircutPct && cacheDeep6PremiumDiscountV3[idx].PocBucketTicks == pocBucketTicks && cacheDeep6PremiumDiscountV3[idx].TargetSigma == targetSigma && cacheDeep6PremiumDiscountV3[idx].StopSigma == stopSigma && cacheDeep6PremiumDiscountV3[idx].TimeoutMinutes == timeoutMinutes && cacheDeep6PremiumDiscountV3[idx].PollSeconds == pollSeconds && cacheDeep6PremiumDiscountV3[idx].UwTicker == uwTicker && cacheDeep6PremiumDiscountV3[idx].FlashAlphaJsonPath == flashAlphaJsonPath && cacheDeep6PremiumDiscountV3[idx].OfflineMode == offlineMode && cacheDeep6PremiumDiscountV3[idx].DebugPerf == debugPerf && cacheDeep6PremiumDiscountV3[idx].ZoneOpacity == zoneOpacity && cacheDeep6PremiumDiscountV3[idx].ShowDashboard == showDashboard && cacheDeep6PremiumDiscountV3[idx].DashboardPos == dashboardPos && cacheDeep6PremiumDiscountV3[idx].ShowLabels == showLabels && cacheDeep6PremiumDiscountV3[idx].EqualsInput(input))
						return cacheDeep6PremiumDiscountV3[idx];
			return CacheIndicator<Deep6PremiumDiscountV3>(new Deep6PremiumDiscountV3(){ SwingStrength = swingStrength, MinSamples = minSamples, CostHaircutPct = costHaircutPct, PocBucketTicks = pocBucketTicks, TargetSigma = targetSigma, StopSigma = stopSigma, TimeoutMinutes = timeoutMinutes, PollSeconds = pollSeconds, UwTicker = uwTicker, FlashAlphaJsonPath = flashAlphaJsonPath, OfflineMode = offlineMode, DebugPerf = debugPerf, ZoneOpacity = zoneOpacity, ShowDashboard = showDashboard, DashboardPos = dashboardPos, ShowLabels = showLabels }, input, ref cacheDeep6PremiumDiscountV3);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.Deep6PremiumDiscountV3 Deep6PremiumDiscountV3(int swingStrength, int minSamples, double costHaircutPct, int pocBucketTicks, double targetSigma, double stopSigma, int timeoutMinutes, int pollSeconds, string uwTicker, string flashAlphaJsonPath, bool offlineMode, bool debugPerf, int zoneOpacity, bool showDashboard, Deep6DashCorner dashboardPos, bool showLabels)
		{
			return indicator.Deep6PremiumDiscountV3(Input, swingStrength, minSamples, costHaircutPct, pocBucketTicks, targetSigma, stopSigma, timeoutMinutes, pollSeconds, uwTicker, flashAlphaJsonPath, offlineMode, debugPerf, zoneOpacity, showDashboard, dashboardPos, showLabels);
		}

		public Indicators.Deep6PremiumDiscountV3 Deep6PremiumDiscountV3(ISeries<double> input , int swingStrength, int minSamples, double costHaircutPct, int pocBucketTicks, double targetSigma, double stopSigma, int timeoutMinutes, int pollSeconds, string uwTicker, string flashAlphaJsonPath, bool offlineMode, bool debugPerf, int zoneOpacity, bool showDashboard, Deep6DashCorner dashboardPos, bool showLabels)
		{
			return indicator.Deep6PremiumDiscountV3(input, swingStrength, minSamples, costHaircutPct, pocBucketTicks, targetSigma, stopSigma, timeoutMinutes, pollSeconds, uwTicker, flashAlphaJsonPath, offlineMode, debugPerf, zoneOpacity, showDashboard, dashboardPos, showLabels);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.Deep6PremiumDiscountV3 Deep6PremiumDiscountV3(int swingStrength, int minSamples, double costHaircutPct, int pocBucketTicks, double targetSigma, double stopSigma, int timeoutMinutes, int pollSeconds, string uwTicker, string flashAlphaJsonPath, bool offlineMode, bool debugPerf, int zoneOpacity, bool showDashboard, Deep6DashCorner dashboardPos, bool showLabels)
		{
			return indicator.Deep6PremiumDiscountV3(Input, swingStrength, minSamples, costHaircutPct, pocBucketTicks, targetSigma, stopSigma, timeoutMinutes, pollSeconds, uwTicker, flashAlphaJsonPath, offlineMode, debugPerf, zoneOpacity, showDashboard, dashboardPos, showLabels);
		}

		public Indicators.Deep6PremiumDiscountV3 Deep6PremiumDiscountV3(ISeries<double> input , int swingStrength, int minSamples, double costHaircutPct, int pocBucketTicks, double targetSigma, double stopSigma, int timeoutMinutes, int pollSeconds, string uwTicker, string flashAlphaJsonPath, bool offlineMode, bool debugPerf, int zoneOpacity, bool showDashboard, Deep6DashCorner dashboardPos, bool showLabels)
		{
			return indicator.Deep6PremiumDiscountV3(input, swingStrength, minSamples, costHaircutPct, pocBucketTicks, targetSigma, stopSigma, timeoutMinutes, pollSeconds, uwTicker, flashAlphaJsonPath, offlineMode, debugPerf, zoneOpacity, showDashboard, dashboardPos, showLabels);
		}
	}
}

#endregion
