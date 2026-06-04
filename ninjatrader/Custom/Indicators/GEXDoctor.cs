#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Windows.Media;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class GEXDoctor : Indicator
    {
        private const string MagnetLineTag = "gexdoctor_magnet";
        private const string MagnetLabelTag = "gexdoctor_magnet_label";
        private const string CallWallLineTag = "gexdoctor_call_wall";
        private const string CallWallLabelTag = "gexdoctor_call_wall_label";
        private const string PutWallLineTag = "gexdoctor_put_wall";
        private const string PutWallLabelTag = "gexdoctor_put_wall_label";
        private const string FlipLineTag = "gexdoctor_flip";
        private const string FlipLabelTag = "gexdoctor_flip_label";
        private const string InvalidationLineTag = "gexdoctor_invalidation";
        private const string InvalidationLabelTag = "gexdoctor_invalidation_label";
        private const string BiasTextTag = "bias_text";
        private const string StaleWarnTag = "stale_warn";

        private DateTime _lastUpdateUtc = DateTime.MinValue;
        private string _statusText = "GEX: Initializing...";
        private Brush _statusBrush = Brushes.White;
        private bool _isStale;
        private string _lastLoggedError = string.Empty;

        private double? _flip;
        private double? _callWall;
        private double? _putWall;
        private double? _primaryMagnet;
        private double? _invalidationLevel;
        private double? _magnetConfidence;
        private string _biasDirection = string.Empty;
        private string _regime = string.Empty;
        private string _invalidationReason = string.Empty;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "GEXDoctor";
                Description = "Reads enriched gex_nq.json and renders magnet, walls, gamma flip, invalidation, and bias.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;

                GexFilePath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json";
                UpdateIntervalSeconds = 60;
                ShowMagnet = true;
                ShowInvalidation = true;
                ShowFlip = true;
            }
            else if (State == State.Terminated)
            {
                ClearDrawings();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            if (_lastUpdateUtc == DateTime.MinValue || (DateTime.UtcNow - _lastUpdateUtc).TotalSeconds >= Math.Max(1, UpdateIntervalSeconds))
                UpdateGexData();

            RenderOverlay();
        }

        private void UpdateGexData()
        {
            _lastUpdateUtc = DateTime.UtcNow;

            try
            {
                if (string.IsNullOrWhiteSpace(GexFilePath) || !File.Exists(GexFilePath))
                {
                    SetNoData("GEX: No Data", "file_not_found", "GEXDoctor file not found: " + GexFilePath);
                    return;
                }

                string json = File.ReadAllText(GexFilePath);
                using (JsonDocument document = JsonDocument.Parse(json))
                {
                    JsonElement root = document.RootElement;

                    _flip = ReadPositiveDouble(root, "flip");
                    _callWall = ReadPositiveDouble(root, "call_wall");
                    _putWall = ReadPositiveDouble(root, "put_wall");
                    _primaryMagnet = ReadPositiveDouble(root, "primary_magnet");
                    _invalidationLevel = ReadPositiveDouble(root, "invalidation_level");
                    _magnetConfidence = ReadUnitInterval(root, "magnet_confidence");
                    _biasDirection = ReadString(root, "bias_direction");
                    _regime = ReadString(root, "regime");
                    _invalidationReason = ReadString(root, "invalidation_reason");
                    _isStale = ComputeIsStale(root);

                    bool hasRequiredLevels = _flip.HasValue && _callWall.HasValue && _putWall.HasValue;
                    if (!hasRequiredLevels)
                        LogOnce("missing_required_fields", "GEXDoctor missing one or more required fields: flip/call_wall/put_wall");
                    else
                        _lastLoggedError = string.Empty;

                    _statusText = BuildBiasText(hasRequiredLevels);
                    _statusBrush = GetBiasBrush(_biasDirection);
                }
            }
            catch (JsonException ex)
            {
                SetNoData("GEX: Parse Error", "parse_error", "GEXDoctor parse error: " + ex.Message);
            }
            catch (Exception ex)
            {
                SetNoData("GEX: Read Error", "read_error", "GEXDoctor read error: " + ex.Message);
            }
        }

        private void RenderOverlay()
        {
            Draw.TextFixed(this, BiasTextTag, _statusText, TextPosition.TopLeft,
                _statusBrush, new SimpleFont("Consolas", 11) { Bold = true },
                Brushes.Transparent, Brushes.Transparent, 0);

            if (_isStale)
            {
                Draw.TextFixed(this, StaleWarnTag, "⚠ GEX DATA STALE", TextPosition.TopRight,
                    Brushes.Red, new SimpleFont("Consolas", 11) { Bold = true },
                    Brushes.Transparent, Brushes.Transparent, 0);
            }
            else
            {
                RemoveDrawObject(StaleWarnTag);
            }

            DrawLevel(MagnetLineTag, MagnetLabelTag, ShowMagnet ? _primaryMagnet : null,
                "⚡ MAGNET", Brushes.Yellow, DashStyleHelper.Solid, 3, 3 * TickSize);
            DrawLevel(CallWallLineTag, CallWallLabelTag, _callWall,
                "CW", Brushes.LimeGreen, DashStyleHelper.Solid, 2, 2 * TickSize);
            DrawLevel(PutWallLineTag, PutWallLabelTag, _putWall,
                "PW", Brushes.OrangeRed, DashStyleHelper.Solid, 2, -2 * TickSize);
            DrawLevel(FlipLineTag, FlipLabelTag, ShowFlip ? _flip : null,
                "FLIP", Brushes.Gold, DashStyleHelper.Dash, 1, TickSize);
            DrawLevel(InvalidationLineTag, InvalidationLabelTag, ShowInvalidation ? _invalidationLevel : null,
                "INVALID", Brushes.Gray, DashStyleHelper.Solid, 1, -TickSize);
        }

        private void DrawLevel(string lineTag, string labelTag, double? price, string prefix, Brush color, DashStyleHelper dashStyle, int width, double labelOffset)
        {
            if (!price.HasValue || price.Value <= 0)
            {
                RemoveDrawObject(lineTag);
                RemoveDrawObject(labelTag);
                return;
            }

            Draw.HorizontalLine(this, lineTag, false, price.Value, color, dashStyle, width);
            Draw.Text(this, labelTag, false,
                prefix + " " + FormatLevel(price.Value),
                0, price.Value + labelOffset, 0,
                color, new SimpleFont("Consolas", 10) { Bold = width >= 2 },
                System.Windows.TextAlignment.Left, null, null, 0);
        }

        private void ClearDrawings()
        {
            RemoveDrawObject(MagnetLineTag);
            RemoveDrawObject(MagnetLabelTag);
            RemoveDrawObject(CallWallLineTag);
            RemoveDrawObject(CallWallLabelTag);
            RemoveDrawObject(PutWallLineTag);
            RemoveDrawObject(PutWallLabelTag);
            RemoveDrawObject(FlipLineTag);
            RemoveDrawObject(FlipLabelTag);
            RemoveDrawObject(InvalidationLineTag);
            RemoveDrawObject(InvalidationLabelTag);
            RemoveDrawObject(BiasTextTag);
            RemoveDrawObject(StaleWarnTag);
        }

        private void SetNoData(string status, string errorKey, string logMessage)
        {
            _flip = null;
            _callWall = null;
            _putWall = null;
            _primaryMagnet = null;
            _invalidationLevel = null;
            _magnetConfidence = null;
            _biasDirection = string.Empty;
            _regime = string.Empty;
            _invalidationReason = string.Empty;
            _isStale = false;
            _statusText = status;
            _statusBrush = Brushes.White;
            LogOnce(errorKey, logMessage);
        }

        private void LogOnce(string key, string message)
        {
            if (string.Equals(_lastLoggedError, key, StringComparison.Ordinal))
                return;

            _lastLoggedError = key;
            Print(message);
        }

        private string BuildBiasText(bool hasRequiredLevels)
        {
            if (!hasRequiredLevels)
                return "GEX: Incomplete Data";

            string biasLabel = ToDisplayCase(_biasDirection);
            string confidenceText = _magnetConfidence.HasValue
                ? string.Format(CultureInfo.InvariantCulture, " {0:0}%", _magnetConfidence.Value)
                : string.Empty;
            string regimeText = string.IsNullOrWhiteSpace(_regime) ? "UNKNOWN" : _regime;
            string callText = _callWall.HasValue ? FormatLevel(_callWall.Value) : "--";
            string putText = _putWall.HasValue ? FormatLevel(_putWall.Value) : "--";

            string text = string.Format(CultureInfo.InvariantCulture,
                "GEX: {0}{1} | {2} | CW {3} | PW {4}",
                biasLabel, confidenceText, regimeText, callText, putText);

            if (!string.IsNullOrWhiteSpace(_invalidationReason))
                text += " | " + _invalidationReason;

            return text;
        }

        private bool ComputeIsStale(JsonElement root)
        {
            string asOfText = ReadString(root, "as_of");
            int staleAfterSeconds = ReadInt(root, "stale_after_seconds", 300);
            if (string.IsNullOrWhiteSpace(asOfText))
                return false;

            DateTimeOffset asOf;
            if (!DateTimeOffset.TryParse(asOfText, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out asOf))
                return false;

            return (DateTimeOffset.UtcNow - asOf.ToUniversalTime()).TotalSeconds > Math.Max(1, staleAfterSeconds);
        }

        private static double? ReadPositiveDouble(JsonElement root, string name)
        {
            double value;
            if (!TryReadDouble(root, name, out value))
                return null;

            return value > 0 ? (double?)value : null;
        }

        private static double? ReadUnitInterval(JsonElement root, string name)
        {
            double value;
            if (!TryReadDouble(root, name, out value))
                return null;

            if (value < 0)
                value = 0;
            if (value > 1)
                value = 1;
            return value;
        }

        private static bool TryReadDouble(JsonElement root, string name, out double value)
        {
            value = 0;

            JsonElement element;
            if (!root.TryGetProperty(name, out element))
                return false;

            if (element.ValueKind == JsonValueKind.Number)
                return element.TryGetDouble(out value);

            if (element.ValueKind == JsonValueKind.String)
                return double.TryParse(element.GetString(), NumberStyles.Any, CultureInfo.InvariantCulture, out value);

            return false;
        }

        private static int ReadInt(JsonElement root, string name, int defaultValue)
        {
            JsonElement element;
            if (!root.TryGetProperty(name, out element))
                return defaultValue;

            if (element.ValueKind == JsonValueKind.Number)
            {
                int intValue;
                if (element.TryGetInt32(out intValue))
                    return intValue;

                double doubleValue;
                if (element.TryGetDouble(out doubleValue))
                    return (int)Math.Round(doubleValue);
            }

            if (element.ValueKind == JsonValueKind.String)
            {
                int intValue;
                if (int.TryParse(element.GetString(), NumberStyles.Any, CultureInfo.InvariantCulture, out intValue))
                    return intValue;
            }

            return defaultValue;
        }

        private static string ReadString(JsonElement root, string name)
        {
            JsonElement element;
            if (!root.TryGetProperty(name, out element) || element.ValueKind == JsonValueKind.Null)
                return string.Empty;

            if (element.ValueKind == JsonValueKind.String)
                return element.GetString() ?? string.Empty;

            return element.ToString();
        }

        private Brush GetBiasBrush(string biasDirection)
        {
            string bias = (biasDirection ?? string.Empty).Trim().ToLowerInvariant();
            if (bias == "bullish")
                return Brushes.LimeGreen;
            if (bias == "bearish")
                return Brushes.OrangeRed;
            return Brushes.White;
        }

        private string ToDisplayCase(string raw)
        {
            string text = (raw ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(text))
                return "Neutral";

            text = text.Replace("_", " ").ToLowerInvariant();
            TextInfo textInfo = CultureInfo.InvariantCulture.TextInfo;
            return textInfo.ToTitleCase(text);
        }

        private string FormatLevel(double value)
        {
            return value.ToString("0.##", CultureInfo.InvariantCulture);
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "GEX File Path", Order = 1, GroupName = "GEX Doctor")]
        public string GexFilePath { get; set; }

        [NinjaScriptProperty]
        [Range(1, 3600)]
        [Display(Name = "Update Interval Seconds", Order = 2, GroupName = "GEX Doctor")]
        public int UpdateIntervalSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Magnet", Order = 3, GroupName = "Display")]
        public bool ShowMagnet { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Invalidation", Order = 4, GroupName = "Display")]
        public bool ShowInvalidation { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Flip", Order = 5, GroupName = "Display")]
        public bool ShowFlip { get; set; }
        #endregion
    }
}
