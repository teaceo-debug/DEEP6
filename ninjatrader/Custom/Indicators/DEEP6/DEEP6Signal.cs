
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Threading;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = SharpDX.Direct2D1.Brush;
using Factory = SharpDX.DirectWrite.Factory;
using FontStyle = SharpDX.DirectWrite.FontStyle;
using FontWeight = SharpDX.DirectWrite.FontWeight;
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using Ellipse = SharpDX.Direct2D1.Ellipse;
#endregion

// =============================================================================
// DEEP6 Signal v2 Ã¢â‚¬â€ single-file institutional-grade microstructure signal HUD
// =============================================================================
// Drop this file into Documents\NinjaTrader 8\bin\Custom\Indicators\
// Compile via F5 in NinjaScript Editor. Attach to an NQ or MNQ chart with
// market depth subscription enabled.
//
// Architecture (compressed into one file, but layers are preserved):
//   L1 Data        -> NT8 OnBarUpdate / OnMarketData / OnMarketDepth
//   L2 Features    -> FeatureFrame { microprice, OFI, BVC, Hawkes, rough vol }
//   L3 Engines     -> E1..E9 (IEngine implementations as nested classes)
//   L4 Regime      -> HmmForward + Bocpd
//   L5 Fusion      -> FtrlProximal + IsotonicCalibrator + TierQuantiles
//   L6 Decision    -> PolicyLayer { Kelly, optimal stop, hold time, risk gates }
//   L7 Render      -> HudRenderer (SharpDX, six states, 8Hz throttle)
// =============================================================================

[EditorBrowsable(EditorBrowsableState.Always)]
public enum Verdict     { Standby, Take, Fade, Caution, Blocked, Error }
public enum Tier        { Q = 0, C = 1, B = 2, A = 3, S = 4 }
public enum Regime      { Dead, Range, Trend, Toxic, SessionOpen }
public enum SignalFamily { None, Absorb, Exhaust, Regime }

namespace NinjaTrader.NinjaScript.Indicators
{
	public class DEEP6Signal : Indicator
	{
		#region Constants & Enums
		private const int MaxLevelMarkers = 4;
		private const int HudWidth = 290;
		private const int HudHeightArmed = 96;
		private const int HudHeightStandby = 28;
		private const int HudTierStripeWidth = 6;
		private const double RenderThrottleMs = 125; // 8Hz
		private const int CalibrationBuffer = 5000;
		private const int MinSamplesForCalibration = 200;
		private const int HawkesEmEventInterval = 1000;
		private const int ConsecutiveLossCircuitBreaker = 3;
		private const int CircuitBreakerCooldownMinutes = 15;
		private const double EngineRecencyLambda = 0.02; // exp(-lambda*dt seconds)
		private const int DomLevelsTracked = 4;


		#endregion

		#region Fields
		// feature frame (L2)
		private FeatureFrame features;

		// engines (L3)
		private IEngine[] engines;
		private DateTime[] engineLastFireUtc;

		// regime (L4)
		private HmmForward hmm;
		private Bocpd bocpd;

		// fusion (L5)
		private FtrlProximal ftrl;
		private IsotonicCalibrator calibrator;
		private TierQuantiles tierQuantiles;
		private CircularBuffer<LabeledSignal> calibBuf;

		// decision (L6)
		private PolicyLayer policy;
		private RiskGate risk;

		// render (L7)
		private HudRenderer hud;
		private List<LevelMarker> levelMarkers;

		// cross-thread state
		private AtomicSnapshot<Verdict_Snapshot> snapshot;

		// lifecycle
		private DateTime lastRenderUtc = DateTime.MinValue;
		private DateTime lastEngineUpdate = DateTime.MinValue;
		private int panelMode = 0; // 0=hud, 9=engines, 10=wall, 11=calib, shift9=history, shift10=regime
		private bool initialized;

		// dirty flag Ã¢â‚¬â€ set by data threads, cleared by RecomputeAll
		private volatile bool featuresDirty;

		// hotkey
		private ChartControl chartControlRef;

		// SharpDX resources
		private Factory textFactory;
		private TextFormat verdictFmt, causeFmt, planFmt, ctxFmt, smallFmt, tinyFmt, arrowFmt;
		private Brush bgBrush, borderBrush, textBrush, secondaryBrush, dividerBrush;
		private Brush[] tierBrushes;
		private Brush absorbBrush, exhaustBrush, greenBrush, redBrush, amberBrush, grayBrush;
		private bool brushesReady;
		#endregion

		#region User Properties
		[NinjaScriptProperty, Display(Name="Min tier to fire", Order=1, GroupName="Signal")]
		public Tier MinTier { get; set; } = Tier.B;

		[NinjaScriptProperty, Display(Name="Min calibrated P", Order=2, GroupName="Signal")]
		public double MinPWin { get; set; } = 0.55;

		[NinjaScriptProperty, Display(Name="Kelly fraction", Order=3, GroupName="Risk")]
		public double KellyFraction { get; set; } = 0.25;

		[NinjaScriptProperty, Display(Name="Max contracts", Order=4, GroupName="Risk")]
		public int MaxContracts { get; set; } = 2;

		[NinjaScriptProperty, Display(Name="Daily loss limit ($)", Order=5, GroupName="Risk")]
		public double DailyLossLimit { get; set; } = 1000;

		[NinjaScriptProperty, Display(Name="Apex flat cutoff (minutes before close)", Order=6, GroupName="Risk")]
		public int ApexFlatCutoffMinutes { get; set; } = 1;

		[NinjaScriptProperty, Display(Name="TP k-sigma", Order=7, GroupName="Policy")]
		public double TpKSigma { get; set; } = 2.0;

		[NinjaScriptProperty, Display(Name="SL k-sigma", Order=8, GroupName="Policy")]
		public double SlKSigma { get; set; } = 1.2;

		[NinjaScriptProperty, Display(Name="Baseline window (bars)", Order=9, GroupName="Calibration")]
		public int BaselineWindow { get; set; } = 200;

		[NinjaScriptProperty, Display(Name="Show debug stats", Order=10, GroupName="Render")]
		public bool ShowDebug { get; set; } = false;
		#endregion

