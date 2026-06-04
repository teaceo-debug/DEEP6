// DEEP6 Standard Deviation Retracement — Drawing Tool
//
// Click-drag on chart: first click = reference (0 SD), drag to 1 SD point.
// The distance between anchors defines "one standard deviation."
// Draws horizontal levels at configurable SD multiples with labels.
// The 0.705 (1/sqrt2) level is highlighted in gold.
//
// Lives in the drawing tools toolbar alongside Fibonacci Retracement.
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
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
#endregion

namespace NinjaTrader.NinjaScript.DrawingTools
{
	/// <summary>
	/// Standard Deviation Retracement drawing tool.
	/// Two-anchor tool: anchor the reference price (0 SD), drag to define 1 SD.
	/// Levels at configurable SD multiples are drawn as horizontal lines.
	/// Inherits all mouse/cursor/selection behaviour from FibonacciRetracements.
	/// </summary>
	public class DEEP6StdDevRetracementTool : FibonacciRetracements
	{
		#region Helpers

		// PriceLevel.Value mapping (with isInverted=true used by base):
		//   price = startPrice + (1 - Value/100) * range
		// We want:
		//   price = startPrice + sdMultiple * range
		// Therefore: sdMultiple = 1 - Value/100  =>  Value = (1 - sdMultiple) * 100

		private static double SdToValue(double sd) => (1.0 - sd) * 100.0;
		private static double ValueToSd(double val) => 1.0 - val / 100.0;

		private static string FormatSd(double sd)
		{
			if (Math.Abs(sd) < 0.0001) return "0";
			return sd.ToString("G5", CultureInfo.InvariantCulture);
		}

		private static PriceLevel MakeSdLevel(double sd, Brush brush, float width,
			DashStyleHelper dash, int opacity)
		{
			PriceLevel level = new PriceLevel(SdToValue(sd), brush, width, dash, opacity);
			level.Name = FormatSd(sd);
			return level;
		}

		private static Brush FrozenBrush(byte r, byte g, byte b)
		{
			SolidColorBrush br = new SolidColorBrush(Color.FromRgb(r, g, b));
			br.Freeze();
			return br;
		}

		#endregion

		#region Lifecycle

		protected override void OnStateChange()
		{
			base.OnStateChange();

			if (State == State.SetDefaults)
			{
				Name                 = "SD Retracement";
				IsExtendedLinesRight = true;
				PriceLevelOpacity    = 0;   // no shaded fill between levels
			}
			else if (State == State.Configure)
			{
				// Base added Fibonacci defaults (7 levels including 23.6).
				// Replace with SD levels on first creation.
				// When loading from saved chart, our SD levels are already serialised.
				bool isFibDefault = PriceLevels.Count == 7
					&& PriceLevels.Any(pl => Math.Abs(pl.Value - 23.6) < 0.1);

				if (PriceLevels.Count == 0 || isFibDefault)
				{
					PriceLevels.Clear();
					PopulateSDLevels();
				}
			}
		}

		private void PopulateSDLevels()
		{
			Brush white = Brushes.White;
			Brush gold  = FrozenBrush(0xFF, 0xD2, 0x3F);   // #FFD23F
			Brush gray  = Brushes.DarkGray;
			Brush lgray = Brushes.Gray;

			//  SD     Value     Visual
			// ----   -------   ------------------------------------------
			PriceLevels.Add(MakeSdLevel(-4,    lgray, 1f,   DashStyleHelper.Dash,  60));
			PriceLevels.Add(MakeSdLevel(-3.5,  lgray, 1f,   DashStyleHelper.Dash,  60));
			PriceLevels.Add(MakeSdLevel(-3.25, lgray, 1f,   DashStyleHelper.Dash,  50));
			PriceLevels.Add(MakeSdLevel(-3,    gray,  1f,   DashStyleHelper.Dash,  70));
			PriceLevels.Add(MakeSdLevel(-2.5,  lgray, 1f,   DashStyleHelper.Dash,  60));
			PriceLevels.Add(MakeSdLevel(-2,    gray,  1f,   DashStyleHelper.Dash,  70));
			PriceLevels.Add(MakeSdLevel(-1,    gray,  1.5f, DashStyleHelper.Dash,  80));
			PriceLevels.Add(MakeSdLevel(-0.5,  lgray, 1f,   DashStyleHelper.Dash,  60));

			// Mean / reference (0 SD) — solid white, prominent
			PriceLevels.Add(MakeSdLevel(0,     white, 2f,   DashStyleHelper.Solid, 100));

			// Retracement zone
			PriceLevels.Add(MakeSdLevel(0.5,   lgray, 1f,   DashStyleHelper.Dash,  60));
			PriceLevels.Add(MakeSdLevel(0.705, gold,  2f,   DashStyleHelper.Solid, 100));  // 1/sqrt(2)
			PriceLevels.Add(MakeSdLevel(1,     gray,  1.5f, DashStyleHelper.Dash,  80));

			// Extensions
			PriceLevels.Add(MakeSdLevel(2,     gray,  1f,   DashStyleHelper.Dash,  70));
			PriceLevels.Add(MakeSdLevel(2.5,   lgray, 1f,   DashStyleHelper.Dash,  60));
			PriceLevels.Add(MakeSdLevel(3,     gray,  1f,   DashStyleHelper.Dash,  70));
			PriceLevels.Add(MakeSdLevel(3.25,  lgray, 1f,   DashStyleHelper.Dash,  50));
			PriceLevels.Add(MakeSdLevel(3.5,   lgray, 1f,   DashStyleHelper.Dash,  60));
			PriceLevels.Add(MakeSdLevel(4,     lgray, 1f,   DashStyleHelper.Dash,  60));
		}

