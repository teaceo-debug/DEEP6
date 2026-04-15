// ProfileAnchorLevels — BCL-only session volume-profile aggregator.
//
// Computes prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs (with retest + age),
// prior-week POC, and rolling 5-day composite VA from completed RTH sessions.
//
// Design constraints:
//   - Zero NinjaTrader.* using directives — must compile under net8.0 test project.
//   - Algorithm mirrors deep6/engines/volume_profile.py session aggregation.
//   - Session boundary via date comparison (same pattern as DEEP6Strategy.cs lines 285-302).
//   - Naked POC retest: Low <= poc <= High on any subsequent bar marks Retested=true.
//   - Age expiry: drop naked POCs with AgeSessions > NakedPocMaxAgeSessions.
//   - Prior-week POC: argmax over aggregated VolumeAtPrice of last 5 completed sessions.
//   - Composite VA: 70% value area over last CompositeSessions (default 5) sessions merged.
//
// Color choices (documented here since file is NT8-API-free):
//   PriorDayPoc  → #FFD23F (poc-yellow)
//   PriorDayVah/Val/Pdh/Pdl/Pdm → #C8D17A (va-olive)
//   NakedPoc     → #FFD23F @ 60% opacity, dashed
//   PriorWeekPoc → #E5C24A, dashed
//   CompositeVah/Val → #C8D17A @ 12% fill band

