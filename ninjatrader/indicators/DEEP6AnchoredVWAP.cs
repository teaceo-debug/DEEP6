// ============================================================
// DRAWING TOOL: DEEP6 Anchored VWAP v1.0
// Purpose: Click-to-anchor VWAP with +/- 1/2/3 StdDev bands
// Type: DrawingTool (chart toolbar pencil icon)
// ============================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
#endregion

namespace NinjaTrader.NinjaScript.DrawingTools
{
	public class DEEP6AnchoredVWAP : DrawingTool
	{
		#region Fields
		private SharpDX.Direct2D1.Brush dxVWAPBrush;
		private SharpDX.Direct2D1.Brush dxBand1Brush;
		private SharpDX.Direct2D1.Brush dxBand2Brush;
		private SharpDX.Direct2D1.Brush dxBand3Brush;
		private StrokeStyle dashedStyle;
		#endregion

		#region ChartAnchor
		[Display(Name = "Anchor", GroupName = "Anchor", Order = 0)]
		public ChartAnchor Anchor { get; set; }

		public override IEnumerable<ChartAnchor> Anchors
		{
			get { return new[] { Anchor }; }
		}
		#endregion

		#region Lifecycle
		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name				= "DEEP6 Anchored VWAP";
				Description			= "Click a bar to anchor VWAP. Line renders forward with StdDev bands.";
				IsAutoScale			= false;
				DrawingState		= DrawingState.Building;

				Anchor				= new ChartAnchor { IsEditing = true, DrawingTool = this };