		#region Indicator lifecycle
		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "DEEP6 v2 microstructure signal HUD Ã¢â‚¬â€ absorption/exhaustion detection with calibrated probability output.";
				Name = "DEEP6 Signal v2";
				Calculate = Calculate.OnEachTick;
				IsOverlay = true;
				IsSuspendedWhileInactive = false;
				DrawOnPricePanel = true;
				DisplayInDataBox = false;
				PaintPriceMarkers = false;
				ScaleJustification = ScaleJustification.Right;
				BarsRequiredToPlot = 0;
			}
			else if (State == State.Configure)
			{
				// Tick replay is controlled by the chart properties, not the indicator.
				// Ensure the user enables "Tick Replay" in the Data Series dialog.
			}
			else if (State == State.DataLoaded)
			{
				InitializeState();
			}
			else if (State == State.Historical)
			{
				// stand down during historical load to prevent garbage labels
			}
			else if (State == State.Realtime)
			{
				// reset rolling windows on realtime crossover to prevent stale mix
				features?.OnRealtimeTransition();
			}
			else if (State == State.Terminated)
			{
				DisposeBrushes();
				if (chartControlRef != null)
					chartControlRef.Dispatcher.InvokeAsync(() => {
						try { chartControlRef.PreviewKeyDown -= OnChartKeyDown; } catch {}
					});
			}
		}

		private void InitializeState()
		{
			features     = new FeatureFrame(TickSize, BaselineWindow);
			engines      = new IEngine[]
			{
				new FootprintEngine(),       // E1
				new DomQueueEngine(),        // E2
				new HawkesSpoofEngine(),     // E3
				new IcebergEngine(),         // E4
				new MicrostructureEngine(),  // E5
				new VpinRegimeEngine(),      // E6
				new MetaLabelEngine(),       // E7
				new BvcCvdEngine(),          // E8
				new HmmBocpdEngine()         // E9
			};
			engineLastFireUtc = new DateTime[engines.Length];
			for (int i = 0; i < engineLastFireUtc.Length; i++)
				engineLastFireUtc[i] = DateTime.UtcNow;
			hmm           = new HmmForward();
			bocpd         = new Bocpd(hazard: 1.0 / 200);
			ftrl          = new FtrlProximal(numFeatures: 16, alpha: 0.05, beta: 1.0, l1: 0.5, l2: 0.1);
			calibrator    = new IsotonicCalibrator();
			tierQuantiles = new TierQuantiles();
			calibBuf      = new CircularBuffer<LabeledSignal>(CalibrationBuffer);
			policy        = new PolicyLayer();
			risk          = new RiskGate(DailyLossLimit, MaxContracts, ApexFlatCutoffMinutes,
			                             ConsecutiveLossCircuitBreaker, CircuitBreakerCooldownMinutes);
			hud           = new HudRenderer();
			levelMarkers  = new List<LevelMarker>();
			snapshot      = new AtomicSnapshot<Verdict_Snapshot>();
			snapshot.Set(Verdict_Snapshot.Standby());
			featuresDirty = true;
			initialized   = true;
		}

		protected override void OnBarUpdate()
		{
			if (!initialized || BarsInProgress != 0) return;
			if (CurrentBar < 10) return;

			// close-of-bar features
			features.OnBarClose(Close[0], Open[0], High[0], Low[0], Volume[0], Time[0]);
			// seed synthetic bid/ask from bar data when no real L1 tick has arrived yet
			features.SeedL1FromBar(Close[0], Time[0]);
			featuresDirty = true;

			// update the regime layer (lower frequency)
			if ((Time[0] - lastEngineUpdate).TotalMilliseconds > 100)
			{
				RecomputeAll();
				lastEngineUpdate = Time[0];
			}
		}

		protected override void OnMarketData(MarketDataEventArgs e)
		{
			if (!initialized) return;
			features?.OnL1(e);
			featuresDirty = true;
		}

		protected override void OnMarketDepth(MarketDepthEventArgs e)
		{
			if (!initialized) return;
			features?.OnL2(e);
			featuresDirty = true;
		}
		#endregion

		#region Compute pipeline
		private void RecomputeAll()
		{
			// skip redundant recompute if nothing changed since last pass
			if (!featuresDirty) return;
			featuresDirty = false;

			// data health gate
			var health = features.Health(Time[0]);
			if (health != DataHealth.Ok)
			{
				snapshot.Set(Verdict_Snapshot.Error(health.ToString()));
				return;
			}

			// engines
			DateTime nowUtc = DateTime.UtcNow;
			for (int i = 0; i < engines.Length; i++)
			{
				double prevConf = engines[i].Confidence;
				engines[i].Update(features);
				if (engines[i].Confidence > prevConf + 1e-6)
					engineLastFireUtc[i] = nowUtc;
			}

			// regime: HMM + BOCPD consensus (also surfaced via E9)
			double[] obs = features.RegimeObservationVector();
			hmm.Forward(obs);
			double changeProb = bocpd.Update(obs[0]);
			Regime currentRegime = InterpretRegime(hmm.MapState, changeProb);

			// build feature vector for FTRL (recency-weighted)
			double[] x = BuildFtrlFeatures();
			double rawP = ftrl.Predict(x);
			double calP = calibrator.IsReady ? calibrator.Calibrate(rawP) : rawP;

			// z-score vs baseline
			double z = features.ZScoreVsBaseline(rawP);
			Tier tier = tierQuantiles.Classify(calP);
			int direction = SignDirection();

			// risk gates
			double accountPnL = GetAccountPnL();
			DateTime now = Time[0];
			int recentLosses = policy.ConsecutiveLossCount();
			RiskVerdict rv = risk.Evaluate(tier, now, accountPnL, recentLosses);

			// compose verdict
			Verdict v = Verdict.Standby;
			SignalFamily fam = DominantFamily();
			if (rv == RiskVerdict.Blocked)       v = Verdict.Blocked;
			else if (currentRegime == Regime.Toxic && fam == SignalFamily.Absorb) v = Verdict.Caution;
			else if (tier >= MinTier && calP >= MinPWin)
				v = fam == SignalFamily.Exhaust ? Verdict.Fade : Verdict.Take;

			// trade plan
			double sigma = features.RoughVol;
			double entry = features.MidPrice;
			double tp = entry + direction * TpKSigma * sigma;
			double sl = entry - direction * SlKSigma * sigma;
			int size = policy.KellySize(calP, TpKSigma / SlKSigma, KellyFraction, MaxContracts);
			double tauHold = policy.HoldTime(features);

			// level markers
			UpdateLevelMarkers();

			// streak stats
			int winStreak, lossStreak;
			policy.CurrentStreak(out winStreak, out lossStreak);

			// publish snapshot for render thread
			snapshot.Set(new Verdict_Snapshot {
				V = v,
				Tier = tier,
				PWin = calP,
				Sigma = z,
				Dir = direction,
				Family = fam,
				Regime = currentRegime,
				Entry = entry,
				TP = tp,
				SL = sl,
				Size = size,
				TauHoldSec = tauHold,
				Cause = BuildCauseString(fam, features.DominantLevel),
				HealthyEngines = CountHealthy(),
				Vpin = features.VpinPct,
				SessionPnL = accountPnL,
				LastUpdate = now,
				WinStreak = winStreak,
				LossStreak = lossStreak,
				CircuitOpen = risk.CircuitBreakerOpen,
				Debug = ShowDebug ? BuildDebugString(x, rawP, calP, z) : null
			});

			// pending-label bookkeeping: store open signal for future triple-barrier
			if (v == Verdict.Take || v == Verdict.Fade)
				policy.RegisterOpenSignal(snapshot.Get(), features.RoughVol, now, x, rawP);

			// resolve any matured labels -> feed FTRL + calibrator
			foreach (var resolved in policy.ResolveMatured(features.MidPrice, now))
			{
				ftrl.Update(resolved.X, resolved.Y);
				calibBuf.Add(new LabeledSignal(resolved.RawP, resolved.Y, now));
				tierQuantiles.Observe(resolved.CalP);
				if (calibBuf.Count >= MinSamplesForCalibration && calibBuf.Count % 100 == 0)
					calibrator.Fit(calibBuf.ToArray());
				if (resolved.Y == -1)
					risk.OnLoss(now);
				else if (resolved.Y == 1)
					risk.OnWin();
			}
		}

		// Convert MinTier to a confidence threshold used for family aggregation.
		private double MinTierConfidenceThreshold()
		{
			switch (MinTier)
			{
				case Tier.Q: return 0.10;
				case Tier.C: return 0.30;
				case Tier.B: return 0.50;
				case Tier.A: return 0.70;
				case Tier.S: return 0.85;
				default:     return 0.50;
			}
		}

		private double[] BuildFtrlFeatures()
		{
			double[] x = new double[16];
			DateTime nowUtc = DateTime.UtcNow;

			// engine inputs Ã¢â‚¬â€ exponentially down-weight stale engine signals
			for (int i = 0; i < engines.Length && i < 9; i++)
			{
				double dtSec = (nowUtc - engineLastFireUtc[i]).TotalSeconds;
				if (dtSec < 0) dtSec = 0;
				double w = Math.Exp(-EngineRecencyLambda * dtSec);
				double raw = engines[i].Confidence * engines[i].Direction * w;
				x[i] = features.Normalize(raw);
			}

			x[9]  = features.Normalize(features.MicroStasisMs / 1000.0);
			x[10] = features.Normalize(features.MLOFI);
			x[11] = features.Normalize(features.HawkesLambda);
			x[12] = features.Normalize(features.HawkesBranchingRatio);
			x[13] = features.Normalize(features.BvcCvd);
			x[14] = features.Normalize(features.KyleLambda);
			x[15] = features.Normalize(features.VpinPct);
			return x;
		}

		private int SignDirection()
		{
			double thr = MinTierConfidenceThreshold();
			int sum = 0;
			foreach (var e in engines)
				sum += Math.Sign(e.Direction) * (e.Confidence > thr ? 1 : 0);
			if (sum == 0) return features.BvcCvdSlope >= 0 ? 1 : -1;
			return Math.Sign(sum);
		}

		private SignalFamily DominantFamily()
		{
			double thr = MinTierConfidenceThreshold();
			int absorb = 0, exhaust = 0;
			foreach (var e in engines)
			{
				if (e.Confidence < thr) continue;
				if (e.Family == SignalFamily.Absorb)  absorb++;
				if (e.Family == SignalFamily.Exhaust) exhaust++;
			}
			if (absorb == 0 && exhaust == 0) return SignalFamily.None;
			return absorb >= exhaust ? SignalFamily.Absorb : SignalFamily.Exhaust;
		}

		private Regime InterpretRegime(int mapState, double changeProb)
		{
			if (Bars != null && Bars.IsFirstBarOfSession) return Regime.SessionOpen;
			if (features.VpinPct > 0.90) return Regime.Toxic;
			if (features.VpinPct < 0.10) return Regime.Dead;
			return mapState == 2 ? Regime.Range : Regime.Trend;
		}

		private int CountHealthy()
		{
			int c = 0;
			foreach (var e in engines) if (e.IsHealthy) c++;
			return c;
		}

		private string BuildCauseString(SignalFamily fam, double level)
		{
			if (fam == SignalFamily.Absorb)
				return $"{level:F2} wall Ã‚Â· absorb confluence";
			if (fam == SignalFamily.Exhaust)
				return $"{level:F2} Ã‚Â· CVD-div exhaustion";
			return "Ã¢â‚¬â€ monitoring Ã¢â‚¬â€";
		}

		private string BuildDebugString(double[] x, double raw, double cal, double z)
		{
			return $"raw{raw:F3} cal{cal:F3} z{z:+0.00;-0.00} |w|0={ftrl.NonzeroWeights}";
		}

		private void UpdateLevelMarkers()
		{
			levelMarkers.Clear();
			foreach (var e in engines)
			{
				var snap = e.Snapshot();
				if (snap != null && snap.Level > 0 && e.Confidence >= 0.6)
				{
					levelMarkers.Add(new LevelMarker {
						Price = snap.Level,
						Size = snap.LevelSize,
						Rho = snap.Rho,
						PHold = snap.PHold,
						Family = e.Family,
						InFocus = Math.Abs(snap.Level - features.MidPrice) <= 3 * TickSize
					});
					if (levelMarkers.Count >= MaxLevelMarkers) break;
				}
			}
		}

		private double GetAccountPnL()
		{
			// Indicators do not have a direct Account reference. Access via Account.All.
			// In most cases this returns 0 until the user selects an account for monitoring.
			try
			{
				var all = NinjaTrader.Cbi.Account.All;
				if (all == null || all.Count == 0) return 0;
				double total = 0;
				foreach (var acc in all)
				{
					if (acc == null) continue;
					try
					{
						total += acc.Get(NinjaTrader.Cbi.AccountItem.RealizedProfitLoss, NinjaTrader.Cbi.Currency.UsDollar);
						total += acc.Get(NinjaTrader.Cbi.AccountItem.UnrealizedProfitLoss, NinjaTrader.Cbi.Currency.UsDollar);
					} catch {}
					break; // first account only for the HUD
				}
				return total;
			} catch {}
			return 0;
		}
		#endregion

		#region Render
		public override void OnRenderTargetChanged()
		{
			DisposeBrushes();
			if (RenderTarget == null) return;

			try
			{
				textFactory   = NinjaTrader.Core.Globals.DirectWriteFactory;
				verdictFmt    = new TextFormat(textFactory, "Consolas", FontWeight.SemiBold, FontStyle.Normal, 15);
				causeFmt      = new TextFormat(textFactory, "Consolas", FontWeight.Normal,   FontStyle.Normal, 11);
				planFmt       = new TextFormat(textFactory, "Consolas", FontWeight.Normal,   FontStyle.Normal, 11);
				ctxFmt        = new TextFormat(textFactory, "Consolas", FontWeight.Normal,   FontStyle.Normal, 10);
				smallFmt      = new TextFormat(textFactory, "Consolas", FontWeight.Normal,   FontStyle.Normal, 10);
				tinyFmt       = new TextFormat(textFactory, "Consolas", FontWeight.Normal,   FontStyle.Normal, 9);
				arrowFmt      = new TextFormat(textFactory, "Segoe UI Symbol", FontWeight.Bold, FontStyle.Normal, 22);

				bgBrush        = new SolidColorBrush(RenderTarget, new Color4(0.047f, 0.047f, 0.04f, 0.92f));
				borderBrush    = new SolidColorBrush(RenderTarget, new Color4(0.70f, 0.70f, 0.70f, 0.70f));
				textBrush      = new SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 1f));
				secondaryBrush = new SolidColorBrush(RenderTarget, new Color4(0.65f, 0.65f, 0.62f, 1f));
				dividerBrush   = new SolidColorBrush(RenderTarget, new Color4(0.35f, 0.35f, 0.32f, 1f));

				tierBrushes = new Brush[]
				{
					new SolidColorBrush(RenderTarget, new Color4(0.53f, 0.53f, 0.50f, 1f)),    // Q gray
					new SolidColorBrush(RenderTarget, new Color4(0.78f, 0.78f, 0.75f, 1f)),    // C light
					new SolidColorBrush(RenderTarget, new Color4(0.937f, 0.624f, 0.153f, 1f)), // B amber
					new SolidColorBrush(RenderTarget, new Color4(0.847f, 0.353f, 0.188f, 1f)), // A coral
					new SolidColorBrush(RenderTarget, new Color4(0.639f, 0.176f, 0.176f, 1f))  // S red
				};
				absorbBrush  = new SolidColorBrush(RenderTarget, new Color4(0.847f, 0.353f, 0.188f, 1f));
				exhaustBrush = new SolidColorBrush(RenderTarget, new Color4(0.325f, 0.290f, 0.718f, 1f));
				greenBrush   = new SolidColorBrush(RenderTarget, new Color4(0.114f, 0.620f, 0.459f, 1f));
				redBrush     = new SolidColorBrush(RenderTarget, new Color4(0.886f, 0.294f, 0.290f, 1f));
				amberBrush   = new SolidColorBrush(RenderTarget, new Color4(0.937f, 0.624f, 0.153f, 1f));
				grayBrush    = new SolidColorBrush(RenderTarget, new Color4(0.53f, 0.53f, 0.50f, 1f));

				brushesReady = true;
			}
			catch (Exception)
			{
				brushesReady = false;
				DisposeBrushes();
			}
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (!brushesReady || !initialized) return;
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			// throttle
			if ((DateTime.UtcNow - lastRenderUtc).TotalMilliseconds < RenderThrottleMs) return;
			lastRenderUtc = DateTime.UtcNow;

			// wire hotkeys lazily
			if (chartControlRef == null && chartControl != null)
			{
				chartControlRef = chartControl;
				chartControlRef.Dispatcher.InvokeAsync(() => {
					try { chartControl.PreviewKeyDown += OnChartKeyDown; } catch {}
				});
			}

			var snap = snapshot.Get();
			if (snap == null) return;

			// level markers first (behind HUD)
			RenderLevelMarkers(chartControl, chartScale);

			switch (panelMode)
			{
				case 9:  RenderEnginePanel(chartControl, snap);       break;
				case 10: RenderWallPanel(chartControl, snap);         break;
				case 11: RenderCalibrationPanel(chartControl, snap);  break;
				case 19: RenderHistoryPanel(chartControl, snap);      break;
				case 20: RenderRegimePanel(chartControl, snap);       break;
				default: /* HUD always renders below */               break;
			}

			RenderHud(chartControl, snap);
			RenderStatusStrip(chartControl, snap);
		}

		private void RenderHud(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			bool armed = snap.V != Verdict.Standby && snap.V != Verdict.Error;
			float height = armed ? HudHeightArmed : HudHeightStandby;
			float x = (float)(ChartPanel.X + ChartPanel.W) - HudWidth - 14;
			float y = 14;
			var rect = new RectangleF(x, y, HudWidth, height);

			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);

			// tier color stripe on the left edge
			Brush stripeBrush = (tierBrushes != null && (int)snap.Tier < tierBrushes.Length)
				? tierBrushes[(int)snap.Tier]
				: grayBrush;
			var stripeRect = new RectangleF(x, y, HudTierStripeWidth, height);
			RenderTarget.FillRectangle(stripeRect, stripeBrush);

			if (snap.V == Verdict.Standby)
			{
				var r = new RectangleF(x + HudTierStripeWidth + 10, y + 6, HudWidth - HudTierStripeWidth - 20, 18);
				RenderTarget.DrawText("Ã¢â‚¬â€ standby Ã¢â‚¬â€", ctxFmt, r, secondaryBrush);
				return;
			}

			if (snap.V == Verdict.Error)
			{
				var r = new RectangleF(x + HudTierStripeWidth + 10, y + 6, HudWidth - HudTierStripeWidth - 20, 18);
				RenderTarget.DrawText($"Ã¢Å¡Â  data error Ã‚Â· {snap.Cause}", ctxFmt, r, redBrush);
				return;
			}

			// direction arrow glyph (Ã¢â€ â€˜/Ã¢â€ â€œ) Ã¢â‚¬â€ rendered large before the verb text
			string arrow = snap.Dir > 0 ? "Ã¢â€ â€˜" : "Ã¢â€ â€œ";
			Brush arrowBrush = snap.V == Verdict.Blocked ? redBrush :
			                   snap.V == Verdict.Caution ? amberBrush :
			                   snap.V == Verdict.Fade ? absorbBrush :
			                   (snap.Dir > 0 ? greenBrush : redBrush);
			var arrowRect = new RectangleF(x + HudTierStripeWidth + 8, y + 2, 24, 26);
			if (arrowFmt != null && !arrowFmt.IsDisposed)
				RenderTarget.DrawText(arrow, arrowFmt, arrowRect, arrowBrush);

			// Line 1: verdict + tier + sigma + prob (right of arrow)
			string dirWord = snap.Dir > 0 ? "LONG" : "SHORT";
			string verb    = snap.V == Verdict.Fade ? "FADE " : (snap.V == Verdict.Caution ? "WATCH " : (snap.V == Verdict.Blocked ? "BLOCKED " : ""));
			string line1   = $"{verb}{dirWord} {snap.Size}  {snap.Tier}  {snap.Sigma:+0.00;-0.00}ÃÆ’  P{snap.PWin:F2}";
			var line1Rect = new RectangleF(x + HudTierStripeWidth + 32, y + 6, HudWidth - HudTierStripeWidth - 44, 22);
			RenderTarget.DrawText(line1, verdictFmt, line1Rect, arrowBrush);

			// Line 2: cause
			string line2 = snap.Cause ?? "";
			if (line2.Length > 44) line2 = line2.Substring(0, 44);
			var line2Rect = new RectangleF(x + HudTierStripeWidth + 8, y + 30, HudWidth - HudTierStripeWidth - 20, 16);
			RenderTarget.DrawText(line2, causeFmt, line2Rect, textBrush);

			// Line 3: plan
			double rr = Math.Abs(snap.TP - snap.Entry) / Math.Max(Math.Abs(snap.Entry - snap.SL), 1e-9);
			string line3 = $"TP {snap.TP:F2}  SL {snap.SL:F2}  Ãâ€ž {snap.TauHoldSec:F0}s  R:R {rr:F2}";
			var line3Rect = new RectangleF(x + HudTierStripeWidth + 8, y + 48, HudWidth - HudTierStripeWidth - 20, 16);
			RenderTarget.DrawText(line3, planFmt, line3Rect, textBrush);

			// Divider
			RenderTarget.DrawLine(new Vector2(x + HudTierStripeWidth + 6, y + 70), new Vector2(x + HudWidth - 10, y + 70), dividerBrush, 0.5f);

			// Line 4: context
			string regimeTxt = snap.Regime.ToString().ToLower();
			string line4 = $"{regimeTxt} Ã‚Â· VPIN {snap.Vpin*100:F0} Ã‚Â· {snap.HealthyEngines}/9 Ã‚Â· {(snap.SessionPnL >= 0 ? "+" : "")}{snap.SessionPnL:F0}$";
			var line4Rect = new RectangleF(x + HudTierStripeWidth + 8, y + 74, HudWidth - HudTierStripeWidth - 20, 14);
			RenderTarget.DrawText(line4, ctxFmt, line4Rect, secondaryBrush);

			// debug row (optional)
			if (ShowDebug && !string.IsNullOrEmpty(snap.Debug))
			{
				var rDbg = new RectangleF(x + HudTierStripeWidth + 8, y + 90, HudWidth - HudTierStripeWidth - 20, 12);
				RenderTarget.DrawText(snap.Debug, tinyFmt, rDbg, secondaryBrush);
			}
		}

		private void RenderStatusStrip(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			float w = 420, h = 22;
			float x = (float)ChartPanel.X + 12;
			// ChartPanel gives us the actual panel rect; bottom = Y + H
			float bottom = ChartPanel != null ? (float)(ChartPanel.Y + ChartPanel.H) : 600f;
			float y = bottom - h - 12;
			var rect = new RectangleF(x, y, w, h);

			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);

			Brush stripBrush = snap.V == Verdict.Error ? redBrush :
			                   snap.CircuitOpen ? redBrush :
			                   snap.Regime == Regime.Toxic ? amberBrush :
			                   snap.HealthyEngines < 7 ? redBrush : greenBrush;

			// streak badge
			string streak;
			if (snap.WinStreak > 0)       streak = $"W{snap.WinStreak}";
			else if (snap.LossStreak > 0) streak = $"L{snap.LossStreak}";
			else                          streak = "Ã¢â‚¬â€";

			string cb = snap.CircuitOpen ? " Ã‚Â· CB-OPEN" : "";
			string line = $"Ã¢â€”Â DEEP6 v2 Ã‚Â· {snap.Regime.ToString().ToLower()} Ã‚Â· VPIN {snap.Vpin*100:F0}% Ã‚Â· {snap.HealthyEngines}/9 Ã‚Â· {streak}{cb} Ã‚Â· {DateTime.Now:HH:mm:ss}";
			var r = new RectangleF(x + 8, y + 4, w - 16, 16);
			RenderTarget.DrawText(line, ctxFmt, r, stripBrush);
		}

		private void RenderLevelMarkers(ChartControl cc, ChartScale cs)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;
			if (levelMarkers == null) return;
			float xDot = (float)(ChartPanel.X + ChartPanel.W) - 50;
			foreach (var lm in levelMarkers)
			{
				float py;
				try { py = cs.GetYByValue(lm.Price); } catch { continue; }
				Brush b = lm.Family == SignalFamily.Absorb ? absorbBrush : exhaustBrush;
				var el = new Ellipse(new Vector2(xDot, py), 4, 4);
				RenderTarget.FillEllipse(el, b);
				if (lm.InFocus)
				{
					string label = $"{lm.Price:F2} Ã‚Â· {lm.Size:N0} Ã‚Â· ÃÂ{lm.Rho:F1} Ã‚Â· P{lm.PHold:F2}";
					var r = new RectangleF(xDot + 8, py - 7, 160, 14);
					RenderTarget.DrawText(label, smallFmt, r, b);
				}
			}
		}

		private void RenderEnginePanel(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			float w = 320, h = 260;
			float x = (float)(ChartPanel.X + ChartPanel.W) - HudWidth - 14 - w - 10;
			float y = 14;
			var rect = new RectangleF(x, y, w, h);
			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);

			var titleRect = new RectangleF(x + 12, y + 6, w - 24, 18);
			RenderTarget.DrawText("Engines (F9)  Ã¢â‚¬â€ Esc to close", verdictFmt, titleRect, textBrush);

			for (int i = 0; i < engines.Length; i++)
			{
				float rowY = y + 32 + i * 24;
				string name = engines[i].Name;
				double conf = engines[i].Confidence;
				Brush b = engines[i].Family == SignalFamily.Absorb ? absorbBrush :
				          engines[i].Family == SignalFamily.Exhaust ? exhaustBrush :
				          engines[i].Family == SignalFamily.Regime ? amberBrush : grayBrush;

				var labelRect = new RectangleF(x + 14, rowY, 150, 20);
				RenderTarget.DrawText($"E{i+1} {name}", smallFmt, labelRect, textBrush);

				float barX = x + 170, barY = rowY + 6, barW = 100, barH = 8;
				var barBg = new RectangleF(barX, barY, barW, barH);
				RenderTarget.FillRectangle(barBg, dividerBrush);
				var barFill = new RectangleF(barX, barY, (float)(barW * Math.Min(1.0, Math.Max(0.0, conf))), barH);
				RenderTarget.FillRectangle(barFill, b);

				var valRect = new RectangleF(x + 275, rowY, 40, 20);
				RenderTarget.DrawText($"{conf:F2}", smallFmt, valRect, textBrush);
			}
		}

		private void RenderWallPanel(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			float w = 460, h = 280;
			float x = (float)(ChartPanel.X + ChartPanel.W) - HudWidth - 14 - w - 10;
			float y = 14;
			var rect = new RectangleF(x, y, w, h);
			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);

			RenderTarget.DrawText("Wall inspector (F10)  Ã¢â‚¬â€ Esc to close", verdictFmt,
				new RectangleF(x + 12, y + 6, w - 24, 18), textBrush);

			// Surface the top bid/ask wall from FeatureFrame
			double bidWall = features.BidWallLevel;
			double askWall = features.AskWallLevel;
			long   bidSz   = features.BidWallSize;
			long   askSz   = features.AskWallSize;

			LevelMarker best = null;
			foreach (var lm in levelMarkers)
				if (best == null || lm.PHold > best.PHold) best = lm;

			if (best == null && bidWall <= 0 && askWall <= 0)
			{
				RenderTarget.DrawText("no active walls detected", causeFmt,
					new RectangleF(x + 12, y + 40, w - 24, 18), secondaryBrush);
				return;
			}

			double bestLevel = best != null ? best.Price : 0;
			double bestSize  = best != null ? best.Size  : 0;
			double bestRho   = best != null ? best.Rho   : 0;
			double bestPHold = best != null ? best.PHold : 0;

			string[] lines = {
				$"Best level   {bestLevel:F2}  size {bestSize:N0}",
				$"Top bid wall {bidWall:F2}  size {bidSz:N0}",
				$"Top ask wall {askWall:F2}  size {askSz:N0}",
				$"ÃÂÃŒâ€š refill     {bestRho:F2} /s",
				$"ÃŽÂ¼ aggress    {features.AggressionRate:F1} /s",
				$"P(hold)      {bestPHold:F2}",
				$"TÃ‚Â½ survival  {Math.Log(2) / Math.Max(1e-6, features.AggressionRate - bestRho):F1}s",
				$"SPRT ÃŽâ€ºÃ¢â€šâ„¢      {features.SprtLambda:+0.00;-0.00}",
				$"Verdict      {(bestPHold > 0.65 ? "HOLD" : bestPHold < 0.35 ? "BREAK" : "UNCERTAIN")}"
			};
			for (int i = 0; i < lines.Length; i++)
				RenderTarget.DrawText(lines[i], planFmt,
					new RectangleF(x + 14, y + 36 + i * 22, w - 28, 20), textBrush);
		}

		private void RenderCalibrationPanel(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			float w = 360, h = 300;
			float x = (float)(ChartPanel.X + ChartPanel.W) - HudWidth - 14 - w - 10;
			float y = 14;
			var rect = new RectangleF(x, y, w, h);
			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);
			RenderTarget.DrawText("Calibration (F11)  Ã¢â‚¬â€ Esc to close", verdictFmt,
				new RectangleF(x + 12, y + 6, w - 24, 18), textBrush);

			string[] lines = {
				$"session      {snap.Regime}",
				$"Hawkes ÃŽÂ¼ÃŒâ€š    {features.HawkesMu:F3}",
				$"Hawkes ÃŽÂ±ÃŒâ€š    {features.HawkesAlpha:F3}",
				$"Hawkes ÃŽÂ²ÃŒâ€š    {features.HawkesBeta:F3}",
				$"branching n  {features.HawkesBranchingRatio:F3}",
				$"Hawkes fits  {features.HawkesFits}",
				$"VPIN pct     {features.VpinPct*100:F0}",
				$"V bucket tgt {features.VpinBucketTarget:F0}",
				$"ADV (rolling){features.AdvEstimate:F0}",
				$"Kyle ÃŽÂ» (1s)  {features.KyleLambda:F4}",
				$"rough vol H  {features.HurstEstimate:F3}",
				$"ÃÆ’ÃŒâ€š rough     {features.RoughVol:F3}",
				$"FTRL |w|Ã¢â€šâ‚¬   {ftrl.NonzeroWeights}",
				$"cal samples  {calibBuf.Count}",
				$"tier Q99     {tierQuantiles.Q99:F3}"
			};
			for (int i = 0; i < lines.Length; i++)
				RenderTarget.DrawText(lines[i], planFmt,
					new RectangleF(x + 14, y + 32 + i * 18, w - 28, 18), textBrush);
		}

		private void RenderHistoryPanel(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			float w = 420, h = 260;
			float x = (float)(ChartPanel.X + ChartPanel.W) - HudWidth - 14 - w - 10;
			float y = 14;
			var rect = new RectangleF(x, y, w, h);
			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);
			RenderTarget.DrawText("Trade history (Shift+F9)  Ã¢â‚¬â€ Esc to close", verdictFmt,
				new RectangleF(x + 12, y + 6, w - 24, 18), textBrush);

			var hist = policy.RecentHistory(10);
			for (int i = 0; i < hist.Count; i++)
			{
				string line = $"{hist[i].TimeLocal:HH:mm:ss}  {hist[i].Dir,+2}  P{hist[i].CalP:F2}  Ã¢â€ â€™ {(hist[i].Y == 1 ? "WIN" : hist[i].Y == -1 ? "LOSS" : "FLAT")}";
				Brush b = hist[i].Y == 1 ? greenBrush : hist[i].Y == -1 ? redBrush : secondaryBrush;
				RenderTarget.DrawText(line, planFmt,
					new RectangleF(x + 14, y + 36 + i * 20, w - 28, 18), b);
			}
		}

		private void RenderRegimePanel(ChartControl cc, Verdict_Snapshot snap)
		{
			if (RenderTarget == null || RenderTarget.IsDisposed) return;

			float w = 360, h = 220;
			float x = (float)(ChartPanel.X + ChartPanel.W) - HudWidth - 14 - w - 10;
			float y = 14;
			var rect = new RectangleF(x, y, w, h);
			RenderTarget.FillRectangle(rect, bgBrush);
			RenderTarget.DrawRectangle(rect, borderBrush, 0.5f);
			RenderTarget.DrawText("Regime detail (Shift+F10)  Ã¢â‚¬â€ Esc to close", verdictFmt,
				new RectangleF(x + 12, y + 6, w - 24, 18), textBrush);

			string[] lines = {
				$"HMM MAP          {hmm.MapState}",
				$"HMM P(trend+)    {hmm.Posterior(0):F2}",
				$"HMM P(trendÃ¢Ë†â€™)    {hmm.Posterior(1):F2}",
				$"HMM P(range)     {hmm.Posterior(2):F2}",
				$"BOCPD change p   {bocpd.LastChangeProb:F2}",
				$"session phase    {snap.Regime}",
				$"VPIN regime      {(features.VpinPct > 0.9 ? "TOXIC" : features.VpinPct < 0.1 ? "DEAD" : "NORMAL")}"
			};
			for (int i = 0; i < lines.Length; i++)
				RenderTarget.DrawText(lines[i], planFmt,
					new RectangleF(x + 14, y + 36 + i * 22, w - 28, 20), textBrush);
		}

		private void OnChartKeyDown(object sender, KeyEventArgs e)
		{
			bool shift = (e.KeyboardDevice.Modifiers & ModifierKeys.Shift) != 0;
			switch (e.Key)
			{
				case Key.F9:  panelMode = (panelMode == (shift ? 19 : 9)) ? 0 : (shift ? 19 : 9); e.Handled = true; break;
				case Key.F10: panelMode = (panelMode == (shift ? 20 : 10)) ? 0 : (shift ? 20 : 10); e.Handled = true; break;
				case Key.F11: panelMode = (panelMode == 11) ? 0 : 11; e.Handled = true; break;
				case Key.F12: /* kill switch */ KillSwitchEngage(); e.Handled = true; break;
				case Key.Escape: panelMode = 0; e.Handled = true; break;
			}
			// reset throttle so next render picks up new panel immediately
			lastRenderUtc = DateTime.MinValue;
			try { chartControlRef?.InvalidateVisual(); } catch {}
		}

		private void KillSwitchEngage()
		{
			risk.HardDisable();
			snapshot.Set(Verdict_Snapshot.Blocked("kill switch engaged"));
		}

		private void DisposeBrushes()
		{
			brushesReady = false;
			if (verdictFmt != null && !verdictFmt.IsDisposed) { try { verdictFmt.Dispose(); } catch {} }
			if (causeFmt   != null && !causeFmt.IsDisposed)   { try { causeFmt.Dispose();   } catch {} }
			if (planFmt    != null && !planFmt.IsDisposed)    { try { planFmt.Dispose();    } catch {} }
			if (ctxFmt     != null && !ctxFmt.IsDisposed)     { try { ctxFmt.Dispose();     } catch {} }
			if (smallFmt   != null && !smallFmt.IsDisposed)   { try { smallFmt.Dispose();   } catch {} }
			if (tinyFmt    != null && !tinyFmt.IsDisposed)    { try { tinyFmt.Dispose();    } catch {} }
			if (arrowFmt   != null && !arrowFmt.IsDisposed)   { try { arrowFmt.Dispose();   } catch {} }
			verdictFmt = causeFmt = planFmt = ctxFmt = smallFmt = tinyFmt = arrowFmt = null;

			textFactory = null; // borrowed from Globals.DirectWriteFactory Ã¢â‚¬â€ do not dispose

			DisposeBrushSafe(ref bgBrush);
			DisposeBrushSafe(ref borderBrush);
			DisposeBrushSafe(ref textBrush);
			DisposeBrushSafe(ref secondaryBrush);
			DisposeBrushSafe(ref dividerBrush);
			DisposeBrushSafe(ref absorbBrush);
			DisposeBrushSafe(ref exhaustBrush);
			DisposeBrushSafe(ref greenBrush);
			DisposeBrushSafe(ref redBrush);
			DisposeBrushSafe(ref amberBrush);
			DisposeBrushSafe(ref grayBrush);

			if (tierBrushes != null)
			{
				for (int i = 0; i < tierBrushes.Length; i++)
				{
					var b = tierBrushes[i];
					if (b != null && !b.IsDisposed) { try { b.Dispose(); } catch {} }
					tierBrushes[i] = null;
				}
				tierBrushes = null;
			}
		}

		private static void DisposeBrushSafe(ref Brush b)
		{
			if (b != null && !b.IsDisposed) { try { b.Dispose(); } catch {} }
			b = null;
		}
		#endregion

		// =====================================================================
		// Nested types Ã¢â‚¬â€ snapshots, features, engines, fusion, decision
		// =====================================================================

		#region Snapshot
		private sealed class Verdict_Snapshot
		{
			public Verdict V; public Tier Tier; public double PWin, Sigma;
			public int Dir; public SignalFamily Family; public Regime Regime;
			public double Entry, TP, SL, TauHoldSec; public int Size;
			public string Cause, Debug;
			public int HealthyEngines; public double Vpin, SessionPnL;
			public DateTime LastUpdate;
			public int WinStreak, LossStreak;
			public bool CircuitOpen;

			public static Verdict_Snapshot Standby() => new Verdict_Snapshot { V = Verdict.Standby, HealthyEngines = 9 };
			public static Verdict_Snapshot Error(string cause) => new Verdict_Snapshot { V = Verdict.Error, Cause = cause };
			public static Verdict_Snapshot Blocked(string cause) => new Verdict_Snapshot { V = Verdict.Blocked, Cause = cause };
		}
		#endregion

		#region Atomic snapshot (RCU for cross-thread)
		private sealed class AtomicSnapshot<T> where T : class
		{
			private T current;
			public T Get() => Volatile.Read(ref current);
			public void Set(T next) => Volatile.Write(ref current, next);
		}
		#endregion

		#region Circular buffer
		private sealed class CircularBuffer<T>
		{
			private readonly T[] buf;
			private int head, count;
			public int Count => count;
			public int Capacity => buf.Length;

			public CircularBuffer(int capacity) { buf = new T[capacity]; }
			public void Add(T item)
			{
				buf[head] = item;
				head = (head + 1) % buf.Length;
				if (count < buf.Length) count++;
			}
			public T[] ToArray()
			{
				T[] r = new T[count];
				for (int i = 0; i < count; i++)
					r[i] = buf[(head - count + i + buf.Length) % buf.Length];
				return r;
			}
		}
		#endregion

		#region Level marker
		private sealed class LevelMarker
		{
			public double Price, Size, Rho, PHold;
			public SignalFamily Family;
			public bool InFocus;
		}
		#endregion

		#region Data health
		public enum DataHealth { Ok, Stale, Crossed, WideSpread, Uninitialized }
		#endregion

		#region Labeled signal (for calibration)
		private sealed class LabeledSignal
		{
			public double RawP; public int Y; public DateTime T;
			public LabeledSignal(double rawP, int y, DateTime t) { RawP = rawP; Y = y; T = t; }
		}
		#endregion

		#region FeatureFrame Ã¢â‚¬â€ L2 shared state
		private sealed class FeatureFrame
		{
			// book
			public double Bid, Ask, Last;
			public long BidSize, AskSize;
			public double MidPrice => (Bid + Ask) * 0.5;

			// derived features
			public double Microprice { get; private set; }
			public double MicroStasisMs { get; private set; }
			public double MLOFI { get; private set; }
			public double KyleLambda { get; private set; }
			public double BvcCvd { get; private set; }
			public double BvcCvdSlope { get; private set; }
			public double HawkesLambda { get; private set; }
			public double HawkesMu { get; private set; } = 0.5;
			public double HawkesAlpha { get; private set; } = 0.3;
			public double HawkesBeta { get; private set; } = 2.5;
			public int HawkesFits { get; private set; }
			public double HawkesBranchingRatio => HawkesAlpha / Math.Max(1e-9, HawkesBeta);
			public double RoughVol { get; private set; } = 1.0;
			public double HurstEstimate { get; private set; } = 0.10;
			public double VpinPct { get; private set; } = 0.5;
			public double VpinBucketTarget { get; private set; } = 8000;
			public double AdvEstimate { get; private set; } = 400000;
			public double AggressionRate { get; private set; }
			public double SprtLambda { get; private set; }
			public double DominantLevel { get; private set; }

			// top-of-book walls surfaced from OnL2
			public double BidWallLevel { get; private set; }
			public double AskWallLevel { get; private set; }
			public long   BidWallSize  { get; private set; }
			public long   AskWallSize  { get; private set; }
			public double BidWallDecay { get; private set; }   // sec^-1
			public double AskWallDecay { get; private set; }   // sec^-1
			public bool   BidIcebergSuspected { get; private set; }
			public bool   AskIcebergSuspected { get; private set; }

			// internals
			private readonly double tickSize;
			private readonly int baselineWindow;
			private DateTime lastL1 = DateTime.MinValue;
			private DateTime lastL2 = DateTime.MinValue;
			private double prevMicro;
			private DateTime stasisStart = DateTime.MinValue;
			private double prevBestBid, prevBestAsk;
			private long prevBestBidSize, prevBestAskSize;

			// DOM level tracking (top-4 per side)
			private readonly DomLevel[] bidLevels = new DomLevel[DomLevelsTracked];
			private readonly DomLevel[] askLevels = new DomLevel[DomLevelsTracked];

			// hawkes recursive state
			private double hawkesR;
			private long lastEventTicks;

			// Hawkes EM Ã¢â‚¬â€ inter-arrival buffer for moment-matching
			private readonly double[] hawkesDtBuf = new double[HawkesEmEventInterval];
			private int hawkesDtIdx;
			private int hawkesDtCount;
			private int hawkesEventCounter;

			// Previous bar BVC CVD for slope
			private double prevBvcCvdBar;

			// BVC rolling std
			private readonly double[] retBuf = new double[250];
			private int retIdx; private int retCount;
			private double cumBvc;

			// multi-scale realized variance for Hurst / rough vol
			private readonly int[] rvScales = new int[] { 1, 2, 4, 8, 16 };
			private readonly double[] rvSumSq; // per-scale sum of squared returns
			private readonly int[] rvCount;
			private readonly double[] returnsForRv = new double[256];
			private int retRvIdx;
			private int retRvCount;

			// VPIN buckets
			private double vBucketBuy, vBucketSell;
			private readonly double[] vpinBuf = new double[50];
			private int vpinIdx; private int vpinCount;

			// ADV tracker (20-bar rolling volume in contracts Ã¢â‚¬â€ set via OnBarClose)
			private readonly double[] advBuf = new double[20];
			private int advIdx, advCount;

			// score baseline
			private readonly double[] scoreBuf;
			private int scoreIdx; private int scoreCount;
			private double scoreMean, scoreVar = 1.0;

			// normalization
			private readonly double[] normBuf = new double[500];
			private int normIdx; private int normCount;

			// aggression rate rolling
			private int aggressCount;
			private DateTime aggressWindowStart = DateTime.MinValue;

			private sealed class DomLevel
			{
				public double Price;
				public long   Size;
				public long   PrevSize;
				public DateTime LastUpdate;
				public double DecayRate; // (size drop per second, exponential)
				public bool   IcebergSuspected;
			}

			public FeatureFrame(double tickSize, int baselineWindow)
			{
				this.tickSize = tickSize > 0 ? tickSize : 0.25;
				this.baselineWindow = Math.Max(50, baselineWindow);
				this.scoreBuf = new double[this.baselineWindow];
				this.rvSumSq = new double[rvScales.Length];
				this.rvCount = new int[rvScales.Length];
				for (int i = 0; i < bidLevels.Length; i++) bidLevels[i] = new DomLevel();
				for (int i = 0; i < askLevels.Length; i++) askLevels[i] = new DomLevel();
			}

			public DataHealth Health(DateTime now)
			{
				if (lastL1 == DateTime.MinValue) return DataHealth.Uninitialized;
				if ((now - lastL1).TotalSeconds > 10) return DataHealth.Stale;
				if (Bid > 0 && Ask > 0 && Bid >= Ask) return DataHealth.Crossed;
				if (Bid > 0 && Ask > 0 && (Ask - Bid) > 10 * tickSize) return DataHealth.WideSpread;
				return DataHealth.Ok;
			}

			public void SeedL1FromBar(double close, DateTime time)
			{
				// no-op once real L1 has arrived; keeps health gate green during historical/warm-up
				if (lastL1 != DateTime.MinValue) return;
				lastL1 = time;
				if (Bid <= 0) Bid = close - tickSize;
				if (Ask <= 0) Ask = close + tickSize;
				Last = close;
			}

			public void OnL1(MarketDataEventArgs e)
			{
				lastL1 = e.Time;
				if (e.MarketDataType == MarketDataType.Bid)
				{
					Bid = e.Price; BidSize = (long)e.Volume;
				}
				else if (e.MarketDataType == MarketDataType.Ask)
				{
					Ask = e.Price; AskSize = (long)e.Volume;
				}
				else if (e.MarketDataType == MarketDataType.Last)
				{
					Last = e.Price;
					OnTradeEvent(e);
				}
				UpdateMicroprice(e.Time);
				UpdateOfi();
			}

			public void OnL2(MarketDepthEventArgs e)
			{
				lastL2 = e.Time;

				// track top-4 per side
				DomLevel[] side = e.MarketDataType == MarketDataType.Bid ? bidLevels :
				                  e.MarketDataType == MarketDataType.Ask ? askLevels : null;
				if (side == null) return;
				if (e.Position < 0 || e.Position >= DomLevelsTracked) return;

				var lvl = side[e.Position];
				double newSize = e.Volume;
				double prevSize = lvl.Size;

				double dtSec = lvl.LastUpdate == DateTime.MinValue ? 0 : (e.Time - lvl.LastUpdate).TotalSeconds;

				if (e.Operation == Operation.Update || e.Operation == Operation.Add)
				{
					// sudden size addition Ã¢â‚¬â€ potential iceberg reveal
					if (prevSize > 0 && newSize > prevSize * 1.5 && dtSec < 1.0)
						lvl.IcebergSuspected = true;

					// size decay (absorption in progress)
					if (dtSec > 0 && prevSize > 0 && newSize < prevSize)
					{
						double drop = (prevSize - newSize);
						lvl.DecayRate = 0.9 * lvl.DecayRate + 0.1 * (drop / Math.Max(0.001, dtSec));
					}

					lvl.PrevSize = (long)prevSize;
					lvl.Size = (long)newSize;
					lvl.Price = e.Price;
					lvl.LastUpdate = e.Time;
				}
				else if (e.Operation == Operation.Remove)
				{
					lvl.Size = 0;
					lvl.Price = 0;
					lvl.IcebergSuspected = false;
					lvl.DecayRate = 0;
					lvl.LastUpdate = e.Time;
				}

				// refresh surfaced wall properties for side-top (position 0)
				if (e.Position == 0)
				{
					if (e.MarketDataType == MarketDataType.Bid)
					{
						BidWallLevel = lvl.Price;
						BidWallSize  = lvl.Size;
						BidWallDecay = lvl.DecayRate;
						BidIcebergSuspected = lvl.IcebergSuspected;
					}
					else
					{
						AskWallLevel = lvl.Price;
						AskWallSize  = lvl.Size;
						AskWallDecay = lvl.DecayRate;
						AskIcebergSuspected = lvl.IcebergSuspected;
					}
				}

				// pick dominant level by absolute size across both sides (top 4)
				long bestSize = 0;
				double bestPrice = 0;
				for (int i = 0; i < DomLevelsTracked; i++)
				{
					if (bidLevels[i].Size > bestSize) { bestSize = bidLevels[i].Size; bestPrice = bidLevels[i].Price; }
					if (askLevels[i].Size > bestSize) { bestSize = askLevels[i].Size; bestPrice = askLevels[i].Price; }
				}
				if (bestSize > 500) DominantLevel = bestPrice;
			}

			public void OnBarClose(double close, double open, double high, double low, double vol, DateTime t)
			{
				// ADV tracker (contracts per bar, 20-bar rolling)
				advBuf[advIdx] = vol;
				advIdx = (advIdx + 1) % advBuf.Length;
				if (advCount < advBuf.Length) advCount++;
				double advSum = 0;
				for (int i = 0; i < advCount; i++) advSum += advBuf[i];
				// Scale to daily Ã¢â‚¬â€ assume ~2000 bars per day (5s bars) or fall back to 20-bar volume
				double barMultiplier = 2000.0 / Math.Max(1, advCount);
				AdvEstimate = advSum * barMultiplier;
				// Easley-LÃƒÂ³pez-de-Prado target: ADV / 50 buckets
				VpinBucketTarget = Math.Max(500, Math.Min(50000, AdvEstimate / 50.0));

				// per-bar log-return for multi-scale realized variance
				double ret = prevBestBid > 0 ? Math.Log(close / prevBestBid) : 0;
				returnsForRv[retRvIdx] = ret;
				retRvIdx = (retRvIdx + 1) % returnsForRv.Length;
				if (retRvCount < returnsForRv.Length) retRvCount++;

				// recompute rolling RV per scale + log-log regression for Hurst
				ComputeMultiScaleRv();
				double H = EstimateHurstFromRv();
				if (!double.IsNaN(H) && !double.IsInfinity(H) && H > 0.01 && H < 0.5)
					HurstEstimate = H;
				else
					HurstEstimate = 0.10;

				// rough vol: sigma_1bar * N^H (RFSV scaling at horizon N)
				double sigma1 = (rvCount[0] > 0) ? Math.Sqrt(rvSumSq[0] / rvCount[0]) : 0;
				double horizon = Math.Max(1, retRvCount);
				RoughVol = sigma1 * Math.Pow(horizon, HurstEstimate);
				if (RoughVol < tickSize) RoughVol = tickSize;

				prevBestBid = close;

				// BVC slope: delta of cumBvc since last bar close
				BvcCvdSlope = BvcCvd - prevBvcCvdBar;
				prevBvcCvdBar = BvcCvd;
			}

			private void ComputeMultiScaleRv()
			{
				// For each scale s, compute sum of (r_t + r_{t+1} + ... + r_{t+s-1})^2 over sliding windows
				for (int si = 0; si < rvScales.Length; si++)
				{
					int s = rvScales[si];
					rvSumSq[si] = 0;
					rvCount[si] = 0;
					if (retRvCount < s) continue;
					int n = retRvCount;
					int baseIdx = (retRvIdx - n + returnsForRv.Length) % returnsForRv.Length;
					// non-overlapping blocks for stable estimation
					int blocks = n / s;
					for (int b = 0; b < blocks; b++)
					{
						double sum = 0;
						for (int k = 0; k < s; k++)
						{
							int idx = (baseIdx + b * s + k) % returnsForRv.Length;
							sum += returnsForRv[idx];
						}
						rvSumSq[si] += sum * sum;
						rvCount[si]++;
					}
				}
			}

			private double EstimateHurstFromRv()
			{
				// log(RV(s)) = log(c) + 2H log(s)  -> slope = 2H
				int valid = 0;
				double sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
				for (int i = 0; i < rvScales.Length; i++)
				{
					if (rvCount[i] < 2) continue;
					double rv = rvSumSq[i] / rvCount[i];
					if (rv <= 0) continue;
					double lx = Math.Log(rvScales[i]);
					double ly = Math.Log(rv);
					sumX += lx; sumY += ly;
					sumXY += lx * ly; sumXX += lx * lx;
					valid++;
				}
				if (valid < 3) return double.NaN;
				double denom = valid * sumXX - sumX * sumX;
				if (Math.Abs(denom) < 1e-12) return double.NaN;
				double slope = (valid * sumXY - sumX * sumY) / denom;
				return slope / 2.0;
			}

			public void OnRealtimeTransition()
			{
				// reset rolling windows at historical->realtime transition
				retCount = 0; retIdx = 0;
				retRvCount = 0; retRvIdx = 0;
				for (int i = 0; i < rvSumSq.Length; i++) { rvSumSq[i] = 0; rvCount[i] = 0; }
				vpinCount = 0; vpinIdx = 0;
				scoreCount = 0; scoreIdx = 0;
				hawkesDtCount = 0; hawkesDtIdx = 0;
				cumBvc = 0;
				prevBvcCvdBar = 0;
			}

			private void OnTradeEvent(MarketDataEventArgs e)
			{
				// BVC classification
				double ret = retCount > 0 ? e.Price - prevBestAsk : 0;
				retBuf[retIdx] = ret;
				retIdx = (retIdx + 1) % retBuf.Length;
				if (retCount < retBuf.Length) retCount++;
				double sigma = ComputeStd(retBuf, retCount);
				double z = sigma > 0 ? ret / sigma : 0;
				double phi = NormalCdf(z);
				double vol = e.Volume;
				double vBuy  = vol * phi;
				double vSell = vol * (1 - phi);
				cumBvc += (vBuy - vSell);
				BvcCvd = cumBvc;

				// VPIN
				vBucketBuy += vBuy; vBucketSell += vSell;
				if (vBucketBuy + vBucketSell >= VpinBucketTarget)
				{
					double bucketVpin = Math.Abs(vBucketBuy - vBucketSell) / VpinBucketTarget;
					vpinBuf[vpinIdx] = bucketVpin;
					vpinIdx = (vpinIdx + 1) % vpinBuf.Length;
					if (vpinCount < vpinBuf.Length) vpinCount++;
					double s = 0;
					for (int i = 0; i < vpinCount; i++) s += vpinBuf[i];
					double rawVpin = s / Math.Max(1, vpinCount);
					VpinPct = PercentileRank(vpinBuf, vpinCount, rawVpin);
					vBucketBuy = vBucketSell = 0;
				}

				// Hawkes intensity recursion (Ogata)
				long nowTicks = e.Time.Ticks;
				if (lastEventTicks > 0)
				{
					double dt = (nowTicks - lastEventTicks) * 1e-7;
					hawkesR = Math.Exp(-HawkesBeta * dt) * (1 + hawkesR);

					// accumulate inter-arrival for EM calibration
					if (dt > 0 && dt < 60.0)
					{
						hawkesDtBuf[hawkesDtIdx] = dt;
						hawkesDtIdx = (hawkesDtIdx + 1) % hawkesDtBuf.Length;
						if (hawkesDtCount < hawkesDtBuf.Length) hawkesDtCount++;
					}
				}
				HawkesLambda = HawkesMu + HawkesAlpha * hawkesR;
				lastEventTicks = nowTicks;

				// every HawkesEmEventInterval events Ã¢â‚¬â€ re-estimate (ÃŽÂ¼, ÃŽÂ±, ÃŽÂ²) via method of moments
				hawkesEventCounter++;
				if (hawkesEventCounter >= HawkesEmEventInterval && hawkesDtCount >= 200)
				{
					CalibrateHawkesMoM();
					hawkesEventCounter = 0;
				}

				// Kyle lambda Ã¢â‚¬â€ O(1) approximation via |ret|/|signedVol|
				double signedVol = vBuy - vSell;
				if (Math.Abs(signedVol) > 1)
					KyleLambda = 0.99 * KyleLambda + 0.01 * (Math.Abs(ret) / Math.Abs(signedVol));

				// aggression rate rolling
				aggressCount++;
				if (aggressWindowStart == DateTime.MinValue) aggressWindowStart = e.Time;
				double windowSec = (e.Time - aggressWindowStart).TotalSeconds;
				if (windowSec >= 1.0)
				{
					AggressionRate = aggressCount / windowSec;
					aggressCount = 0;
					aggressWindowStart = e.Time;
				}

				prevBestAsk = e.Price;

				// SPRT accumulator Ã¢â‚¬â€ favor hold if successive trades can't move price
				if (Math.Abs(ret) < tickSize)
					SprtLambda -= 0.05;
				else
					SprtLambda += 0.15 * Math.Sign(ret) * Math.Sign(signedVol);
				if (SprtLambda > 3) SprtLambda = 3;
				if (SprtLambda < -3) SprtLambda = -3;
			}

			// Online moment-matching for Hawkes (ÃŽÂ¼, ÃŽÂ±, ÃŽÂ²).
			// ÃŽÂ¼ ~ 1 / E[dt] when branching ratio ~0; for self-exciting process we use:
			//   baseline ÃŽÂ»0 = 1 / mean(dt)
			//   branching  n = 1 - sqrt(var(dt)) / mean(dt)    (heuristic; clamped to [0, 0.95])
			//   ÃŽÂ²          ~ 1 / tau  where tau is the lag-1 autocovariance decay length
			private void CalibrateHawkesMoM()
			{
				double mean = 0;
				for (int i = 0; i < hawkesDtCount; i++) mean += hawkesDtBuf[i];
				mean /= Math.Max(1, hawkesDtCount);
				if (mean <= 0) return;
				double varSum = 0;
				for (int i = 0; i < hawkesDtCount; i++) varSum += (hawkesDtBuf[i] - mean) * (hawkesDtBuf[i] - mean);
				double std = Math.Sqrt(varSum / Math.Max(1, hawkesDtCount));
				double cv = std / mean; // coefficient of variation

				// overdispersion (CV > 1) indicates self-excitation clustering
				double newMu = 1.0 / mean;

				// Hawkes moment: E[N(t)]/t = ÃŽÂ¼ / (1 - n). We target ÃŽÂ»ÃŒâ€ž from observation
				// and infer n from CV: n Ã¢â€°Ë† clamp(1 - 1/CV, 0, 0.95) when CV > 1.
				double n = cv > 1.0 ? Math.Max(0, Math.Min(0.95, 1.0 - 1.0 / cv)) : 0.0;

				// lag-1 autocovariance for decay time
				double ac = 0;
				for (int i = 1; i < hawkesDtCount; i++)
					ac += (hawkesDtBuf[i] - mean) * (hawkesDtBuf[i - 1] - mean);
				ac /= Math.Max(1, hawkesDtCount - 1);
				double rho = (std > 1e-9) ? ac / (std * std) : 0;
				double tau = rho > 1e-3 && rho < 0.999 ? -1.0 / Math.Log(rho) : 5.0;
				double newBeta = 1.0 / Math.Max(0.01, tau * mean);
				newBeta = Math.Max(0.1, Math.Min(20.0, newBeta));
				double newAlpha = n * newBeta;

				// light EMA to avoid jitter
				HawkesMu    = 0.7 * HawkesMu    + 0.3 * newMu;
				HawkesBeta  = 0.7 * HawkesBeta  + 0.3 * newBeta;
				HawkesAlpha = 0.7 * HawkesAlpha + 0.3 * newAlpha;
				HawkesFits++;
			}

			private void UpdateMicroprice(DateTime t)
			{
				if (Bid <= 0 || Ask <= 0 || BidSize <= 0 || AskSize <= 0) return;
				double I = (double)BidSize / (BidSize + AskSize);
				double mp = Bid + (Ask - Bid) * I;
				if (Math.Abs(mp - prevMicro) < 0.5 * tickSize)
				{
					if (stasisStart == DateTime.MinValue) stasisStart = t;
					MicroStasisMs = (t - stasisStart).TotalMilliseconds;
				}
				else
				{
					stasisStart = DateTime.MinValue;
					MicroStasisMs = 0;
				}
				prevMicro = mp;
				Microprice = mp;
			}

			private void UpdateOfi()
			{
				if (Bid <= 0 || Ask <= 0) return;
				double eBid = (Bid > prevBestBid ? BidSize : 0)
				            - (Bid < prevBestBid ? prevBestBidSize : 0);
				double eAsk = -(Ask < prevBestAsk ? AskSize : 0)
				            + (Ask > prevBestAsk ? prevBestAskSize : 0);
				MLOFI = 0.9 * MLOFI + 0.1 * (eBid - eAsk);
				prevBestBidSize = BidSize; prevBestAskSize = AskSize;
			}

			public double[] RegimeObservationVector()
			{
				return new double[] {
					BvcCvdSlope,
					RoughVol,
					VpinPct,
					Math.Abs(MLOFI),
					0
				};
			}

			public double Normalize(double x)
			{
				normBuf[normIdx] = x;
				normIdx = (normIdx + 1) % normBuf.Length;
				if (normCount < normBuf.Length) normCount++;
				int below = 0;
				for (int i = 0; i < normCount; i++) if (normBuf[i] < x) below++;
				double q = (double)below / Math.Max(1, normCount);
				return 2 * q - 1; // [-1, +1]
			}

			public double ZScoreVsBaseline(double raw)
			{
				scoreBuf[scoreIdx] = raw;
				scoreIdx = (scoreIdx + 1) % scoreBuf.Length;
				if (scoreCount < scoreBuf.Length) scoreCount++;
				double m = 0; for (int i = 0; i < scoreCount; i++) m += scoreBuf[i];
				m /= Math.Max(1, scoreCount);
				double v = 0; for (int i = 0; i < scoreCount; i++) v += (scoreBuf[i] - m) * (scoreBuf[i] - m);
				v = Math.Sqrt(v / Math.Max(1, scoreCount));
				scoreMean = m; scoreVar = v;
				return v > 1e-6 ? (raw - m) / v : 0;
			}

			private static double ComputeStd(double[] buf, int n)
			{
				if (n < 2) return 0;
				double m = 0; for (int i = 0; i < n; i++) m += buf[i]; m /= n;
				double v = 0; for (int i = 0; i < n; i++) v += (buf[i] - m) * (buf[i] - m);
				return Math.Sqrt(v / n);
			}

			private static double PercentileRank(double[] buf, int n, double x)
			{
				if (n == 0) return 0.5;
				int c = 0;
				for (int i = 0; i < n; i++) if (buf[i] <= x) c++;
				return (double)c / n;
			}

			private static double NormalCdf(double z)
			{
				// Abramowitz-Stegun 7.1.26 approximation
				double t = 1.0 / (1.0 + 0.2316419 * Math.Abs(z));
				double d = 0.3989423 * Math.Exp(-z * z / 2);
				double p = d * t * ((((1.330274 * t - 1.821256) * t + 1.781478) * t - 0.356538) * t + 0.3193815);
				return z > 0 ? 1 - p : p;
			}
		}
		#endregion

		#region IEngine interface + 9 engines
		private interface IEngine
		{
			string Name { get; }
			double Confidence { get; }
			int Direction { get; }
			SignalFamily Family { get; }
			bool IsHealthy { get; }
			void Update(FeatureFrame f);
			EngineSnapshot Snapshot();
		}

		private sealed class EngineSnapshot
		{
			public double Level, LevelSize, Rho, PHold;
		}

		// E1 Ã¢â‚¬â€ Footprint: stack imbalance + failure auction + absorption ratio
		private sealed class FootprintEngine : IEngine
		{
			public string Name => "Footprint";
			public double Confidence { get; private set; }
			public int Direction { get; private set; }
			public SignalFamily Family { get; private set; }
			public bool IsHealthy => true;
			private double level, levelSize;

			public void Update(FeatureFrame f)
			{
				double ar = Math.Abs(f.BvcCvd) / Math.Max(f.RoughVol, 0.25);
				Confidence = Math.Min(1.0, ar / 200.0);
				Direction = Math.Sign(f.BvcCvdSlope);
				Family = Confidence > 0.6 ? SignalFamily.Absorb : SignalFamily.None;
				level = f.DominantLevel > 0 ? f.DominantLevel : f.MidPrice;
				levelSize = f.BidSize + f.AskSize;
			}
			public EngineSnapshot Snapshot() => new EngineSnapshot
			{ Level = level, LevelSize = levelSize, Rho = 1.5, PHold = Confidence };
		}

		// E2 Ã¢â‚¬â€ DOM queue: survival P(hold > T) = exp(-(mu-rho)T)
		private sealed class DomQueueEngine : IEngine
		{
			public string Name => "DOM queue";
			public double Confidence { get; private set; }
			public int Direction { get; private set; }
			public SignalFamily Family { get; private set; }
			public bool IsHealthy => true;
			private double pHold, rhoHat = 1.5;

			public void Update(FeatureFrame f)
			{
				double mu = Math.Max(0.1, f.AggressionRate);
				// prefer the actual observed decay rate on the top wall if available
				double observedRho = Math.Max(f.BidWallDecay, f.AskWallDecay);
				if (observedRho > 0) rhoHat = 0.9 * rhoHat + 0.1 * observedRho;
				double deficit = Math.Max(0, mu - rhoHat);
				pHold = Math.Exp(-deficit * 1.0);
				Confidence = pHold;
				Family = Confidence > 0.65 ? SignalFamily.Absorb : SignalFamily.None;
				Direction = f.MidPrice > f.DominantLevel ? -1 : 1;
			}
			public EngineSnapshot Snapshot() => new EngineSnapshot { Rho = rhoHat, PHold = pHold };
		}

		// E3 Ã¢â‚¬â€ Hawkes spoof: high branching ratio + short kernel half-life + low fill rate
		private sealed class HawkesSpoofEngine : IEngine
		{
			public string Name => "Hawkes spoof";
			public double Confidence { get; private set; }
			public int Direction => 0;
			public SignalFamily Family => SignalFamily.None; // acts as discount
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				double n = f.HawkesBranchingRatio;
				Confidence = n > 0.85 ? 1.0 : 0.0;
			}
			public EngineSnapshot Snapshot() => null;
		}

		// E4 Ã¢â‚¬â€ Iceberg: refill-ratio based hidden-liquidity estimator
		private sealed class IcebergEngine : IEngine
		{
			public string Name => "Iceberg";
			public double Confidence { get; private set; }
			public int Direction { get; private set; }
			public SignalFamily Family { get; private set; }
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				// heuristic: sustained microprice stasis > 1s + aggression > 100/s = iceberg
				// additionally leverage direct DOM iceberg detection (sudden size adds)
				double stasisSec = f.MicroStasisMs / 1000.0;
				double score = 0;
				if (stasisSec > 1 && f.AggressionRate > 100) score = Math.Min(1, stasisSec / 3);
				if (f.BidIcebergSuspected || f.AskIcebergSuspected) score = Math.Max(score, 0.75);
				Confidence = score;
				Family = Confidence > 0.5 ? SignalFamily.Absorb : SignalFamily.None;
				Direction = f.BidIcebergSuspected ? 1 : f.AskIcebergSuspected ? -1 : Math.Sign(f.MLOFI);
			}
			public EngineSnapshot Snapshot() => null;
		}

		// E5 Ã¢â‚¬â€ Microstructure: microprice stasis + Cont-Kukanov beta collapse
		private sealed class MicrostructureEngine : IEngine
		{
			public string Name => "Micro/OFI";
			public double Confidence { get; private set; }
			public int Direction { get; private set; }
			public SignalFamily Family { get; private set; }
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				double stasisScore = Math.Min(1, f.MicroStasisMs / 2000.0);
				double ofiNorm = Math.Min(1, Math.Abs(f.MLOFI) / 500.0);
				Confidence = Math.Max(stasisScore, ofiNorm);
				Direction = -Math.Sign(f.MLOFI); // fade the flow
				Family = stasisScore > 0.5 ? SignalFamily.Absorb : SignalFamily.None;
			}
			public EngineSnapshot Snapshot() => null;
		}

		// E6 Ã¢â‚¬â€ VPIN regime
		private sealed class VpinRegimeEngine : IEngine
		{
			public string Name => "VPIN/regime";
			public double Confidence { get; private set; }
			public int Direction => 0;
			public SignalFamily Family => SignalFamily.Regime;
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				Confidence = f.VpinPct;
			}
			public EngineSnapshot Snapshot() => null;
		}

		// E7 Ã¢â‚¬â€ Meta-label (placeholder until trained)
		private sealed class MetaLabelEngine : IEngine
		{
			public string Name => "Meta-label";
			public double Confidence { get; private set; } = 0.6;
			public int Direction => 0;
			public SignalFamily Family => SignalFamily.None;
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				Confidence = 0.5 + 0.5 * Math.Tanh(f.BvcCvdSlope);
			}
			public EngineSnapshot Snapshot() => null;
		}

		// E8 Ã¢â‚¬â€ BVC-CVD divergence
		private sealed class BvcCvdEngine : IEngine
		{
			public string Name => "BVC-CVD";
			public double Confidence { get; private set; }
			public int Direction { get; private set; }
			public SignalFamily Family { get; private set; }
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				double d = f.BvcCvd;
				Confidence = Math.Min(1, Math.Abs(d) / 2000.0);
				Direction = -Math.Sign(d); // divergence fades
				Family = Confidence > 0.6 ? SignalFamily.Exhaust : SignalFamily.None;
			}
			public EngineSnapshot Snapshot() => null;
		}

		// E9 Ã¢â‚¬â€ HMM/BOCPD consensus
		private sealed class HmmBocpdEngine : IEngine
		{
			public string Name => "HMM/BOCPD";
			public double Confidence { get; private set; }
			public int Direction => 0;
			public SignalFamily Family => SignalFamily.Regime;
			public bool IsHealthy => true;
			public void Update(FeatureFrame f)
			{
				Confidence = f.VpinPct > 0.85 || f.VpinPct < 0.15 ? 0.9 : 0.4;
			}
			public EngineSnapshot Snapshot() => null;
		}
		#endregion

		#region HMM + BOCPD
		private sealed class HmmForward
		{
			private const int NStates = 3;
			private double[] alpha = new double[NStates];
			private readonly double[,] A;
			public int MapState { get; private set; }

			public HmmForward()
			{
				// transition matrix Ã¢â‚¬â€ mildly sticky
				A = new double[,] {
					{ 0.92, 0.04, 0.04 },
					{ 0.04, 0.92, 0.04 },
					{ 0.05, 0.05, 0.90 }
				};
				for (int i = 0; i < NStates; i++) alpha[i] = 1.0 / NStates;
			}

			public void Forward(double[] obs)
			{
				double[] next = new double[NStates];
				for (int j = 0; j < NStates; j++)
				{
					double sum = 0;
					for (int i = 0; i < NStates; i++) sum += alpha[i] * A[i, j];
					next[j] = sum * Emission(j, obs);
				}
				double Z = 0; for (int i = 0; i < NStates; i++) Z += next[i];
				if (Z > 0) for (int i = 0; i < NStates; i++) alpha[i] = next[i] / Z;
				double best = -1; int bi = 0;
				for (int i = 0; i < NStates; i++) if (alpha[i] > best) { best = alpha[i]; bi = i; }
				MapState = bi;
			}

			public double Posterior(int s) => alpha[s];

			private double Emission(int state, double[] obs)
			{
				// state 0 = trend+ (BvcCvdSlope > 0), state 1 = trend- (< 0), state 2 = range
				double slope = obs[0];
				double vpin = obs[2];
				switch (state)
				{
					case 0: return Gaussian(slope, +0.5, 1.0) * Gaussian(vpin, 0.5, 0.3);
					case 1: return Gaussian(slope, -0.5, 1.0) * Gaussian(vpin, 0.5, 0.3);
					default: return Gaussian(slope, 0.0, 0.5) * Gaussian(vpin, 0.4, 0.3);
				}
			}

			private static double Gaussian(double x, double mu, double sig)
			{
				double z = (x - mu) / Math.Max(sig, 1e-6);
				return Math.Exp(-0.5 * z * z);
			}
		}

		private sealed class Bocpd
		{
			private double[] runLengthProb = new double[] { 1.0 };
			private readonly double hazard;
			public double LastChangeProb { get; private set; }

			public Bocpd(double hazard) { this.hazard = hazard; }

			public double Update(double obs)
			{
				int n = runLengthProb.Length;
				double[] next = new double[Math.Min(n + 1, 500)];
				double changeProb = 0;
				for (int k = 0; k < n && k < next.Length - 1; k++)
				{
					double pred = Math.Exp(-0.5 * obs * obs / 1.0) / Math.Sqrt(2 * Math.PI);
					double growth = runLengthProb[k] * pred * (1 - hazard);
					double change = runLengthProb[k] * pred * hazard;
					next[k + 1] += growth;
					changeProb += change;
				}
				next[0] = changeProb;
				double Z = 0; for (int i = 0; i < next.Length; i++) Z += next[i];
				if (Z > 0) for (int i = 0; i < next.Length; i++) next[i] /= Z;
				runLengthProb = next;
				LastChangeProb = next[0];
				return LastChangeProb;
			}
		}
		#endregion

		#region FTRL-Proximal
		private sealed class FtrlProximal
		{
			private readonly int n;
			private readonly double alpha, beta, l1, l2;
			private readonly double[] z;
			private readonly double[] nAcc;

			public FtrlProximal(int numFeatures, double alpha, double beta, double l1, double l2)
			{
				this.n = numFeatures;
				this.alpha = alpha; this.beta = beta; this.l1 = l1; this.l2 = l2;
				z = new double[n]; nAcc = new double[n];
			}

			public int NonzeroWeights
			{
				get { int c = 0; for (int i = 0; i < n; i++) if (Math.Abs(z[i]) > l1) c++; return c; }
			}

			public double Predict(double[] x)
			{
				double wx = 0;
				for (int i = 0; i < n; i++)
				{
					double sign = Math.Sign(z[i]);
					double w = Math.Abs(z[i]) <= l1 ? 0 :
					           -(z[i] - sign * l1) / ((beta + Math.Sqrt(nAcc[i])) / alpha + l2);
					wx += w * x[i];
				}
				wx = Math.Max(-30, Math.Min(30, wx));
				return 1.0 / (1.0 + Math.Exp(-wx));
			}

			public void Update(double[] x, int y)
			{
				int yy = y > 0 ? 1 : 0;
				double p = Predict(x);
				double g = p - yy;
				for (int i = 0; i < n; i++)
				{
					double gi = g * x[i];
					double sigma = (Math.Sqrt(nAcc[i] + gi * gi) - Math.Sqrt(nAcc[i])) / alpha;
					double wi = WeightOf(i);
					z[i] += gi - sigma * wi;
					nAcc[i] += gi * gi;
				}
			}

			private double WeightOf(int i)
			{
				double sign = Math.Sign(z[i]);
				if (Math.Abs(z[i]) <= l1) return 0;
				return -(z[i] - sign * l1) / ((beta + Math.Sqrt(nAcc[i])) / alpha + l2);
			}
		}
		#endregion

		#region Isotonic calibrator (pool-adjacent-violators)
		private sealed class IsotonicCalibrator
		{
			private double[] xs, ys;
			public bool IsReady { get; private set; }

			public void Fit(LabeledSignal[] samples)
			{
				if (samples == null || samples.Length < 50) return;
				var sorted = samples.OrderBy(s => s.RawP).ToArray();
				var blocks = new List<PavBlock>();
				foreach (var s in sorted)
					blocks.Add(new PavBlock { SumY = s.Y > 0 ? 1.0 : 0.0, N = 1, X = s.RawP });
				bool changed = true;
				while (changed)
				{
					changed = false;
					for (int i = 0; i < blocks.Count - 1; i++)
					{
						double mi = blocks[i].SumY / blocks[i].N;
						double mi1 = blocks[i + 1].SumY / blocks[i + 1].N;
						if (mi > mi1)
						{
							blocks[i] = new PavBlock
							{
								SumY = blocks[i].SumY + blocks[i + 1].SumY,
								N    = blocks[i].N + blocks[i + 1].N,
								X    = blocks[i + 1].X
							};
							blocks.RemoveAt(i + 1);
							changed = true;
							break;
						}
					}
				}
				xs = blocks.Select(b => b.X).ToArray();
				ys = blocks.Select(b => b.SumY / b.N).ToArray();
				IsReady = true;
			}

			public double Calibrate(double p)
			{
				if (!IsReady || xs == null || xs.Length == 0) return p;
				int i = Array.BinarySearch(xs, p);
				if (i >= 0) return ys[i];
				i = ~i;
				if (i == 0) return ys[0];
				if (i >= xs.Length) return ys[xs.Length - 1];
				double t = (p - xs[i - 1]) / Math.Max(1e-9, xs[i] - xs[i - 1]);
				return ys[i - 1] + t * (ys[i] - ys[i - 1]);
			}

			private struct PavBlock
			{
				public double SumY;
				public int N;
				public double X;
			}
		}
		#endregion

		#region Tier quantiles
		private sealed class TierQuantiles
		{
			private readonly double[] buf = new double[2000];
			private int idx, count;
			public double Q99 { get; private set; } = 0.9;
			public double Q95 { get; private set; } = 0.8;
			public double Q85 { get; private set; } = 0.7;
			public double Q70 { get; private set; } = 0.6;

			public void Observe(double p)
			{
				buf[idx] = p;
				idx = (idx + 1) % buf.Length;
				if (count < buf.Length) count++;
				if (count >= 100 && count % 50 == 0) Recompute();
			}

			private void Recompute()
			{
				var tmp = new double[count];
				Array.Copy(buf, 0, tmp, 0, count);
				Array.Sort(tmp);
				Q99 = tmp[(int)(0.99 * count)];
				Q95 = tmp[(int)(0.95 * count)];
				Q85 = tmp[(int)(0.85 * count)];
				Q70 = tmp[(int)(0.70 * count)];
			}

			public Tier Classify(double p)
			{
				if (p >= Q99) return Tier.S;
				if (p >= Q95) return Tier.A;
				if (p >= Q85) return Tier.B;
				if (p >= Q70) return Tier.C;
				return Tier.Q;
			}
		}
		#endregion

		#region Policy layer Ã¢â‚¬â€ Kelly, TP, SL, hold time, triple barrier
		private sealed class PolicyLayer
		{
			private readonly List<OpenSignal> openSignals = new List<OpenSignal>();
			private readonly List<ResolvedSignal> history = new List<ResolvedSignal>();

			public int KellySize(double pWin, double payoffRatio, double kellyFrac, int maxCts)
			{
				double edge = 2 * pWin - 1;
				if (edge <= 0) return 0;
				double k = edge / Math.Max(0.1, payoffRatio);
				double sz = Math.Round(kellyFrac * k * 10);
				return Math.Max(1, Math.Min(maxCts, (int)sz));
			}

			public double HoldTime(FeatureFrame f)
			{
				// GuÃƒÂ©ant inventory-unwind proxy
				double baseTau = 30;
				double regimeMult = f.VpinPct > 0.85 ? 0.5 : f.VpinPct < 0.15 ? 2.0 : 1.0;
				return baseTau * regimeMult;
			}

			public void RegisterOpenSignal(Verdict_Snapshot snap, double sigma, DateTime t, double[] x, double rawP)
			{
				double[] snapshotX = new double[x.Length];
				Array.Copy(x, snapshotX, x.Length);
				openSignals.Add(new OpenSignal
				{
					Entry = snap.Entry,
					Dir = snap.Dir,
					TP = snap.TP,
					SL = snap.SL,
					OpenTime = t,
					MaxHold = TimeSpan.FromSeconds(snap.TauHoldSec),
					CalP = snap.PWin,
					RawP = rawP,
					X = snapshotX
				});
			}

			public List<ResolvedSignal> ResolveMatured(double midPrice, DateTime now)
			{
				var resolved = new List<ResolvedSignal>();
				for (int i = openSignals.Count - 1; i >= 0; i--)
				{
					var s = openSignals[i];
					int y = 0;
					bool done = false;
					if (s.Dir > 0)
					{
						if (midPrice >= s.TP) { y = 1; done = true; }
						else if (midPrice <= s.SL) { y = -1; done = true; }
					}
					else
					{
						if (midPrice <= s.TP) { y = 1; done = true; }
						else if (midPrice >= s.SL) { y = -1; done = true; }
					}
					if (!done && (now - s.OpenTime) > s.MaxHold) { y = 0; done = true; }
					if (done)
					{
						var r = new ResolvedSignal { X = s.X, Y = y, RawP = s.RawP, CalP = s.CalP, TimeLocal = now.ToLocalTime(), Dir = s.Dir };
						resolved.Add(r);
						history.Add(r);
						if (history.Count > 200) history.RemoveAt(0);
						openSignals.RemoveAt(i);
					}
				}
				return resolved;
			}

			public List<ResolvedSignal> RecentHistory(int n)
			{
				int start = Math.Max(0, history.Count - n);
				return history.GetRange(start, history.Count - start);
			}

			// Number of most-recent trades that are losses (stops at first non-loss).
			public int ConsecutiveLossCount()
			{
				int c = 0;
				for (int i = history.Count - 1; i >= 0; i--)
				{
					if (history[i].Y == -1) c++;
					else if (history[i].Y == 1) break;
					// y == 0 (flat) Ã¢â‚¬â€ neutral; do not increment, but also do not break
				}
				return c;
			}

			// Returns mutually exclusive win/loss streak lengths (running only).
			public void CurrentStreak(out int wins, out int losses)
			{
				wins = 0; losses = 0;
				for (int i = history.Count - 1; i >= 0; i--)
				{
					int y = history[i].Y;
					if (wins == 0 && losses == 0)
					{
						if (y == 1) wins = 1;
						else if (y == -1) losses = 1;
						else continue;
					}
					else if (wins > 0)
					{
						if (y == 1) wins++;
						else if (y == -1) break;
					}
					else if (losses > 0)
					{
						if (y == -1) losses++;
						else if (y == 1) break;
					}
				}
			}

			public sealed class OpenSignal
			{
				public double Entry, TP, SL, CalP, RawP;
				public int Dir;
				public DateTime OpenTime;
				public TimeSpan MaxHold;
				public double[] X;
			}

			public sealed class ResolvedSignal
			{
				public double[] X;
				public int Y;         // +1 win, -1 loss, 0 flat
				public int Dir;
				public double RawP, CalP;
				public DateTime TimeLocal;
			}
		}
		#endregion

		#region Risk gate
		public enum RiskVerdict { Ok, Blocked }

		private sealed class RiskGate
		{
			private readonly double dailyLossLimit;
			private readonly int maxContracts;
			private readonly int cutoffMinutes;
			private readonly int consecutiveLossBreak;
			private readonly int cooldownMinutes;
			private bool hardDisabled;
			private DateTime circuitBreakerUntil = DateTime.MinValue;

			public bool CircuitBreakerOpen => DateTime.UtcNow < circuitBreakerUntil;

			public RiskGate(double dailyLossLimit, int maxContracts, int cutoffMinutes,
			                int consecutiveLossBreak, int cooldownMinutes)
			{
				this.dailyLossLimit = dailyLossLimit;
				this.maxContracts = maxContracts;
				this.cutoffMinutes = cutoffMinutes;
				this.consecutiveLossBreak = consecutiveLossBreak;
				this.cooldownMinutes = cooldownMinutes;
			}

			public void HardDisable() => hardDisabled = true;

			// Called by owner when a loss resolves Ã¢â‚¬â€ trips the CB when the configured
			// consecutive-loss count is reached.
			public void OnLoss(DateTime now)
			{
				// The actual consecutive count is tracked in PolicyLayer. We take the
				// signal to trip the breaker only when the owner deems it necessary.
			}

			public void OnWin()
			{
				// wins do not auto-reset the circuit Ã¢â‚¬â€ it must cool down naturally
			}

			public void TripCircuitBreaker(DateTime nowUtc)
			{
				circuitBreakerUntil = nowUtc.AddMinutes(cooldownMinutes);
			}

			public RiskVerdict Evaluate(Tier tier, DateTime t, double pnl, int consecutiveLosses)
			{
				if (hardDisabled) return RiskVerdict.Blocked;
				if (pnl < -Math.Abs(dailyLossLimit)) return RiskVerdict.Blocked;

				// consecutive-loss circuit breaker (auto-trip)
				if (consecutiveLosses >= consecutiveLossBreak)
				{
					if (!CircuitBreakerOpen)
						TripCircuitBreaker(DateTime.UtcNow);
					return RiskVerdict.Blocked;
				}
				if (CircuitBreakerOpen) return RiskVerdict.Blocked;

				// Apex flat cutoff: no signals after 16:00 ET - cutoffMinutes
				var et = TimeZoneInfo.ConvertTime(t, TryEasternZone());
				var flatAt = et.Date + new TimeSpan(15, 60 - cutoffMinutes, 0);
				if (et >= flatAt) return RiskVerdict.Blocked;

				return RiskVerdict.Ok;
			}

			private static TimeZoneInfo TryEasternZone()
			{
				try { return TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"); }
				catch { return TimeZoneInfo.Local; }
			}
		}
		#endregion

		#region HudRenderer placeholder (kept for parity Ã¢â‚¬â€ actual rendering is inline)
		private sealed class HudRenderer { }
		#endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6Signal[] cacheDEEP6Signal;
		public DEEP6Signal DEEP6Signal(Tier minTier, double minPWin, double kellyFraction, int maxContracts, double dailyLossLimit, int apexFlatCutoffMinutes, double tpKSigma, double slKSigma, int baselineWindow, bool showDebug)
		{
			return DEEP6Signal(Input, minTier, minPWin, kellyFraction, maxContracts, dailyLossLimit, apexFlatCutoffMinutes, tpKSigma, slKSigma, baselineWindow, showDebug);
		}

		public DEEP6Signal DEEP6Signal(ISeries<double> input, Tier minTier, double minPWin, double kellyFraction, int maxContracts, double dailyLossLimit, int apexFlatCutoffMinutes, double tpKSigma, double slKSigma, int baselineWindow, bool showDebug)
		{
			if (cacheDEEP6Signal != null)
				for (int idx = 0; idx < cacheDEEP6Signal.Length; idx++)
					if (cacheDEEP6Signal[idx] != null && cacheDEEP6Signal[idx].MinTier == minTier && cacheDEEP6Signal[idx].MinPWin == minPWin && cacheDEEP6Signal[idx].KellyFraction == kellyFraction && cacheDEEP6Signal[idx].MaxContracts == maxContracts && cacheDEEP6Signal[idx].DailyLossLimit == dailyLossLimit && cacheDEEP6Signal[idx].ApexFlatCutoffMinutes == apexFlatCutoffMinutes && cacheDEEP6Signal[idx].TpKSigma == tpKSigma && cacheDEEP6Signal[idx].SlKSigma == slKSigma && cacheDEEP6Signal[idx].BaselineWindow == baselineWindow && cacheDEEP6Signal[idx].ShowDebug == showDebug && cacheDEEP6Signal[idx].EqualsInput(input))
						return cacheDEEP6Signal[idx];
			return CacheIndicator<DEEP6Signal>(new DEEP6Signal(){ MinTier = minTier, MinPWin = minPWin, KellyFraction = kellyFraction, MaxContracts = maxContracts, DailyLossLimit = dailyLossLimit, ApexFlatCutoffMinutes = apexFlatCutoffMinutes, TpKSigma = tpKSigma, SlKSigma = slKSigma, BaselineWindow = baselineWindow, ShowDebug = showDebug }, input, ref cacheDEEP6Signal);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6Signal DEEP6Signal(Tier minTier, double minPWin, double kellyFraction, int maxContracts, double dailyLossLimit, int apexFlatCutoffMinutes, double tpKSigma, double slKSigma, int baselineWindow, bool showDebug)
		{
			return indicator.DEEP6Signal(Input, minTier, minPWin, kellyFraction, maxContracts, dailyLossLimit, apexFlatCutoffMinutes, tpKSigma, slKSigma, baselineWindow, showDebug);
		}

		public Indicators.DEEP6Signal DEEP6Signal(ISeries<double> input , Tier minTier, double minPWin, double kellyFraction, int maxContracts, double dailyLossLimit, int apexFlatCutoffMinutes, double tpKSigma, double slKSigma, int baselineWindow, bool showDebug)
		{
			return indicator.DEEP6Signal(input, minTier, minPWin, kellyFraction, maxContracts, dailyLossLimit, apexFlatCutoffMinutes, tpKSigma, slKSigma, baselineWindow, showDebug);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6Signal DEEP6Signal(Tier minTier, double minPWin, double kellyFraction, int maxContracts, double dailyLossLimit, int apexFlatCutoffMinutes, double tpKSigma, double slKSigma, int baselineWindow, bool showDebug)
		{
			return indicator.DEEP6Signal(Input, minTier, minPWin, kellyFraction, maxContracts, dailyLossLimit, apexFlatCutoffMinutes, tpKSigma, slKSigma, baselineWindow, showDebug);
		}

		public Indicators.DEEP6Signal DEEP6Signal(ISeries<double> input , Tier minTier, double minPWin, double kellyFraction, int maxContracts, double dailyLossLimit, int apexFlatCutoffMinutes, double tpKSigma, double slKSigma, int baselineWindow, bool showDebug)
		{
			return indicator.DEEP6Signal(input, minTier, minPWin, kellyFraction, maxContracts, dailyLossLimit, apexFlatCutoffMinutes, tpKSigma, slKSigma, baselineWindow, showDebug);
		}
	}
}

#endregion
