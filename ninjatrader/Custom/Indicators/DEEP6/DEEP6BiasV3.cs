#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = SharpDX.Direct2D1.Brush;
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
	public class DEEP6BiasV3 : Indicator
	{
		#region Layout constants
		private const float HudW			= 316f;
		private const float HudH			= 146f;
		private const float Corner			= 6f;
		private const float PadL			= 14f;
		private const float PadR			= 14f;

		// Row Y offsets from panel top
		private const float RowDir			= 10f;		// Direction + Mode
		private const float RowGauge		= 36f;		// Score gauge
		private const float RowConf			= 54f;		// Confidence bar
		private const float RowSession		= 70f;		// Session · XAMD
		private const float RowDomain		= 88f;		// Domain score pips
		private const float RowSep			= 112f;		// Separator line
		private const float RowFooter		= 118f;		// Footer / stale

		// Gauge dimensions
		private const float GaugeTrackW		= 176f;
		private const float GaugeTrackH		= 10f;
		private const float ConfTrackW		= 136f;
		private const float ConfTrackH		= 8f;
		private const float LabelColW		= 44f;
		private const int	ScoreMin		= -12;
		private const int	ScoreMax		= 12;
		private const int	ScoreRange		= 24;

		// Domain pip layout
		private const float DotRadius		= 5f;
		private const float DomainSpacing	= 52f;
		#endregion

		#region State fields
		private readonly object _lock = new object();
		private Timer _timer;
		private BiasV3Snapshot _snap;
		private DateTime _lastWriteUtc = DateTime.MinValue;
		private bool _wasStale;
		#endregion

		#region TextFormat fields (not RT-dependent)
		private TextFormat _fmtHero;
		private TextFormat _fmtArrow;
		private TextFormat _fmtBody;
		private TextFormat _fmtData;
		private TextFormat _fmtLabel;
		private TextFormat _fmtDomLabel;
		private TextFormat _fmtDomScore;
		private bool _formatsReady;
		#endregion

		#region Brush fields (RT-dependent)
		private SolidColorBrush _brBg;
		private SolidColorBrush _brBorder;
		private SolidColorBrush _brText;
		private SolidColorBrush _brMuted;
		private SolidColorBrush _brDim;
		private SolidColorBrush _brBull;
		private SolidColorBrush _brBear;
		private SolidColorBrush _brNeutral;
		private SolidColorBrush _brGo;
		private SolidColorBrush _brCaution;
		private SolidColorBrush _brStop;
		private SolidColorBrush _brStale;
		private SolidColorBrush _brTrack;
		private SolidColorBrush _brSep;
		private bool _brushesReady;
		#endregion

		#region Lifecycle
		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name						= "DEEP6BiasV3";
				Description					= "DEEP6 Bias v3 — institutional HUD overlay.";
				Calculate					= Calculate.OnBarClose;
				IsOverlay					= true;
				DrawOnPricePanel			= true;
				DisplayInDataBox			= false;
				PaintPriceMarkers			= false;
				IsSuspendedWhileInactive	= true;
				ScaleJustification			= ScaleJustification.Right;
				BarsRequiredToPlot			= 0;

				JsonFilePath				= @"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\bias_v3.json";
				RefreshSeconds				= 5;
				StaleThresholdSeconds		= 30;
				HudOffsetX					= 15;
				HudOffsetY					= 15;
				HudOpacity					= 0.92;
			}
			else if (State == State.DataLoaded)
			{
				BuildTextFormats();
				_timer = new Timer(OnTimerTick, null, 500, Math.Max(1, RefreshSeconds) * 1000);
			}
			else if (State == State.Terminated)
			{
				if (_timer != null) { _timer.Dispose(); _timer = null; }
				ReleaseBrushes();
				ReleaseTextFormats();
			}
		}

		protected override void OnBarUpdate() { }
		#endregion

		#region TextFormat lifecycle
		private void BuildTextFormats()
		{
			try
			{
				var dw = NinjaTrader.Core.Globals.DirectWriteFactory;
				_fmtHero		= new TextFormat(dw, "Segoe UI", FontWeight.SemiBold, FontStyle.Normal, FontStretch.Normal, 15f);
				_fmtArrow		= new TextFormat(dw, "Segoe UI Symbol", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 17f);
				_fmtBody		= new TextFormat(dw, "Segoe UI", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 11f);
				_fmtData		= new TextFormat(dw, "Consolas", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 11f);
				_fmtLabel		= new TextFormat(dw, "Segoe UI", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 9f);
				_fmtDomLabel	= new TextFormat(dw, "Segoe UI", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 8f);
				_fmtDomScore	= new TextFormat(dw, "Consolas", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 9f);

				_fmtHero.TextAlignment		= TextAlignment.Leading;
				_fmtArrow.TextAlignment		= TextAlignment.Leading;
				_fmtBody.TextAlignment		= TextAlignment.Leading;
				_fmtData.TextAlignment		= TextAlignment.Leading;
				_fmtLabel.TextAlignment		= TextAlignment.Leading;
				_fmtDomLabel.TextAlignment	= TextAlignment.Center;
				_fmtDomScore.TextAlignment	= TextAlignment.Center;

				_formatsReady = true;
			}
			catch { _formatsReady = false; }
		}

		private void ReleaseTextFormats()
		{
			_formatsReady = false;
			SafeDispose(ref _fmtHero);
			SafeDispose(ref _fmtArrow);
			SafeDispose(ref _fmtBody);
			SafeDispose(ref _fmtData);
			SafeDispose(ref _fmtLabel);
			SafeDispose(ref _fmtDomLabel);
			SafeDispose(ref _fmtDomScore);
		}
		#endregion

		#region Brush lifecycle (RT-dependent)
		public override void OnRenderTargetChanged()
		{
			ReleaseBrushes();
			if (RenderTarget == null) return;

			try
			{
				float alpha = ClampF((float)HudOpacity, 0.1f, 1f);

				_brBg		= MakeBrush(0.071f, 0.078f, 0.102f, alpha);
				_brBorder	= MakeBrush(0.20f,  0.22f,  0.26f,  0.80f);
				_brText		= MakeBrush(0.949f, 0.957f, 0.973f, 1f);
				_brMuted	= MakeBrush(0.608f, 0.639f, 0.682f, 1f);
				_brDim		= MakeBrush(0.353f, 0.388f, 0.431f, 1f);
				_brBull		= MakeBrush(0f,     0.784f, 0.325f, 1f);		// #00C853
				_brBear		= MakeBrush(1f,     0.090f, 0.267f, 1f);		// #FF1744
				_brNeutral	= MakeBrush(0.471f, 0.565f, 0.612f, 1f);		// #78909C
				_brGo		= MakeBrush(0f,     0.784f, 0.325f, 1f);		// #00C853
				_brCaution	= MakeBrush(0.961f, 0.678f, 0.149f, 1f);		// #F5AD26
				_brStop		= MakeBrush(1f,     0.231f, 0.188f, 1f);		// #FF3B30
				_brStale	= MakeBrush(0.980f, 0.804f, 0.275f, 1f);		// #FACD46
				_brTrack	= MakeBrush(0.12f,  0.13f,  0.16f,  1f);
				_brSep		= MakeBrush(0.20f,  0.22f,  0.26f,  0.50f);

				_brushesReady = true;
			}
			catch
			{
				_brushesReady = false;
				ReleaseBrushes();
			}
		}

		private SolidColorBrush MakeBrush(float r, float g, float b, float a)
		{
			return new SolidColorBrush(RenderTarget, new Color4(r, g, b, a));
		}

		private void ReleaseBrushes()
		{
			_brushesReady = false;
			SafeDispose(ref _brBg);
			SafeDispose(ref _brBorder);
			SafeDispose(ref _brText);
			SafeDispose(ref _brMuted);
			SafeDispose(ref _brDim);
			SafeDispose(ref _brBull);
			SafeDispose(ref _brBear);
			SafeDispose(ref _brNeutral);
			SafeDispose(ref _brGo);
			SafeDispose(ref _brCaution);
			SafeDispose(ref _brStop);
			SafeDispose(ref _brStale);
			SafeDispose(ref _brTrack);
			SafeDispose(ref _brSep);
		}
		#endregion

		#region JSON reader (timer thread)
		private void OnTimerTick(object state)
		{
			try { ReadJson(); }
			catch { /* swallow — timer must not crash */ }
		}

		private void ReadJson()
		{
			string path = JsonFilePath;
			if (string.IsNullOrEmpty(path) || !File.Exists(path))
			{
				bool changed;
				lock (_lock)
				{
					changed = _snap != null;
					_snap = null;
					_lastWriteUtc = DateTime.MinValue;
				}
				if (changed) RequestRepaint();
				return;
			}

			DateTime writeUtc = File.GetLastWriteTimeUtc(path);
			bool fileChanged = writeUtc != _lastWriteUtc;
			BiasV3Snapshot parsed = null;

			if (fileChanged)
			{
				var serializer = new JavaScriptSerializer();
				using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
				using (var sr = new StreamReader(fs))
					parsed = serializer.Deserialize<BiasV3Snapshot>(sr.ReadToEnd());
				_lastWriteUtc = writeUtc;
			}

			bool needRepaint = fileChanged;
			lock (_lock)
			{
				if (parsed != null)
					_snap = parsed;

				if (_snap != null)
				{
					int age = Math.Max(0, (int)(DateTime.UtcNow - _lastWriteUtc).TotalSeconds);
					bool nowStale = age > Math.Max(1, StaleThresholdSeconds);
					_snap.file_age_seconds = age;
					_snap.file_write_utc = _lastWriteUtc;
					_snap.stale = nowStale;

					// Repaint on stale transition or while stale (to update counter)
					if (nowStale != _wasStale || nowStale)
						needRepaint = true;
					_wasStale = nowStale;
				}
			}

			if (needRepaint)
				RequestRepaint();
		}

		private void RequestRepaint()
		{
			if (ChartControl != null)
				ChartControl.Dispatcher.BeginInvoke(new Action(() =>
				{
					try { ChartControl.InvalidateVisual(); }
					catch { }
				}));
		}
		#endregion

		#region OnRender — main entry
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);

			if (!_brushesReady || !_formatsReady || RenderTarget == null || RenderTarget.IsDisposed || ChartPanel == null)
				return;

			BiasV3Snapshot snap;
			lock (_lock) { snap = _snap; }

			float ox = (float)ChartPanel.X + HudOffsetX;
			float oy = (float)ChartPanel.Y + HudOffsetY;

			// ── Panel background with rounded corners ──
			RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;
			var panel = new RoundedRectangle
			{
				Rect = new RectangleF(ox, oy, ox + HudW, oy + HudH),
				RadiusX = Corner,
				RadiusY = Corner
			};
			RenderTarget.FillRoundedRectangle(panel, _brBg);
			RenderTarget.DrawRoundedRectangle(panel, _brBorder, 1f);

			if (snap == null)
			{
				PaintWaiting(ox, oy);
				return;
			}

			PaintDirection(ox, oy, snap);
			PaintScoreGauge(ox, oy, snap);
			PaintConfidence(ox, oy, snap);
			PaintSession(ox, oy, snap);
			PaintDomains(ox, oy, snap);

			// ── Separator ──
			float sepL = ox + PadL;
			float sepR = ox + HudW - PadR;
			RenderTarget.DrawLine(new Vector2(sepL, oy + RowSep), new Vector2(sepR, oy + RowSep), _brSep, 0.5f);

			PaintFooter(ox, oy, snap);
		}
		#endregion

		#region Paint: Waiting state
		private void PaintWaiting(float ox, float oy)
		{
			DrawText(ox + PadL, oy + 32f, "BIAS ENGINE", _fmtHero, _brDim, 200f, 22f);
			DrawText(ox + PadL, oy + 56f, "Waiting for data\u2026", _fmtBody, _brDim, 200f, 16f);

			string fileName = string.Empty;
			try { fileName = Path.GetFileName(JsonFilePath ?? string.Empty); }
			catch { }
			if (!string.IsNullOrEmpty(fileName))
				DrawText(ox + PadL, oy + 78f, fileName, _fmtLabel, _brDim, HudW - PadL - PadR, 14f);
		}
		#endregion

		#region Paint: Row 1 — Direction + Mode
		private void PaintDirection(float ox, float oy, BiasV3Snapshot s)
		{
			float y = oy + RowDir;
			SolidColorBrush dirBr = GetDirectionBrush(s);
			string arrow = GetArrowGlyph(s);
			string label = Str(s.bias_label);

			// Arrow glyph
			DrawText(ox + PadL, y - 1f, arrow, _fmtArrow, dirBr, 30f, 24f);

			// Bias label
			float labelX = ox + PadL + (arrow.Length > 1 ? 30f : 22f);
			DrawText(labelX, y + 1f, label, _fmtHero, dirBr, 170f, 22f);

			// Mode dot (right side)
			SolidColorBrush modeBr = GetModeBrush(s);
			float dotCx = ox + HudW - PadR - 56f;
			float dotCy = y + 11f;
			var dot = new Ellipse(new Vector2(dotCx, dotCy), 5f, 5f);
			RenderTarget.FillEllipse(dot, modeBr);
			RenderTarget.DrawEllipse(dot, _brBorder, 0.5f);

			// Mode text
			DrawText(dotCx + 10f, y + 3f, Str(s.mode), _fmtBody, modeBr, 46f, 16f);
		}
		#endregion

		#region Paint: Row 2 — Score gauge
		private void PaintScoreGauge(float ox, float oy, BiasV3Snapshot s)
		{
			float y = oy + RowGauge;
			float gaugeX = ox + PadL + LabelColW + 4f;
			float gaugeY = y + 2f;

			// Label
			DrawText(ox + PadL, y, "SCORE", _fmtLabel, _brMuted, LabelColW, 14f);

			// Track
			RenderTarget.AntialiasMode = AntialiasMode.Aliased;
			float trackL = gaugeX;
			float trackT = gaugeY;
			float trackR = gaugeX + GaugeTrackW;
			float trackB = gaugeY + GaugeTrackH;
			RenderTarget.FillRectangle(new RectangleF(trackL, trackT, trackR, trackB), _brTrack);

			// Fill from center
			int score = ClampI(s.bias_score, ScoreMin, ScoreMax);
			float center = gaugeX + GaugeTrackW / 2f;
			float pxPerUnit = GaugeTrackW / (float)ScoreRange;

			if (score != 0)
			{
				SolidColorBrush fillBr = score > 0 ? _brBull : _brBear;
				float fillL, fillR;
				if (score > 0)
				{
					fillL = center;
					fillR = center + score * pxPerUnit;
				}
				else
				{
					fillL = center + score * pxPerUnit;
					fillR = center;
				}
				RenderTarget.FillRectangle(new RectangleF(fillL, trackT + 1f, fillR, trackB - 1f), fillBr);
			}

			// Center tick mark
			RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;
			RenderTarget.DrawLine(new Vector2(center, trackT), new Vector2(center, trackB), _brMuted, 1f);

			// Score text
			SolidColorBrush scoreBr = score > 0 ? _brBull : score < 0 ? _brBear : _brNeutral;
			string scoreTxt = score > 0 ? "+" + score.ToString(CultureInfo.InvariantCulture) : score.ToString(CultureInfo.InvariantCulture);
			DrawText(trackR + 8f, y, scoreTxt, _fmtData, scoreBr, 40f, 14f);
		}
		#endregion

		#region Paint: Row 3 — Confidence bar
		private void PaintConfidence(float ox, float oy, BiasV3Snapshot s)
		{
			float y = oy + RowConf;
			float barX = ox + PadL + LabelColW + 4f;
			float barY = y + 2f;

			// Label
			DrawText(ox + PadL, y, "CONF", _fmtLabel, _brMuted, LabelColW, 12f);

			// Track
			RenderTarget.AntialiasMode = AntialiasMode.Aliased;
			float trackL = barX;
			float trackT = barY;
			float trackR = barX + ConfTrackW;
			float trackB = barY + ConfTrackH;
			RenderTarget.FillRectangle(new RectangleF(trackL, trackT, trackR, trackB), _brTrack);

			// Fill
			float pct = ClampF(s.confidence_pct / 100f, 0f, 1f);
			if (pct > 0.01f)
			{
				SolidColorBrush fillBr = GetDirectionBrush(s);
				float fillR = trackL + pct * ConfTrackW;
				RenderTarget.FillRectangle(new RectangleF(trackL, trackT + 1f, fillR, trackB - 1f), fillBr);
			}
			RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

			// Percentage text
			string pctTxt = s.confidence_pct.ToString(CultureInfo.InvariantCulture) + "%";
			DrawText(trackR + 8f, y, pctTxt, _fmtData, _brText, 40f, 12f);
		}
		#endregion

		#region Paint: Row 4 — Session · XAMD
		private void PaintSession(float ox, float oy, BiasV3Snapshot s)
		{
			float y = oy + RowSession;
			string text = Str(s.session_label) + "  \u00B7  " + Str(s.xamd_phase);
			DrawText(ox + PadL, y, text, _fmtBody, _brText, HudW - PadL - PadR, 16f);
		}
		#endregion

		#region Paint: Row 5 — Domain score pips
		private void PaintDomains(float ox, float oy, BiasV3Snapshot s)
		{
			float y = oy + RowDomain;
			float contentW = HudW - PadL - PadR;

			string[] labels = { "ICT", "MAC", "FLW", "KRN", "GEX" };
			int[] scores;
			if (s.domain_scores != null)
				scores = new int[] { s.domain_scores.ict, s.domain_scores.macro, s.domain_scores.flow,
									 s.domain_scores.kronos, s.domain_scores.gex };
			else
				scores = new int[] { 0, 0, 0, 0, 0 };

			// Center 5 pips across content width
			float totalSpan = (labels.Length - 1) * DomainSpacing;
			float startX = ox + PadL + (contentW - totalSpan) / 2f;

			for (int i = 0; i < labels.Length; i++)
			{
				float cx = startX + i * DomainSpacing;
				int val = scores[i];

				// Colored dot
				SolidColorBrush dotBr = val > 0 ? _brBull : val < 0 ? _brBear : _brDim;
				var pip = new Ellipse(new Vector2(cx, y + DotRadius), DotRadius, DotRadius);
				RenderTarget.FillEllipse(pip, dotBr);

				// Label below dot
				DrawTextCentered(cx - 20f, y + DotRadius * 2f + 2f, 40f, 10f, labels[i], _fmtDomLabel, _brMuted);

				// Score value below label
				string valTxt = val > 0 ? "+" + val.ToString(CultureInfo.InvariantCulture) : val.ToString(CultureInfo.InvariantCulture);
				DrawTextCentered(cx - 20f, y + DotRadius * 2f + 11f, 40f, 10f, valTxt, _fmtDomScore, dotBr);
			}
		}
		#endregion

		#region Paint: Row 6 — Footer / Stale
		private void PaintFooter(float ox, float oy, BiasV3Snapshot s)
		{
			float y = oy + RowFooter;
			float maxW = HudW - PadL - PadR;

			if (s.stale)
			{
				string staleTxt = string.Format(CultureInfo.InvariantCulture, "\u26A0 STALE ({0}s)", s.file_age_seconds);
				DrawText(ox + PadL, y, staleTxt, _fmtLabel, _brStale, maxW, 14f);
			}
			else
			{
				string footer = Str(s.version) + "  \u00B7  " + Str(s.mode_reason);
				DrawText(ox + PadL, y, footer, _fmtLabel, _brDim, maxW, 14f);
			}
		}
		#endregion

		#region Text drawing helpers
		private void DrawText(float x, float y, string text, TextFormat fmt, Brush brush, float maxW, float maxH)
		{
			if (string.IsNullOrEmpty(text) || fmt == null || brush == null) return;
			using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, fmt, maxW, maxH))
				RenderTarget.DrawTextLayout(new Vector2(x, y), layout, brush);
		}

		private void DrawTextCentered(float slotX, float slotY, float slotW, float slotH, string text, TextFormat fmt, Brush brush)
		{
			if (string.IsNullOrEmpty(text) || fmt == null || brush == null) return;
			using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, fmt, slotW, slotH))
			{
				float textW = layout.Metrics.Width;
				float dx = slotX + (slotW - textW) / 2f;
				RenderTarget.DrawTextLayout(new Vector2(dx, slotY), layout, brush);
			}
		}
		#endregion

		#region Brush selection helpers
		private SolidColorBrush GetDirectionBrush(BiasV3Snapshot s)
		{
			string t = Str(s.bias_label).ToUpperInvariant();
			if (t.Contains("BULL") || s.bias_score > 0) return _brBull;
			if (t.Contains("BEAR") || s.bias_score < 0) return _brBear;
			return _brNeutral;
		}

		private SolidColorBrush GetModeBrush(BiasV3Snapshot s)
		{
			string t = Str(s.mode).ToUpperInvariant();
			if (t == "GO")   return _brGo;
			if (t == "STOP") return _brStop;
			return _brCaution;
		}

		private string GetArrowGlyph(BiasV3Snapshot s)
		{
			string t = Str(s.bias_label).ToUpperInvariant();
			bool strong = t.Contains("STRONG");
			if (t.Contains("BULL") || s.bias_score > 0)
				return strong ? "\u25B2\u25B2" : "\u25B2";
			if (t.Contains("BEAR") || s.bias_score < 0)
				return strong ? "\u25BC\u25BC" : "\u25BC";
			return "\u25CF";
		}
		#endregion

		#region Utility
		private static string Str(string v)
		{
			return string.IsNullOrEmpty(v) ? "\u2014" : v;
		}

		private static int ClampI(int v, int lo, int hi)
		{
			return v < lo ? lo : v > hi ? hi : v;
		}

		private static float ClampF(float v, float lo, float hi)
		{
			return v < lo ? lo : v > hi ? hi : v;
		}

		private static void SafeDispose<T>(ref T resource) where T : class, IDisposable
		{
			if (resource != null)
			{
				try { resource.Dispose(); }
				catch { }
				resource = null;
			}
		}
		#endregion

		#region Properties
		[NinjaScriptProperty]
		[Display(Name = "JSON File Path", GroupName = "1. Data", Order = 1)]
		public string JsonFilePath { get; set; }

		[NinjaScriptProperty]
		[Range(1, 60)]
		[Display(Name = "Refresh Seconds", GroupName = "1. Data", Order = 2)]
		public int RefreshSeconds { get; set; }

		[NinjaScriptProperty]
		[Range(1, 300)]
		[Display(Name = "Stale Threshold Seconds", GroupName = "1. Data", Order = 3)]
		public int StaleThresholdSeconds { get; set; }

		[NinjaScriptProperty]
		[Range(0, 400)]
		[Display(Name = "HUD Offset X", GroupName = "2. Layout", Order = 1)]
		public int HudOffsetX { get; set; }

		[NinjaScriptProperty]
		[Range(0, 400)]
		[Display(Name = "HUD Offset Y", GroupName = "2. Layout", Order = 2)]
		public int HudOffsetY { get; set; }

		[NinjaScriptProperty]
		[Range(0.10, 1.00)]
		[Display(Name = "HUD Opacity", GroupName = "2. Layout", Order = 3)]
		public double HudOpacity { get; set; }
		#endregion
	}

	#region Data model
	public class BiasV3Snapshot
	{
		public string bias_label { get; set; }
		public int bias_score { get; set; }
		public double confidence { get; set; }
		public int confidence_pct { get; set; }
		public string mode { get; set; }
		public string mode_reason { get; set; }
		public string session_label { get; set; }
		public string xamd_phase { get; set; }
		public BiasV3DomainScores domain_scores { get; set; }
		public int setup_quality { get; set; }
		public double updated_ts { get; set; }
		public string version { get; set; }

		// Computed by indicator
		public bool stale { get; set; }
		public int file_age_seconds { get; set; }
		public DateTime file_write_utc { get; set; }
	}

	public class BiasV3DomainScores
	{
		public int ict { get; set; }
		public int macro { get; set; }
		public int flow { get; set; }
		public int kronos { get; set; }
		public int gex { get; set; }
	}
	#endregion
}
