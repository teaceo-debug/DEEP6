// GexSharedState: machine-readable latest-value latch for mapped GEX levels.
//
// Purpose:
//   DEEP6GexLevels publishes mapped NQ levels after each successful fetch.
//   DEEP6Footprint and future vendor adapters consume the latest snapshot to add
//   structural context (walls / gamma flip / nearest target selection) without
//   coupling chart logic to any one data source.
//
// NT8-API-free: no NinjaTrader.* using directives so this compiles under net48 and net8.0.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge
{
    public sealed class MappedGexLevel
    {
        public string Kind;
        public double NqPrice;
        public double SourceStrike;
        public double SourceSpot;
        public double Weight;
    }

    public sealed class GexContextSnapshot
    {
        public string Instrument;
        public DateTime FetchedUtc;
        public bool Stale;
        public string Underlying;
        public double UnderlyingSpot;
        public double NqSpot;
        public double MappingRatio;
        public double GammaFlip;
        public double CallWall;
        public double PutWall;
        public List<MappedGexLevel> Levels = new List<MappedGexLevel>();
    }

    public static class GexSharedState
    {
        private static readonly ConcurrentDictionary<string, GexContextSnapshot> _latest =
            new ConcurrentDictionary<string, GexContextSnapshot>(StringComparer.Ordinal);

        public static void Publish(string instrument, GexContextSnapshot snapshot)
        {
            if (string.IsNullOrWhiteSpace(instrument) || snapshot == null)
                return;
            snapshot.Instrument = instrument;
            _latest[instrument] = snapshot;
        }

        public static GexContextSnapshot Latest(string instrument)
        {
            if (string.IsNullOrWhiteSpace(instrument))
                return null;
            GexContextSnapshot snap;
            return _latest.TryGetValue(instrument, out snap) ? snap : null;
        }

        public static void Clear(string instrument)
        {
            if (string.IsNullOrWhiteSpace(instrument))
                return;
            GexContextSnapshot dummy;
            _latest.TryRemove(instrument, out dummy);
        }

        public static MappedGexLevel NearestAbove(string instrument, double price)
        {
            var snap = Latest(instrument);
            if (snap == null || snap.Levels == null) return null;
            return snap.Levels.Where(l => l != null && l.NqPrice > price)
                              .OrderBy(l => l.NqPrice)
                              .FirstOrDefault();
        }

        public static MappedGexLevel NearestBelow(string instrument, double price)
        {
            var snap = Latest(instrument);
            if (snap == null || snap.Levels == null) return null;
            return snap.Levels.Where(l => l != null && l.NqPrice < price)
                              .OrderByDescending(l => l.NqPrice)
                              .FirstOrDefault();
        }

        public static MappedGexLevel NearestOfKind(string instrument, string kind, double price)
        {
            var snap = Latest(instrument);
            if (snap == null || snap.Levels == null || string.IsNullOrWhiteSpace(kind)) return null;
            return snap.Levels.Where(l => l != null && string.Equals(l.Kind, kind, StringComparison.Ordinal))
                              .OrderBy(l => System.Math.Abs(l.NqPrice - price))
                              .FirstOrDefault();
        }
    }
}
