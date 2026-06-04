// DEEP6 Range Volume Profile — Drawing Tool
//
// Self-contained fixed-range volume profile drawing tool.
// Draw a rectangle across a bar range; the tool snaps vertically to the true
// bar high/low range, builds an inline volume profile, highlights LVNs, and
// renders POC / value area extensions.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
#endregion

namespace NinjaTrader.NinjaScript.DrawingTools
{
	public class DEEP6RangeVolumeProfile : Rectangle
	{
		#region Fields
		private ChartAnchor firstAnchor;
		private ChartAnchor lastAnchor;
		private int cachedStartBar = -1;
		private int cachedEndBar = -1;
		private int cachedProfileRows = -1;
		private int cachedValueAreaPercent = -1;
		private int cachedLvnStrength = -1;

		private double rangeHigh = double.MinValue;
		private double rangeLow = double.MaxValue;
		private double rowSize = 0.0;
		private double totalVolume = 0.0;
		private double maxVolume = 0.0;
		private double[] profileVolumes;
		private double[] profilePrices;
		private List<int> lvnIndices;
		private int pocIndex = -1;
		private int vahIndex = -1;
		private int valIndex = -1;
		private bool isCalculating;
		private string loadingMessage = "Loading...";

		private SharpDX.Direct2D1.SolidColorBrush pocBrushDx;
		private SharpDX.Direct2D1.SolidColorBrush vahValBrushDx;
		private SharpDX.Direct2D1.SolidColorBrush lvnBrushDx;
		private SharpDX.Direct2D1.SolidColorBrush textBrushDx;
		private SharpDX.Direct2D1.SolidColorBrush lowVolumeBrushDx;
		private SharpDX.Direct2D1.SolidColorBrush midVolumeBrushDx;
		private SharpDX.Direct2D1.SolidColorBrush highVolumeBrushDx;
		private SharpDX.Direct2D1.StrokeStyle dottedStrokeStyle;
		#endregion

		#region Lifecycle
		protected override void OnStateChange()
		{
			base.OnStateChange();

			if (State == State.SetDefaults)
			{
				Name = "DEEP6 Range Volume Profile";
				Description = "Draggable fixed-range volume profile with inline LVN detection.";
				AreaOpacity = 5;
				AreaBrush = Brushes.DimGray;
				OutlineStroke = new Stroke(Brushes.Gray, DashStyleHelper.Dash, 1f, 50);

				ProfileRows = 200;
				ValueAreaPercent = 70;
				HistogramWidth = 60;
				ShowPoc = true;
				ShowValueArea = true;
				ShowLvnMarkers = true;
				LvnStrength = 10;
			}
			else if (State == State.Configure)
			{
				ZOrderType = DrawingToolZOrder.AlwaysDrawnFirst;
				ZOrder = -1;
				SafeDispose(ref dottedStrokeStyle);
				dottedStrokeStyle = new SharpDX.Direct2D1.StrokeStyle(
					Core.Globals.D2DFactory,
					new SharpDX.Direct2D1.StrokeStyleProperties
					{
						DashStyle = SharpDX.Direct2D1.DashStyle.Dot
					});
			}
			else if (State == State.Terminated)
			{
				DisposeDxResources();
				SafeDispose(ref dottedStrokeStyle);
			}
		}

