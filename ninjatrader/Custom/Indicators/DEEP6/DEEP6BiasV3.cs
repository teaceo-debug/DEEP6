#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Xml.Serialization;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = SharpDX.Direct2D1.Brush;
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using Ellipse = SharpDX.Direct2D1.Ellipse;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6BiasV3 : Indicator
    {
        private const float HudWidth = 280f;
        private const float HudHeight = 128f;
        private const double RenderThrottleMs = 125.0;
        private readonly object snapshotLock = new object();
        private Timer refreshTimer;
        private BiasSnapshot activeBias;
        private string statusText = "WAITING FOR BIAS ENGINE";
        private DateTime lastJsonWriteTimeUtc = DateTime.MinValue;
        private int lastFileAgeSeconds = int.MaxValue;
        private bool isStale;
        private string lastSignature = "";
        private DateTime lastRenderUtc = DateTime.MinValue;
        private TextFormat titleFormat, bodyFormat, smallFormat;
        private Brush panelBrush, borderBrush, textBrush, mutedBrush;
        private Brush bullBrush, bearBrush, neutralBrush;
        private Brush greenBrush, amberBrush, redBrush;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Bias v3 HUD — reads bias_v3.json and renders directional bias overlay.";
                Name = "DEEP6BiasV3";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = false;
                IsSuspendedWhileInactive = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                BarsRequiredToPlot = 0;
                JsonFilePath = @"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\bias_v3.json";
                RefreshSeconds = 5;
                StaleThresholdSeconds = 30;
                HudOffsetX = 15;
                HudOffsetY = 15;
                HudOpacity = 0.85;
            }
            else if (State == State.Historical)
            {
                refreshTimer = new Timer(ReadSnapshotSafe, null, 500, Math.Max(1, RefreshSeconds) * 1000);
            }
            else if (State == State.Terminated)
            {
                if (refreshTimer != null) { refreshTimer.Dispose(); refreshTimer = null; }
                DisposeDx();
            }
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;
            float a = (float)Math.Max(0.10, Math.Min(1.00, HudOpacity));
            titleFormat = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", FontWeight.Bold, FontStyle.Normal, 14f);
            bodyFormat = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", FontWeight.Normal, FontStyle.Normal, 12f);
            smallFormat = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", FontWeight.Normal, FontStyle.Normal, 11f);
            panelBrush = new SolidColorBrush(RenderTarget, new Color4(0.08f, 0.08f, 0.10f, a));
            borderBrush = new SolidColorBrush(RenderTarget, new Color4(0.30f, 0.30f, 0.34f, Math.Min(1f, a + 0.10f)));
            textBrush = new SolidColorBrush(RenderTarget, new Color4(0.96f, 0.96f, 0.97f, 1f));
            mutedBrush = new SolidColorBrush(RenderTarget, new Color4(0.47f, 0.56f, 0.61f, 1f));
            bullBrush = new SolidColorBrush(RenderTarget, new Color4(0.00f, 0.78f, 0.33f, 1f));
            bearBrush = new SolidColorBrush(RenderTarget, new Color4(1.00f, 0.09f, 0.27f, 1f));
            neutralBrush = new SolidColorBrush(RenderTarget, new Color4(0.47f, 0.56f, 0.61f, 1f));
            greenBrush = new SolidColorBrush(RenderTarget, new Color4(0.00f, 0.78f, 0.33f, 1f));
            amberBrush = new SolidColorBrush(RenderTarget, new Color4(1.00f, 0.70f, 0.00f, 1f));
            redBrush = new SolidColorBrush(RenderTarget, new Color4(1.00f, 0.09f, 0.27f, 1f));
        }

        private void DisposeDx()
        {
            if (titleFormat != null) { titleFormat.Dispose(); titleFormat = null; }
            if (bodyFormat != null) { bodyFormat.Dispose(); bodyFormat = null; }
            if (smallFormat != null) { smallFormat.Dispose(); smallFormat = null; }
            Db(ref panelBrush); Db(ref borderBrush); Db(ref textBrush); Db(ref mutedBrush);
            Db(ref bullBrush); Db(ref bearBrush); Db(ref neutralBrush);
            Db(ref greenBrush); Db(ref amberBrush); Db(ref redBrush);
        }
        private static void Db(ref Brush b) { if (b != null) { b.Dispose(); b = null; } }

        private void ReadSnapshotSafe(object state)
        {
            try { ReadSnapshot(); }
            catch (Exception ex)
            {
                lock (snapshotLock) { activeBias = null; statusText = "READ ERROR: " + ex.Message; isStale = true; }
                Rr();
            }
        }

        private void ReadSnapshot()
        {
            string path = JsonFilePath;
            if (!File.Exists(path))
            {
                lock (snapshotLock) { activeBias = null; statusText = "WAITING FOR BIAS ENGINE"; isStale = false; }
                Rr(); return;
            }
            DateTime wt = File.GetLastWriteTimeUtc(path);
            int age = Math.Max(0, (int)(DateTime.UtcNow - wt).TotalSeconds);
            bool st = age > Math.Max(1, StaleThresholdSeconds);
            if (wt == lastJsonWriteTimeUtc)
            {
                bool changed;
                lock (snapshotLock) { changed = (isStale != st); lastFileAgeSeconds = age; isStale = st; }
                if (changed) Rr();
                return;
            }
            var ser = new JavaScriptSerializer();
            BiasSnapshot payload;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs))
                payload = ser.Deserialize<BiasSnapshot>(sr.ReadToEnd());
            lock (snapshotLock)
            {
                activeBias = payload; lastJsonWriteTimeUtc = wt;
                lastFileAgeSeconds = age; isStale = st;
                statusText = st ? string.Format("STALE ({0}s ago)", age) : "OK";
            }
            Rr();
        }

        private void Rr()
        {
            if (ChartControl != null)
                ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
        }

        protected override void OnBarUpdate() { }

        protected override void OnRender(ChartControl cc, ChartScale cs)
        {
            base.OnRender(cc, cs);
            if (RenderTarget == null || ChartPanel == null || titleFormat == null) return;
            if ((DateTime.UtcNow - lastRenderUtc).TotalMilliseconds < RenderThrottleMs) return;
            lastRenderUtc = DateTime.UtcNow;

            BiasSnapshot snap; string st; bool stale; int age;
            lock (snapshotLock) { snap = activeBias; st = statusText; stale = isStale; age = lastFileAgeSeconds; }

            float x = (float)(ChartPanel.X + HudOffsetX);
            float y = (float)(ChartPanel.Y + HudOffsetY);
            float h = stale ? HudHeight + 22f : HudHeight;
            var rect = new RectangleF(x, y, HudWidth, h);
            var rr = new RoundedRectangle { Rect = rect, RadiusX = 8f, RadiusY = 8f };
            RenderTarget.FillRoundedRectangle(rr, panelBrush);
            RenderTarget.DrawRoundedRectangle(rr, borderBrush, 1f);

            if (snap == null)
            {
                RenderTarget.DrawText(st, titleFormat, new RectangleF(x + 12f, y + 16f, HudWidth - 24f, 28f), textBrush);
                return;
            }

            Brush db = Db2(snap.bias_label); Brush mb = Mb2(snap.mode);
            string arrow = (snap.bias_label ?? "").ToUpperInvariant().Contains("BULL") ? "^" :
                           (snap.bias_label ?? "").ToUpperInvariant().Contains("BEAR") ? "v" : "-";
            int cpct = snap.confidence_pct > 0 ? snap.confidence_pct : (int)Math.Round(snap.confidence * 100.0);

            float rx = x + 12f, ry = y + 10f;
            RenderTarget.DrawText(string.Format("{0} {1}", snap.bias_label ?? "NEUTRAL", arrow), titleFormat,
                new RectangleF(rx, ry, HudWidth - 24f, 22f), db);

            ry += 26f;
            RenderTarget.DrawText(string.Format("Score: {0}{1}", snap.bias_score >= 0 ? "+" : "", snap.bias_score),
                bodyFormat, new RectangleF(rx, ry, 110f, 20f), db);
            RenderTarget.DrawText(string.Format("Conf: {0}%", cpct),
                bodyFormat, new RectangleF(rx + 118f, ry, 120f, 20f), textBrush);

            ry += 24f;
            RenderTarget.FillEllipse(new Ellipse(new Vector2(rx + 7f, ry + 9f), 6f, 6f), mb);
            RenderTarget.DrawText(snap.mode ?? "UNKNOWN", bodyFormat,
                new RectangleF(rx + 20f, ry - 1f, 120f, 20f), mb);

            ry += 24f;
            RenderTarget.DrawText(string.Format("{0} | {1}", snap.session_label ?? "?", snap.xamd_phase ?? "?"),
                smallFormat, new RectangleF(rx, ry, HudWidth - 24f, 18f), mutedBrush);

            if (stale)
            {
                ry += 22f;
                RenderTarget.DrawText(string.Format("STALE ({0}s ago)", age), smallFormat,
                    new RectangleF(rx, ry, HudWidth - 24f, 18f), amberBrush);
            }
        }

        private Brush Db2(string l) { string v = (l ?? "").ToUpperInvariant(); return v.Contains("BULL") ? bullBrush : v.Contains("BEAR") ? bearBrush : neutralBrush; }
        private Brush Mb2(string m) { string v = (m ?? "").ToUpperInvariant(); return v == "GO" ? greenBrush : v == "CAUTION" ? amberBrush : v == "STOP" ? redBrush : mutedBrush; }

        [NinjaScriptProperty][Display(Name = "JSON File Path", GroupName = "1. Data", Order = 1)]
        public string JsonFilePath { get; set; }
        [NinjaScriptProperty][Range(1, 60)][Display(Name = "Refresh Seconds", GroupName = "1. Data", Order = 2)]
        public int RefreshSeconds { get; set; }
        [NinjaScriptProperty][Range(1, 300)][Display(Name = "Stale Threshold Sec", GroupName = "1. Data", Order = 3)]
        public int StaleThresholdSeconds { get; set; }
        [NinjaScriptProperty][Display(Name = "HUD Offset X", GroupName = "2. HUD", Order = 1)]
        public int HudOffsetX { get; set; }
        [NinjaScriptProperty][Display(Name = "HUD Offset Y", GroupName = "2. HUD", Order = 2)]
        public int HudOffsetY { get; set; }
        [NinjaScriptProperty][Range(0.10, 1.00)][Display(Name = "HUD Opacity", GroupName = "2. HUD", Order = 3)]
        public double HudOpacity { get; set; }
    }

    public class BiasSnapshot
    {
        public string bias_label { get; set; }
        public int bias_score { get; set; }
        public double confidence { get; set; }
        public int confidence_pct { get; set; }
        public string mode { get; set; }
        public string mode_reason { get; set; }
        public string session_label { get; set; }
        public string xamd_phase { get; set; }
        public Dictionary<string, int> domain_scores { get; set; }
        public int setup_quality { get; set; }
        public double updated_ts { get; set; }
        public string version { get; set; }
    }
}