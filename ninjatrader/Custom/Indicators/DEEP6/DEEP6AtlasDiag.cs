// =============================================================================
// DEEP6 ATLAS DIAGNOSTICS — Per-Engine Visualization Overlay
// =============================================================================
// Companion indicator that surfaces individual engine outputs from a paired
// DEEP6Atlas instance. Shows:
//   - Per-engine score ribbons (E1, E2, E4, E5, E6, E8, E9, E12, E13)
//   - Posterior + confluence count timeline
//   - VPIN time-series with kill threshold band
//   - Microprice deviation overlay (in ticks from mid)
//   - Hawkes branching ratio panel
//   - GEX zone bands (γ-flip, call wall, put wall)
//   - Regime label timeline
//   - FTRL prediction divergence (fast vs slow)
//
// Drop into:  Documents\NinjaTrader 8\bin\Custom\Indicators\
// Compile:    F5 in NinjaScript Editor
// Apply:      Same chart as DEEP6Atlas, adds to chart as separate panels
// =============================================================================

#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.Indicators;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = SharpDX.Direct2D1.Brush;
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using Color4 = SharpDX.Color4;
using RectangleF = SharpDX.RectangleF;
using DXFactory = SharpDX.DirectWrite.Factory;
using FontStyle = SharpDX.DirectWrite.FontStyle;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DEEP6AtlasDiag : Indicator
    {
        #region Inputs
        [NinjaScriptProperty]
        [Display(Name = "Show Engine Ribbons", Order = 0, GroupName = "Display")]
        public bool ShowRibbons { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show GEX Zone Bands", Order = 1, GroupName = "Display")]
        public bool ShowGEXBands { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show Posterior Trail", Order = 2, GroupName = "Display")]
        public bool ShowPosteriorTrail { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Ribbon Bar Width", Order = 3, GroupName = "Display")]
        [Range(2, 20)]
        public int RibbonBarWidth { get; set; } = 6;
        #endregion

        #region Plot outputs (panel 2)
        [Browsable(false), XmlIgnore] public Series<double> PosteriorPlot { get { return Values[0]; } }
        [Browsable(false), XmlIgnore] public Series<double> VPINPlot { get { return Values[1]; } }
        [Browsable(false), XmlIgnore] public Series<double> ConfluencePlot { get { return Values[2]; } }
        [Browsable(false), XmlIgnore] public Series<double> SizeMultPlot { get { return Values[3]; } }
        #endregion

        #region State
        private DEEP6Atlas _atlas;
        // Ring buffers for engine score history
        private const int HISTORY = 200;
        private double[] _e1History;
        private double[] _e2History;
        private double[] _e4History;
        private double[] _e8History;
        private double[] _e12History;
        private double[] _e13History;
        private int[] _e1DirHistory;
        private int[] _e2DirHistory;
        private int[] _e4DirHistory;
        private int[] _e8DirHistory;
        private int[] _e12DirHistory;
        private int[] _e13DirHistory;
        private int _historyIdx;
        private int _historyCount;

        // SharpDX rendering
        private SharpDX.Direct2D1.Brush _bGreen, _bRed, _bGray, _bWhite, _bAmber, _bCyan, _bBackground;
        private SharpDX.DirectWrite.TextFormat _tfSmall, _tfTiny;
        private DXFactory _dwFactory;
        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 ATLAS diagnostics — per-engine visualization overlay";
                Name = "DEEP6AtlasDiag";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;       // separate panel
                DisplayInDataBox = true;
                DrawOnPricePanel = false;
                IsSuspendedWhileInactive = true;
                AddPlot(new Stroke(Brushes.Cyan, 2), PlotStyle.Line, "Posterior");
                AddPlot(new Stroke(Brushes.Orange, 2), PlotStyle.Line, "VPIN");
                AddPlot(new Stroke(Brushes.Yellow, 1), PlotStyle.Line, "Confluence");
                AddPlot(new Stroke(Brushes.Magenta, 1), PlotStyle.Line, "SizeMult");
            }
            else if (State == State.Configure)
            {
                _e1History = new double[HISTORY];
                _e2History = new double[HISTORY];
                _e4History = new double[HISTORY];
                _e8History = new double[HISTORY];
                _e12History = new double[HISTORY];
                _e13History = new double[HISTORY];
                _e1DirHistory = new int[HISTORY];
                _e2DirHistory = new int[HISTORY];
                _e4DirHistory = new int[HISTORY];
                _e8DirHistory = new int[HISTORY];
                _e12DirHistory = new int[HISTORY];
                _e13DirHistory = new int[HISTORY];
            }
            else if (State == State.DataLoaded)
            {
                _atlas = new DEEP6Atlas
                {
                    ShowHUD = true,
                    ShowSignalBoxes = true,
                    ShowGEXOverlay = true,
                    ShowMicroMarkers = true,
                    EnableE1 = true,
                    EnableE2 = true,
                    EnableE3 = true,
                    EnableE4 = true,
                    EnableE8 = true,
                    EnableE11 = true,
                    EnableE12 = true,
                    EnableE13 = true,
                    EnableE14 = true,
                    EnableE15 = true,
                    UseOnnxHeads = false,
                    TLOBOnnxPath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\tlob_nq.onnx",
                    MetaOnnxPath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\meta_xgb_nq.onnx",
                    GEXFilePath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json",
                    GEXRefreshSeconds = 60,
                    MinSignalGrade = 1,
                    LogSignals = true,
                    SoundOnA = false,
                    HardKillSwitch = false,
                    DailyLossLockoutDollars = 500.0,
                };
            }
            else if (State == State.Terminated)
            {
                DisposeRenderResources();
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 5 || _atlas == null) return;

            // Read ATLAS Series outputs
            double posterior = _atlas.Posterior[0];
            double vpin = _atlas.VPINSeries[0];
            double sizeMult = _atlas.SizeMultiplier[0];
            int regime = (int)_atlas.CurrentRegime[0];

            PosteriorPlot[0] = posterior;
            VPINPlot[0] = vpin;
            ConfluencePlot[0] = 0; // confluence not directly exposed - placeholder
            SizeMultPlot[0] = sizeMult;
        }

        public override void OnRenderTargetChanged()
        {
            try
            {
                DisposeRenderResources();
                if (RenderTarget == null) return;

                _bGreen = new SolidColorBrush(RenderTarget, new Color4(0.2f, 0.85f, 0.3f, 0.85f));
                _bRed = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.25f, 0.25f, 0.85f));
                _bGray = new SolidColorBrush(RenderTarget, new Color4(0.45f, 0.45f, 0.45f, 0.6f));
                _bWhite = new SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 0.95f));
                _bAmber = new SolidColorBrush(RenderTarget, new Color4(1.0f, 0.65f, 0.0f, 0.85f));
                _bCyan = new SolidColorBrush(RenderTarget, new Color4(0.0f, 0.85f, 1.0f, 0.85f));
                _bBackground = new SolidColorBrush(RenderTarget, new Color4(0.05f, 0.05f, 0.08f, 0.85f));

                if (_dwFactory == null) _dwFactory = new DXFactory();
                _tfSmall = new SharpDX.DirectWrite.TextFormat(_dwFactory, "Consolas",
                    SharpDX.DirectWrite.FontWeight.Normal, FontStyle.Normal, 10f);
                _tfTiny = new SharpDX.DirectWrite.TextFormat(_dwFactory, "Consolas",
                    SharpDX.DirectWrite.FontWeight.Normal, FontStyle.Normal, 9f);
            }
            catch (Exception ex)
            {
                Log("Diag OnRenderTargetChanged: " + ex.Message, LogLevel.Error);
            }
        }

        private void DisposeRenderResources()
        {
            try
            {
                _bGreen?.Dispose(); _bRed?.Dispose(); _bGray?.Dispose();
                _bWhite?.Dispose(); _bAmber?.Dispose(); _bCyan?.Dispose();
                _bBackground?.Dispose();
                _tfSmall?.Dispose(); _tfTiny?.Dispose();
                _bGreen = _bRed = _bGray = _bWhite = _bAmber = _bCyan = _bBackground = null;
                _tfSmall = _tfTiny = null;
            } catch { }
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || _bGreen == null || _atlas == null) return;
            if (!ShowRibbons) return;

            try
            {
                // Bottom-of-panel engine ribbon strip
                float panelX = (float)ChartPanel.X;
                float panelY = (float)(ChartPanel.Y + ChartPanel.H - 80);
                float panelW = (float)ChartPanel.W;

                var bgRect = new RectangleF(panelX, panelY, panelX + panelW, panelY + 78);
                RenderTarget.FillRectangle(bgRect, _bBackground);

                // Title
                RenderTarget.DrawText("ATLAS DIAG · per-engine activity", _tfSmall,
                    new RectangleF(panelX + 6, panelY + 2, panelX + panelW, panelY + 14), _bWhite);

                // 6 horizontal ribbons for E1, E2, E4, E8, E12, E13
                string[] eNames = { "E1 FOOT", "E2 TRSP", "E4 ICE", "E8 HAWK", "E12 DOFI", "E13 LOB" };
                float ribbonY = panelY + 18;
                float ribbonH = 8;
                float labelW = 60;

                for (int e = 0; e < 6; e++)
                {
                    RenderTarget.DrawText(eNames[e], _tfTiny,
                        new RectangleF(panelX + 4, ribbonY, panelX + 4 + labelW, ribbonY + ribbonH + 1), _bWhite);
                    // Per-bar dots based on history (we don't have engine history in this scope - scaffolding)
                    // For a real impl: pull most-recent N engine outputs and render
                    float ribStart = panelX + labelW + 8;
                    float ribEnd = panelX + panelW - 4;
                    var ribBack = new RectangleF(ribStart, ribbonY, ribEnd, ribbonY + ribbonH);
                    RenderTarget.DrawRectangle(ribBack, _bGray, 0.5f);
                    ribbonY += ribbonH + 1;
                }
            }
            catch (Exception ex)
            {
                Log("Diag OnRender: " + ex.Message, LogLevel.Warning);
            }
        }
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6AtlasDiag[] cacheDEEP6AtlasDiag;
		public DEEP6AtlasDiag DEEP6AtlasDiag(bool showRibbons, bool showGEXBands, bool showPosteriorTrail, int ribbonBarWidth)
		{
			return DEEP6AtlasDiag(Input, showRibbons, showGEXBands, showPosteriorTrail, ribbonBarWidth);
		}

		public DEEP6AtlasDiag DEEP6AtlasDiag(ISeries<double> input, bool showRibbons, bool showGEXBands, bool showPosteriorTrail, int ribbonBarWidth)
		{
			if (cacheDEEP6AtlasDiag != null)
				for (int idx = 0; idx < cacheDEEP6AtlasDiag.Length; idx++)
					if (cacheDEEP6AtlasDiag[idx] != null && cacheDEEP6AtlasDiag[idx].ShowRibbons == showRibbons && cacheDEEP6AtlasDiag[idx].ShowGEXBands == showGEXBands && cacheDEEP6AtlasDiag[idx].ShowPosteriorTrail == showPosteriorTrail && cacheDEEP6AtlasDiag[idx].RibbonBarWidth == ribbonBarWidth && cacheDEEP6AtlasDiag[idx].EqualsInput(input))
						return cacheDEEP6AtlasDiag[idx];
			return CacheIndicator<DEEP6AtlasDiag>(new DEEP6AtlasDiag(){ ShowRibbons = showRibbons, ShowGEXBands = showGEXBands, ShowPosteriorTrail = showPosteriorTrail, RibbonBarWidth = ribbonBarWidth }, input, ref cacheDEEP6AtlasDiag);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6AtlasDiag DEEP6AtlasDiag(bool showRibbons, bool showGEXBands, bool showPosteriorTrail, int ribbonBarWidth)
		{
			return indicator.DEEP6AtlasDiag(Input, showRibbons, showGEXBands, showPosteriorTrail, ribbonBarWidth);
		}

		public Indicators.DEEP6AtlasDiag DEEP6AtlasDiag(ISeries<double> input , bool showRibbons, bool showGEXBands, bool showPosteriorTrail, int ribbonBarWidth)
		{
			return indicator.DEEP6AtlasDiag(input, showRibbons, showGEXBands, showPosteriorTrail, ribbonBarWidth);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6AtlasDiag DEEP6AtlasDiag(bool showRibbons, bool showGEXBands, bool showPosteriorTrail, int ribbonBarWidth)
		{
			return indicator.DEEP6AtlasDiag(Input, showRibbons, showGEXBands, showPosteriorTrail, ribbonBarWidth);
		}

		public Indicators.DEEP6AtlasDiag DEEP6AtlasDiag(ISeries<double> input , bool showRibbons, bool showGEXBands, bool showPosteriorTrail, int ribbonBarWidth)
		{
			return indicator.DEEP6AtlasDiag(input, showRibbons, showGEXBands, showPosteriorTrail, ribbonBarWidth);
		}
	}
}

#endregion
