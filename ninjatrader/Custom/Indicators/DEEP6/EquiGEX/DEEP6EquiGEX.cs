#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public partial class DEEP6EquiGEX : Indicator
    {
        private NinjaTrader.NinjaScript.Indicators.ATR _atr;
        private bool _unsupportedInstrument;
        private double _wW, _wD, _wA;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6 EquiGEX";
                Description = "Institutional equilibrium model with GEX-derived Synthetic Fair Value";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                IsAutoScale = false;
                BarsRequiredToPlot = 20;
                IsSuspendedWhileInactive = false;

                WeightWeekly = 0.50;
                WeightDaily = 0.30;
                WeightAVWAP = 0.20;
                VolMultiplier = 2.0;
                GexJsonPath = "";
                ShowDashboard = true;
                ShowDebugValues = false;
            }
            else if (State == State.DataLoaded)
            {
                _atr = ATR(14);

                string root = NormalizeRoot(Instrument.MasterInstrument.Name);
                if (root != "NQ" && root != "ES")
                {
                    _unsupportedInstrument = true;
                    Print("[EquiGEX] WARNING: Unsupported instrument '" + Instrument.MasterInstrument.Name + "' (root=" + root + "). Use ES or NQ.");
                }

                double total = WeightWeekly + WeightDaily + WeightAVWAP;
                if (total > 0)
                {
                    _wW = WeightWeekly / total;
                    _wD = WeightDaily / total;
                    _wA = WeightAVWAP / total;
                }
                else
                {
                    _wW = 1.0 / 3.0;
                    _wD = 1.0 / 3.0;
                    _wA = 1.0 / 3.0;
                }

                if (string.IsNullOrEmpty(GexJsonPath))
                {
                    string defaultPath = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                        @"NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json");
                    Print("[EquiGEX] Using default GEX JSON path: " + defaultPath);
                }
                else
                {
                    Print("[EquiGEX] Using custom GEX JSON path: " + GexJsonPath);
                }

                Print("[EquiGEX] Weights normalized: W=" + _wW.ToString("F3") + " D=" + _wD.ToString("F3") + " A=" + _wA.ToString("F3"));
            }
            else if (State == State.Realtime)
            {
                StartJsonPolling();
            }
            else if (State == State.Terminated)
            {
                StopJsonPolling();
                DisposeDx();
            }
        }

        protected override void OnBarUpdate()
        {
            if (_unsupportedInstrument)
                return;

            if (CurrentBar < BarsRequiredToPlot)
                return;

            UpdateAVWAP();
            UpdateSFVAndZones();
            UpdateTrend();
            UpdateBiasChip();
        }

        private string NormalizeRoot(string instrumentName)
        {
            if (string.IsNullOrEmpty(instrumentName))
                return string.Empty;

            string clean = instrumentName.Trim();
            int space = clean.IndexOf(' ');
            if (space > 0)
                clean = clean.Substring(0, space);
            clean = clean.ToUpperInvariant();

            if (clean == "MNQ") return "NQ";
            if (clean == "MES") return "ES";
            return clean;
        }

        #region Public Properties — Read-only state

        [Browsable(false)]
        public ZoneType CurrentZone { get; private set; }

        [Browsable(false)]
        public double CurrentSFV { get; private set; }

        [Browsable(false)]
        public double CurrentPremiumBand { get; private set; }

        [Browsable(false)]
        public double CurrentDiscountBand { get; private set; }

        [Browsable(false)]
        public BiasDirection CurrentBias { get; private set; }

        #endregion

        #region NinjaScriptProperty Parameters

        [NinjaScriptProperty]
        [Display(Name = "Weight: Weekly ZeroGamma", Order = 1, GroupName = "SFV Weights")]
        public double WeightWeekly { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Weight: Daily ZeroGamma", Order = 2, GroupName = "SFV Weights")]
        public double WeightDaily { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Weight: AVWAP", Order = 3, GroupName = "SFV Weights")]
        public double WeightAVWAP { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Volatility Multiplier", Order = 1, GroupName = "Bands")]
        public double VolMultiplier { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "GEX JSON Path", Order = 1, GroupName = "Data")]
        public string GexJsonPath { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Dashboard", Order = 1, GroupName = "Display")]
        public bool ShowDashboard { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Debug Values", Order = 2, GroupName = "Display")]
        public bool ShowDebugValues { get; set; }

        #endregion
    }
}