using System;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Levels
{
    // ─── Public enums and value types ───────────────────────────────────────────

    public enum ProfileAnchorKind
    {
        PriorDayPoc,
        PriorDayVah,
        PriorDayVal,
        Pdh,
        Pdl,
        Pdm,
        NakedPoc,
        PriorWeekPoc,
        CompositeVah,
        CompositeVal,
    }

    public sealed class ProfileAnchor
    {
        public ProfileAnchorKind Kind;
        public double Price;
        /// <summary>"PDH", "PDL", "PDM", "PD POC", "PD VAH", "PD VAL", "PW POC", "nPOC"</summary>
        public string Label;
        /// <summary>Date of the completed session that produced this level.</summary>
        public DateTime OriginSession;
        /// <summary>Number of completed sessions since OriginSession.</summary>
        public int AgeSessions;
        /// <summary>Naked POC: true once a later bar's Low &lt;= Price &lt;= High.</summary>
        public bool Retested;
    }

    public sealed class SessionProfile
    {
        public DateTime SessionDate;
        public double Open, High, Low, Close;
        /// <summary>Mid = (High + Low) / 2 → PDM.</summary>
        public double Mid;
        public double SessionPoc, Vah, Val;
        /// <summary>price → total volume (ask + bid) across all bars in the session.</summary>
        public SortedDictionary<double, long> VolumeAtPrice = new SortedDictionary<double, long>();
    }

    public sealed class ProfileAnchorSnapshot
    {
        public List<ProfileAnchor> Levels = new List<ProfileAnchor>();
        /// <summary>Null when fewer than CompositeSessions sessions have completed.</summary>
        public double? CompositeVah;
        public double? CompositeVal;
    }

    // ─── Main aggregator ────────────────────────────────────────────────────────

    public sealed class ProfileAnchorLevels
    {
        // ---- Configuration ----

        /// <summary>Number of completed sessions used for rolling composite VA.</summary>
        public int CompositeSessions = 5;

        /// <summary>Maximum age (in completed sessions) before a naked POC is dropped.</summary>
        public int NakedPocMaxAgeSessions = 20;

        /// <summary>Instrument tick size — used for ComputeValueArea step size.</summary>
        public double TickSize = 0.25;

        // ---- Internal state ----

        private readonly List<SessionProfile> _completed = new List<SessionProfile>();
        private SessionProfile _current = new SessionProfile { SessionDate = DateTime.MinValue };

        // Naked POC tracker: each entry carries the completed-session POC and whether it has been retested.
        // Keyed by (OriginSession, Price) so the same price from two different sessions is tracked separately.
        private readonly List<ProfileAnchor> _nakedPocs = new List<ProfileAnchor>();

        // ---- Test seams ----

        internal IReadOnlyList<SessionProfile> CompletedSessions => _completed;
        internal SessionProfile CurrentSession => _current;

        // ---- Public API ────────────────────────────────────────────────────────

        /// <summary>
        /// Called at bar-close for every finalized FootprintBar.
        /// Detects session boundary via date change before accumulating the bar.
        /// </summary>
        public void OnBarClose(FootprintBar bar, DateTime barTimeEt)
        {
            DateTime barDate = barTimeEt.Date;

            // Session boundary: date changed since last bar
            if (_current.SessionDate != DateTime.MinValue && barDate != _current.SessionDate)
                OnSessionBoundary(barDate);

            // Initialize current session on first bar ever
            if (_current.SessionDate == DateTime.MinValue)
                _current.SessionDate = barDate;

            // Accumulate OHLC
            if (_current.Open == 0) _current.Open = bar.Open;
            if (bar.High > _current.High) _current.High = bar.High;
            if (_current.Low == 0 || bar.Low < _current.Low) _current.Low = bar.Low;
            _current.Close = bar.Close;

            // Merge bar.Levels into session VolumeAtPrice
            foreach (var kv in bar.Levels)
            {
                long vol = kv.Value.AskVol + kv.Value.BidVol;
                if (vol <= 0) continue;
                long existing;
                _current.VolumeAtPrice.TryGetValue(kv.Key, out existing);
                _current.VolumeAtPrice[kv.Key] = existing + vol;
            }

            // Check naked POC retest: any existing naked POC whose price falls within this bar's range
            if (bar.Low > 0 && bar.High > 0)
            {
                foreach (var np in _nakedPocs)
                {
                    if (!np.Retested && bar.Low <= np.Price && np.Price <= bar.High)
                        np.Retested = true;
                }
            }
        }

        /// <summary>
        /// Called when a new session date is detected. Finalizes the prior session,
        /// computes POC/VAH/VAL, promotes its POC to the naked-POC tracker,
        /// and starts a fresh CurrentSession for newSessionDate.
        /// </summary>
        public void OnSessionBoundary(DateTime newSessionDate)
        {
            if (_current.SessionDate == DateTime.MinValue || _current.VolumeAtPrice.Count == 0)
            {
                _current.SessionDate = newSessionDate;
                return;
            }

            // Finalize current session
            _current.Mid = (_current.High + _current.Low) / 2.0;
            _current.SessionPoc = ComputePoc(_current.VolumeAtPrice);
            var va = ComputeValueArea(_current.VolumeAtPrice, TickSize);
            _current.Vah = va.vah;
            _current.Val = va.val;

            _completed.Add(_current);

            // Increment age on all existing naked POCs
            foreach (var np in _nakedPocs)
                np.AgeSessions++;

            // Add this session's POC as a new naked POC candidate
            if (_current.SessionPoc > 0)
            {
                _nakedPocs.Add(new ProfileAnchor
                {
                    Kind          = ProfileAnchorKind.NakedPoc,
                    Price         = _current.SessionPoc,
                    Label         = "nPOC",
                    OriginSession = _current.SessionDate,
                    AgeSessions   = 0,
                    Retested      = false,
                });
            }

            // Drop expired naked POCs
            _nakedPocs.RemoveAll(np => np.AgeSessions > NakedPocMaxAgeSessions);

            // Cap completed list to prevent unbounded growth
            // Keep enough for prior-week (5) + composite (CompositeSessions) + a small buffer
            int cap = System.Math.Max(NakedPocMaxAgeSessions + 5, CompositeSessions + 5);
            while (_completed.Count > cap)
                _completed.RemoveAt(0);

            // Start fresh session
            _current = new SessionProfile { SessionDate = newSessionDate };
        }

        /// <summary>
        /// Returns a point-in-time snapshot of all profile-anchor levels.
        /// Reads _completed and _nakedPocs; does NOT mutate state.
        /// </summary>
        public ProfileAnchorSnapshot BuildSnapshot()
        {
            var snap = new ProfileAnchorSnapshot();

            // Prior day (most recent completed session)
            if (_completed.Count >= 1)
            {
                var pd = _completed[_completed.Count - 1];

                if (pd.SessionPoc > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.PriorDayPoc, Price = pd.SessionPoc, Label = "PD POC", OriginSession = pd.SessionDate });
                if (pd.Vah > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.PriorDayVah, Price = pd.Vah, Label = "PD VAH", OriginSession = pd.SessionDate });
                if (pd.Val > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.PriorDayVal, Price = pd.Val, Label = "PD VAL", OriginSession = pd.SessionDate });
                if (pd.High > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdh, Price = pd.High, Label = "PDH", OriginSession = pd.SessionDate });
                if (pd.Low > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdl, Price = pd.Low, Label = "PDL", OriginSession = pd.SessionDate });
                if (pd.Mid > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdm, Price = pd.Mid, Label = "PDM", OriginSession = pd.SessionDate });
            }

            // Prior-week POC: argmax of VolumeAtPrice merged across last 5 completed sessions
            int pwCount = System.Math.Min(5, _completed.Count);
            if (pwCount >= 1)
            {
                var pwDict = new Dictionary<double, long>();
                for (int i = _completed.Count - pwCount; i < _completed.Count; i++)
                {
                    foreach (var kv in _completed[i].VolumeAtPrice)
                    {
                        long acc;
                        pwDict.TryGetValue(kv.Key, out acc);
                        pwDict[kv.Key] = acc + kv.Value;
                    }
                }
                double pwPoc = ComputePocFromDict(pwDict);
                if (pwPoc > 0)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.PriorWeekPoc, Price = pwPoc, Label = "PW POC" });
            }

            // Naked POCs (not retested, within age limit)
            foreach (var np in _nakedPocs)
            {
                if (!np.Retested && np.AgeSessions <= NakedPocMaxAgeSessions)
                {
                    snap.Levels.Add(new ProfileAnchor
                    {
                        Kind          = ProfileAnchorKind.NakedPoc,
                        Price         = np.Price,
                        Label         = "nPOC",
                        OriginSession = np.OriginSession,
                        AgeSessions   = np.AgeSessions,
                        Retested      = false,
                    });
                }
            }

            // Composite VA (last CompositeSessions completed sessions)
            if (_completed.Count >= CompositeSessions)
            {
                var compDict = new Dictionary<double, long>();
                for (int i = _completed.Count - CompositeSessions; i < _completed.Count; i++)
                {
                    foreach (var kv in _completed[i].VolumeAtPrice)
                    {
                        long acc;
                        compDict.TryGetValue(kv.Key, out acc);
                        compDict[kv.Key] = acc + kv.Value;
                    }
                }
                var cva = ComputeValueArea(compDict, TickSize);
                snap.CompositeVah = cva.vah > 0 ? (double?)cva.vah : null;
                snap.CompositeVal = cva.val > 0 ? (double?)cva.val : null;

                if (snap.CompositeVah.HasValue)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.CompositeVah, Price = snap.CompositeVah.Value, Label = "Comp VAH" });
                if (snap.CompositeVal.HasValue)
                    snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.CompositeVal, Price = snap.CompositeVal.Value, Label = "Comp VAL" });
            }

            return snap;
        }

        /// <summary>Clear all state — call from DEEP6Footprint State.DataLoaded.</summary>
        public void Reset()
        {
            _completed.Clear();
            _nakedPocs.Clear();
            _current = new SessionProfile { SessionDate = DateTime.MinValue };
        }

        // ---- Static helpers ───────────────────────────────────────────────────

        private static double ComputePoc(SortedDictionary<double, long> vap)
        {
            double bestPx = 0;
            long bestVol = -1;
            foreach (var kv in vap)
            {
                if (kv.Value > bestVol) { bestVol = kv.Value; bestPx = kv.Key; }
            }
            return bestPx;
        }

        private static double ComputePocFromDict(Dictionary<double, long> vap)
        {
            double bestPx = 0;
            long bestVol = -1;
            foreach (var kv in vap)
            {
                if (kv.Value > bestVol) { bestVol = kv.Value; bestPx = kv.Key; }
            }
            return bestPx;
        }

        /// <summary>
        /// 70% value area from a price→volume dictionary.
        /// Mirrors FootprintBar.ComputeValueArea but accepts any dictionary type.
        /// </summary>
        private static (double vah, double val) ComputeValueArea(IEnumerable<KeyValuePair<double, long>> vap, double tickSize, double vaPct = 0.70)
        {
            long total = 0;
            var sorted = new List<KeyValuePair<double, long>>();
            foreach (var kv in vap)
            {
                if (kv.Value > 0) sorted.Add(kv);
                total += kv.Value;
            }
            if (sorted.Count == 0 || total == 0) return (0, 0);

            sorted.Sort((a, b) => b.Value.CompareTo(a.Value)); // descending by volume
            double target = total * vaPct;
            double acc = 0;
            var inVa = new List<double>();
            foreach (var kv in sorted)
            {
                acc += kv.Value;
                inVa.Add(kv.Key);
                if (acc >= target) break;
            }
            if (inVa.Count == 0) return (0, 0);
            double maxPx = inVa[0], minPx = inVa[0];
            foreach (var px in inVa) { if (px > maxPx) maxPx = px; if (px < minPx) minPx = px; }
            return (maxPx + tickSize, minPx);
        }
    }
}
