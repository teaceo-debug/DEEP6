// MADConfluenceAI.Scoring.cs — Confluence scoring, setup classification, market context, trade decision
using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public enum MADRegime { Trending, Ranging, Volatile, Thin }
    public enum MADTrend { Bullish, Bearish, Neutral }
    public enum MADSessionType { TrendDay, RotationalDay, BreakoutDay, ChopDay, Unknown }
    public enum MADTier { Elite, High, Moderate, Wait, DoNotTrade }
    public enum MADAction { Long, Short, Wait, DoNotTrade }
    public enum MADSetupType { Reversal, Breakout, FailedBreakout, AbsorptionBounce, TrendContinuation, ExhaustionReversal, LiquiditySweepReversal, None }

    public sealed class MADScorerResult
    {
        public double Score;
        public MADTier Tier;
        public MADSignalDirection Direction;
        public string Detail;
        public List<MADSignalResult> ContributingSignals = new List<MADSignalResult>();
    }

    public sealed class MADMarketContext
    {
        public MADTrend TrendDirection;
        public double TimeModifier;
        public MADSessionType SessionType;
        public double Momentum;
    }

    public sealed class MADDecision
    {
        public MADAction Action;
        public double Score;
        public MADTier Tier;
        public MADSetupType SetupType;
        public double StopPrice;
        public double TargetPrice;
        public double RiskRewardRatio;
        public string Detail;
    }

    public enum MADLevelType
    {
        PrevDayHigh, PrevDayLow, PrevDayMid,
        PrevWeekHigh, PrevWeekLow,
        VwapLine, Vwap1SigmaUp, Vwap1SigmaDown, Vwap2SigmaUp, Vwap2SigmaDown, Vwap3SigmaUp, Vwap3SigmaDown,
        SessionPoc, SessionVah, SessionVal,
        OpeningRangeHigh, OpeningRangeLow,
        SessionHigh, SessionLow,
        Psychological,
        NakedPoc
    }

    public sealed class MADLevel
    {
        public MADLevelType Type;
        public double Price;
        public int TouchCount;          // how many times price has tested this level
        public DateTime CreatedDate;    // session/week when created
        public double QualityScore;     // 0-1 computed from confluence + age + touch count

        public void ComputeQuality(double currentPrice, double tickSize, List<MADLevel> allLevels)
        {
            // Base quality by type
            double baseQuality = Type switch
            {
                MADLevelType.PrevDayHigh or MADLevelType.PrevDayLow => 0.8,
                MADLevelType.SessionPoc => 0.75,
                MADLevelType.SessionVah or MADLevelType.SessionVal => 0.65,
                MADLevelType.VwapLine => 0.70,
                MADLevelType.NakedPoc => 0.85,
                MADLevelType.Psychological => 0.50,
                MADLevelType.OpeningRangeHigh or MADLevelType.OpeningRangeLow => 0.60,
                _ => 0.40
            };

            // Touch count bonus (each touch = +0.05, max +0.15)
            double touchBonus = Math.Min(0.15, TouchCount * 0.05);

            // Confluence bonus: +0.15 if another level within 1 tick
            int confluenceCount = 0;
            foreach (var other in allLevels)
            {
                if (other == this) continue;
                if (Math.Abs(other.Price - Price) <= tickSize) confluenceCount++;
            }
            double confluenceBonus = confluenceCount > 0 ? Math.Min(0.15, confluenceCount * 0.08) : 0;

            QualityScore = Math.Min(1.0, baseQuality + touchBonus + confluenceBonus);
        }
    }

    public sealed class MADLevelEngine
    {
        private const double TickSize = 0.25;   // NQ tick size
        private const int MaxLevels = 200;

        private List<MADLevel> _levels = new List<MADLevel>();

        // VWAP state (reset each session)
        private double _vwapSumPV = 0;    // sum of (price * volume)
        private double _vwapSumV = 0;     // sum of volume
        private double _vwapSumV_PV2 = 0; // sum of (volume * price^2) for variance
        public double VwapValue { get; private set; }
        public double Vwap1SigmaUp { get; private set; }
        public double Vwap1SigmaDown { get; private set; }
        public double Vwap2SigmaUp { get; private set; }
        public double Vwap2SigmaDown { get; private set; }

        public IReadOnlyList<MADLevel> Levels => _levels;

        // Update VWAP with a new tick: price and volume
        public void UpdateVwap(double price, long volume)
        {
            _vwapSumPV += price * volume;
            _vwapSumV += volume;
            _vwapSumV_PV2 += volume * price * price;

            if (_vwapSumV == 0) return;
            VwapValue = _vwapSumPV / _vwapSumV;

            // Standard deviation: sqrt(sum(v*p^2)/sum(v) - VWAP^2)
            double variance = (_vwapSumV_PV2 / _vwapSumV) - (VwapValue * VwapValue);
            double sigma = variance > 0 ? Math.Sqrt(variance) : 0;

            Vwap1SigmaUp = VwapValue + sigma;
            Vwap1SigmaDown = VwapValue - sigma;
            Vwap2SigmaUp = VwapValue + 2 * sigma;
            Vwap2SigmaDown = VwapValue - 2 * sigma;

            // Update VWAP level in list
            UpdateOrAddLevel(MADLevelType.VwapLine, VwapValue);
            UpdateOrAddLevel(MADLevelType.Vwap1SigmaUp, Vwap1SigmaUp);
            UpdateOrAddLevel(MADLevelType.Vwap1SigmaDown, Vwap1SigmaDown);
            UpdateOrAddLevel(MADLevelType.Vwap2SigmaUp, Vwap2SigmaUp);
            UpdateOrAddLevel(MADLevelType.Vwap2SigmaDown, Vwap2SigmaDown);
        }

        private void UpdateOrAddLevel(MADLevelType type, double price)
        {
            for (int i = 0; i < _levels.Count; i++)
            {
                if (_levels[i].Type == type) { _levels[i].Price = price; return; }
            }
            AddLevel(type, price);
        }

        public void SetPriorDayLevels(double high, double low)
        {
            AddLevel(MADLevelType.PrevDayHigh, high);
            AddLevel(MADLevelType.PrevDayLow, low);
            AddLevel(MADLevelType.PrevDayMid, (high + low) / 2.0);
        }

        public void SetVolumeLevels(double poc, double vah, double val)
        {
            UpdateOrAddLevel(MADLevelType.SessionPoc, poc);
            UpdateOrAddLevel(MADLevelType.SessionVah, vah);
            UpdateOrAddLevel(MADLevelType.SessionVal, val);
        }

        public void SetOpeningRange(double orHigh, double orLow)
        {
            UpdateOrAddLevel(MADLevelType.OpeningRangeHigh, orHigh);
            UpdateOrAddLevel(MADLevelType.OpeningRangeLow, orLow);
        }

        public void SetSessionExtremes(double sessionHigh, double sessionLow)
        {
            UpdateOrAddLevel(MADLevelType.SessionHigh, sessionHigh);
            UpdateOrAddLevel(MADLevelType.SessionLow, sessionLow);
        }

        // Record a price touching a level (increments TouchCount)
        public void RecordTouch(double price)
        {
            foreach (var level in _levels)
            {
                if (Math.Abs(level.Price - price) <= TickSize)
                    level.TouchCount++;
            }
        }

        // Get all levels within `tolerance` ticks of `price`, sorted by quality desc
        public List<MADLevel> GetNearbyLevels(double price, double toleranceTicks)
        {
            double tolerancePoints = toleranceTicks * TickSize;
            var nearby = new List<MADLevel>();
            foreach (var level in _levels)
            {
                if (Math.Abs(level.Price - price) <= tolerancePoints)
                    nearby.Add(level);
            }
            nearby.Sort((a, b) => b.QualityScore.CompareTo(a.QualityScore));
            return nearby;
        }

        // Generate NQ psychological levels in visible price range
        public void GeneratePsychologicalLevels(double low, double high)
        {
            // Remove existing psychological levels
            _levels.RemoveAll(l => l.Type == MADLevelType.Psychological);

            // NQ psychologicals at every 25 points (100 ticks): 20000, 20025, 20050, 20075...
            double start = Math.Floor(low / 25.0) * 25.0;
            for (double p = start; p <= high && _levels.Count < MaxLevels; p += 25.0)
            {
                AddLevel(MADLevelType.Psychological, p);
            }
        }

        public void RecomputeQuality()
        {
            foreach (var level in _levels)
                level.ComputeQuality(level.Price, TickSize, _levels);
        }

        public void ResetSession()
        {
            _levels.RemoveAll(l => l.Type == MADLevelType.VwapLine ||
                                   l.Type == MADLevelType.Vwap1SigmaUp || l.Type == MADLevelType.Vwap1SigmaDown ||
                                   l.Type == MADLevelType.Vwap2SigmaUp || l.Type == MADLevelType.Vwap2SigmaDown ||
                                   l.Type == MADLevelType.SessionHigh || l.Type == MADLevelType.SessionLow);
            _vwapSumPV = _vwapSumV = _vwapSumV_PV2 = 0;
            VwapValue = 0; Vwap1SigmaUp = 0; Vwap1SigmaDown = 0;
            Vwap2SigmaUp = 0; Vwap2SigmaDown = 0;
        }

        private void AddLevel(MADLevelType type, double price)
        {
            if (_levels.Count >= MaxLevels) return;
            _levels.Add(new MADLevel { Type = type, Price = price, CreatedDate = DateTime.Today, QualityScore = 0.5 });
        }
    }

    /// <summary>
    /// Tracks session-level market state: ATR20, volume EMA, session rollover,
    /// opening range, prior day levels, and HTF bias. Pure C# — no NT8 dependency.
    /// </summary>
    public sealed class MADMarketState
    {
        // --- ATR20 (manual computation, no NT8 dependency) ---
        private readonly double[] _trueRanges = new double[25];
        private int _trCount;
        private double _prevClose = double.NaN;
        public double Atr20 { get; private set; }

        // --- Volume EMA (12-period) ---
        public double VolEma { get; private set; }
        private bool _volEmaInitialized;
        private const double VolEmaAlpha = 2.0 / 13.0;

        // --- Session tracking ---
        public DateTime SessionDate { get; private set; }
        public bool IsRth { get; private set; }
        public double SessionHigh { get; private set; }
        public double SessionLow { get; private set; }

        // --- Opening range (first N minutes of RTH) ---
        public double OpeningRangeHigh { get; private set; }
        public double OpeningRangeLow { get; private set; }
        private bool _orSet;

        // --- Prior day levels ---
        public double PrevDayHigh { get; private set; }
        public double PrevDayLow { get; private set; }
        public double PrevDayClose { get; private set; }
        public double PrevDayPoc { get; private set; }

        // --- HTF bias (updated from secondary series) ---
        public MADTrend HtfBias { get; set; } = MADTrend.Neutral;
        public double HtfMomentum { get; set; }

        // --- Configuration (settable for tests / different instruments) ---
        public TimeSpan RthStart { get; set; } = new TimeSpan(9, 30, 0);   // 9:30 ET
        public TimeSpan RthEnd { get; set; } = new TimeSpan(16, 0, 0);     // 16:00 ET
        public int OpeningRangeMinutes { get; set; } = 30;

        // --- Cached last close for session rollover ---
        private double _lastClose;

        public void Update(double high, double low, double close, long volume, DateTime barTime)
        {
            // RTH detection
            TimeSpan t = barTime.TimeOfDay;
            IsRth = t >= RthStart && t < RthEnd;

            // Session rollover on date change
            if (barTime.Date != SessionDate)
            {
                if (SessionDate != default(DateTime))
                {
                    PrevDayHigh = SessionHigh;
                    PrevDayLow = SessionLow;
                    PrevDayClose = _lastClose;
                }
                SessionDate = barTime.Date;
                SessionHigh = high;
                SessionLow = low;
                _orSet = false;
                OpeningRangeHigh = 0;
                OpeningRangeLow = 0;
            }

            // Session extremes
            if (high > SessionHigh) SessionHigh = high;
            if (low < SessionLow || SessionLow == 0) SessionLow = low;

            // Opening range (first N minutes of RTH)
            if (IsRth && !_orSet)
            {
                TimeSpan elapsed = t - RthStart;
                if (elapsed.TotalMinutes <= OpeningRangeMinutes)
                {
                    if (OpeningRangeHigh == 0)
                    {
                        OpeningRangeHigh = high;
                        OpeningRangeLow = low;
                    }
                    else
                    {
                        if (high > OpeningRangeHigh) OpeningRangeHigh = high;
                        if (low < OpeningRangeLow) OpeningRangeLow = low;
                    }
                }
                else
                {
                    _orSet = true;
                }
            }

            // ATR20 (true range uses prior bar close for gap computation)
            double tr;
            if (double.IsNaN(_prevClose))
                tr = high - low;
            else
                tr = Math.Max(high - low, Math.Max(Math.Abs(high - _prevClose), Math.Abs(low - _prevClose)));

            _trueRanges[_trCount % 25] = tr;
            _trCount++;
            if (_trCount >= 20)
            {
                double sum = 0;
                for (int i = 0; i < 20; i++)
                    sum += _trueRanges[(_trCount - 1 - i) % 25];
                Atr20 = sum / 20.0;
            }

            _prevClose = close;
            _lastClose = close;

            // Volume EMA (12-period)
            if (!_volEmaInitialized) { VolEma = volume; _volEmaInitialized = true; }
            else VolEma = volume * VolEmaAlpha + VolEma * (1 - VolEmaAlpha);
        }

        public void Reset()
        {
            _trCount = 0;
            _prevClose = double.NaN;
            Atr20 = 0;
            VolEma = 0;
            _volEmaInitialized = false;
            SessionDate = default(DateTime);
            SessionHigh = 0;
            SessionLow = 0;
            _orSet = false;
            OpeningRangeHigh = 0;
            OpeningRangeLow = 0;
            PrevDayHigh = 0;
            PrevDayLow = 0;
            PrevDayClose = 0;
            PrevDayPoc = 0;
            HtfBias = MADTrend.Neutral;
            HtfMomentum = 0;
            _lastClose = 0;
        }

        public void SetPriorDayPoc(double poc) { PrevDayPoc = poc; }
    }

    /// <summary>
    /// Session-level volume profile engine. Accumulates tick volume by price from footprint bars,
    /// computes POC, Value Area (68%), HVN/LVN, and tracks naked POCs across sessions.
    /// Pure C# — no NT8 dependency.
    /// </summary>
    public sealed class MADVolumeProfile
    {
        private const double TickSize = 0.25;       // NQ tick size
        private const int MaxNakedPocs = 200;
        private const double ValueAreaPercent = 0.68;

        private readonly SortedDictionary<double, long> _sessionProfile = new SortedDictionary<double, long>();
        private readonly List<double> _nakedPocs = new List<double>();

        // Computed results
        public double Poc { get; private set; }
        public double Vah { get; private set; }
        public double Val { get; private set; }
        public List<double> Hvns { get; private set; } = new List<double>();
        public List<double> Lvns { get; private set; } = new List<double>();
        public IReadOnlyList<double> NakedPocs => _nakedPocs;
        public long TotalVolume { get; private set; }

        /// <summary>
        /// Accumulate price-level volumes into the session profile.
        /// Each entry maps a price to its total volume at that level.
        /// In production, call with bar.Levels transformed to price→totalVol.
        /// </summary>
        public void AddLevels(IEnumerable<KeyValuePair<double, long>> priceLevelVolumes)
        {
            if (priceLevelVolumes == null) return;
            foreach (var kv in priceLevelVolumes)
            {
                if (kv.Value <= 0) continue;
                long existing;
                _sessionProfile.TryGetValue(kv.Key, out existing);
                _sessionProfile[kv.Key] = existing + kv.Value;
            }
        }

        /// <summary>
        /// Compute POC, Value Area (VAH/VAL), HVN, and LVN from accumulated profile.
        /// </summary>
        public void ComputeProfile()
        {
            Poc = 0; Vah = 0; Val = 0;
            Hvns.Clear(); Lvns.Clear();
            TotalVolume = 0;

            if (_sessionProfile.Count == 0) return;

            // Build price/volume arrays for indexed access
            var prices = new List<double>(_sessionProfile.Count);
            var volumes = new List<long>(_sessionProfile.Count);
            long maxVol = 0;
            int pocIdx = 0;

            foreach (var kv in _sessionProfile)
            {
                prices.Add(kv.Key);
                volumes.Add(kv.Value);
                TotalVolume += kv.Value;
                if (kv.Value > maxVol) { maxVol = kv.Value; pocIdx = prices.Count - 1; }
            }

            Poc = prices[pocIdx];

            // Value Area: expand from POC outward until 68% captured
            long vaVolume = volumes[pocIdx];
            int lo = pocIdx;
            int hi = pocIdx;
            long targetVolume = (long)(TotalVolume * ValueAreaPercent);

            while (vaVolume < targetVolume && (lo > 0 || hi < prices.Count - 1))
            {
                long volBelow = lo > 0 ? volumes[lo - 1] : 0;
                long volAbove = hi < prices.Count - 1 ? volumes[hi + 1] : 0;

                if (lo <= 0)
                {
                    hi++;
                    vaVolume += volumes[hi];
                }
                else if (hi >= prices.Count - 1)
                {
                    lo--;
                    vaVolume += volumes[lo];
                }
                else if (volAbove >= volBelow)
                {
                    hi++;
                    vaVolume += volumes[hi];
                }
                else
                {
                    lo--;
                    vaVolume += volumes[lo];
                }
            }

            Val = prices[lo];
            Vah = prices[hi];

            // HVN/LVN detection: local maxima/minima in volume distribution
            if (prices.Count >= 3)
            {
                // Compute average volume for threshold
                double avgVol = (double)TotalVolume / prices.Count;

                for (int i = 1; i < prices.Count - 1; i++)
                {
                    long prev = volumes[i - 1];
                    long curr = volumes[i];
                    long next = volumes[i + 1];

                    // HVN: local max above average
                    if (curr > prev && curr > next && curr > avgVol)
                        Hvns.Add(prices[i]);

                    // LVN: local min below average
                    if (curr < prev && curr < next && curr < avgVol)
                        Lvns.Add(prices[i]);
                }
            }
        }

        /// <summary>
        /// End of session: save current POC as naked POC, clear profile for next session.
        /// </summary>
        public void ResetSession()
        {
            if (Poc != 0 && !_nakedPocs.Contains(Poc))
            {
                _nakedPocs.Add(Poc);
                if (_nakedPocs.Count > MaxNakedPocs)
                    _nakedPocs.RemoveAt(0);
            }

            _sessionProfile.Clear();
            Poc = 0; Vah = 0; Val = 0;
            Hvns.Clear(); Lvns.Clear();
            TotalVolume = 0;
        }

        /// <summary>
        /// Remove naked POCs within 1 tick of the given price (they've been filled/visited).
        /// </summary>
        public void CheckNakedPocFills(double price)
        {
            _nakedPocs.RemoveAll(p => Math.Abs(p - price) <= TickSize);
        }

        /// <summary>
        /// Full reset including naked POCs.
        /// </summary>
        public void Reset()
        {
            _sessionProfile.Clear();
            _nakedPocs.Clear();
            Poc = 0; Vah = 0; Val = 0;
            Hvns.Clear(); Lvns.Clear();
            TotalVolume = 0;
        }
    }

    public partial class MADConfluenceAI : Indicator
    {
        // ── T18: Weighted Confluence Scoring Engine ─────────────────────
        private MADScorerResult RunScoringEngine(List<MADSignalResult> signals, MADConfig config, MADRegime regime, bool isAtKeyLevel)
        {
            var result = new MADScorerResult { Score = 0, Tier = MADTier.DoNotTrade, Direction = MADSignalDirection.Neutral, Detail = "No signals" };
            if (signals == null || signals.Count == 0) return result;

            // Step 1: Determine majority direction
            int longCount = 0, shortCount = 0;
            foreach (var s in signals)
            {
                if (s.Direction == MADSignalDirection.Long) longCount++;
                else if (s.Direction == MADSignalDirection.Short) shortCount++;
            }
            MADSignalDirection majorityDir = longCount > shortCount ? MADSignalDirection.Long
                : shortCount > longCount ? MADSignalDirection.Short
                : MADSignalDirection.Neutral;

            if (majorityDir == MADSignalDirection.Neutral)
            {
                result.Detail = "No majority direction";
                return result;
            }

            // Step 2: Compute weighted contributions
            double totalContribution = 0;
            double maxPossibleScore = 0;
            var categorySet = new HashSet<string>();

            foreach (var s in signals)
            {
                double categoryWeight = GetCategoryWeight(s.SignalId, config);
                maxPossibleScore += categoryWeight;

                double directionAgreement = s.Direction == majorityDir ? 1.0 : -0.5;
                if (s.Direction == MADSignalDirection.Neutral) directionAgreement = 0.0;

                double contribution = s.Strength * categoryWeight * directionAgreement;
                totalContribution += contribution;

                if (s.Direction == majorityDir)
                {
                    result.ContributingSignals.Add(s);
                    string cat = GetSignalCategory(s.SignalId);
                    if (cat != null) categorySet.Add(cat);
                }
            }

            double rawScore = maxPossibleScore > 0 ? (totalContribution / maxPossibleScore) * 100.0 : 0;

            // Step 3: Category agreement bonus
            if (categorySet.Count >= 3) rawScore += 10;

            // Step 4: Level proximity bonus
            if (isAtKeyLevel) rawScore += 5;

            // Step 5: Regime modifier
            switch (regime)
            {
                case MADRegime.Trending:
                    // Favor continuation, penalize reversal
                    rawScore += 10;
                    break;
                case MADRegime.Ranging:
                    // Favor reversal, penalize breakout
                    rawScore += 10;
                    break;
                case MADRegime.Volatile:
                    rawScore -= 5;
                    break;
                case MADRegime.Thin:
                    rawScore -= 15;
                    break;
            }

            // Step 6: Clamp 0-100
            rawScore = Math.Max(0, Math.Min(100, rawScore));

            // Step 7: Tier classification
            MADTier tier;
            if (rawScore >= 90) tier = MADTier.Elite;
            else if (rawScore >= 75) tier = MADTier.High;
            else if (rawScore >= 60) tier = MADTier.Moderate;
            else if (rawScore >= 40) tier = MADTier.Wait;
            else tier = MADTier.DoNotTrade;

            result.Score = rawScore;
            result.Tier = tier;
            result.Direction = majorityDir;
            result.Detail = string.Format("Score={0:F1}, Tier={1}, Dir={2}, Categories={3}, Regime={4}",
                rawScore, tier, majorityDir, categorySet.Count, regime);

            return result;
        }

        private static double GetCategoryWeight(string signalId, MADConfig config)
        {
            if (string.IsNullOrEmpty(signalId)) return 1.0;
            if (signalId.StartsWith("ABS")) return config.AbsorptionWeight;
            if (signalId.StartsWith("EXH")) return config.ExhaustionWeight;
            if (signalId.StartsWith("DELT")) return config.DeltaWeight;
            if (signalId.StartsWith("IMB")) return config.ImbalanceWeight;
            if (signalId.StartsWith("ICE")) return config.IcebergWeight;
            if (signalId.StartsWith("LIQSW")) return config.LiquidityWeight;
            if (signalId.StartsWith("TRAP") || signalId.StartsWith("FAIL")) return config.TrapWeight;
            return 1.0;
        }

        private static string GetSignalCategory(string signalId)
        {
            if (string.IsNullOrEmpty(signalId)) return null;
            if (signalId.StartsWith("ABS")) return "absorption";
            if (signalId.StartsWith("EXH")) return "exhaustion";
            if (signalId.StartsWith("DELT")) return "delta";
            if (signalId.StartsWith("IMB")) return "imbalance";
            if (signalId.StartsWith("ICE")) return "iceberg";
            if (signalId.StartsWith("LIQSW")) return "liquidity";
            if (signalId.StartsWith("TRAP")) return "trap";
            if (signalId.StartsWith("FAIL")) return "auction";
            if (signalId.StartsWith("REG")) return "regime";
            return null;
        }

        // ── T19: Setup Classifier ──────────────────────────────────────
        private MADSetupType ClassifySetup(List<MADSignalResult> signals, MADRegime regime, bool isAtKeyLevel)
        {
            if (signals == null || signals.Count == 0) return MADSetupType.None;

            bool hasAbs = false, hasExh = false, hasImb = false, hasTrap = false;
            bool hasDelt = false, hasDelt02 = false, hasLiqSw = false;

            foreach (var s in signals)
            {
                if (s.SignalId == null) continue;
                if (s.SignalId.StartsWith("ABS")) hasAbs = true;
                if (s.SignalId.StartsWith("EXH")) hasExh = true;
                if (s.SignalId.StartsWith("IMB")) hasImb = true;
                if (s.SignalId.StartsWith("TRAP")) hasTrap = true;
                if (s.SignalId.StartsWith("DELT")) hasDelt = true;
                if (s.SignalId == "DELT-02") hasDelt02 = true;
                if (s.SignalId.StartsWith("LIQSW")) hasLiqSw = true;
            }

            // Priority order: check most specific patterns first
            if (hasAbs && hasExh && isAtKeyLevel && regime == MADRegime.Ranging)
                return MADSetupType.Reversal;

            if (hasImb && regime == MADRegime.Trending)
                return MADSetupType.Breakout;

            if (hasTrap)
                return MADSetupType.FailedBreakout;

            if (hasAbs && hasDelt)
                return MADSetupType.AbsorptionBounce;

            if (regime == MADRegime.Trending && hasDelt02)
                return MADSetupType.TrendContinuation;

            if (hasExh && hasDelt)
                return MADSetupType.ExhaustionReversal;

            if (hasLiqSw && hasAbs)
                return MADSetupType.LiquiditySweepReversal;

            return MADSetupType.None;
        }

        // ── T20: Market Context Builder ────────────────────────────────
        private MADMarketContext BuildMarketContext(MADMarketState state, MADRegime regime, DateTime barTime)
        {
            var ctx = new MADMarketContext();

            // Trend from HTF bias
            ctx.TrendDirection = state != null ? state.HtfBias : MADTrend.Neutral;

            // Time-of-day modifier (ET assumed)
            TimeSpan tod = barTime.TimeOfDay;
            double hours = tod.TotalHours;

            if (hours >= 9.5 && hours < 10.0)
                ctx.TimeModifier = -5;          // opening volatility — risky for reversals, ok for breakouts
            else if (hours >= 10.0 && hours < 11.5)
                ctx.TimeModifier = 5;           // prime trading — best odds
            else if (hours >= 11.5 && hours < 13.5)
                ctx.TimeModifier = -10;         // midday chop
            else if (hours >= 13.5 && hours < 15.0)
                ctx.TimeModifier = 3;           // afternoon move
            else if (hours >= 15.0 && hours < 16.0)
                ctx.TimeModifier = -5;          // close proximity
            else
                ctx.TimeModifier = -15;         // outside RTH

            // Session type inference
            if (state != null && state.Atr20 > 0)
            {
                double sessionRange = state.SessionHigh - state.SessionLow;
                double rangeRatio = sessionRange / state.Atr20;

                if (regime == MADRegime.Trending && rangeRatio > 1.5)
                    ctx.SessionType = MADSessionType.TrendDay;
                else if (regime == MADRegime.Ranging && rangeRatio < 0.8)
                    ctx.SessionType = MADSessionType.ChopDay;
                else if (regime == MADRegime.Volatile)
                    ctx.SessionType = MADSessionType.BreakoutDay;
                else if (regime == MADRegime.Ranging)
                    ctx.SessionType = MADSessionType.RotationalDay;
                else
                    ctx.SessionType = MADSessionType.Unknown;
            }
            else
            {
                ctx.SessionType = MADSessionType.Unknown;
            }

            // Momentum from HTF
            ctx.Momentum = state != null ? state.HtfMomentum : 0;

            return ctx;
        }

        // ── T21: Trade Decision Logic ──────────────────────────────────
        private MADDecision MakeDecision(MADScorerResult scorer, MADMarketContext context, MADSetupType setupType,
            double currentPrice, List<MADLevel> nearbyLevels, MADConfig config)
        {
            var decision = new MADDecision
            {
                SetupType = setupType,
                Action = MADAction.DoNotTrade,
                Detail = "Insufficient confluence"
            };

            if (scorer == null || context == null)
                return decision;

            // Step 1: Apply time modifier to score
            double adjustedScore = scorer.Score + context.TimeModifier;
            adjustedScore = Math.Max(0, Math.Min(100, adjustedScore));

            // Recompute tier from adjusted score
            MADTier adjustedTier;
            if (adjustedScore >= 90) adjustedTier = MADTier.Elite;
            else if (adjustedScore >= 75) adjustedTier = MADTier.High;
            else if (adjustedScore >= 60) adjustedTier = MADTier.Moderate;
            else if (adjustedScore >= 40) adjustedTier = MADTier.Wait;
            else adjustedTier = MADTier.DoNotTrade;

            decision.Score = adjustedScore;
            decision.Tier = adjustedTier;

            // Step 2: Midday override — Wait unless Elite
            double hours = DateTime.MinValue.TimeOfDay.TotalHours; // placeholder
            if (context.TimeModifier <= -10 && adjustedScore < config.EliteThreshold)
            {
                decision.Action = MADAction.Wait;
                decision.Detail = "Midday suppression — score below Elite threshold";
                return decision;
            }

            // Step 3: Decision rules
            MADAction action;
            if (adjustedScore >= config.EliteThreshold && setupType != MADSetupType.None)
            {
                action = scorer.Direction == MADSignalDirection.Long ? MADAction.Long : MADAction.Short;
            }
            else if (adjustedScore >= config.HighThreshold && setupType != MADSetupType.None)
            {
                action = scorer.Direction == MADSignalDirection.Long ? MADAction.Long : MADAction.Short;
            }
            else if (adjustedScore >= config.MinConfidenceScore && setupType != MADSetupType.None)
            {
                action = scorer.Direction == MADSignalDirection.Long ? MADAction.Long : MADAction.Short;
            }
            else if (adjustedScore >= 40 || setupType == MADSetupType.None)
            {
                action = MADAction.Wait;
            }
            else
            {
                action = MADAction.DoNotTrade;
            }

            decision.Action = action;

            // Step 4: SL/TP calculation (only if actionable)
            if (action == MADAction.Long || action == MADAction.Short)
            {
                double tickSize = 0.25; // NQ
                double defaultStopDist = config.DefaultStopTicks * tickSize;
                double defaultTargetDist = config.DefaultTargetTicks * tickSize;

                double stopPrice = 0;
                double targetPrice = 0;

                if (action == MADAction.Long)
                {
                    // Stop: nearest level below price + 2 tick buffer
                    double bestStopLevel = currentPrice - defaultStopDist;
                    if (nearbyLevels != null)
                    {
                        foreach (var lvl in nearbyLevels)
                        {
                            if (lvl.Price < currentPrice && lvl.Price > bestStopLevel)
                                bestStopLevel = lvl.Price;
                        }
                    }
                    stopPrice = bestStopLevel - (2 * tickSize);

                    // Target: next level above price
                    double bestTargetLevel = currentPrice + defaultTargetDist;
                    if (nearbyLevels != null)
                    {
                        foreach (var lvl in nearbyLevels)
                        {
                            if (lvl.Price > currentPrice && lvl.Price < bestTargetLevel)
                                bestTargetLevel = lvl.Price;
                        }
                    }
                    targetPrice = bestTargetLevel;
                }
                else // Short
                {
                    // Stop: nearest level above price + 2 tick buffer
                    double bestStopLevel = currentPrice + defaultStopDist;
                    if (nearbyLevels != null)
                    {
                        foreach (var lvl in nearbyLevels)
                        {
                            if (lvl.Price > currentPrice && lvl.Price < bestStopLevel)
                                bestStopLevel = lvl.Price;
                        }
                    }
                    stopPrice = bestStopLevel + (2 * tickSize);

                    // Target: next level below price
                    double bestTargetLevel = currentPrice - defaultTargetDist;
                    if (nearbyLevels != null)
                    {
                        foreach (var lvl in nearbyLevels)
                        {
                            if (lvl.Price < currentPrice && lvl.Price > bestTargetLevel)
                                bestTargetLevel = lvl.Price;
                        }
                    }
                    targetPrice = bestTargetLevel;
                }

                // Enforce minimums
                double minStopDist = config.DefaultStopTicks * tickSize;
                if (Math.Abs(currentPrice - stopPrice) < minStopDist)
                    stopPrice = action == MADAction.Long
                        ? currentPrice - minStopDist
                        : currentPrice + minStopDist;

                double minTargetDist = config.DefaultTargetTicks * tickSize;
                if (Math.Abs(targetPrice - currentPrice) < minTargetDist)
                    targetPrice = action == MADAction.Long
                        ? currentPrice + minTargetDist
                        : currentPrice - minTargetDist;

                decision.StopPrice = stopPrice;
                decision.TargetPrice = targetPrice;

                // R:R calculation
                double stopDist = Math.Abs(currentPrice - stopPrice);
                double targetDist = Math.Abs(targetPrice - currentPrice);
                decision.RiskRewardRatio = stopDist > 0 ? targetDist / stopDist : 0;

                // R:R < 1.5 → downgrade tier
                if (decision.RiskRewardRatio < 1.5 && decision.Tier != MADTier.DoNotTrade)
                {
                    if (decision.Tier == MADTier.Elite) decision.Tier = MADTier.High;
                    else if (decision.Tier == MADTier.High) decision.Tier = MADTier.Moderate;
                    else if (decision.Tier == MADTier.Moderate) decision.Tier = MADTier.Wait;
                    else if (decision.Tier == MADTier.Wait) decision.Tier = MADTier.DoNotTrade;

                    // If downgraded to DoNotTrade, change action
                    if (decision.Tier == MADTier.DoNotTrade)
                        decision.Action = MADAction.DoNotTrade;
                }

                decision.Detail = string.Format("Score={0:F1}, Setup={1}, R:R={2:F2}, SL={3:F2}, TP={4:F2}",
                    adjustedScore, setupType, decision.RiskRewardRatio, stopPrice, targetPrice);
            }
            else
            {
                decision.Detail = string.Format("Score={0:F1}, Setup={1}, Action={2}",
                    adjustedScore, setupType, action);
            }

            return decision;
        }
    }
}
