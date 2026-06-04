#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6DarkPoolOverlay : Indicator
    {
        private const string BiasTag = "dp_bias_box";
        private const string WarningTag = "dp_warning";
        private const string SwingLineTag = "dp_swing_eq";
        private const string SupportLinePrefix = "dp_support_";
        private const string ResistLinePrefix = "dp_resist_";

        private readonly object _sync = new object();
        private Timer _refreshTimer;
        private DPOverlayDto _snapshot;
        private DateTime _lastFileWriteUtc = DateTime.MinValue;
        private DateTime _lastRefreshUtc = DateTime.MinValue;
        private string _warningText = "âš  WAITING FOR DARK POOL JSON";
        private Brush _warningBrush = Brushes.Goldenrod;
        private Brush _biasBrush = Brushes.White;
        private bool _isStale = true;
        private string _lastPrintedState = string.Empty;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6DarkPoolOverlay";
                Description = "Reads gex_terminal_nt8.json dark pool fields and renders support/resistance overlays with DP bias.";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 0;

                JsonFilePath = @"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_terminal_nt8.json";
                RefreshSeconds = 5;
                ShowDPLevels = true;
                ShowSwingEquilibrium = true;
                ShowBiasBox = true;
                MaxLevels = 5;
            }
            else if (State == State.DataLoaded)
            {
                _refreshTimer = new Timer(OnRefreshTimer, null, 250, Math.Max(1, RefreshSeconds) * 1000);
                RefreshSnapshot();
            }
            else if (State == State.Terminated)
            {
                if (_refreshTimer != null)
                {
                    _refreshTimer.Dispose();
                    _refreshTimer = null;
                }

                ClearDrawings();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0 || CurrentBar < 1)
                return;

            RefreshSnapshot();
            UpdateDrawObjects();
        }

        private void OnRefreshTimer(object state)
        {
            try
            {
                RefreshSnapshot();
                if (ChartControl != null)
                {
                    ChartControl.Dispatcher.BeginInvoke(new Action(delegate
                    {
                        try
                        {
                            ChartControl.InvalidateVisual();
                        }
                        catch
                        {
                        }
                    }));
                }
            }
            catch (Exception ex)
            {
                MarkUnavailable("âš  DP READ ERROR", ex.Message);
            }
        }

        private void RefreshSnapshot()
        {
            string path = JsonFilePath;
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                MarkUnavailable("âš  DP JSON MISSING", path);
                return;
            }

            DateTime writeUtc = File.GetLastWriteTimeUtc(path);
            DPOverlayDto parsed = null;

            if (writeUtc != _lastFileWriteUtc)
            {
                var serializer = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 };
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var sr = new StreamReader(fs))
                    parsed = serializer.Deserialize<DPOverlayDto>(sr.ReadToEnd());

                if (parsed == null)
                    throw new InvalidOperationException("Parsed dark pool payload was null.");
            }

            lock (_sync)
            {
                if (parsed != null)
                {
                    _snapshot = parsed;
                    _lastFileWriteUtc = writeUtc;
                }

                _lastRefreshUtc = DateTime.UtcNow;
                UpdateStateFromSnapshot(null);
            }
        }

        private void MarkUnavailable(string warning, string details)
        {
            lock (_sync)
            {
                _lastRefreshUtc = DateTime.UtcNow;
                UpdateStateFromSnapshot(string.IsNullOrWhiteSpace(details) ? warning : warning + " Â· " + Shorten(details, 72));
            }
        }

        private void UpdateStateFromSnapshot(string warningOverride)
        {
            _isStale = true;
            _biasBrush = ResolveBiasBrush(_snapshot != null ? (_snapshot.direction_signal ?? _snapshot.dp_bias) : null);
            _warningBrush = Brushes.OrangeRed;

            if (_snapshot == null)
            {
                _warningText = string.IsNullOrWhiteSpace(warningOverride) ? "âš  DP UNAVAILABLE" : warningOverride;
                return;
            }

            bool snapshotUnavailable = string.Equals((_snapshot.status ?? string.Empty).Trim(), "unavailable", StringComparison.OrdinalIgnoreCase);
            bool payloadStale = ComputeIsStale(_snapshot);

            if (!string.IsNullOrWhiteSpace(warningOverride))
            {
                _warningText = warningOverride;
                _isStale = true;
                return;
            }

            _isStale = payloadStale || snapshotUnavailable;
            if (snapshotUnavailable)
                _warningText = "âš  DP UNAVAILABLE";
            else if (_isStale)
                _warningText = "âš  DP DATA STALE";
            else
                _warningText = string.Empty;

            if (!_isStale)
                _warningBrush = Brushes.Transparent;
        }

        private bool ComputeIsStale(DPOverlayDto snapshot)
        {
            DateTime asOfUtc;
            if (!TryGetAsOfUtc(snapshot != null ? snapshot.as_of : null, out asOfUtc))
                return true;

            int staleAfterSeconds = snapshot != null ? Math.Max(1, snapshot.stale_after_seconds) : 1;
            return (DateTime.UtcNow - asOfUtc).TotalSeconds > staleAfterSeconds;
        }

        private bool TryGetAsOfUtc(object raw, out DateTime asOfUtc)
        {
            asOfUtc = DateTime.MinValue;
            if (raw == null)
                return false;

            if (raw is DateTime)
            {
                DateTime value = (DateTime)raw;
                asOfUtc = value.Kind == DateTimeKind.Utc ? value : value.ToUniversalTime();
                return true;
            }

            if (raw is double || raw is float || raw is decimal || raw is int || raw is long)
            {
                double seconds;
                try
                {
                    seconds = Convert.ToDouble(raw, CultureInfo.InvariantCulture);
                }
                catch
                {
                    return false;
                }

                try
                {
                    asOfUtc = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(seconds);
                    return true;
                }
                catch
                {
                    return false;
                }
            }

            string text = raw as string;
            if (string.IsNullOrWhiteSpace(text))
                return false;

            DateTimeOffset parsed;
            if (!DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out parsed))
                return false;

            asOfUtc = parsed.UtcDateTime;
            return true;
        }

        private void UpdateDrawObjects()
        {
            DPOverlayDto snapshot;
            string warningText;
            Brush warningBrush;
            Brush biasBrush;
            bool isStale;

            lock (_sync)
            {
                snapshot = _snapshot;
                warningText = _warningText;
                warningBrush = _warningBrush;
                biasBrush = _biasBrush;
                isStale = _isStale;
            }

            if (ShowBiasBox)
            {
                Draw.TextFixed(this, BiasTag, BuildBiasText(snapshot, isStale), TextPosition.BottomRight,
                    biasBrush, new SimpleFont("Consolas", 11) { Bold = true },
                    Brushes.Transparent, Brushes.Transparent, 0);
            }
            else
            {
                RemoveDrawObject(BiasTag);
            }

            if (string.IsNullOrWhiteSpace(warningText))
                RemoveDrawObject(WarningTag);
            else
                Draw.TextFixed(this, WarningTag, warningText, TextPosition.TopRight,
                    warningBrush, new SimpleFont("Consolas", 11) { Bold = true },
                    Brushes.Transparent, Brushes.Transparent, 0);

            DrawDPLevels(snapshot);

            double? swingEq = ShowSwingEquilibrium ? NormalizePrice(snapshot != null ? snapshot.swing_equilibrium : 0d) : null;
            string swingLabel = swingEq.HasValue
                ? string.Format(CultureInfo.InvariantCulture, "SWING EQ {0:N2}", swingEq.Value)
                : "";
            DrawLevelWithLabel(SwingLineTag, "dp_swing_lbl", swingEq, swingLabel, Brushes.Cyan, DashStyleHelper.Dash, 1);

            PrintLevels(snapshot);
        }

        // Debug method removed — clean production build

        private void DrawDPLevels(DPOverlayDto snapshot)
        {
            int max = Math.Max(1, MaxLevels);
            List<DPLevelDto> levels = snapshot != null && snapshot.dp_levels != null
                ? snapshot.dp_levels
                : new List<DPLevelDto>();

            int supportIndex = 0;
            int resistIndex = 0;

            if (ShowDPLevels)
            {
                for (int i = 0; i < levels.Count && (supportIndex + resistIndex) < max; i++)
                {
                    DPLevelDto level = levels[i];
                    if (level == null)
                        continue;

                    double? price = NormalizePrice(level.price);
                    if (!price.HasValue)
                        continue;

                    string levelType = (level.type ?? string.Empty).Trim().ToUpperInvariant();
                    string premLabel = level.premium >= 1000000
                        ? string.Format(CultureInfo.InvariantCulture, "${0:N1}M", level.premium / 1000000.0)
                        : string.Format(CultureInfo.InvariantCulture, "${0:N0}K", level.premium / 1000.0);
                    string countLabel = level.count > 0
                        ? string.Format(CultureInfo.InvariantCulture, " {0}p", level.count)
                        : "";

                    if (levelType == "SUPPORT")
                    {
                        string lineTag = SupportLinePrefix + supportIndex;
                        string lblTag = "dp_sup_lbl_" + supportIndex;
                        string label = string.Format(CultureInfo.InvariantCulture,
                            "DP SUPPORT {0:N2} | {1}{2}", price.Value, premLabel, countLabel);
                        DrawLevelWithLabel(lineTag, lblTag, price, label, Brushes.LimeGreen, DashStyleHelper.Solid, 2);
                        supportIndex++;
                    }
                    else if (levelType == "RESIST")
                    {
                        string lineTag = ResistLinePrefix + resistIndex;
                        string lblTag = "dp_res_lbl_" + resistIndex;
                        string label = string.Format(CultureInfo.InvariantCulture,
                            "DP RESIST {0:N2} | {1}{2}", price.Value, premLabel, countLabel);
                        DrawLevelWithLabel(lineTag, lblTag, price, label, Brushes.OrangeRed, DashStyleHelper.Solid, 2);
                        resistIndex++;
                    }
                }
            }

            ClearUnusedIndexedDrawings(SupportLinePrefix, supportIndex, max);
            ClearUnusedIndexedDrawings(ResistLinePrefix, resistIndex, max);
        }

        private void ClearUnusedIndexedDrawings(string linePrefix, int usedCount, int maxCount)
        {
            string lblPrefix = linePrefix.Contains("Support") ? "dp_sup_lbl_" : "dp_res_lbl_";
            for (int i = usedCount; i < maxCount; i++)
            {
                RemoveDrawObject(linePrefix + i);
                RemoveDrawObject(lblPrefix + i);
            }
        }

        private void DrawLevelWithLabel(string lineTag, string labelTag, double? price, string label, Brush brush, DashStyleHelper dashStyle, int width)
        {
            if (!price.HasValue)
            {
                RemoveDrawObject(lineTag);
                RemoveDrawObject(labelTag);
                return;
            }

            Draw.HorizontalLine(this, lineTag, false, price.Value, brush, dashStyle, width);
            Draw.Text(this, labelTag, false,
                label,
                0, price.Value + 2 * TickSize, 0,
                brush, new SimpleFont("Consolas", 10) { Bold = width >= 2 },
                System.Windows.TextAlignment.Left, null, null, 0);
        }

        private string BuildBiasText(DPOverlayDto snapshot, bool isStale)
        {
            if (snapshot == null)
                return "DP BIAS: WAITING\nDIR FLAT 0%\n0/10 BUY | 0/10 SELL";

            string direction = ToDisplay(snapshot.dp_bias, "NEUTRAL");
            string signal = ToDisplay(snapshot.direction_signal, "FLAT");
            string suffix = isStale ? " (STALE)" : string.Empty;
            return string.Format(CultureInfo.InvariantCulture,
                "DP BIAS: {0}{1}\nDIR {2} {3}%\n{4}/10 BUY | {5}/10 SELL",
                direction,
                suffix,
                signal,
                Math.Max(0, snapshot.direction_confidence),
                Math.Max(0, snapshot.signal_confluence_buy),
                Math.Max(0, snapshot.signal_confluence_sell));
        }

        private void PrintLevels(DPOverlayDto snapshot)
        {
            string direction = ToDisplay(snapshot != null ? snapshot.direction_signal : null, "FLAT");
            string state = string.Format(CultureInfo.InvariantCulture,
                "dir={0}|conf={1}|swing={2}|buy={3}|sell={4}|levels={5}|status={6}",
                direction,
                snapshot != null ? Math.Max(0, snapshot.direction_confidence) : 0,
                FormatNullablePrice(ShowSwingEquilibrium ? NormalizePrice(snapshot != null ? snapshot.swing_equilibrium : 0d) : null),
                snapshot != null ? Math.Max(0, snapshot.signal_confluence_buy) : 0,
                snapshot != null ? Math.Max(0, snapshot.signal_confluence_sell) : 0,
                snapshot != null && snapshot.dp_levels != null ? snapshot.dp_levels.Count : 0,
                ToDisplay(snapshot != null ? snapshot.status : null, "UNKNOWN"));

            if (state == _lastPrintedState)
                return;

            _lastPrintedState = state;
            Print(string.Format(CultureInfo.InvariantCulture,
                "[DEEP6DarkPoolOverlay] draw {0} bias={1} reason={2}",
                state,
                ToDisplay(snapshot != null ? snapshot.dp_bias : null, "NEUTRAL"),
                Shorten(snapshot != null ? snapshot.direction_reason : null, 96)));
        }

        private Brush ResolveBiasBrush(string direction)
        {
            string text = (direction ?? string.Empty).Trim().ToUpperInvariant();
            if (text == "BULLISH" || text == "LONG" || text == "UP")
                return Brushes.LimeGreen;
            if (text == "BEARISH" || text == "SHORT" || text == "DOWN")
                return Brushes.OrangeRed;
            return Brushes.White;
        }

        private double? NormalizePrice(double value)
        {
            if (double.IsNaN(value) || double.IsInfinity(value) || value <= 0)
                return null;
            return value;
        }

        private string FormatPrice(double value)
        {
            return value.ToString("N2", CultureInfo.InvariantCulture);
        }

        private string FormatNullablePrice(double? value)
        {
            return value.HasValue ? FormatPrice(value.Value) : "NA";
        }

        private string ToDisplay(string value, string fallback)
        {
            return string.IsNullOrWhiteSpace(value) ? fallback : value.Trim().ToUpperInvariant();
        }

        private string Shorten(string text, int maxLength)
        {
            if (string.IsNullOrWhiteSpace(text) || text.Length <= maxLength)
                return text;
            return text.Substring(0, Math.Max(0, maxLength - 3)) + "...";
        }

        private void ClearDrawings()
        {
            RemoveDrawObject(BiasTag);
            RemoveDrawObject(WarningTag);
            RemoveDrawObject(SwingLineTag);

            int max = Math.Max(1, MaxLevels);
            ClearUnusedIndexedDrawings(SupportLinePrefix, 0, max);
            ClearUnusedIndexedDrawings(ResistLinePrefix, 0, max);
        }

        [NinjaScriptProperty]
        [Display(Name = "JsonFilePath", Order = 1, GroupName = "Parameters")]
        [PropertyEditor("NinjaTrader.Gui.Tools.PathEditor")]
        public string JsonFilePath { get; set; }

        [NinjaScriptProperty]
        [Range(1, 3600)]
        [Display(Name = "RefreshSeconds", Order = 2, GroupName = "Parameters")]
        public int RefreshSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowDPLevels", Order = 3, GroupName = "Display")]
        public bool ShowDPLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowSwingEquilibrium", Order = 4, GroupName = "Display")]
        public bool ShowSwingEquilibrium { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowBiasBox", Order = 5, GroupName = "Display")]
        public bool ShowBiasBox { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "MaxLevels", Order = 6, GroupName = "Display")]
        public int MaxLevels { get; set; }

        private class DPOverlayDto
        {
            public int schema_version { get; set; }
            public object as_of { get; set; }
            public int stale_after_seconds { get; set; }
            public string status { get; set; }
            public List<DPLevelDto> dp_levels { get; set; }
            public int signal_confluence_buy { get; set; }
            public int signal_confluence_sell { get; set; }
            public double swing_equilibrium { get; set; }
            public string dp_bias { get; set; }
            public string direction_signal { get; set; }
            public int direction_confidence { get; set; }
            public string direction_reason { get; set; }
            public double? primary_magnet { get; set; }
        }

        private class DPLevelDto
        {
            public double price { get; set; }
            public string type { get; set; }
            public double premium { get; set; }
            public int count { get; set; }
        }
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6.DEEP6DarkPoolOverlay[] cacheDEEP6DarkPoolOverlay;
		public DEEP6.DEEP6DarkPoolOverlay DEEP6DarkPoolOverlay(string jsonFilePath, int refreshSeconds, bool showDPLevels, bool showSwingEquilibrium, bool showBiasBox, int maxLevels)
		{
			return DEEP6DarkPoolOverlay(Input, jsonFilePath, refreshSeconds, showDPLevels, showSwingEquilibrium, showBiasBox, maxLevels);
		}

		public DEEP6.DEEP6DarkPoolOverlay DEEP6DarkPoolOverlay(ISeries<double> input, string jsonFilePath, int refreshSeconds, bool showDPLevels, bool showSwingEquilibrium, bool showBiasBox, int maxLevels)
		{
			if (cacheDEEP6DarkPoolOverlay != null)
				for (int idx = 0; idx < cacheDEEP6DarkPoolOverlay.Length; idx++)
					if (cacheDEEP6DarkPoolOverlay[idx] != null && cacheDEEP6DarkPoolOverlay[idx].JsonFilePath == jsonFilePath && cacheDEEP6DarkPoolOverlay[idx].RefreshSeconds == refreshSeconds && cacheDEEP6DarkPoolOverlay[idx].ShowDPLevels == showDPLevels && cacheDEEP6DarkPoolOverlay[idx].ShowSwingEquilibrium == showSwingEquilibrium && cacheDEEP6DarkPoolOverlay[idx].ShowBiasBox == showBiasBox && cacheDEEP6DarkPoolOverlay[idx].MaxLevels == maxLevels && cacheDEEP6DarkPoolOverlay[idx].EqualsInput(input))
						return cacheDEEP6DarkPoolOverlay[idx];
			return CacheIndicator<DEEP6.DEEP6DarkPoolOverlay>(new DEEP6.DEEP6DarkPoolOverlay(){ JsonFilePath = jsonFilePath, RefreshSeconds = refreshSeconds, ShowDPLevels = showDPLevels, ShowSwingEquilibrium = showSwingEquilibrium, ShowBiasBox = showBiasBox, MaxLevels = maxLevels }, input, ref cacheDEEP6DarkPoolOverlay);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6.DEEP6DarkPoolOverlay DEEP6DarkPoolOverlay(string jsonFilePath, int refreshSeconds, bool showDPLevels, bool showSwingEquilibrium, bool showBiasBox, int maxLevels)
		{
			return indicator.DEEP6DarkPoolOverlay(Input, jsonFilePath, refreshSeconds, showDPLevels, showSwingEquilibrium, showBiasBox, maxLevels);
		}

		public Indicators.DEEP6.DEEP6DarkPoolOverlay DEEP6DarkPoolOverlay(ISeries<double> input , string jsonFilePath, int refreshSeconds, bool showDPLevels, bool showSwingEquilibrium, bool showBiasBox, int maxLevels)
		{
			return indicator.DEEP6DarkPoolOverlay(input, jsonFilePath, refreshSeconds, showDPLevels, showSwingEquilibrium, showBiasBox, maxLevels);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6.DEEP6DarkPoolOverlay DEEP6DarkPoolOverlay(string jsonFilePath, int refreshSeconds, bool showDPLevels, bool showSwingEquilibrium, bool showBiasBox, int maxLevels)
		{
			return indicator.DEEP6DarkPoolOverlay(Input, jsonFilePath, refreshSeconds, showDPLevels, showSwingEquilibrium, showBiasBox, maxLevels);
		}

		public Indicators.DEEP6.DEEP6DarkPoolOverlay DEEP6DarkPoolOverlay(ISeries<double> input , string jsonFilePath, int refreshSeconds, bool showDPLevels, bool showSwingEquilibrium, bool showBiasBox, int maxLevels)
		{
			return indicator.DEEP6DarkPoolOverlay(input, jsonFilePath, refreshSeconds, showDPLevels, showSwingEquilibrium, showBiasBox, maxLevels);
		}
	}
}

#endregion