		#endregion

		#region Rendering

		public override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			// Guard: nothing placed yet
			if (Anchors.All(a => a.IsEditing))
				return;

			RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.PerPrimitive;

			ChartPanel chartPanel    = chartControl.ChartPanels[PanelIndex];
			Point anchorStartPoint   = StartAnchor.GetPoint(chartControl, chartPanel, chartScale);
			Point anchorEndPoint     = EndAnchor.GetPoint(chartControl, chartPanel, chartScale);

			// ── Anchor line (diagonal connector between the two clicks) ──
			AnchorLineStroke.RenderTarget = RenderTarget;

			SharpDX.Direct2D1.Brush anchorBrush = IsInHitTest
				? chartControl.SelectionBrush
				: AnchorLineStroke.BrushDX;

			RenderTarget.DrawLine(
				anchorStartPoint.ToVector2(),
				anchorEndPoint.ToVector2(),
				anchorBrush,
				AnchorLineStroke.Width,
				AnchorLineStroke.StrokeStyle);

			if (PriceLevels == null || !PriceLevels.Any())
				return;

			SetAllPriceLevelsRenderTarget();

			// ── Horizontal level lines ──
			foreach (PriceLevel pl in PriceLevels.Where(p => p.IsVisible && p.Stroke != null))
			{
				Tuple<Point, Point> pts = GetPriceLevelLinePoints(pl, chartControl, chartScale, true);

				double pixAdj       = (pl.Stroke.Width % 2.0).ApproxCompare(0) == 0 ? 0.5d : 0d;
				Vector pixAdjVec    = new Vector(pixAdj, pixAdj);

				RenderTarget.DrawLine(
					(pts.Item1 + pixAdjVec).ToVector2(),
					(pts.Item2 + pixAdjVec).ToVector2(),
					pl.Stroke.BrushDX,
					pl.Stroke.Width,
					pl.Stroke.StrokeStyle);
			}

			if (IsInHitTest)
				return;

			// ── SD labels ──
			double totalPriceRange = EndAnchor.Price - StartAnchor.Price;
			double anchorMinX      = Math.Min(anchorStartPoint.X, anchorEndPoint.X);
			double anchorMaxX      = Math.Max(anchorStartPoint.X, anchorEndPoint.X);

			foreach (PriceLevel pl in PriceLevels.Where(p => p.IsVisible && p.Stroke != null))
			{
				Tuple<Point, Point> pts = GetPriceLevelLinePoints(pl, chartControl, chartScale, true);

				float plPixAdj = (pl.Stroke.Width % 2.0).ApproxCompare(0) == 0 ? 0.5f : 0f;
				double price   = pl.GetPrice(StartAnchor.Price, totalPriceRange, true);

				DrawSdLabel(chartPanel, anchorMinX, anchorMaxX + plPixAdj,
					pts.Item1.Y, price, pl);
			}
		}

		private void DrawSdLabel(ChartPanel chartPanel, double minX, double maxX,
			double y, double price, PriceLevel priceLevel)
		{
			if (TextLocation == TextLocation.Off || priceLevel?.Stroke?.BrushDX == null)
				return;

			SimpleFont wpfFont = chartPanel.ChartControl.Properties.LabelFont ?? new SimpleFont();
			SharpDX.DirectWrite.TextFormat textFmt = wpfFont.ToDirectWriteTextFormat();
			textFmt.TextAlignment = SharpDX.DirectWrite.TextAlignment.Leading;
			textFmt.WordWrapping  = SharpDX.DirectWrite.WordWrapping.NoWrap;

			// Format: "SD_VALUE (PRICE)"
			double sd       = ValueToSd(priceLevel.Value);
			string sdStr    = FormatSd(sd);
			string priceStr = price.ToString(
				Core.Globals.GetTickFormatString(AttachedTo.Instrument.MasterInstrument.TickSize));
			string label    = sdStr + " (" + priceStr + ")";

			const double edgePad = 2d;
			float layoutW = (float)Math.Abs(maxX - minX);
			SharpDX.DirectWrite.TextLayout textLayout =
				new SharpDX.DirectWrite.TextLayout(
					Core.Globals.DirectWriteFactory, label, textFmt, layoutW, textFmt.FontSize);

			double drawX;
			if (IsExtendedLinesLeft && TextLocation == TextLocation.ExtremeLeft)
				drawX = chartPanel.X + edgePad;
			else if (IsExtendedLinesRight && TextLocation == TextLocation.ExtremeRight)
				drawX = chartPanel.X + chartPanel.W - textLayout.Metrics.Width;
			else if (TextLocation == TextLocation.InsideLeft || TextLocation == TextLocation.ExtremeLeft)
				drawX = minX - 1;
			else
				drawX = maxX - 1 - textLayout.Metrics.Width;

			RenderTarget.DrawTextLayout(
				new SharpDX.Vector2((float)drawX, (float)(y - textFmt.FontSize - edgePad)),
				textLayout,
				priceLevel.Stroke.BrushDX,
				SharpDX.Direct2D1.DrawTextOptions.NoSnap);

			textFmt.Dispose();
			textLayout.Dispose();
		}

		#endregion
	}
}
