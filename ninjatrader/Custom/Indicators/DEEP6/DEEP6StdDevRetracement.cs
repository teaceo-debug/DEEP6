// DEEP6StdDevRetracement — Standard Deviation Retracement Levels
//
// Plots horizontal lines at configurable standard-deviation multiples from a
// rolling SMA mean.  The 0.705 (1/sqrt2) level is highlighted in gold — a
// statistically significant half-variance retracement point.
//
// Visual hierarchy:
//   Mean (0)      solid white  2 px
//   +/-0.705      solid gold   2 px
//   Integer SDs   dashed gray  1 px
//   Fractional    dashed gray  1 px
//
// Install: copy to
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\
// then F5 in the NinjaScript Editor.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Windows.Media;
using System.Xml.Serialization;
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
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
	public class DEEP6StdDevRetracement : Indicator
	{
		#region Fields

		private SMA    _sma;
		private StdDev _stdDev;

		private double[] _multiples;   // parsed SD multiples, sorted ascending
		private double[] _prices;      // computed price for each multiple on current bar

		// SharpDX — brushes (render-target-dependent)
		private Brush _lineBrush;
		private Brush _meanBrush;
		private Brush _goldBrush;
		private Brush _textBrush;
		private Brush _goldTextBrush;
		private Brush _bgBrush;
		private bool  _brushesReady;

		// SharpDX — factory resources (render-target-independent)
		private TextFormat  _labelFmt;
		private StrokeStyle _dashStyle;

		#endregion

		#region Lifecycle

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description          = "Standard Deviation Retracement — horizontal levels at SD multiples from rolling mean";
				Name                 = "DEEP6 SD Retracement";
				Calculate            = Calculate.OnBarClose;
				IsOverlay            = true;
				DisplayInDataBox     = false;
				DrawOnPricePanel     = true;
				IsSuspendedWhileInactive = true;
				BarsRequiredToPlot   = 0;

				Period     = 20;
				SDLevels   = "-4,-3.5,-3.25,-3,-2.5,-2,-1,-0.5,0,0.5,0.705,1,2,2.5,3,3.25,3.5,4";
				LineWidth  = 1;
				LabelSize  = 10;
				ShowLabels = true;
			}
			else if (State == State.Configure)
			{
				// Factory resources — survive render-target changes
				_labelFmt = new TextFormat(
					NinjaTrader.Core.Globals.DirectWriteFactory,
					"Consolas",
					SharpDX.DirectWrite.FontWeight.Medium,
					SharpDX.DirectWrite.FontStyle.Normal,
					LabelSize)
				{
					TextAlignment      = TextAlignment.Leading,
					ParagraphAlignment = ParagraphAlignment.Center
				};

				_dashStyle = new StrokeStyle(
					NinjaTrader.Core.Globals.D2DFactory,
					new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom },
					new float[] { 4f, 3f });
			}
			else if (State == State.DataLoaded)
			{
				_sma    = SMA(Close, Period);
				_stdDev = StdDev(Close, Period);
				ParseLevels();
			}
			else if (State == State.Terminated)
			{
				DisposeDx();
			}
		}

		#endregion

		#region Data

		private void ParseLevels()
		{
			var list = new List<double>();
			if (!string.IsNullOrWhiteSpace(SDLevels))
			{
				foreach (string tok in SDLevels.Split(','))
				{
					if (double.TryParse(tok.Trim(), NumberStyles.Float,
						CultureInfo.InvariantCulture, out double v))
						list.Add(v);
				}
			}
			list.Sort();
			_multiples = list.ToArray();
			_prices    = new double[_multiples.Length];
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < Period) return;

			double mean = _sma[0];
			double sd   = _stdDev[0];

			for (int i = 0; i < _multiples.Length; i++)
				_prices[i] = mean + _multiples[i] * sd;
		}

		#endregion

		#region Rendering

		public override void OnRenderTargetChanged()
		{
			DisposeBrushes();

			if (RenderTarget == null) return;

			_lineBrush     = new SolidColorBrush(RenderTarget, new Color4(0.608f, 0.639f, 0.682f, 0.70f));   // #9BA3AE @ 70%
			_meanBrush     = new SolidColorBrush(RenderTarget, new Color4(0.949f, 0.957f, 0.973f, 0.90f));   // #F2F4F8 @ 90%
			_goldBrush     = new SolidColorBrush(RenderTarget, new Color4(1f, 0.824f, 0.247f, 1f));          // #FFD23F
			_textBrush     = new SolidColorBrush(RenderTarget, new Color4(0.949f, 0.957f, 0.973f, 1f));      // #F2F4F8
			_goldTextBrush = new SolidColorBrush(RenderTarget, new Color4(1f, 0.824f, 0.247f, 1f));          // #FFD23F
			_bgBrush       = new SolidColorBrush(RenderTarget, new Color4(0.055f, 0.063f, 0.078f, 0.85f));   // #0E1014 @ 85%

			_brushesReady = true;
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);

			if (!_brushesReady || RenderTarget == null)  return;
			if (_prices == null || _multiples == null)    return;
			if (CurrentBar < Period)                      return;

			float xL = ChartPanel.X;
			float xR = ChartPanel.X + ChartPanel.W;
			float yT = ChartPanel.Y;
			float yB = ChartPanel.Y + ChartPanel.H;

			RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

			for (int i = 0; i < _multiples.Length; i++)
			{
				float y = chartScale.GetYByValue(_prices[i]);
				if (y < yT - 5f || y > yB + 5f) continue;

				double m       = _multiples[i];
				bool isMean    = Math.Abs(m) < 0.0001;
				bool isGold    = Math.Abs(Math.Abs(m) - 0.705) < 0.001;

				// Visual hierarchy: brush, width, stroke style
				Brush       brush;
				float       w;
				StrokeStyle style;

				if (isGold)
				{
					brush = _goldBrush;
					w     = LineWidth + 1;
					style = null;
				}
				else if (isMean)
				{
					brush = _meanBrush;
					w     = LineWidth + 1;
					style = null;
				}
				else
				{
					brush = _lineBrush;
					w     = LineWidth;
					style = _dashStyle;
				}

				// --- horizontal line ---
				var p1 = new Vector2(xL, y);
				var p2 = new Vector2(xR, y);

				if (style != null)
					RenderTarget.DrawLine(p1, p2, brush, w, style);
				else
					RenderTarget.DrawLine(p1, p2, brush, w);

				// --- right-aligned label ---
				if (!ShowLabels) continue;

				string label = FormatLabel(m);
				Brush  tb    = isGold ? _goldTextBrush : _textBrush;

				using (var layout = new TextLayout(
					NinjaTrader.Core.Globals.DirectWriteFactory,
					label, _labelFmt, 100f, 20f))
				{
					float tw = layout.Metrics.Width;
					float th = layout.Metrics.Height;
					float lx = xR - tw - 12f;
					float ly = y - th / 2f;

					// background pill
					var bg = new SharpDX.RectangleF(lx - 4f, ly - 1f, tw + 8f, th + 2f);
					RenderTarget.FillRectangle(bg, _bgBrush);

					// text
					RenderTarget.DrawTextLayout(new Vector2(lx, ly), layout, tb);
				}
			}
		}

		private static string FormatLabel(double val)
		{
			if (Math.Abs(val) < 0.0001) return "0";
			// Keep significant digits, trim trailing zeros
			string s = val.ToString("G5", CultureInfo.InvariantCulture);
			return s;
		}

		#endregion

		#region Disposal

		private void DisposeBrushes()
		{
			_brushesReady = false;
			SafeDispose(ref _lineBrush);
			SafeDispose(ref _meanBrush);
			SafeDispose(ref _goldBrush);
			SafeDispose(ref _textBrush);
			SafeDispose(ref _goldTextBrush);
			SafeDispose(ref _bgBrush);
		}

		private void DisposeDx()
		{
			DisposeBrushes();
			SafeDispose(ref _labelFmt);
			SafeDispose(ref _dashStyle);
		}

		private static void SafeDispose<T>(ref T res) where T : class, IDisposable
		{
			if (res == null) return;
			try
			{
				var d = res as SharpDX.DisposeBase;
				if (d != null && d.IsDisposed) { res = null; return; }
				res.Dispose();
			}
			catch { }
			res = null;
		}

		#endregion

		#region Properties

		[NinjaScriptProperty]
		[Range(2, int.MaxValue)]
		[Display(Name = "Period", Description = "Lookback period for SMA and StdDev calculation",
			Order = 1, GroupName = "Parameters")]
		public int Period { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "SD Levels", Description = "Comma-separated SD multiples (e.g. -4,-3,-2,-1,0,0.705,1,2,3,4)",
			Order = 2, GroupName = "Parameters")]
		public string SDLevels { get; set; }

		[NinjaScriptProperty]
		[Range(1, 5)]
		[Display(Name = "Line Width", Order = 1, GroupName = "Visual")]
		public int LineWidth { get; set; }

		[NinjaScriptProperty]
		[Range(7, 16)]
		[Display(Name = "Label Size", Description = "Font size for SD labels (pt)",
			Order = 2, GroupName = "Visual")]
		public int LabelSize { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show Labels", Order = 3, GroupName = "Visual")]
		public bool ShowLabels { get; set; }

		#endregion
	}
}