				VWAPBrush			= Brushes.DodgerBlue;
				VWAPWidth			= 2;
				Band1Brush			= Brushes.Gray;
				Band2Brush			= Brushes.Orange;
				Band3Brush			= Brushes.Red;
				BandWidth			= 1;
				ShowBand1			= true;
				ShowBand2			= true;
				ShowBand3			= false;
			}
			else if (State == State.Terminated)
			{
				DisposeResources();
			}
		}
		#endregion

		#region Mouse Interaction
		public override Cursor GetCursor(ChartControl chartControl, ChartPanel chartPanel, ChartScale chartScale, System.Windows.Point point)
		{
			if (DrawingState == DrawingState.Building)
				return System.Windows.Input.Cursors.Pen;

			if (IsLocked)
				return null;

			// If near anchor, show move cursor
			System.Windows.Point anchorPoint = Anchor.GetPoint(chartControl, chartPanel, chartScale);
			if (System.Windows.Point.Subtract(point, anchorPoint).Length < 10)
				return System.Windows.Input.Cursors.SizeAll;

			return null;
		}

		public override void OnMouseDown(ChartControl chartControl, ChartPanel chartPanel, ChartScale chartScale, ChartAnchor dataPoint)
		{
			if (DrawingState == DrawingState.Building)
			{
				dataPoint.CopyDataValues(Anchor);
				Anchor.IsEditing	= false;
				DrawingState		= DrawingState.Normal;
				IsSelected			= false;
			}
			else if (DrawingState == DrawingState.Editing)
			{
				// Allow re-anchoring
				dataPoint.CopyDataValues(Anchor);
			}
		}

		public override void OnMouseMove(ChartControl chartControl, ChartPanel chartPanel, ChartScale chartScale, ChartAnchor dataPoint)
		{
			if (DrawingState == DrawingState.Building)
			{
				dataPoint.CopyDataValues(Anchor);
			}
		}

		public override void OnMouseUp(ChartControl chartControl, ChartPanel chartPanel, ChartScale chartScale, ChartAnchor dataPoint)
		{
			if (DrawingState == DrawingState.Editing)
				DrawingState = DrawingState.Normal;
		}
		#endregion

		#region Rendering
		public override void OnRenderTargetChanged()
		{
			DisposeResources();

			if (RenderTarget == null) return;

			if (VWAPBrush != null)
				dxVWAPBrush = VWAPBrush.ToDxBrush(RenderTarget);
			if (Band1Brush != null)
				dxBand1Brush = Band1Brush.ToDxBrush(RenderTarget);
			if (Band2Brush != null)
				dxBand2Brush = Band2Brush.ToDxBrush(RenderTarget);
			if (Band3Brush != null)
				dxBand3Brush = Band3Brush.ToDxBrush(RenderTarget);

			dashedStyle = new StrokeStyle(RenderTarget.Factory, new StrokeStyleProperties
			{
				DashStyle = SharpDX.Direct2D1.DashStyle.Dash
			});
		}

		public override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (Anchor == null || chartControl == null || chartScale == null || RenderTarget == null)
				return;

			ChartBars chartBars = GetAttachedToChartBars();
			if (chartBars == null || chartBars.Bars == null)
				return;

			Bars bars = chartBars.Bars;
			if (bars.Count == 0) return;

			// Find anchor bar index
			int anchorIdx = GetBarIndexFromTime(bars, Anchor.Time);
			if (anchorIdx < 0) anchorIdx = 0;

			int lastIdx = bars.Count - 1;
			if (anchorIdx > lastIdx) return;

			// Visible range for rendering
			int fromIdx = chartBars.FromIndex;
			int toIdx   = chartBars.ToIndex;

			// Accumulate VWAP from anchor forward
			double cumTPxVol  = 0;
			double cumVol     = 0;
			double cumTP2xVol = 0;

			float prevX    = 0, prevVwapY  = 0;
			float prevB1U  = 0, prevB1L    = 0;
			float prevB2U  = 0, prevB2L    = 0;
			float prevB3U  = 0, prevB3L    = 0;
			bool  hasPrev  = false;

			for (int i = anchorIdx; i <= lastIdx && i <= toIdx; i++)
			{
				double high  = bars.GetHigh(i);
				double low   = bars.GetLow(i);
				double close = bars.GetClose(i);
				double vol   = bars.GetVolume(i);

				if (vol <= 0)
				{
					// Zero-vol bar: carry forward previous point (hasPrev stays same)
					continue;
				}

				double tp = (high + low + close) / 3.0;
				cumTPxVol  += tp * vol;
				cumVol     += vol;
				cumTP2xVol += tp * tp * vol;

				double vwap     = cumTPxVol / cumVol;
				double variance = (cumTP2xVol / cumVol) - (vwap * vwap);
				double stdDev   = variance > 0 ? Math.Sqrt(variance) : 0;

				// Only render if this bar is in visible range
				if (i < fromIdx)
				{
					// Still accumulating but not drawing yet
					float x = chartControl.GetXByBarIndex(chartBars, i);
					float y = chartScale.GetYByValue(vwap);
					prevX    = x;
					prevVwapY = y;
					prevB1U  = chartScale.GetYByValue(vwap + stdDev);
					prevB1L  = chartScale.GetYByValue(vwap - stdDev);
					prevB2U  = chartScale.GetYByValue(vwap + 2.0 * stdDev);
					prevB2L  = chartScale.GetYByValue(vwap - 2.0 * stdDev);
					prevB3U  = chartScale.GetYByValue(vwap + 3.0 * stdDev);
					prevB3L  = chartScale.GetYByValue(vwap - 3.0 * stdDev);
					hasPrev  = true;
					continue;
				}

				float curX     = chartControl.GetXByBarIndex(chartBars, i);
				float curVwapY = chartScale.GetYByValue(vwap);
				float curB1U   = chartScale.GetYByValue(vwap + stdDev);
				float curB1L   = chartScale.GetYByValue(vwap - stdDev);
				float curB2U   = chartScale.GetYByValue(vwap + 2.0 * stdDev);
				float curB2L   = chartScale.GetYByValue(vwap - 2.0 * stdDev);
				float curB3U   = chartScale.GetYByValue(vwap + 3.0 * stdDev);
				float curB3L   = chartScale.GetYByValue(vwap - 3.0 * stdDev);

				if (hasPrev)
				{
					float width = IsSelected ? VWAPWidth + 1 : VWAPWidth;

					// VWAP line
					if (dxVWAPBrush != null)
						RenderTarget.DrawLine(new Vector2(prevX, prevVwapY), new Vector2(curX, curVwapY), dxVWAPBrush, width);

					float bw = IsSelected ? BandWidth + 1 : BandWidth;

					// +/- 1 StdDev
					if (ShowBand1 && dxBand1Brush != null && dashedStyle != null)
					{
						RenderTarget.DrawLine(new Vector2(prevX, prevB1U), new Vector2(curX, curB1U), dxBand1Brush, bw, dashedStyle);
						RenderTarget.DrawLine(new Vector2(prevX, prevB1L), new Vector2(curX, curB1L), dxBand1Brush, bw, dashedStyle);
					}

					// +/- 2 StdDev
					if (ShowBand2 && dxBand2Brush != null && dashedStyle != null)
					{
						RenderTarget.DrawLine(new Vector2(prevX, prevB2U), new Vector2(curX, curB2U), dxBand2Brush, bw, dashedStyle);
						RenderTarget.DrawLine(new Vector2(prevX, prevB2L), new Vector2(curX, curB2L), dxBand2Brush, bw, dashedStyle);
					}

					// +/- 3 StdDev
					if (ShowBand3 && dxBand3Brush != null && dashedStyle != null)
					{
						RenderTarget.DrawLine(new Vector2(prevX, prevB3U), new Vector2(curX, curB3U), dxBand3Brush, bw, dashedStyle);
						RenderTarget.DrawLine(new Vector2(prevX, prevB3L), new Vector2(curX, curB3L), dxBand3Brush, bw, dashedStyle);
					}
				}

				prevX     = curX;
				prevVwapY = curVwapY;
				prevB1U   = curB1U;
				prevB1L   = curB1L;
				prevB2U   = curB2U;
				prevB2L   = curB2L;
				prevB3U   = curB3U;
				prevB3L   = curB3L;
				hasPrev   = true;
			}

			// Draw anchor marker (small diamond)
			if (anchorIdx >= fromIdx && anchorIdx <= toIdx)
			{
				float ax = chartControl.GetXByBarIndex(chartBars, anchorIdx);
				float ay = chartScale.GetYByValue(Anchor.Price);
				float sz = 5f;

				if (dxVWAPBrush != null)
				{
					RenderTarget.DrawLine(new Vector2(ax, ay - sz), new Vector2(ax + sz, ay), dxVWAPBrush, 2);
					RenderTarget.DrawLine(new Vector2(ax + sz, ay), new Vector2(ax, ay + sz), dxVWAPBrush, 2);
					RenderTarget.DrawLine(new Vector2(ax, ay + sz), new Vector2(ax - sz, ay), dxVWAPBrush, 2);
					RenderTarget.DrawLine(new Vector2(ax - sz, ay), new Vector2(ax, ay - sz), dxVWAPBrush, 2);
				}
			}
		}
		#endregion

		#region Helpers
		private int GetBarIndexFromTime(Bars bars, DateTime time)
		{
			if (bars == null || bars.Count == 0) return -1;

			// Binary search for closest bar
			int lo = 0;
			int hi = bars.Count - 1;

			while (lo <= hi)
			{
				int mid = (lo + hi) / 2;
				DateTime midTime = bars.GetTime(mid);

				if (midTime == time) return mid;
				if (midTime < time) lo = mid + 1;
				else hi = mid - 1;
			}

			// Return closest bar at or after the anchor time
			return Math.Min(lo, bars.Count - 1);
		}

		private void DisposeResources()
		{
			if (dxVWAPBrush != null)  { dxVWAPBrush.Dispose();  dxVWAPBrush  = null; }
			if (dxBand1Brush != null) { dxBand1Brush.Dispose(); dxBand1Brush = null; }
			if (dxBand2Brush != null) { dxBand2Brush.Dispose(); dxBand2Brush = null; }
			if (dxBand3Brush != null) { dxBand3Brush.Dispose(); dxBand3Brush = null; }
			if (dashedStyle != null)  { dashedStyle.Dispose();  dashedStyle  = null; }
		}
		#endregion

		#region Properties
		[NinjaScriptProperty]
		[XmlIgnore]
		[Display(Name = "VWAP Color", Order = 1, GroupName = "Visuals")]
		public Brush VWAPBrush { get; set; }

		[Browsable(false)]
		public string VWAPBrushSerialize
		{
			get { return Serialize.BrushToString(VWAPBrush); }
			set { VWAPBrush = Serialize.StringToBrush(value); }
		}

		[NinjaScriptProperty]
		[Range(1, 10)]
		[Display(Name = "VWAP Width", Order = 2, GroupName = "Visuals")]
		public int VWAPWidth { get; set; }

		[NinjaScriptProperty]
		[XmlIgnore]
		[Display(Name = "+/- 1 StdDev Color", Order = 3, GroupName = "Visuals")]
		public Brush Band1Brush { get; set; }

		[Browsable(false)]
		public string Band1BrushSerialize
		{
			get { return Serialize.BrushToString(Band1Brush); }
			set { Band1Brush = Serialize.StringToBrush(value); }
		}

		[NinjaScriptProperty]
		[XmlIgnore]
		[Display(Name = "+/- 2 StdDev Color", Order = 4, GroupName = "Visuals")]
		public Brush Band2Brush { get; set; }

		[Browsable(false)]
		public string Band2BrushSerialize
		{
			get { return Serialize.BrushToString(Band2Brush); }
			set { Band2Brush = Serialize.StringToBrush(value); }
		}

		[NinjaScriptProperty]
		[XmlIgnore]
		[Display(Name = "+/- 3 StdDev Color", Order = 5, GroupName = "Visuals")]
		public Brush Band3Brush { get; set; }

		[Browsable(false)]
		public string Band3BrushSerialize
		{
			get { return Serialize.BrushToString(Band3Brush); }
			set { Band3Brush = Serialize.StringToBrush(value); }
		}

		[NinjaScriptProperty]
		[Range(1, 5)]
		[Display(Name = "Band Width", Order = 6, GroupName = "Visuals")]
		public int BandWidth { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show +/- 1 StdDev", Order = 1, GroupName = "Bands")]
		public bool ShowBand1 { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show +/- 2 StdDev", Order = 2, GroupName = "Bands")]
		public bool ShowBand2 { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show +/- 3 StdDev", Order = 3, GroupName = "Bands")]
		public bool ShowBand3 { get; set; }
		#endregion
	}
}