		public override void OnRenderTargetChanged()
		{
			DisposeDxResources();

			if (RenderTarget == null)
				return;

			pocBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0xFF38C8, 1f));
			vahValBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0x9BA3AE, 0.85f));
			lvnBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0x00E0FF, 0.95f));
			textBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0xF2F4F8, 0.95f));
			lowVolumeBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0xFF4444, 0.90f));
			midVolumeBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0xFF8C00, 0.90f));
			highVolumeBrushDx = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(0xFFD23F, 0.95f));
		}
		#endregion

		#region Rendering
		public override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (StartAnchor == null || EndAnchor == null || RenderTarget == null || StartAnchor.SlotIndex < 0 || EndAnchor.SlotIndex < 0)
				return;

			ChartBars chartBarsObj = AttachedTo != null ? AttachedTo.ChartObject as ChartBars : null;
			if (chartBarsObj == null || chartBarsObj.Bars == null || chartBarsObj.Count <= 0)
				return;

			UpdateAnchorOrdering();
			EnsureProfile(chartBarsObj);

			base.OnRender(chartControl, chartScale);

			Rect anchorsRect = GetAnchorsRect(chartControl, chartScale);
			if (anchorsRect.Width <= 1 || anchorsRect.Height <= 1)
				return;

			if (isCalculating || profileVolumes == null || profilePrices == null || totalVolume <= 0 || pocIndex < 0)
			{
				DrawLoadingText(chartControl, anchorsRect);
				return;
			}

			ChartPanel chartPanel = chartControl.ChartPanels[chartScale.PanelIndex];
			float left = (float)anchorsRect.Left;
			float right = left + (float)(anchorsRect.Width * HistogramWidth / 100.0);
			float chartRight = chartPanel.X + chartPanel.W;

			RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;
			for (int i = 0; i < profileVolumes.Length; i++)
			{
				if (profileVolumes[i] <= 0)
					continue;

				double rowLow = profilePrices[i];
				double rowHigh = rowLow + rowSize;
				float y1 = (float)chartScale.GetYByValue(rowHigh);
				float y2 = (float)chartScale.GetYByValue(rowLow);
				float top = Math.Min(y1, y2);
				float bottom = Math.Max(y1, y2);
				if (bottom - top < 1f)
					bottom = top + 1f;

				float normalized = maxVolume > 0 ? (float)(profileVolumes[i] / maxVolume) : 0f;
				float width = (right - left) * normalized;
				if (width < 1f)
					width = 1f;

				RenderTarget.FillRectangle(
					new SharpDX.RectangleF(left, top, width, bottom - top),
					GetGradientBrush(normalized));
			}

			RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.PerPrimitive;

			if (ShowLvnMarkers && lvnIndices != null)
			{
				foreach (int index in lvnIndices)
				{
					double price = profilePrices[index] + rowSize * 0.5;
					float y = (float)chartScale.GetYByValue(price);
					RenderTarget.FillEllipse(new SharpDX.Direct2D1.Ellipse(new SharpDX.Vector2(left + 4f, y), 2.5f, 2.5f), lvnBrushDx);
					RenderTarget.DrawLine(new SharpDX.Vector2(left + 8f, y), new SharpDX.Vector2(left + 14f, y), lvnBrushDx, 1f);
				}
			}

			if (ShowPoc)
			{
				float y = (float)chartScale.GetYByValue(profilePrices[pocIndex] + rowSize * 0.5);
				RenderTarget.DrawLine(new SharpDX.Vector2(left, y), new SharpDX.Vector2(chartRight, y), pocBrushDx, 1.5f);
			}

			if (ShowValueArea && vahIndex >= 0 && valIndex >= 0)
			{
				float vahY = (float)chartScale.GetYByValue(profilePrices[vahIndex] + rowSize);
				float valY = (float)chartScale.GetYByValue(profilePrices[valIndex]);
				RenderTarget.DrawLine(new SharpDX.Vector2(left, vahY), new SharpDX.Vector2(chartRight, vahY), vahValBrushDx, 1f, dottedStrokeStyle);
				RenderTarget.DrawLine(new SharpDX.Vector2(left, valY), new SharpDX.Vector2(chartRight, valY), vahValBrushDx, 1f, dottedStrokeStyle);
			}
		}
		#endregion

		#region Calculation
		private void EnsureProfile(ChartBars chartBarsObj)
		{
			if (DrawingState != DrawingState.Normal)
				return;

			int startBar = Math.Min((int)firstAnchor.SlotIndex, (int)lastAnchor.SlotIndex);
			int endBar = Math.Max((int)firstAnchor.SlotIndex, (int)lastAnchor.SlotIndex);
			if (endBar >= chartBarsObj.Count - 1)
				endBar = chartBarsObj.Count - 1;

			bool needsRecalc = startBar != cachedStartBar
				|| endBar != cachedEndBar
				|| ProfileRows != cachedProfileRows
				|| ValueAreaPercent != cachedValueAreaPercent
				|| LvnStrength != cachedLvnStrength
				|| profileVolumes == null
				|| profilePrices == null;

			if (!needsRecalc)
				return;

			cachedStartBar = startBar;
			cachedEndBar = endBar;
			cachedProfileRows = ProfileRows;
			cachedValueAreaPercent = ValueAreaPercent;
			cachedLvnStrength = LvnStrength;

			CalculateProfile(chartBarsObj.Bars, startBar, endBar);
			SnapAnchorsToRange(endBar);
		}

		private void CalculateProfile(Bars bars, int startBar, int endBar)
		{
			isCalculating = true;
			loadingMessage = "Calculating...";

			profileVolumes = new double[ProfileRows + 1];
			profilePrices = new double[ProfileRows + 1];
			lvnIndices = new List<int>();
			totalVolume = 0.0;
			maxVolume = 0.0;
			pocIndex = -1;
			vahIndex = -1;
			valIndex = -1;
			rangeHigh = double.MinValue;
			rangeLow = double.MaxValue;

			if (startBar < 0 || endBar < startBar)
			{
				isCalculating = false;
				return;
			}

			for (int i = startBar; i <= endBar; i++)
			{
				double high = bars.GetHigh(i);
				double low = bars.GetLow(i);
				if (high > rangeHigh)
					rangeHigh = high;
				if (low < rangeLow)
					rangeLow = low;
			}

			if (rangeHigh <= rangeLow)
			{
				rangeHigh = rangeLow + (AttachedTo != null && AttachedTo.Instrument != null ? AttachedTo.Instrument.MasterInstrument.TickSize : 1.0);
			}

			rowSize = (rangeHigh - rangeLow) / ProfileRows;
			double tickSize = AttachedTo != null && AttachedTo.Instrument != null
				? AttachedTo.Instrument.MasterInstrument.TickSize
				: 0.01;
			if (rowSize < tickSize)
				rowSize = tickSize;

			for (int i = 0; i < profilePrices.Length; i++)
				profilePrices[i] = rangeLow + i * rowSize;

			for (int i = startBar; i <= endBar; i++)
			{
				double high = bars.GetHigh(i);
				double low = bars.GetLow(i);
				double volume = bars.GetVolume(i);
				if (volume <= 0)
					continue;

				int r1 = ClampRowIndex((int)Math.Floor((Math.Min(low, high) - rangeLow) / rowSize));
				int r2 = ClampRowIndex((int)Math.Floor((Math.Max(low, high) - rangeLow) / rowSize));
				int span = r2 - r1 + 1;
				if (span <= 0)
					continue;

				double addVolume = volume / span;
				for (int row = r1; row <= r2; row++)
					profileVolumes[row] += addVolume;
			}

			for (int i = 0; i < profileVolumes.Length; i++)
			{
				totalVolume += profileVolumes[i];
				if (profileVolumes[i] > maxVolume)
				{
					maxVolume = profileVolumes[i];
					pocIndex = i;
				}
			}

			CalculateValueArea();
			CalculateLvnLevels();
			isCalculating = false;
			loadingMessage = "Loading...";
		}

		private void CalculateValueArea()
		{
			if (pocIndex < 0 || totalVolume <= 0)
				return;

			double target = totalVolume * (ValueAreaPercent / 100.0);
			double accumulated = profileVolumes[pocIndex];
			int up = pocIndex;
			int down = pocIndex;

			while (accumulated < target && (down > 0 || up < profileVolumes.Length - 1))
			{
				double nextDown = down > 0 ? profileVolumes[down - 1] : -1.0;
				double nextUp = up < profileVolumes.Length - 1 ? profileVolumes[up + 1] : -1.0;

				if (nextUp >= nextDown)
				{
					if (up < profileVolumes.Length - 1)
					{
						up++;
						accumulated += profileVolumes[up];
					}
					else if (down > 0)
					{
						down--;
						accumulated += profileVolumes[down];
					}
				}
				else
				{
					if (down > 0)
					{
						down--;
						accumulated += profileVolumes[down];
					}
					else if (up < profileVolumes.Length - 1)
					{
						up++;
						accumulated += profileVolumes[up];
					}
				}
			}

			vahIndex = up;
			valIndex = down;
		}

		private void CalculateLvnLevels()
		{
			if (profileVolumes == null || profileVolumes.Length <= LvnStrength * 2 + 1)
				return;

			for (int i = 0; i < profileVolumes.Length; i++)
			{
				double value = profileVolumes[i];
				if (value <= 0)
					continue;

				bool isLvn = true;
				for (int j = -LvnStrength; j <= LvnStrength; j++)
				{
					if (j == 0)
						continue;
					int k = i + j;
					if (k < 0 || k >= profileVolumes.Length)
						continue;
					if (profileVolumes[k] < value)
					{
						isLvn = false;
						break;
					}
				}

				if (isLvn)
					lvnIndices.Add(i);
			}
		}
		#endregion

		#region Helpers
		private void UpdateAnchorOrdering()
		{
			if (StartAnchor.SlotIndex > EndAnchor.SlotIndex)
			{
				firstAnchor = EndAnchor;
				lastAnchor = StartAnchor;
			}
			else
			{
				firstAnchor = StartAnchor;
				lastAnchor = EndAnchor;
			}
		}

		private void SnapAnchorsToRange(int endBar)
		{
			if (StartAnchor.SlotIndex <= EndAnchor.SlotIndex)
			{
				StartAnchor.Price = rangeHigh;
				EndAnchor.Price = rangeLow;
				EndAnchor.SlotIndex = endBar;
			}
			else
			{
				StartAnchor.Price = rangeLow;
				EndAnchor.Price = rangeHigh;
				StartAnchor.SlotIndex = endBar;
			}
		}

		private int ClampRowIndex(int index)
		{
			if (index < 0)
				return 0;
			if (index >= ProfileRows + 1)
				return ProfileRows;
			return index;
		}

		private Rect GetAnchorsRect(ChartControl chartControl, ChartScale chartScale)
		{
			if (StartAnchor == null || EndAnchor == null)
				return new Rect();

			ChartPanel chartPanel = chartControl.ChartPanels[chartScale.PanelIndex];
			Point startPoint = StartAnchor.GetPoint(chartControl, chartPanel, chartScale);
			Point endPoint = EndAnchor.GetPoint(chartControl, chartPanel, chartScale);

			double left = Math.Min(endPoint.X, startPoint.X);
			double top = Math.Min(endPoint.Y, startPoint.Y);
			double width = Math.Abs(endPoint.X - startPoint.X);
			double height = Math.Abs(endPoint.Y - startPoint.Y);
			return new Rect(left, top, width, height);
		}

		private void DrawLoadingText(ChartControl chartControl, Rect anchorsRect)
		{
			if (textBrushDx == null || anchorsRect.Width <= 0 || anchorsRect.Height <= 0)
				return;

			using (SharpDX.DirectWrite.TextFormat textFormat = chartControl.Properties.LabelFont.ToDirectWriteTextFormat())
			{
				textFormat.TextAlignment = SharpDX.DirectWrite.TextAlignment.Center;
				textFormat.ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center;

				using (SharpDX.DirectWrite.TextLayout textLayout = new SharpDX.DirectWrite.TextLayout(
					Core.Globals.DirectWriteFactory,
					loadingMessage,
					textFormat,
					(float)anchorsRect.Width,
					(float)anchorsRect.Height))
				{
					RenderTarget.DrawTextLayout(
						new SharpDX.Vector2((float)anchorsRect.X, (float)anchorsRect.Y),
						textLayout,
						textBrushDx);
				}
			}
		}

		private SharpDX.Direct2D1.SolidColorBrush GetGradientBrush(float normalized)
		{
			if (normalized >= 0.80f)
				return highVolumeBrushDx;
			if (normalized >= 0.45f)
				return midVolumeBrushDx;
			return lowVolumeBrushDx;
		}

		private SharpDX.Color4 ToColor4(int rgb, float alpha)
		{
			return new SharpDX.Color4(
				((rgb >> 16) & 0xFF) / 255f,
				((rgb >> 8) & 0xFF) / 255f,
				(rgb & 0xFF) / 255f,
				alpha);
		}

		private void DisposeDxResources()
		{
			SafeDispose(ref pocBrushDx);
			SafeDispose(ref vahValBrushDx);
			SafeDispose(ref lvnBrushDx);
			SafeDispose(ref textBrushDx);
			SafeDispose(ref lowVolumeBrushDx);
			SafeDispose(ref midVolumeBrushDx);
			SafeDispose(ref highVolumeBrushDx);
		}

		private void SafeDispose<T>(ref T resource) where T : class, IDisposable
		{
			try
			{
				if (resource != null)
				{
					resource.Dispose();
					resource = null;
				}
			}
			catch
			{
				resource = null;
			}
		}
		#endregion

		#region Properties
		[NinjaScriptProperty]
		[Range(50, 1000)]
		[Display(Name = "Profile Rows", Order = 1, GroupName = "Parameters")]
		public int ProfileRows { get; set; }

		[NinjaScriptProperty]
		[Range(10, 90)]
		[Display(Name = "Value Area Percent", Order = 2, GroupName = "Parameters")]
		public int ValueAreaPercent { get; set; }

		[NinjaScriptProperty]
		[Range(10, 100)]
		[Display(Name = "Histogram Width (%)", Order = 3, GroupName = "Parameters")]
		public int HistogramWidth { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show POC", Order = 4, GroupName = "Parameters")]
		public bool ShowPoc { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show Value Area", Order = 5, GroupName = "Parameters")]
		public bool ShowValueArea { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show LVN Markers", Order = 6, GroupName = "Parameters")]
		public bool ShowLvnMarkers { get; set; }

		[NinjaScriptProperty]
		[Range(3, 50)]
		[Display(Name = "LVN Strength", Order = 7, GroupName = "Parameters")]
		public int LvnStrength { get; set; }
		#endregion
	}
}
