// DEEP6 Low Volume Node (LVN) Finder — Drawing Tool
//
// Draw a range on the chart (click start, drag to end).
// Builds a volume profile within that range and marks the low-volume
// price levels — the thin spots where price moves fast through.
//
// LVN lines extend right so you can see where future price may accelerate.
//
// Install: copy to %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\DrawingTools\
// then F5 in the NinjaScript Editor.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
#endregion

namespace NinjaTrader.NinjaScript.DrawingTools
{
	/// <summary>
	/// Low Volume Node finder drawing tool.
	/// Two-anchor: define a time/price range, tool builds a volume profile
	/// and draws horizontal lines at local volume minima (LVN levels).
	/// </summary>
	public class DEEP6LowVolumeNodeTool : FibonacciRetracements
	{
		#region Fields

		// Cached LVN calculation
		private readonly List<double> _lvnPrices  = new List<double>();
		private double   _lowestLvnPrice;
		private DateTime _cacheStartTime;
		private DateTime _cacheEndTime;
		private double   _cacheStartPrice;
		private double   _cacheEndPrice;

		// Profile workspace
		private double[] _profileVol;
		private double[] _profilePrice;

		// Brushes
		private SharpDX.Direct2D1.SolidColorBrush _lvnBrush;
		private SharpDX.Direct2D1.SolidColorBrush _lowestLvnBrush;
		private SharpDX.Direct2D1.SolidColorBrush _textBrush;
		private SharpDX.Direct2D1.SolidColorBrush _bgBrush;
		private SharpDX.Direct2D1.StrokeStyle     _lvnDash;
		private SharpDX.DirectWrite.TextFormat     _labelFmt;
		private bool _dxReady;

		#endregion

		#region Lifecycle

		protected override void OnStateChange()
		{
			base.OnStateChange();

			if (State == State.SetDefaults)
			{
				Name                 = "LVN Finder";
				IsExtendedLinesRight = true;
				PriceLevelOpacity    = 0;

				ProfileRows = 200;
				LvnStrength = 15;
			}
			else if (State == State.Configure)
			{
				// We don't use static PriceLevels — lines are data-driven
				PriceLevels.Clear();

				_labelFmt = new SharpDX.DirectWrite.TextFormat(
					Core.Globals.DirectWriteFactory,
					"Consolas",
					SharpDX.DirectWrite.FontWeight.Medium,
					SharpDX.DirectWrite.FontStyle.Normal,
					10f);

				_lvnDash = new SharpDX.Direct2D1.StrokeStyle(
					Core.Globals.D2DFactory,
					new SharpDX.Direct2D1.StrokeStyleProperties
					{
						DashStyle = SharpDX.Direct2D1.DashStyle.Custom
					},
					new float[] { 6f, 3f });
			}
			else if (State == State.Terminated)
			{
				DisposeDx();
			}
		}

