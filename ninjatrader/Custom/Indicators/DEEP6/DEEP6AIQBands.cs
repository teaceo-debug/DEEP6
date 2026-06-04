#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
	public enum DEEP6AIQBandsMethod
	{
		ATR,
		StdDev
	}

	/// <summary>
	/// DEEP6 AIQ-style Trading Bands.
	/// Center line: EMA of close.
	/// Band width: ATR or Standard Deviation, selectable via Method.
	/// Crossover dots mark price crossing bands (AIQ signal logic).
	///
	/// ATR mode:    Upper = EMA + Multiplier * ATR,  Lower = EMA - Multiplier * ATR
	/// StdDev mode: Upper = EMA + Multiplier * StdDev, Lower = EMA - Multiplier * StdDev
	///
	/// Based on AIQ Trading Expert Pro band formulas published in
	/// Stocks & Commodities Magazine.
	/// </summary>
	public class DEEP6AIQBands : Indicator
	{
		private EMA		emaCenter;
		private ATR		atrSeries;
		private StdDev	stdDevSeries;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description		= "AIQ-style Trading Bands. EMA center with ATR or StdDev envelope.";
				Name			= "DEEP6 AIQ Bands";
				IsOverlay		= true;
				IsSuspendedWhileInactive = true;
				Calculate		= Calculate.OnBarClose;

				EmaPeriod		= 20;
				AtrPeriod		= 20;
				Multiplier		= 2.0;
				BandMethod		= DEEP6AIQBandsMethod.ATR;
				ShowCrossovers	= true;

				AddPlot(new Stroke(Brushes.DodgerBlue, DashStyleHelper.Solid, 2), PlotStyle.Line, "Upper");
				AddPlot(new Stroke(Brushes.DimGray, DashStyleHelper.Dash, 1), PlotStyle.Line, "Midline");
				AddPlot(new Stroke(Brushes.DodgerBlue, DashStyleHelper.Solid, 2), PlotStyle.Line, "Lower");
				AddPlot(new Stroke(Brushes.Lime, 1), PlotStyle.Dot, "CrossUp");
				AddPlot(new Stroke(Brushes.Red, 1), PlotStyle.Dot, "CrossDn");
			}
			else if (State == State.DataLoaded)
			{
				emaCenter	= EMA(Close, EmaPeriod);
				atrSeries	= ATR(AtrPeriod);
				stdDevSeries = StdDev(Close, EmaPeriod);
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < Math.Max(EmaPeriod, AtrPeriod))
				return;

			double center = emaCenter[0];
			double offset;

			if (BandMethod == DEEP6AIQBandsMethod.ATR)
				offset = atrSeries[0] * Multiplier;
			else
				offset = stdDevSeries[0] * Multiplier;

			double upper = center + offset;
			double lower = center - offset;

			Midline[0]	= center;
			Upper[0]	= upper;
			Lower[0]	= lower;

			// Crossover signals (AIQ EDS logic)
			// AIQupperDN: price crosses from above to below Upper Band
			// AIQlowerUP: price crosses from below to above Lower Band
			if (ShowCrossovers && CurrentBar >= 1)
			{
				// Price was above upper band last bar, now at or below
				if (Close[1] > Upper[1] && Close[0] <= Upper[0])
				{
					CrossDn[0] = upper;
				}

				// Price was below lower band last bar, now at or above
				if (Close[1] < Lower[1] && Close[0] >= Lower[0])
				{
					CrossUp[0] = lower;
				}
			}
		}

		#region Properties

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> Upper => Values[0];

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> Midline => Values[1];

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> Lower => Values[2];

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> CrossUp => Values[3];

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> CrossDn => Values[4];

		[Range(1, int.MaxValue), NinjaScriptProperty]
		[Display(Name = "EMA Period", Description = "Period for the center EMA line",
			GroupName = "Parameters", Order = 0)]
		public int EmaPeriod { get; set; }

		[Range(1, int.MaxValue), NinjaScriptProperty]
		[Display(Name = "ATR Period", Description = "Period for ATR calculation (ATR mode only)",
			GroupName = "Parameters", Order = 1)]
		public int AtrPeriod { get; set; }

		[Range(0.01, double.MaxValue), NinjaScriptProperty]
		[Display(Name = "Multiplier", Description = "Band width multiplier",
			GroupName = "Parameters", Order = 2)]
		public double Multiplier { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Band Method", Description = "ATR or StdDev band width calculation",
			GroupName = "Parameters", Order = 3)]
		public DEEP6AIQBandsMethod BandMethod { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show Crossovers", Description = "Show dots when price crosses bands",
			GroupName = "Parameters", Order = 4)]
		public bool ShowCrossovers { get; set; }

		#endregion
	}
}
