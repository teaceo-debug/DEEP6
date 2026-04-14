// DEEP6 Footprint — massive.com GEX client.
// Pulls options chain snapshot (e.g. QQQ), aggregates per-strike gamma × OI to form a
// GEX profile with gamma-flip, call wall, put wall.
//
// Auth: Authorization: Bearer <apiKey>  (massive.com official SDK pattern)
// Endpoint: GET /v3/snapshot/options/{underlying}
//
// Network calls MUST be made off the NT8 UI thread. Use FetchAsync() from a
// fire-and-forget Task.Run in the indicator; write the result to a volatile
// reference, and read it inside OnRender without blocking.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    public enum GexLevelKind
    {
        GammaFlip,
        CallWall,
        PutWall,
        MajorPositive,
        MajorNegative,
    }

    public sealed class GexLevel
    {
        public double Strike;
        public double GexNotional;   // signed $ per 1% move
        public GexLevelKind Kind;
        public string Label;
    }

    public sealed class GexProfile
    {
        public string Underlying;
        public double Spot;
        public double GammaFlip;
        public double CallWall;
        public double PutWall;
        public List<GexLevel> Levels = new List<GexLevel>();
        public DateTime FetchedUtc;

        public static GexProfile FromChain(string underlying, double spot, Dictionary<double, double> byStrike)
        {
            var profile = new GexProfile { Underlying = underlying, Spot = spot, FetchedUtc = DateTime.UtcNow };
            var sorted = byStrike.OrderBy(kv => kv.Key).ToList();

            // gamma flip = cumulative GEX zero-crossing (ascending strikes)
            double cum = 0.0;
            double flip = spot;
            bool found = false;
            foreach (var kv in sorted)
            {
                double prev = cum;
                cum += kv.Value;
                if (!found && ((prev <= 0 && cum > 0) || (prev >= 0 && cum < 0)))
                {
                    flip = kv.Key;
                    found = true;
                }
            }
            profile.GammaFlip = flip;

            double callWallStrike = spot, callWallVal = double.NegativeInfinity;
            double putWallStrike  = spot, putWallVal  = double.PositiveInfinity;
            foreach (var kv in sorted)
            {
                if (kv.Value > callWallVal) { callWallVal = kv.Value; callWallStrike = kv.Key; }
                if (kv.Value < putWallVal)  { putWallVal  = kv.Value; putWallStrike  = kv.Key; }
            }
            profile.CallWall = callWallStrike;
            profile.PutWall  = putWallStrike;

            // top 5 absolute GEX nodes as major positive / major negative
            var nodes = sorted
                .OrderByDescending(kv => Math.Abs(kv.Value))
                .Take(8)
                .ToList();
            foreach (var kv in nodes)
            {
                GexLevelKind kind;
                if (Math.Abs(kv.Key - flip) < 1e-6) kind = GexLevelKind.GammaFlip;
                else if (Math.Abs(kv.Key - callWallStrike) < 1e-6) kind = GexLevelKind.CallWall;
                else if (Math.Abs(kv.Key - putWallStrike) < 1e-6) kind = GexLevelKind.PutWall;
                else if (kv.Value > 0) kind = GexLevelKind.MajorPositive;
                else kind = GexLevelKind.MajorNegative;

                profile.Levels.Add(new GexLevel
                {
                    Strike = kv.Key,
                    GexNotional = kv.Value,
                    Kind = kind,
                    Label = string.Format("{0} {1:F0}", KindLabel(kind), kv.Key),
                });
            }
            return profile;
        }

        private static string KindLabel(GexLevelKind k)
        {
            switch (k)
            {
                case GexLevelKind.GammaFlip: return "FLIP";
                case GexLevelKind.CallWall:  return "CALL WALL";
                case GexLevelKind.PutWall:   return "PUT WALL";
                case GexLevelKind.MajorPositive: return "+GEX";
                case GexLevelKind.MajorNegative: return "-GEX";
                default: return "GEX";
            }
        }
    }

    public sealed class MassiveGexClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string _apiKey;
        private readonly string _baseUrl;

        public MassiveGexClient(string apiKey, string baseUrl = "https://api.massive.com")
        {
            _apiKey = apiKey ?? throw new ArgumentNullException("apiKey");
            _baseUrl = baseUrl.TrimEnd('/');

            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            _http = new HttpClient
            {
                BaseAddress = new Uri(_baseUrl),
                Timeout = TimeSpan.FromSeconds(8),
            };
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
            _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            _http.DefaultRequestHeaders.UserAgent.ParseAdd("DEEP6-NT8/1.0");
        }

        // Aggregates chain gamma × OI × 100 × spot² × 0.01 × sign(call=+1, put=-1) per strike.
        // Returns null on failure (caller logs and keeps last good profile).
        public async Task<GexProfile> FetchAsync(string underlying, CancellationToken ct = default(CancellationToken))
        {
            try
            {
                var byStrike = new Dictionary<double, double>();
                double spot = 0;
                string url = string.Format("/v3/snapshot/options/{0}?limit=250", underlying);
                int safetyPages = 0;

                while (!string.IsNullOrEmpty(url) && safetyPages < 20)
                {
                    safetyPages++;
                    var req = new HttpRequestMessage(HttpMethod.Get, url);
                    var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
                    if (!resp.IsSuccessStatusCode) return null;
                    var json = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);

                    var parsed = ParseChain(json);
                    foreach (var c in parsed.results)
                    {
                        if (c.open_interest <= 0) continue;
                        if (c.greeks == null) continue;
                        if (c.details == null) continue;
                        if (c.underlying_asset != null && c.underlying_asset.price > 0)
                            spot = c.underlying_asset.price;
                        double sign = string.Equals(c.details.contract_type, "call", StringComparison.OrdinalIgnoreCase) ? +1.0 : -1.0;
                        double gamma = c.greeks.gamma;
                        double gex = gamma * c.open_interest * 100.0 * spot * spot * 0.01 * sign;
                        double strike = c.details.strike_price;
                        double acc;
                        byStrike.TryGetValue(strike, out acc);
                        byStrike[strike] = acc + gex;
                    }
                    url = parsed.next_url;
                    if (!string.IsNullOrEmpty(url) && url.StartsWith(_baseUrl)) url = url.Substring(_baseUrl.Length);
                }

                if (spot == 0 || byStrike.Count == 0) return null;
                return GexProfile.FromChain(underlying, spot, byStrike);
            }
            catch
            {
                return null;
            }
        }

        private static ChainResponse ParseChain(string json)
        {
            var ser = new DataContractJsonSerializer(typeof(ChainResponse));
            using (var ms = new MemoryStream(Encoding.UTF8.GetBytes(json)))
            {
                return (ChainResponse)ser.ReadObject(ms);
            }
        }

        public void Dispose() { _http.Dispose(); }

        // --- DTOs (DataContract for .NET Framework 4.8 compatibility) ---

        [DataContract]
        private sealed class ChainResponse
        {
            [DataMember(Name = "status")]    public string status;
            [DataMember(Name = "next_url")]  public string next_url;
            [DataMember(Name = "results")]   public List<OptionContract> results = new List<OptionContract>();
        }

        [DataContract]
        private sealed class OptionContract
        {
            [DataMember(Name = "open_interest")]    public int open_interest;
            [DataMember(Name = "greeks")]           public Greeks greeks;
            [DataMember(Name = "details")]          public Details details;
            [DataMember(Name = "underlying_asset")] public UnderlyingAsset underlying_asset;
        }

        [DataContract]
        private sealed class Greeks
        {
            [DataMember(Name = "delta")] public double delta;
            [DataMember(Name = "gamma")] public double gamma;
            [DataMember(Name = "theta")] public double theta;
            [DataMember(Name = "vega")]  public double vega;
        }

        [DataContract]
        private sealed class Details
        {
            [DataMember(Name = "ticker")]          public string ticker;
            [DataMember(Name = "contract_type")]   public string contract_type;
            [DataMember(Name = "strike_price")]    public double strike_price;
            [DataMember(Name = "expiration_date")] public string expiration_date;
        }

        [DataContract]
        private sealed class UnderlyingAsset
        {
            [DataMember(Name = "ticker")] public string ticker;
            [DataMember(Name = "price")]  public double price;
        }
    }
}
