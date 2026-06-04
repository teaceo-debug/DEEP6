// DEEP6 DepthRadar — Full-spectrum DOM liquidity levels indicator.
//
// Carbon copy of FootprintV7's RenderLiquidityWalls / DrawWallsForSide rendering:
//   - Same single brush per side via .ToDxBrush()
//   - Same continuous thickness formula: Min(4, 1.5 + (MaxSize/WallMin)*0.4)
//   - Same label format, font, positioning
//   - Same ICE annotation
//
// Only differences from FootprintV7's built-in L2 walls:
//   - No LiquidityMaxPerSide cap — shows every qualifying level
//   - Full DOM depth (40+ levels, not just top 10)
//   - Glow bloom on levels >= GlowThreshold (100+ by default)
//   - Standalone indicator (own OnMarketDepth subscription)

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Threading;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6DepthRadar : Indicator
    {
        // ---- L2 Level State (identical to FootprintV7.L2LevelState) ----
        private sealed class L2LevelState
        {
            public long     CurrentSize;
            public long     MaxSize;
            public DateTime LastUpdate;
            public int      RefillCount;
        }

        // ---- Per-price dictionaries — written by OnMarketDepth, snapshot-read by OnRender ----
        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;
        private long _depthCallbacks;

        // ---- DX Resources (identical types to FootprintV7) ----
        // Single brush per side — created via .ToDxBrush(), same as FootprintV7._wallBidDx / _wallAskDx
        private SharpDX.Direct2D1.Brush _wallBidDx;
        private SharpDX.Direct2D1.Brush _wallAskDx;
        // Glow bloom brushes for levels >= GlowThreshold (3 passes: outer → inner)
        private SharpDX.Direct2D1.SolidColorBrush[] _glowBidDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowAskDx;
        private static readonly float[] GLOW_ALPHAS = { 0.08f, 0.18f, 0.35f };
        private static readonly float[] GLOW_WIDTHS = { 14f,   8f,    5f    };
        // HUD
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBg;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBorder;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudText;
        // Fonts — same as FootprintV7._labelFont
        private TextFormat _labelFont;
        private TextFormat _hudFont;

        // ---- Invalidation ----
        private Timer _invalidateTimer;
        private int _dirty;
        private const int INVALIDATE_MS = 50;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "Full-spectrum DOM liquidity levels. Identical rendering to DEEP6 Footprint V7 walls — no max cap, full DOM depth, glow on large walls.";
                Name                = "DEEP6 Depth Radar";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                IsSuspendedWhileInactive = false;
                DisplayInDataBox    = false;
                ScaleJustification  = ScaleJustification.Right;

                // Same defaults as FootprintV7 section "5. Liquidity (L2)"
                WallMinSize         = 50;
                WallStaleSec        = 90;
                MaxDepthLevels      = 40;
                GlowThreshold       = 100;
                ShowBids            = true;
                ShowAsks            = true;
                ShowLabels          = true;

                // Same colors as FootprintV7.WallBidBrush / WallAskBrush
                WallBidBrush        = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));   // bright blue
                WallAskBrush        = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));   // warm orange
            }
            else if (State == State.DataLoaded)
            {
                ClearBooks();
                Interlocked.Exchange(ref _dirty, 1);
                if (_invalidateTimer == null)
                    _invalidateTimer = new Timer(OnInvalidateTick, null, INVALIDATE_MS, INVALIDATE_MS);
            }
            else if (State == State.Historical)
            {
                try { SetZOrder(-1); } catch { }
            }
            else if (State == State.Realtime)
            {
                Print("[DEEP6DepthRadar] Realtime — waiting for L2 DOM data from Rithmic");
            }
            else if (State == State.Terminated)
            {
                if (_invalidateTimer != null) { _invalidateTimer.Dispose(); _invalidateTimer = null; }
                DisposeDx();
                ClearBooks();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0 || CurrentBar < 0) return;

            if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
            {
                ClearBooks();
                Interlocked.Exchange(ref _depthCallbacks, 0);
                Interlocked.Exchange(ref _dirty, 1);
            }
        }

        // ---- L2 depth intake (same as FootprintV7.OnMarketDepth but full DOM depth) ----

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e == null) return;
            if (e.MarketDataType != MarketDataType.Bid && e.MarketDataType != MarketDataType.Ask) return;
            if (e.Price <= 0) return;
            if (MaxDepthLevels > 0 && e.Position >= MaxDepthLevels) return;

            Interlocked.Increment(ref _depthCallbacks);

            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
            var dict = e.MarketDataType == MarketDataType.Bid ? _l2Bids : _l2Asks;

            lock (_l2Lock)
            {
                L2LevelState st;
                if (!dict.TryGetValue(e.Price, out st))
                {
                    st = new L2LevelState();
                    dict[e.Price] = st;
                }

                // Iceberg detection (same logic as FootprintV7)
                if (st.MaxSize > 0 && st.CurrentSize < st.MaxSize * 0.5 && newSize >= st.MaxSize * 0.5)
                    st.RefillCount++;

                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = DateTime.UtcNow;

                // Periodic prune (same 30s cadence as FootprintV7)
                if ((DateTime.UtcNow - _lastL2Prune).TotalSeconds > 30)
                {
                    PruneL2(_l2Bids);
                    PruneL2(_l2Asks);
                    _lastL2Prune = DateTime.UtcNow;
                }
            }

            Interlocked.Exchange(ref _dirty, 1);
        }

        private void PruneL2(Dictionary<double, L2LevelState> dict)
        {
            var cutoff = DateTime.UtcNow.AddSeconds(-Math.Max(WallStaleSec * 3, 300));
            var stale = new List<double>();
            foreach (var kv in dict)
                if (kv.Value.LastUpdate < cutoff) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        // ---- Invalidation timer ----

        private void OnInvalidateTick(object state)
        {
            if (Interlocked.CompareExchange(ref _dirty, 0, 0) != 1) return;
            try
            {
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (ChartControl != null) ChartControl.InvalidateVisual();
                    }));
            }
            catch { }
        }

        // ---- DX Resource Management ----

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            // Single brush per side — identical to FootprintV7:
            //   _wallBidDx = WallBidBrush.ToDxBrush(RenderTarget);
            //   _wallAskDx = WallAskBrush.ToDxBrush(RenderTarget);
            _wallBidDx = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx = WallAskBrush.ToDxBrush(RenderTarget);

            // Glow bloom brushes (same base color, lower alpha, for levels >= GlowThreshold)
            Color bidC = ExtractColor(WallBidBrush, Color.FromArgb(220, 43, 140, 255));
            Color askC = ExtractColor(WallAskBrush, Color.FromArgb(220, 255, 138, 61));
            _glowBidDx = new SharpDX.Direct2D1.SolidColorBrush[3];
            _glowAskDx = new SharpDX.Direct2D1.SolidColorBrush[3];
            for (int g = 0; g < 3; g++)
            {
                _glowBidDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(bidC.R / 255f, bidC.G / 255f, bidC.B / 255f, GLOW_ALPHAS[g]));
                _glowAskDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(askC.R / 255f, askC.G / 255f, askC.B / 255f, GLOW_ALPHAS[g]));
            }

            // HUD
            _dxHudBg     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.03f, 0.04f, 0.06f, 0.84f));
            _dxHudBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.16f, 0.19f, 0.24f, 1f));
            _dxHudText   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.96f, 0.97f, 0.98f, 1f));

            // Same font as FootprintV7._labelFont: Segoe UI 10pt, trailing alignment
            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment      = SharpDX.DirectWrite.TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
        }

        // ---- Rendering (carbon copy of FootprintV7.RenderLiquidityWalls + DrawWallsForSide) ----

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest) return;
            if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;
            if (_wallBidDx == null || _wallAskDx == null || _labelFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            RenderWalls(chartScale, panelRight);
            Interlocked.Exchange(ref _dirty, 0);
        }

        /// <summary>
        /// Identical to FootprintV7.RenderLiquidityWalls — snapshot under lock, then draw both sides.
        /// </summary>
        private void RenderWalls(ChartScale cs, float panelRight)
        {
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-WallStaleSec);

            // Deep-clone inside the lock (same pattern as FootprintV7)
            List<KeyValuePair<double, L2LevelState>> bidSnap, askSnap;
            lock (_l2Lock)
            {
                bidSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Bids.Count);
                foreach (var kv in _l2Bids)
                    bidSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate  = kv.Value.LastUpdate,  RefillCount = kv.Value.RefillCount }));

                askSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Asks.Count);
                foreach (var kv in _l2Asks)
                    askSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate  = kv.Value.LastUpdate,  RefillCount = kv.Value.RefillCount }));
            }

            int bidRendered = 0, askRendered = 0;
            if (ShowBids) bidRendered = DrawWallsForSide(cs, bidSnap, _wallBidDx, "BID", true,  fresh, minVis, maxVis, panelRight);
            if (ShowAsks) askRendered = DrawWallsForSide(cs, askSnap, _wallAskDx, "ASK", false, fresh, minVis, maxVis, panelRight);
            DrawHud(bidRendered, askRendered);
        }

        /// <summary>
        /// Identical to FootprintV7.DrawWallsForSide — same brush, same thickness formula,
        /// same label format, same coordinates. Only change: no LiquidityMaxPerSide cap.
        /// Glow bloom added for levels >= GlowThreshold.
        /// </summary>
        private int DrawWallsForSide(
            ChartScale cs,
            List<KeyValuePair<double, L2LevelState>> snap,
            SharpDX.Direct2D1.Brush brush,
            string side,
            bool isBid,
            DateTime fresh,
            double minVis,
            double maxVis,
            float panelRight)
        {
            if (snap == null || snap.Count == 0) return 0;

            // Filter eligible walls: meet size threshold, recently updated, in visible range.
            var walls = new List<KeyValuePair<double, L2LevelState>>();
            foreach (var kv in snap)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                if (kv.Value.LastUpdate < fresh) continue;
                if (kv.Key < minVis || kv.Key > maxVis) continue;
                walls.Add(kv);
            }

            // Sort by max-size descending (same as FootprintV7).
            walls.Sort((a, b) => b.Value.MaxSize.CompareTo(a.Value.MaxSize));

            // NO cap — show all qualifying walls (FootprintV7 caps at LiquidityMaxPerSide here).
            int show = walls.Count;

            float lastLabelY = float.MinValue;
            const float LABEL_MIN_GAP = 14f;

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                var st = walls[i].Value;
                float y = (float)cs.GetYByValue(price);

                // ── Glow bloom for levels >= GlowThreshold ──
                if (st.MaxSize >= GlowThreshold)
                {
                    var glowBrushes = isBid ? _glowBidDx : _glowAskDx;
                    if (glowBrushes != null)
                    {
                        for (int g = 0; g < 3; g++)
                            RenderTarget.DrawLine(
                                new Vector2((float)ChartPanel.X, y),
                                new Vector2(panelRight - 90, y),
                                glowBrushes[g],
                                GLOW_WIDTHS[g]);
                    }
                }

                // ── Line thickness scales 1.5px → 4px based on size (same formula as FootprintV7) ──
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)WallMinSize) * 0.4);
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight - 90, y),
                    brush, thickness);

                // ── Label (same format as FootprintV7: "BID 21025.50  150 ICE×3") ──
                if (!ShowLabels) continue;

                float labelY = y - 8f;
                if (lastLabelY != float.MinValue && Math.Abs(labelY - lastLabelY) < LABEL_MIN_GAP)
                    continue;

                string label = string.Format("{0} {1:F2}  {2}{3}",
                    side, price, st.MaxSize,
                    st.RefillCount >= 2 ? " ICE\u00d7" + st.RefillCount : "");

                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                    label, _labelFont, 180f, 16f))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 184, labelY), layout, brush);
                }

                lastLabelY = labelY;
            }

            return show;
        }

        private void DrawHud(int bidCount, int askCount)
        {
            if (_hudFont == null || _dxHudBg == null || _dxHudText == null) return;

            long callbacks = Interlocked.Read(ref _depthCallbacks);
            string text = string.Format("DEPTH RADAR | B:{0} A:{1} | cb: {2:N0}",
                bidCount, askCount, callbacks);

            float w = 300f;
            float h = 20f;
            float x = (float)ChartPanel.X + 8f;
            float y = (float)(ChartPanel.Y + ChartPanel.H) - h - 8f;

            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), _dxHudBg);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), _dxHudBorder, 1f);

            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                text, _hudFont, w - 10f, h))
            {
                RenderTarget.DrawTextLayout(new Vector2(x + 5f, y + 2f), layout, _dxHudText);
            }
        }

        // ---- Helpers ----

        private void ClearBooks()
        {
            lock (_l2Lock)
            {
                _l2Bids.Clear();
                _l2Asks.Clear();
                _lastL2Prune = DateTime.MinValue;
            }
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _wallBidDx);
            DisposeBrush(ref _wallAskDx);
            DisposeGlowArray(ref _glowBidDx);
            DisposeGlowArray(ref _glowAskDx);
            DisposeSolidBrush(ref _dxHudBg);
            DisposeSolidBrush(ref _dxHudBorder);
            DisposeSolidBrush(ref _dxHudText);
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
            if (_hudFont   != null) { _hudFont.Dispose();   _hudFont   = null; }
        }

        private static void DisposeGlowArray(ref SharpDX.Direct2D1.SolidColorBrush[] arr)
        {
            if (arr == null) return;
            for (int i = 0; i < arr.Length; i++)
                DisposeSolidBrush(ref arr[i]);
            arr = null;
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b)
        {
            if (b != null) { b.Dispose(); b = null; }
        }

        private static void DisposeSolidBrush(ref SharpDX.Direct2D1.SolidColorBrush b)
        {
            if (b != null) { b.Dispose(); b = null; }
        }

        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        private static Color ExtractColor(Brush brush, Color fallback)
        {
            var solid = brush as SolidColorBrush;
            return solid != null ? solid.Color : fallback;
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 1, GroupName = "1. Liquidity",
            Description = "Minimum contracts to show a level")]
        public int WallMinSize { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 2, GroupName = "1. Liquidity",
            Description = "Hide levels not updated within this window")]
        public int WallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(5, 50)]
        [Display(Name = "Max Depth Levels", Order = 3, GroupName = "1. Liquidity",
            Description = "DOM levels to consume per side (Rithmic provides 40+ for NQ)")]
        public int MaxDepthLevels { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10000)]
        [Display(Name = "Glow Threshold (contracts)", Order = 4, GroupName = "1. Liquidity",
            Description = "Levels at or above this size get a glow bloom effect")]
        public int GlowThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Bids", Order = 1, GroupName = "2. Display")]
        public bool ShowBids { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Asks", Order = 2, GroupName = "2. Display")]
        public bool ShowAsks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Labels", Order = 3, GroupName = "2. Display")]
        public bool ShowLabels { get; set; }

        [XmlIgnore]
        [Display(Name = "Bid Color (resting buy)", Order = 1, GroupName = "3. Colors")]
        public Brush WallBidBrush { get; set; }

        [Browsable(false)]
        public string WallBidBrushSerialize
        {
            get { return Serialize.BrushToString(WallBidBrush); }
            set { WallBidBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Ask Color (resting sell)", Order = 2, GroupName = "3. Colors")]
        public Brush WallAskBrush { get; set; }

        [Browsable(false)]
        public string WallAskBrushSerialize
        {
            get { return Serialize.BrushToString(WallAskBrush); }
            set { WallAskBrush = Serialize.StringToBrush(value); }
        }

        #endregion
    }
}
