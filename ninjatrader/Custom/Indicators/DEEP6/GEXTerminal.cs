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
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using System.Xml.Serialization;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class GEXTerminal : Indicator
    {
        private const string HudTag = "gex_hud";
        private const string WarningTag = "gex_warning";
        private const string FlipLineTag = "gex_flip";
        private const string CallWallLineTag = "gex_cwall";
        private const string PutWallLineTag = "gex_pwall";
        private const string MagnetLineTag = "gex_0dte_magnet";
        private const string PrimaryMagnetLineTag = "gex_primary_magnet";

        private readonly object _sync = new object();
        private Timer _refreshTimer;
        private SnapshotDto _snapshot;
        private DateTime _lastFileWriteUtc = DateTime.MinValue;
        private DateTime _lastRefreshUtc = DateTime.MinValue;
        private string _warningText = "âš  WAITING FOR GEX JSON";
        private Brush _warningBrush = Brushes.Goldenrod;
        private Brush _hudBrush = Brushes.White;
        private bool _isStale = true;
        private string _lastPrintedState = string.Empty;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "GEXTerminal";
                Description = "Reads gex_terminal_nt8.json and renders a GEX verdict HUD with on-chart levels.";
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
                ShowFlip = true;
                ShowWalls = true;
                ShowZeroDteMagnet = true;
                ShowMagnet = true;
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
                MarkUnavailable("âš  GEX READ ERROR", ex.Message);
            }
        }

        private void RefreshSnapshot()
        {
            string path = JsonFilePath;
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                MarkUnavailable("âš  GEX JSON MISSING", path);
                return;
            }

            DateTime writeUtc = File.GetLastWriteTimeUtc(path);
            SnapshotDto parsed = null;

            if (writeUtc != _lastFileWriteUtc)
            {
                var serializer = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 };
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var sr = new StreamReader(fs))
                    parsed = serializer.Deserialize<SnapshotDto>(sr.ReadToEnd());

                if (parsed == null)
                    throw new InvalidOperationException("Parsed GEX payload was null.");
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
            _hudBrush = ResolveBiasBrush(_snapshot != null ? (_snapshot.direction_signal ?? _snapshot.bias_direction) : null);
            _warningBrush = Brushes.OrangeRed;

            if (_snapshot == null)
            {
                _warningText = string.IsNullOrWhiteSpace(warningOverride) ? "âš  GEX UNAVAILABLE" : warningOverride;
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
                _warningText = "âš  GEX UNAVAILABLE";
            else if (_isStale)
                _warningText = "âš  GEX DATA STALE";
            else
                _warningText = string.Empty;

            if (!_isStale)
                _warningBrush = Brushes.Transparent;
        }

        private bool ComputeIsStale(SnapshotDto snapshot)
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
                asOfUtc = ((DateTime)raw).Kind == DateTimeKind.Utc ? (DateTime)raw : ((DateTime)raw).ToUniversalTime();
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
            SnapshotDto snapshot;
            string warningText;
            Brush warningBrush;
            Brush hudBrush;

            lock (_sync)
            {
                snapshot = _snapshot;
                warningText = _warningText;
                warningBrush = _warningBrush;
                hudBrush = _hudBrush;
            }

            Draw.TextFixed(this, HudTag, BuildHudText(snapshot), TextPosition.TopLeft,
                hudBrush, new SimpleFont("Consolas", 11) { Bold = true },
                Brushes.Transparent, Brushes.Transparent, 0);

            if (string.IsNullOrWhiteSpace(warningText))
                RemoveDrawObject(WarningTag);
            else
                Draw.TextFixed(this, WarningTag, warningText, TextPosition.TopRight,
                    warningBrush, new SimpleFont("Consolas", 11) { Bold = true },
                    Brushes.Transparent, Brushes.Transparent, 0);

            double? flip = ShowFlip ? NormalizePrice(snapshot != null ? snapshot.gamma_flip : 0d) : null;
            double? callWall = ShowWalls ? NormalizePrice(snapshot != null ? snapshot.call_wall : 0d) : null;
            double? putWall = ShowWalls ? NormalizePrice(snapshot != null ? snapshot.put_wall : 0d) : null;
            double? zeroDteMagnet = ShowZeroDteMagnet ? NormalizePrice(snapshot != null ? snapshot.zero_dte_magnet : 0d) : null;
            double? primaryMagnet = ShowMagnet ? NormalizePrice(snapshot != null && snapshot.primary_magnet.HasValue ? snapshot.primary_magnet.Value : 0d) : null;

            DrawLevel(FlipLineTag, "gex_flip_lbl", flip, "FLIP", Brushes.Gold, DashStyleHelper.Dash, 2);
            DrawLevel(CallWallLineTag, "gex_cwall_lbl", callWall, "CALL WALL", Brushes.Red, DashStyleHelper.Solid, 2);
            DrawLevel(PutWallLineTag, "gex_pwall_lbl", putWall, "PUT WALL", Brushes.LimeGreen, DashStyleHelper.Solid, 2);
            DrawLevel(MagnetLineTag, "gex_0dte_lbl", zeroDteMagnet, "0DTE", Brushes.DeepSkyBlue, DashStyleHelper.Dot, 1);
            DrawLevel(PrimaryMagnetLineTag, "gex_magnet_lbl", primaryMagnet, "\u26A1 MAGNET", Brushes.Yellow, DashStyleHelper.Solid, 2);

            PrintLevels(snapshot, flip, callWall, putWall, zeroDteMagnet, primaryMagnet);
        }

        private void DrawLevel(string lineTag, string labelTag, double? price, string label, Brush brush, DashStyleHelper dashStyle, int width)
        {
            if (!price.HasValue)
            {
                RemoveDrawObject(lineTag);
                RemoveDrawObject(labelTag);
                return;
            }

            Draw.HorizontalLine(this, lineTag, false, price.Value, brush, dashStyle, width);
            Draw.Text(this, labelTag, false,
                label + " " + price.Value.ToString("N2", CultureInfo.InvariantCulture),
                0, price.Value + 2 * TickSize, 0,
                brush, new SimpleFont("Consolas", 10) { Bold = width >= 2 },
                System.Windows.TextAlignment.Left, null, null, 0);
        }

        private void PrintLevels(SnapshotDto snapshot, double? flip, double? callWall, double? putWall, double? zeroDteMagnet, double? primaryMagnet)
        {
            string state = string.Format(CultureInfo.InvariantCulture,
                "dir={0}|conf={1}|flip={2}|call={3}|put={4}|z={5}|pm={6}|status={7}",
                ToDisplay(snapshot != null ? snapshot.direction_signal : null, "FLAT"),
                snapshot != null ? Math.Max(0, snapshot.direction_confidence) : 0,
                FormatNullablePrice(flip),
                FormatNullablePrice(callWall),
                FormatNullablePrice(putWall),
                FormatNullablePrice(zeroDteMagnet),
                FormatNullablePrice(primaryMagnet),
                ToDisplay(snapshot != null ? snapshot.status : null, "UNKNOWN"));

            if (state == _lastPrintedState)
                return;

            _lastPrintedState = state;
            Print(string.Format(CultureInfo.InvariantCulture,
                "[GEXTerminal] draw {0} reason={1}",
                state,
                Shorten(snapshot != null ? snapshot.direction_reason : null, 96)));
        }

        private string BuildHudText(SnapshotDto snapshot)
        {
            if (snapshot == null)
                return "GEX TERMINAL\nWAITING FOR SNAPSHOT";

            string direction = ToDisplay(snapshot.direction_signal, ToDisplay(snapshot.bias_direction, "FLAT"));
            string grade = ToDisplay(snapshot.bias_grade, "-");
            string regime = ToDisplay(snapshot.regime_name, "Unknown");
            string dealerRegime = ToDisplay(snapshot.dealer_regime, "neutral");
            string hedgeDirection = ToDisplay(snapshot.hedge_direction, "neutral");
            string flowDirection = ToDisplay(snapshot.flow_direction, "neutral");
            string headline = Shorten((snapshot.headline ?? string.Empty).Trim(), 84);
            string status = ToDisplay(snapshot.status, "unknown");

            string line1 = string.Format(CultureInfo.InvariantCulture,
                "GEX {0} {1}%  GRADE {2}",
                direction,
                Math.Max(0, snapshot.direction_confidence > 0 ? snapshot.direction_confidence : snapshot.bias_confidence),
                grade);

            string line2 = string.Format(CultureInfo.InvariantCulture,
                "REGIME {0} | STATUS {1}",
                regime,
                status);

            string line3 = string.Format(CultureInfo.InvariantCulture,
                "DEALER {0} | HEDGE {1} | FLOW {2}",
                dealerRegime,
                hedgeDirection,
                flowDirection);

            if (string.IsNullOrWhiteSpace(headline))
                return line1 + "\n" + line2 + "\n" + line3;

            return line1 + "\n" + line2 + "\n" + line3 + "\n" + headline;
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
            return value.ToString("0.00", CultureInfo.InvariantCulture);
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
            RemoveDrawObject(HudTag);
            RemoveDrawObject(WarningTag);
            RemoveDrawObject(FlipLineTag);
            RemoveDrawObject(CallWallLineTag);
            RemoveDrawObject(PutWallLineTag);
            RemoveDrawObject(MagnetLineTag);
            RemoveDrawObject(PrimaryMagnetLineTag);
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
        [Display(Name = "ShowFlip", Order = 3, GroupName = "Display")]
        public bool ShowFlip { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowWalls", Order = 4, GroupName = "Display")]
        public bool ShowWalls { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowZeroDteMagnet", Order = 5, GroupName = "Display")]
        public bool ShowZeroDteMagnet { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowMagnet", Description = "Draw primary magnet level from dark pool + GEX confluence", Order = 6, GroupName = "Display")]
        public bool ShowMagnet { get; set; }

        private class SnapshotDto
        {
            public int schema_version { get; set; }
            public object as_of { get; set; }
            public int stale_after_seconds { get; set; }
            public string status { get; set; }
            public string bias_direction { get; set; }
            public int bias_confidence { get; set; }
            public string bias_grade { get; set; }
            public string direction_signal { get; set; }
            public int direction_confidence { get; set; }
            public string direction_reason { get; set; }
            public string regime_name { get; set; }
            public double gamma_flip { get; set; }
            public double call_wall { get; set; }
            public double put_wall { get; set; }
            public double zero_dte_magnet { get; set; }
            public double hvl { get; set; }
            public double expected_move_up { get; set; }
            public double expected_move_down { get; set; }
            public string dealer_regime { get; set; }
            public string hedge_direction { get; set; }
            public string flow_direction { get; set; }
            public double flow_intensity { get; set; }
            public string headline { get; set; }
            public List<double> dark_pool_levels_nq { get; set; }
            public double? primary_magnet { get; set; }
            public object magnet_confidence { get; set; }
        }
    }
}