		public override void OnRenderTargetChanged()
		{
			DisposeBrushes();
			if (RenderTarget == null) return;

			// Teal/cyan for LVN lines (institutional, stands out on dark bg)
			_lvnBrush       = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
				new SharpDX.Color4(0.118f, 0.565f, 1f, 0.85f));          // #1E90FF DodgerBlue @ 85%
			_lowestLvnBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
				new SharpDX.Color4(0f, 0.878f, 1f, 1f));                 // #00E0FF Cyan (most significant)
			_textBrush      = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
				new SharpDX.Color4(0.949f, 0.957f, 0.973f, 1f));         // #F2F4F8
			_bgBrush        = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
				new SharpDX.Color4(0.055f, 0.063f, 0.078f, 0.85f));      // #0E1014 @ 85%

			_dxReady = true;
		}

		#endregion

		#region Volume Profile Calculation

		private bool NeedsRecalc()
		{
			return StartAnchor.Time  != _cacheStartTime
				|| EndAnchor.Time    != _cacheEndTime
				|| Math.Abs(StartAnchor.Price - _cacheStartPrice) > 0.0001
				|| Math.Abs(EndAnchor.Price   - _cacheEndPrice)   > 0.0001;
		}

		private void CalculateLVNs()
		{
			_cacheStartTime  = StartAnchor.Time;
			_cacheEndTime    = EndAnchor.Time;
			_cacheStartPrice = StartAnchor.Price;
			_cacheEndPrice   = EndAnchor.Price;
			_lvnPrices.Clear();
			_lowestLvnPrice  = double.NaN;

			// Access chart bar data via AttachedTo.ChartObject
			ChartBars chartBarsObj = AttachedTo?.ChartObject as ChartBars;
			if (chartBarsObj == null)
			{
				// Fallback: try IChartBars interface
				NinjaTrader.Gui.NinjaScript.IChartBars icb = AttachedTo?.ChartObject as NinjaTrader.Gui.NinjaScript.IChartBars;
				if (icb != null) chartBarsObj = icb.ChartBars;
			}
			if (chartBarsObj == null) return;
			Bars bars = chartBarsObj.Bars;
			if (bars == null || bars.Count < 2) return;

			DateTime t1 = _cacheStartTime < _cacheEndTime ? _cacheStartTime : _cacheEndTime;
			DateTime t2 = _cacheStartTime > _cacheEndTime ? _cacheStartTime : _cacheEndTime;

			int startIdx = bars.GetBar(t1);
			int endIdx   = bars.GetBar(t2);
			if (startIdx < 0) startIdx = 0;
			if (endIdx >= bars.Count) endIdx = bars.Count - 1;
			if (startIdx >= endIdx) return;

			// Price range
			double yMin = double.MaxValue, yMax = double.MinValue;
			for (int i = startIdx; i <= endIdx; i++)
			{
				double h = bars.GetHigh(i);
				double l = bars.GetLow(i);
				if (h > yMax) yMax = h;
				if (l < yMin) yMin = l;
			}
			if (yMax <= yMin) return;

			double tickSize = AttachedTo.Instrument.MasterInstrument.TickSize;
			int rows = ProfileRows;
			double step = (yMax - yMin) / rows;
			if (step < tickSize) step = tickSize;

			// Build volume profile
			if (_profileVol == null || _profileVol.Length != rows + 1)
			{
				_profileVol   = new double[rows + 1];
				_profilePrice = new double[rows + 1];
			}
			else
			{
				Array.Clear(_profileVol, 0, _profileVol.Length);
			}

			for (int i = 0; i <= rows; i++)
				_profilePrice[i] = yMin + i * (yMax - yMin) / rows;

			for (int i = startIdx; i <= endIdx; i++)
			{
				double vol = bars.GetVolume(i);
				if (vol <= 0) continue;
				double l = bars.GetLow(i);
				double h = bars.GetHigh(i);
				int r1 = Math.Max(0, Math.Min(rows, (int)Math.Floor((l - yMin) / step)));
				int r2 = Math.Max(0, Math.Min(rows, (int)Math.Floor((h - yMin) / step)));
				int span = r2 - r1 + 1;
				double addVol = span > 0 ? vol / span : 0;
				for (int r = r1; r <= r2; r++)
					_profileVol[r] += addVol;
			}

			// Find local minima (LVN)
			int strength = LvnStrength;
			double lowestVol = double.MaxValue;

			for (int i = strength; i <= rows - strength; i++)
			{
				double val = _profileVol[i];
				if (val <= 0) continue;

				bool isMin = true;
				for (int j = -strength; j <= strength; j++)
				{
					if (j == 0) continue;
					int idx = i + j;
					if (idx < 0 || idx > rows) { isMin = false; break; }
					if (_profileVol[idx] < val) { isMin = false; break; }
				}

				if (isMin)
				{
					_lvnPrices.Add(_profilePrice[i]);
					if (val < lowestVol)
					{
						lowestVol       = val;
						_lowestLvnPrice = _profilePrice[i];
					}
				}
			}
		}

		#endregion

		#region Rendering

		public override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (Anchors.All(a => a.IsEditing))
				return;

			RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.PerPrimitive;

			ChartPanel panel  = chartControl.ChartPanels[PanelIndex];
			Point startPt     = StartAnchor.GetPoint(chartControl, panel, chartScale);
			Point endPt       = EndAnchor.GetPoint(chartControl, panel, chartScale);

			// ── Anchor line ──
			AnchorLineStroke.RenderTarget = RenderTarget;
			SharpDX.Direct2D1.Brush anchorBrush = IsInHitTest
				? chartControl.SelectionBrush : AnchorLineStroke.BrushDX;
			RenderTarget.DrawLine(startPt.ToVector2(), endPt.ToVector2(),
				anchorBrush, AnchorLineStroke.Width, AnchorLineStroke.StrokeStyle);

			if (IsInHitTest) return;
			if (!_dxReady)   return;

			// ── Recalculate if anchors moved ──
			if (NeedsRecalc())
				CalculateLVNs();

			if (_lvnPrices.Count == 0) return;

			// ── LVN lines ──
			float xLeft  = IsExtendedLinesLeft  ? panel.X : (float)Math.Min(startPt.X, endPt.X);
			float xRight = IsExtendedLinesRight  ? panel.X + panel.W : (float)Math.Max(startPt.X, endPt.X);

			foreach (double lvnPrice in _lvnPrices)
			{
				float y = chartScale.GetYByValue(lvnPrice);
				if (y < panel.Y - 5 || y > panel.Y + panel.H + 5) continue;

				bool isLowest = !double.IsNaN(_lowestLvnPrice)
					&& Math.Abs(lvnPrice - _lowestLvnPrice) < 0.0001;

				SharpDX.Direct2D1.Brush lineBrush = isLowest ? _lowestLvnBrush : _lvnBrush;
				float lineWidth  = isLowest ? 2f : 1.5f;

				if (isLowest)
					RenderTarget.DrawLine(
						new SharpDX.Vector2(xLeft, y),
						new SharpDX.Vector2(xRight, y),
						lineBrush, lineWidth);
				else
					RenderTarget.DrawLine(
						new SharpDX.Vector2(xLeft, y),
						new SharpDX.Vector2(xRight, y),
						lineBrush, lineWidth, _lvnDash);

				// ── Label ──
				DrawLvnLabel(y, lvnPrice, isLowest, xRight);
			}
		}

		private void DrawLvnLabel(float y, double price, bool isLowest, float xRight)
		{
			if (TextLocation == TextLocation.Off) return;

			string priceStr = price.ToString(
				Core.Globals.GetTickFormatString(AttachedTo.Instrument.MasterInstrument.TickSize));
			string label = isLowest ? "LVN* " + priceStr : "LVN " + priceStr;

			using (SharpDX.DirectWrite.TextLayout layout = new SharpDX.DirectWrite.TextLayout(
				Core.Globals.DirectWriteFactory, label, _labelFmt, 200f, 16f))
			{
				float tw = layout.Metrics.Width;
				float th = layout.Metrics.Height;
				float lx = xRight - tw - 12f;
				float ly = y - th / 2f;

				SharpDX.RectangleF bg = new SharpDX.RectangleF(lx - 4f, ly - 1f, tw + 8f, th + 2f);
				RenderTarget.FillRectangle(bg, _bgBrush);

				SharpDX.Direct2D1.Brush tb = isLowest ? _lowestLvnBrush : _textBrush;
				RenderTarget.DrawTextLayout(new SharpDX.Vector2(lx, ly), layout, tb);
			}
		}

		public override void OnCalculateMinMax()
		{
			MinValue = double.MaxValue;
			MaxValue = double.MinValue;

			if (!IsVisible || Anchors.All(a => a.IsEditing))
				return;

			// Include anchor prices
			MinValue = Math.Min(StartAnchor.Price, EndAnchor.Price);
			MaxValue = Math.Max(StartAnchor.Price, EndAnchor.Price);

			// Include LVN prices
			foreach (double p in _lvnPrices)
			{
				MinValue = Math.Min(MinValue, p);
				MaxValue = Math.Max(MaxValue, p);
			}
		}

		#endregion

		#region Disposal

		private void DisposeBrushes()
		{
			_dxReady = false;
			SafeDispose(ref _lvnBrush);
			SafeDispose(ref _lowestLvnBrush);
			SafeDispose(ref _textBrush);
			SafeDispose(ref _bgBrush);
		}

		private void DisposeDx()
		{
			DisposeBrushes();
			SafeDispose(ref _lvnDash);
			SafeDispose(ref _labelFmt);
		}

		private static void SafeDispose<T>(ref T res) where T : class, IDisposable
		{
			if (res == null) return;
			try
			{
				SharpDX.DisposeBase d = res as SharpDX.DisposeBase;
				if (d != null && d.IsDisposed) { res = null; return; }
				res.Dispose();
			}
			catch { }
			res = null;
		}

		#endregion

		#region Properties

		[NinjaScriptProperty]
		[Range(50, 1000)]
		[Display(Name = "Profile Rows", Description = "Resolution of volume profile (more rows = finer detection)",
			Order = 1, GroupName = "LVN Parameters")]
		public int ProfileRows { get; set; }

		[NinjaScriptProperty]
		[Range(3, 50)]
		[Display(Name = "LVN Strength", Description = "Local minimum window — higher = fewer but stronger LVNs",
			Order = 2, GroupName = "LVN Parameters")]
		public int LvnStrength { get; set; }

		#endregion
	}
}
