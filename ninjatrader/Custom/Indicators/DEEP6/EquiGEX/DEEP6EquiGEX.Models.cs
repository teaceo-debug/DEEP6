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
    public enum ZoneType { Premium, Equilibrium, Discount, Unknown }
    public enum GammaRegime { Positive, Negative, Unknown }
    public enum BiasDirection { Bullish, Bearish, Neutral }
    public enum TrendDirection { Bullish, Bearish, Neutral }

    public class GexSnapshot
    {
        public string asof { get; set; }
        public string underlying { get; set; }
        public double spot { get; set; }
        public GexTenor weekly { get; set; }
        public GexTenor daily { get; set; }
    }

    public class GexTenor
    {
        public List<GexStrike> strikes { get; set; }
        public double call_wall { get; set; }
        public double zero_gamma { get; set; }
        public double put_wall { get; set; }
        public double net_gex { get; set; }
    }

    public class GexStrike
    {
        public double k { get; set; }
        public double gex { get; set; }
    }

    public partial class DEEP6EquiGEX
    {
        private class GexState
        {
            public GexSnapshot Snapshot;
            public DateTime LastValidRead;
            public bool IsStale;
            public bool HasData;
            public string StatusText;
        }

        private readonly object _gexLock = new object();
        private GexState _gexState = new GexState();
        private Timer _jsonTimer;
        private static readonly JavaScriptSerializer _jsonSerializer = new JavaScriptSerializer();
        private const int JSON_POLL_MS = 30000;
        private const int STALE_THRESHOLD_SEC = 600;

        private void StartJsonPolling()
        {
            _jsonTimer = new Timer(ReadSnapshotSafe, null, 0, JSON_POLL_MS);
        }

        private void StopJsonPolling()
        {
            if (_jsonTimer != null)
            {
                _jsonTimer.Dispose();
                _jsonTimer = null;
            }
        }

        private void ReadSnapshotSafe(object state)
        {
            try
            {
                ReadSnapshot();
            }
            catch (Exception ex)
            {
                lock (_gexLock)
                {
                    _gexState.StatusText = "Read error: " + ex.Message;
                }
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
            }
        }

        private void ReadSnapshot()
        {
            string path = GexJsonPath;
            if (string.IsNullOrEmpty(path))
                path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    @"NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json");

            if (!File.Exists(path))
            {
                lock (_gexLock)
                {
                    _gexState.HasData = false;
                    _gexState.StatusText = "Missing JSON";
                }
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
                return;
            }

            GexSnapshot snapshot;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs))
                snapshot = _jsonSerializer.Deserialize<GexSnapshot>(sr.ReadToEnd());

            string root = NormalizeRoot(Instrument.MasterInstrument.Name);
            if (snapshot == null || string.IsNullOrEmpty(snapshot.underlying)
                || !string.Equals(root, snapshot.underlying, StringComparison.OrdinalIgnoreCase))
            {
                lock (_gexLock)
                {
                    _gexState.HasData = false;
                    _gexState.StatusText = "No matching asset";
                }
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
                return;
            }

            bool isStale = false;
            if (!string.IsNullOrEmpty(snapshot.asof))
            {
                DateTime asofUtc;
                if (DateTime.TryParse(snapshot.asof, System.Globalization.CultureInfo.InvariantCulture,
                    System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal,
                    out asofUtc))
                {
                    isStale = (DateTime.UtcNow - asofUtc).TotalSeconds > STALE_THRESHOLD_SEC;
                }
            }

            lock (_gexLock)
            {
                _gexState.Snapshot = snapshot;
                _gexState.HasData = true;
                _gexState.IsStale = isStale;
                _gexState.LastValidRead = DateTime.UtcNow;
                _gexState.StatusText = isStale ? "STALE FEED" : "OK";
            }

            if (ChartControl != null)
                ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
        }

        private GexState GetGexState()
        {
            lock (_gexLock) { return _gexState; }
        }
    }
}
