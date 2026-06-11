// =====================================================================================
// UWDarkPoolCore.cs
// Core service layer for the UW_DarkPoolLiquidityMap NinjaTrader 8 indicator.
//
// This file intentionally contains NO NinjaTrader, WPF, or SharpDX dependencies so the
// parsing, clustering, scoring, and decay logic can be unit-tested in a plain .NET 4.8
// test project outside of NinjaTrader.
//
// Written against C# 5 language features only (no string interpolation, no null-
// conditional operators, no expression-bodied members) so it compiles on both the
// legacy NinjaTrader 8.0 compiler and the NinjaTrader 8.1 Roslyn compiler.
//
// DISCLAIMER: Dark-pool / off-lit prints are post-trade, delayed-settlement data.
// Levels produced here are statistical inferences ("Inferred Support", "Liquidity
// Zone"), NOT guaranteed resting orders or a hidden order book.
// =====================================================================================

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace UWLiquidityMap.Core
{
	#region Enums

	public enum LiquidityLevelType
	{
		Support,
		Resistance,
		Magnet,
		Absorption,
		Exhaustion,
		NeutralCluster
	}

	public enum LiquidityLevelSide
	{
		BidSideInferred,
		AskSideInferred,
		MidpointOrUnknown,
		Mixed
	}

	public enum LevelGroupingMode
	{
		Auto,           // max(2 ticks, 0.03% of price, 0.05 * ATR(14))
		ExactPrice,
		TickBucket,
		AtrBucket,
		PercentBucket
	}

	public enum UwBackoffMode
	{
		Exponential,
		Linear,
		Fixed
	}

	public enum UwLogLevel
	{
		Error = 0,
		Warning = 1,
		Info = 2,
		Debug = 3
	}

	public enum UwThemePreset
	{
		DarkInstitutional,
		LightInstitutional,
		BloombergLike,
		Minimal,
		ColorblindSafe,
		Custom
	}

	public enum LabelDisplayMode
	{
		None,
		Compact,
		Full
	}

	public enum DashboardCorner
	{
		TopLeft,
		TopRight,
		BottomLeft,
		BottomRight
	}

	public enum UwApiErrorKind
	{
		Auth,           // 401 / 403
		NotFound,       // 404
		Validation,     // 422
		RateLimited,    // 429
		Server,         // 5xx
		Network,        // DNS, TLS, timeout
		Unknown
	}

	#endregion

	#region Data model

	/// <summary>One dark-pool / off-lit trade print (REST or WebSocket sourced).</summary>
	public sealed class UwDarkPoolTrade
	{
		public string Ticker { get; set; }
		public DateTime ExecutedAtUtc { get; set; }
		public DateTime? TrfExecutedAtUtc { get; set; }
		public decimal Price { get; set; }
		public long Size { get; set; }
		public decimal Premium { get; set; }
		public decimal? NbboBid { get; set; }
		public decimal? NbboAsk { get; set; }
		public long? NbboBidQuantity { get; set; }
		public long? NbboAskQuantity { get; set; }
		public string MarketCenter { get; set; }
		public string SaleConditionCodes { get; set; }
		public string ExtHourSoldCodes { get; set; }
		public string TradeCode { get; set; }
		public string TradeSettlement { get; set; }
		public bool Canceled { get; set; }
		public string TrackingId { get; set; }

		public string DedupKey()
		{
			if (!string.IsNullOrEmpty(TrackingId))
				return TrackingId;
			return ExecutedAtUtc.Ticks.ToString(CultureInfo.InvariantCulture) + "|"
				+ Price.ToString(CultureInfo.InvariantCulture) + "|"
				+ Size.ToString(CultureInfo.InvariantCulture);
		}
	}

	/// <summary>One row of GET /api/stock/{ticker}/stock-volume-price-levels.</summary>
	public sealed class UwOffLitPriceLevel
	{
		public decimal Price { get; set; }
		public long LitVolume { get; set; }
		public long OffLitVolume { get; set; }
	}

	/// <summary>An aggregated, scored, classified liquidity level ready for rendering.</summary>
	public sealed class LiquidityLevel
	{
		public decimal Price { get; set; }
		public decimal ClusterWidth { get; set; }       // full zone height in price units
		public decimal Score { get; set; }              // 0..100, relative to strongest level
		public decimal StrengthPercentile { get; set; } // 0..100, true percentile rank
		public long TotalDarkPoolSize { get; set; }
		public decimal TotalDarkPoolPremium { get; set; }
		public long OffLitVolume { get; set; }
		public long LitVolume { get; set; }
		public decimal OffLitShare { get; set; }        // 0..1
		public int PrintCount { get; set; }
		public DateTime FirstSeenUtc { get; set; }
		public DateTime LastSeenUtc { get; set; }
		public LiquidityLevelType Type { get; set; }
		public LiquidityLevelSide InferredSide { get; set; }
		public bool IsFresh { get; set; }
		public bool IsDecayed { get; set; }
		public bool IsNearCurrentPrice { get; set; }
		public string Label { get; set; }
		public string Tooltip { get; set; }

		// Renderer hints (precomputed so OnRender does zero scoring math)
		public double PremiumWeight { get; set; }       // 0..1 -> line width
		public int TouchCount { get; set; }
		public int RejectionCount { get; set; }
		public int BreakCount { get; set; }
		internal double RawScore { get; set; }
	}

	/// <summary>Immutable result of one aggregation pass. Safe to read from the render thread.</summary>
	public sealed class LiquiditySnapshot
	{
		public readonly ReadOnlyCollection<LiquidityLevel> Levels;
		public readonly ReadOnlyCollection<UwDarkPoolTrade> RecentPrints;
		public readonly DateTime GeneratedUtc;
		public readonly double CurrentPrice;
		public readonly int TradeCountCached;
		public readonly UwDarkPoolTrade LargestRecentPrint;
		public readonly LiquidityLevel StrongestSupport;
		public readonly LiquidityLevel StrongestResistance;

		public LiquiditySnapshot(IList<LiquidityLevel> levels, IList<UwDarkPoolTrade> recentPrints,
			DateTime generatedUtc, double currentPrice, int tradeCountCached,
			UwDarkPoolTrade largestRecentPrint, LiquidityLevel strongestSupport, LiquidityLevel strongestResistance)
		{
			Levels = new ReadOnlyCollection<LiquidityLevel>(levels ?? new List<LiquidityLevel>());
			RecentPrints = new ReadOnlyCollection<UwDarkPoolTrade>(recentPrints ?? new List<UwDarkPoolTrade>());
			GeneratedUtc = generatedUtc;
			CurrentPrice = currentPrice;
			TradeCountCached = tradeCountCached;
			LargestRecentPrint = largestRecentPrint;
			StrongestSupport = strongestSupport;
			StrongestResistance = strongestResistance;
		}

		public static readonly LiquiditySnapshot Empty = new LiquiditySnapshot(
			new List<LiquidityLevel>(), new List<UwDarkPoolTrade>(), DateTime.MinValue, 0, 0, null, null, null);
	}

	/// <summary>One chart bar sample used for touch/rejection/break confirmation.</summary>
	public struct BarSample
	{
		public DateTime TimeUtc;
		public double High;
		public double Low;
		public double Close;
	}

	#endregion

	#region JSON (dependency-free)

	/// <summary>
	/// Minimal, allocation-conscious JSON parser. Produces Dictionary&lt;string,object&gt;,
	/// List&lt;object&gt;, string, decimal (or double for out-of-range), bool, or null.
	/// Used instead of Newtonsoft.Json so the indicator compiles with zero external
	/// references on every NinjaTrader 8 install.
	/// </summary>
	public static class JsonLite
	{
		public static object Parse(string json)
		{
			if (string.IsNullOrEmpty(json))
				return null;
			int i = 0;
			object v = ParseValue(json, ref i);
			return v;
		}

		private static object ParseValue(string s, ref int i)
		{
			SkipWs(s, ref i);
			if (i >= s.Length)
				throw new FormatException("Unexpected end of JSON.");
			char c = s[i];
			if (c == '{') return ParseObject(s, ref i);
			if (c == '[') return ParseArray(s, ref i);
			if (c == '"') return ParseString(s, ref i);
			if (c == 't') { Expect(s, ref i, "true"); return true; }
			if (c == 'f') { Expect(s, ref i, "false"); return false; }
			if (c == 'n') { Expect(s, ref i, "null"); return null; }
			return ParseNumber(s, ref i);
		}

		private static Dictionary<string, object> ParseObject(string s, ref int i)
		{
			var d = new Dictionary<string, object>(StringComparer.Ordinal);
			i++; // {
			SkipWs(s, ref i);
			if (i < s.Length && s[i] == '}') { i++; return d; }
			while (i < s.Length)
			{
				SkipWs(s, ref i);
				if (i >= s.Length) throw new FormatException("Unterminated object.");
				if (s[i] != '"') throw new FormatException("Expected property name at " + i + ".");
				string key = ParseString(s, ref i);
				SkipWs(s, ref i);
				if (i >= s.Length || s[i] != ':') throw new FormatException("Expected ':' at " + i + ".");
				i++;
				object val = ParseValue(s, ref i);
				d[key] = val;
				SkipWs(s, ref i);
				if (i >= s.Length) throw new FormatException("Unterminated object.");
				if (s[i] == ',') { i++; continue; }
				if (s[i] == '}') { i++; return d; }
				throw new FormatException("Expected ',' or '}' at " + i + ".");
			}
			throw new FormatException("Unterminated object.");
		}

		private static List<object> ParseArray(string s, ref int i)
		{
			var a = new List<object>();
			i++; // [
			SkipWs(s, ref i);
			if (i < s.Length && s[i] == ']') { i++; return a; }
			while (i < s.Length)
			{
				object val = ParseValue(s, ref i);
				a.Add(val);
				SkipWs(s, ref i);
				if (i >= s.Length) throw new FormatException("Unterminated array.");
				if (s[i] == ',') { i++; continue; }
				if (s[i] == ']') { i++; return a; }
				throw new FormatException("Expected ',' or ']' at " + i + ".");
			}
			throw new FormatException("Unterminated array.");
		}

		private static string ParseString(string s, ref int i)
		{
			i++; // opening quote
			var sb = new StringBuilder();
			while (i < s.Length)
			{
				char c = s[i++];
				if (c == '"')
					return sb.ToString();
				if (c == '\\')
				{
					if (i >= s.Length) break;
					char e = s[i++];
					switch (e)
					{
						case '"': sb.Append('"'); break;
						case '\\': sb.Append('\\'); break;
						case '/': sb.Append('/'); break;
						case 'b': sb.Append('\b'); break;
						case 'f': sb.Append('\f'); break;
						case 'n': sb.Append('\n'); break;
						case 'r': sb.Append('\r'); break;
						case 't': sb.Append('\t'); break;
						case 'u':
							if (i + 4 <= s.Length)
							{
								int cp = int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
								sb.Append((char)cp);
								i += 4;
							}
							break;
						default: sb.Append(e); break;
					}
				}
				else
					sb.Append(c);
			}
			throw new FormatException("Unterminated string.");
		}

		private static object ParseNumber(string s, ref int i)
		{
			int start = i;
			while (i < s.Length)
			{
				char c = s[i];
				if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E')
					i++;
				else
					break;
			}
			string tok = s.Substring(start, i - start);
			decimal dec;
			if (decimal.TryParse(tok, NumberStyles.Float, CultureInfo.InvariantCulture, out dec))
				return dec;
			double dbl;
			if (double.TryParse(tok, NumberStyles.Float, CultureInfo.InvariantCulture, out dbl))
				return dbl;
			throw new FormatException("Invalid number '" + tok + "' at " + start + ".");
		}

		private static void Expect(string s, ref int i, string literal)
		{
			if (i + literal.Length > s.Length || string.CompareOrdinal(s, i, literal, 0, literal.Length) != 0)
				throw new FormatException("Invalid literal at " + i + ".");
			i += literal.Length;
		}

		private static void SkipWs(string s, ref int i)
		{
			while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n'))
				i++;
		}

		// ---- Defensive accessors (UW returns numerics both as strings and numbers) ----

		public static Dictionary<string, object> AsObj(object o)
		{
			return o as Dictionary<string, object>;
		}

		public static List<object> AsArr(object o)
		{
			return o as List<object>;
		}

		public static string GetString(Dictionary<string, object> d, string key)
		{
			object v;
			if (d == null || !d.TryGetValue(key, out v) || v == null)
				return null;
			if (v is string)
				return (string)v;
			return Convert.ToString(v, CultureInfo.InvariantCulture);
		}

		public static decimal? GetDecimal(Dictionary<string, object> d, string key)
		{
			object v;
			if (d == null || !d.TryGetValue(key, out v) || v == null)
				return null;
			if (v is decimal) return (decimal)v;
			if (v is double) return (decimal)(double)v;
			if (v is bool) return null;
			string s = v as string;
			if (s != null)
			{
				decimal dec;
				if (decimal.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out dec))
					return dec;
			}
			return null;
		}

		public static long? GetLong(Dictionary<string, object> d, string key)
		{
			decimal? v = GetDecimal(d, key);
			if (!v.HasValue) return null;
			try { return (long)Math.Round(v.Value); }
			catch (OverflowException) { return null; }
		}

		public static bool GetBool(Dictionary<string, object> d, string key, bool fallback)
		{
			object v;
			if (d == null || !d.TryGetValue(key, out v) || v == null)
				return fallback;
			if (v is bool) return (bool)v;
			string s = v as string;
			if (s != null)
			{
				if (string.Equals(s, "true", StringComparison.OrdinalIgnoreCase)) return true;
				if (string.Equals(s, "false", StringComparison.OrdinalIgnoreCase)) return false;
			}
			return fallback;
		}

		public static DateTime? GetUtcTime(Dictionary<string, object> d, string key)
		{
			string s = GetString(d, key);
			if (string.IsNullOrEmpty(s))
				return null;
			DateTime dt;
			if (DateTime.TryParse(s, CultureInfo.InvariantCulture,
				DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out dt))
				return dt;
			// epoch millis fallback
			long ms;
			if (long.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out ms) && ms > 100000000000L)
				return new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddMilliseconds(ms);
			return null;
		}
	}

	#endregion

	#region Diagnostics

	/// <summary>Thread-safe diagnostics surface consumed by the on-chart dashboard.</summary>
	public sealed class DiagnosticsState
	{
		private readonly object sync = new object();
		private string status = "Idle";
		private string wsStatus = "Off";
		private string lastError = "";
		private DateTime lastRestSuccessUtc = DateTime.MinValue;
		private DateTime lastWsMessageUtc = DateTime.MinValue;
		private DateTime rateLimitedUntilUtc = DateTime.MinValue;
		private int reconnectCount;
		private int parseErrorCount;
		private int droppedMessageCount;
		private int wsMessageCount;
		private int tradesIngested;

		public string Status { get { lock (sync) return status; } }
		public string WsStatus { get { lock (sync) return wsStatus; } }
		public string LastError { get { lock (sync) return lastError; } }
		public DateTime LastRestSuccessUtc { get { lock (sync) return lastRestSuccessUtc; } }
		public DateTime LastWsMessageUtc { get { lock (sync) return lastWsMessageUtc; } }
		public DateTime RateLimitedUntilUtc { get { lock (sync) return rateLimitedUntilUtc; } }
		public int ReconnectCount { get { return Thread.VolatileRead(ref reconnectCount); } }
		public int ParseErrorCount { get { return Thread.VolatileRead(ref parseErrorCount); } }
		public int DroppedMessageCount { get { return Thread.VolatileRead(ref droppedMessageCount); } }
		public int WsMessageCount { get { return Thread.VolatileRead(ref wsMessageCount); } }
		public int TradesIngested { get { return Thread.VolatileRead(ref tradesIngested); } }

		public void SetStatus(string s) { lock (sync) status = s ?? ""; }
		public void SetWsStatus(string s) { lock (sync) wsStatus = s ?? ""; }
		public void SetError(string s) { lock (sync) lastError = s ?? ""; }
		public void NoteRestSuccess() { lock (sync) lastRestSuccessUtc = DateTime.UtcNow; }
		public void NoteWsMessage() { lock (sync) lastWsMessageUtc = DateTime.UtcNow; Interlocked.Increment(ref wsMessageCount); }
		public void NoteRateLimit(TimeSpan backoff) { lock (sync) rateLimitedUntilUtc = DateTime.UtcNow.Add(backoff); }
		public void NoteReconnect() { Interlocked.Increment(ref reconnectCount); }
		public void NoteParseError() { Interlocked.Increment(ref parseErrorCount); }
		public void NoteDropped() { Interlocked.Increment(ref droppedMessageCount); }
		public void NoteIngested(int n) { Interlocked.Add(ref tradesIngested, n); }

		public bool IsRateLimited { get { return RateLimitedUntilUtc > DateTime.UtcNow; } }
	}

	#endregion

	#region API client

	public sealed class UwApiException : Exception
	{
		public UwApiErrorKind Kind { get; private set; }
		public HttpStatusCode? Status { get; private set; }

		public UwApiException(UwApiErrorKind kind, HttpStatusCode? status, string message)
			: base(message)
		{
			Kind = kind;
			Status = status;
		}
	}

	/// <summary>Query parameters for GET /api/darkpool/{ticker}.</summary>
	public sealed class UwDarkPoolQuery
	{
		public string Date { get; set; }            // yyyy-MM-dd, optional
		public DateTime? NewerThanUtc { get; set; }
		public DateTime? OlderThanUtc { get; set; }
		public decimal? MinPremium { get; set; }
		public decimal? MaxPremium { get; set; }
		public long? MinSize { get; set; }
		public long? MaxSize { get; set; }
		public long? MinVolume { get; set; }
		public long? MaxVolume { get; set; }
		public int Limit { get; set; }
	}

	/// <summary>
	/// Async REST client for the Unusual Whales API. All calls are fully asynchronous,
	/// cancellable, and retried with configurable backoff. Never logs the API key.
	/// </summary>
	public sealed class UwApiClient : IDisposable
	{
		public const string BaseUrl = "https://api.unusualwhales.com";

		private readonly HttpClient http;
		private readonly int maxRetries;
		private readonly UwBackoffMode backoffMode;
		private readonly DiagnosticsState diag;
		private readonly Random jitter = new Random();
		private bool disposed;

		public UwApiClient(string apiKey, int timeoutSeconds, int maxRetries, UwBackoffMode backoffMode, DiagnosticsState diag)
		{
			this.maxRetries = Math.Max(0, maxRetries);
			this.backoffMode = backoffMode;
			this.diag = diag ?? new DiagnosticsState();
			http = new HttpClient();
			http.BaseAddress = new Uri(BaseUrl);
			http.Timeout = TimeSpan.FromSeconds(Math.Max(5, timeoutSeconds));
			http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", apiKey ?? string.Empty);
			http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
			http.DefaultRequestHeaders.UserAgent.ParseAdd("UW-DarkPoolLiquidityMap-NT8/1.0");
		}

		public async Task<List<UwDarkPoolTrade>> GetDarkPoolTradesAsync(string ticker, UwDarkPoolQuery q, CancellationToken ct)
		{
			string url = BuildDarkPoolUrl(ticker, q);
			string json = await GetJsonAsync(url, ct).ConfigureAwait(false);
			return ParseDarkPoolTrades(json, ticker, diag);
		}

		public async Task<List<UwOffLitPriceLevel>> GetVolumePriceLevelsAsync(string ticker, string dateYyyyMmDd, CancellationToken ct)
		{
			string url = "/api/stock/" + Uri.EscapeDataString(ticker) + "/stock-volume-price-levels";
			if (!string.IsNullOrEmpty(dateYyyyMmDd))
				url += "?date=" + Uri.EscapeDataString(dateYyyyMmDd);
			string json = await GetJsonAsync(url, ct).ConfigureAwait(false);
			return ParseVolumePriceLevels(json, diag);
		}

		// ---------------- URL building ----------------

		public static string BuildDarkPoolUrl(string ticker, UwDarkPoolQuery q)
		{
			var sb = new StringBuilder();
			sb.Append("/api/darkpool/").Append(Uri.EscapeDataString(ticker ?? ""));
			var parms = new List<string>();
			if (q != null)
			{
				if (!string.IsNullOrEmpty(q.Date)) parms.Add("date=" + Uri.EscapeDataString(q.Date));
				if (q.NewerThanUtc.HasValue) parms.Add("newer_than=" + Uri.EscapeDataString(q.NewerThanUtc.Value.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)));
				if (q.OlderThanUtc.HasValue) parms.Add("older_than=" + Uri.EscapeDataString(q.OlderThanUtc.Value.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)));
				if (q.MinPremium.HasValue && q.MinPremium.Value > 0) parms.Add("min_premium=" + q.MinPremium.Value.ToString("0.##", CultureInfo.InvariantCulture));
				if (q.MaxPremium.HasValue && q.MaxPremium.Value > 0) parms.Add("max_premium=" + q.MaxPremium.Value.ToString("0.##", CultureInfo.InvariantCulture));
				if (q.MinSize.HasValue && q.MinSize.Value > 0) parms.Add("min_size=" + q.MinSize.Value.ToString(CultureInfo.InvariantCulture));
				if (q.MaxSize.HasValue && q.MaxSize.Value > 0) parms.Add("max_size=" + q.MaxSize.Value.ToString(CultureInfo.InvariantCulture));
				if (q.MinVolume.HasValue && q.MinVolume.Value > 0) parms.Add("min_volume=" + q.MinVolume.Value.ToString(CultureInfo.InvariantCulture));
				if (q.MaxVolume.HasValue && q.MaxVolume.Value > 0) parms.Add("max_volume=" + q.MaxVolume.Value.ToString(CultureInfo.InvariantCulture));
				int limit = q.Limit <= 0 ? 200 : Math.Min(q.Limit, 500);
				parms.Add("limit=" + limit.ToString(CultureInfo.InvariantCulture));
			}
			if (parms.Count > 0)
				sb.Append('?').Append(string.Join("&", parms));
			return sb.ToString();
		}

		// ---------------- HTTP with retry/backoff ----------------

		private async Task<string> GetJsonAsync(string url, CancellationToken ct)
		{
			Exception last = null;
			for (int attempt = 0; attempt <= maxRetries; attempt++)
			{
				ct.ThrowIfCancellationRequested();
				try
				{
					using (HttpResponseMessage resp = await http.GetAsync(url, ct).ConfigureAwait(false))
					{
						string body = resp.Content == null
							? string.Empty
							: await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
						int code = (int)resp.StatusCode;

						if (resp.IsSuccessStatusCode)
						{
							diag.NoteRestSuccess();
							return body;
						}
						if (code == 401 || code == 403)
							throw new UwApiException(UwApiErrorKind.Auth, resp.StatusCode,
								"Auth/API plan issue (HTTP " + code + "). Check API key and subscription tier.");
						if (code == 404)
							throw new UwApiException(UwApiErrorKind.NotFound, resp.StatusCode,
								"Ticker not supported or no data (HTTP 404).");
						if (code == 422)
							throw new UwApiException(UwApiErrorKind.Validation, resp.StatusCode,
								"Parameter validation failed (HTTP 422): " + Util.Truncate(body, 200));
						if (code == 429)
						{
							double waitSec = GetRetryAfterSeconds(resp);
							if (waitSec <= 0) waitSec = BackoffSeconds(attempt) * 4.0;
							waitSec = Math.Min(waitSec, 120);
							diag.NoteRateLimit(TimeSpan.FromSeconds(waitSec));
							last = new UwApiException(UwApiErrorKind.RateLimited, resp.StatusCode,
								"Rate limited (HTTP 429). Backing off " + (int)waitSec + "s.");
							await Task.Delay(TimeSpan.FromSeconds(waitSec), ct).ConfigureAwait(false);
							continue;
						}
						last = new UwApiException(UwApiErrorKind.Server, resp.StatusCode,
							"Server error (HTTP " + code + ").");
					}
				}
				catch (UwApiException)
				{
					throw; // Auth / NotFound / Validation: do not retry
				}
				catch (OperationCanceledException)
				{
					if (ct.IsCancellationRequested)
						throw;
					// HttpClient timeout surfaces as TaskCanceledException without ct cancellation
					last = new UwApiException(UwApiErrorKind.Network, null, "Request timed out.");
				}
				catch (Exception ex)
				{
					last = new UwApiException(UwApiErrorKind.Network, null, "Network error: " + ex.Message);
				}

				if (attempt < maxRetries)
				{
					try { await Task.Delay(TimeSpan.FromSeconds(BackoffSeconds(attempt)), ct).ConfigureAwait(false); }
					catch (OperationCanceledException) { throw; }
				}
			}
			throw last ?? new UwApiException(UwApiErrorKind.Unknown, null, "Request failed after retries.");
		}

		private double BackoffSeconds(int attempt)
		{
			double jit;
			lock (jitter) jit = jitter.NextDouble();
			switch (backoffMode)
			{
				case UwBackoffMode.Linear: return 2.0 * (attempt + 1) + jit;
				case UwBackoffMode.Fixed: return 5.0 + jit;
				default: return Math.Min(60.0, Math.Pow(2, attempt) * 2.0) + jit;
			}
		}

		private static double GetRetryAfterSeconds(HttpResponseMessage resp)
		{
			try
			{
				if (resp.Headers.RetryAfter != null)
				{
					if (resp.Headers.RetryAfter.Delta.HasValue)
						return resp.Headers.RetryAfter.Delta.Value.TotalSeconds;
					if (resp.Headers.RetryAfter.Date.HasValue)
						return (resp.Headers.RetryAfter.Date.Value.UtcDateTime - DateTime.UtcNow).TotalSeconds;
				}
			}
			catch { }
			return 0;
		}

		// ---------------- Parsing (public + static so unit tests can hit them) ----------------

		public static List<UwDarkPoolTrade> ParseDarkPoolTrades(string json, string fallbackTicker, DiagnosticsState diag)
		{
			var result = new List<UwDarkPoolTrade>();
			object root = JsonLite.Parse(json);
			List<object> arr = JsonLite.AsArr(root);
			if (arr == null)
			{
				Dictionary<string, object> obj = JsonLite.AsObj(root);
				if (obj != null)
				{
					object dataNode;
					if (obj.TryGetValue("data", out dataNode))
						arr = JsonLite.AsArr(dataNode);
				}
			}
			if (arr == null)
				return result;

			foreach (object item in arr)
			{
				Dictionary<string, object> d = JsonLite.AsObj(item);
				if (d == null) continue;
				try
				{
					UwDarkPoolTrade t = ParseTrade(d, fallbackTicker);
					if (t != null)
						result.Add(t);
				}
				catch
				{
					if (diag != null) diag.NoteParseError();
				}
			}
			return result;
		}

		public static UwDarkPoolTrade ParseTrade(Dictionary<string, object> d, string fallbackTicker)
		{
			decimal? price = JsonLite.GetDecimal(d, "price");
			if (!price.HasValue || price.Value <= 0)
				return null;

			long? size = JsonLite.GetLong(d, "size");
			if (!size.HasValue)
				size = JsonLite.GetLong(d, "volume"); // WS payloads sometimes use volume for the print size
			if (!size.HasValue || size.Value <= 0)
				return null;

			var t = new UwDarkPoolTrade();
			string tick = JsonLite.GetString(d, "ticker");
			if (string.IsNullOrEmpty(tick))
				tick = JsonLite.GetString(d, "symbol");
			t.Ticker = string.IsNullOrEmpty(tick) ? fallbackTicker : tick.ToUpperInvariant();

			t.Price = price.Value;
			t.Size = size.Value;

			decimal? prem = JsonLite.GetDecimal(d, "premium");
			t.Premium = prem.HasValue ? prem.Value : price.Value * size.Value;

			DateTime? exec = JsonLite.GetUtcTime(d, "executed_at");
			t.ExecutedAtUtc = exec.HasValue ? exec.Value : DateTime.UtcNow;
			t.TrfExecutedAtUtc = JsonLite.GetUtcTime(d, "trf_executed_at");

			t.NbboBid = JsonLite.GetDecimal(d, "nbbo_bid");
			t.NbboAsk = JsonLite.GetDecimal(d, "nbbo_ask");
			t.NbboBidQuantity = JsonLite.GetLong(d, "nbbo_bid_quantity");
			t.NbboAskQuantity = JsonLite.GetLong(d, "nbbo_ask_quantity");
			t.MarketCenter = JsonLite.GetString(d, "market_center");
			t.SaleConditionCodes = JsonLite.GetString(d, "sale_cond_codes");
			t.ExtHourSoldCodes = JsonLite.GetString(d, "ext_hour_sold_codes");
			t.TradeCode = JsonLite.GetString(d, "trade_code");
			t.TradeSettlement = JsonLite.GetString(d, "trade_settlement");
			t.Canceled = JsonLite.GetBool(d, "canceled", false);
			t.TrackingId = JsonLite.GetString(d, "tracking_id");
			return t;
		}

		public static List<UwOffLitPriceLevel> ParseVolumePriceLevels(string json, DiagnosticsState diag)
		{
			var result = new List<UwOffLitPriceLevel>();
			object root = JsonLite.Parse(json);
			List<object> arr = JsonLite.AsArr(root);
			if (arr == null)
			{
				Dictionary<string, object> obj = JsonLite.AsObj(root);
				if (obj != null)
				{
					object dataNode;
					if (obj.TryGetValue("data", out dataNode))
						arr = JsonLite.AsArr(dataNode);
				}
			}
			if (arr == null)
				return result;

			foreach (object item in arr)
			{
				Dictionary<string, object> d = JsonLite.AsObj(item);
				if (d == null) continue;
				try
				{
					decimal? price = JsonLite.GetDecimal(d, "price");
					if (!price.HasValue || price.Value <= 0) continue;
					long? lit = JsonLite.GetLong(d, "lit_vol");
					long? off = JsonLite.GetLong(d, "off_vol");
					var lvl = new UwOffLitPriceLevel();
					lvl.Price = price.Value;
					lvl.LitVolume = lit.HasValue ? Math.Max(0, lit.Value) : 0;
					lvl.OffLitVolume = off.HasValue ? Math.Max(0, off.Value) : 0;
					result.Add(lvl);
				}
				catch
				{
					if (diag != null) diag.NoteParseError();
				}
			}
			return result;
		}

		public void Dispose()
		{
			if (disposed) return;
			disposed = true;
			try { http.Dispose(); } catch { }
		}
	}

	#endregion

	#region WebSocket client

	/// <summary>
	/// Optional streaming client for wss://api.unusualwhales.com/socket?token=KEY.
	/// Joins the off_lit_trades channel, filters locally by ticker, reconnects with
	/// exponential backoff, and treats 5 minutes of silence as a dead connection.
	/// </summary>
	public sealed class UwWebSocketClient : IDisposable
	{
		private readonly string apiKey;
		private readonly DiagnosticsState diag;
		private readonly Action<UwDarkPoolTrade> onTrade;
		private volatile string tickerFilter;
		private volatile bool streaming;
		private bool disposed;

		public UwWebSocketClient(string apiKey, string tickerFilter, Action<UwDarkPoolTrade> onTrade, DiagnosticsState diag)
		{
			this.apiKey = apiKey ?? "";
			this.tickerFilter = (tickerFilter ?? "").ToUpperInvariant();
			this.onTrade = onTrade;
			this.diag = diag ?? new DiagnosticsState();
		}

		public bool IsStreaming { get { return streaming; } }
		public string TickerFilter { get { return tickerFilter; } set { tickerFilter = (value ?? "").ToUpperInvariant(); } }

		public async Task RunAsync(CancellationToken ct)
		{
			int failures = 0;
			while (!ct.IsCancellationRequested)
			{
				ClientWebSocket ws = null;
				try
				{
					ws = new ClientWebSocket();
					ws.Options.KeepAliveInterval = TimeSpan.FromSeconds(20);
					diag.SetWsStatus("Connecting");
					Uri uri = new Uri("wss://api.unusualwhales.com/socket?token=" + Uri.EscapeDataString(apiKey));

					using (var connectCts = CancellationTokenSource.CreateLinkedTokenSource(ct))
					{
						connectCts.CancelAfter(TimeSpan.FromSeconds(20));
						await ws.ConnectAsync(uri, connectCts.Token).ConfigureAwait(false);
					}

					await SendTextAsync(ws, "{\"channel\":\"off_lit_trades\",\"msg_type\":\"join\"}", ct).ConfigureAwait(false);
					diag.SetWsStatus("Streaming");
					streaming = true;
					failures = 0;

					await ReceiveLoopAsync(ws, ct).ConfigureAwait(false);
				}
				catch (OperationCanceledException)
				{
					if (ct.IsCancellationRequested) break;
				}
				catch (Exception ex)
				{
					diag.SetError("WS: " + ex.Message);
				}
				finally
				{
					streaming = false;
					if (ws != null) { try { ws.Dispose(); } catch { } }
				}

				if (ct.IsCancellationRequested) break;
				failures++;
				diag.NoteReconnect();
				double delaySec = Math.Min(60.0, Math.Pow(2, Math.Min(failures, 6)));
				diag.SetWsStatus("Reconnecting in " + (int)delaySec + "s");
				try { await Task.Delay(TimeSpan.FromSeconds(delaySec), ct).ConfigureAwait(false); }
				catch (OperationCanceledException) { break; }
			}
			streaming = false;
			diag.SetWsStatus("Stopped");
		}

		private static async Task SendTextAsync(ClientWebSocket ws, string text, CancellationToken ct)
		{
			byte[] bytes = Encoding.UTF8.GetBytes(text);
			await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, ct).ConfigureAwait(false);
		}

		private async Task ReceiveLoopAsync(ClientWebSocket ws, CancellationToken ct)
		{
			var buffer = new byte[16 * 1024];
			var sb = new StringBuilder();
			while (!ct.IsCancellationRequested && ws.State == WebSocketState.Open)
			{
				WebSocketReceiveResult r;
				using (var rxCts = CancellationTokenSource.CreateLinkedTokenSource(ct))
				{
					rxCts.CancelAfter(TimeSpan.FromMinutes(5));
					try
					{
						r = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), rxCts.Token).ConfigureAwait(false);
					}
					catch (OperationCanceledException)
					{
						if (ct.IsCancellationRequested) throw;
						throw new TimeoutException("WebSocket idle > 5 minutes; reconnecting.");
					}
				}

				if (r.MessageType == WebSocketMessageType.Close)
				{
					try { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "closing", CancellationToken.None).ConfigureAwait(false); }
					catch { }
					return;
				}
				if (r.MessageType != WebSocketMessageType.Text)
					continue;

				sb.Append(Encoding.UTF8.GetString(buffer, 0, r.Count));
				if (!r.EndOfMessage)
				{
					if (sb.Length > 4 * 1024 * 1024) { sb.Clear(); diag.NoteDropped(); } // runaway frame guard
					continue;
				}

				string msg = sb.ToString();
				sb.Length = 0;
				diag.NoteWsMessage();
				try { HandleMessage(msg); }
				catch { diag.NoteParseError(); }
			}
		}

		/// <summary>Public so unit tests can feed fixture messages directly.</summary>
		public void HandleMessage(string msg)
		{
			object root = JsonLite.Parse(msg);

			// Shape 1: ["off_lit_trades", {payload}] or ["off_lit_trades", [{payload},...]]
			List<object> arr = JsonLite.AsArr(root);
			if (arr != null)
			{
				if (arr.Count >= 2)
				{
					string channel = arr[0] as string;
					if (channel != null && channel.IndexOf("off_lit", StringComparison.OrdinalIgnoreCase) < 0
						&& channel.IndexOf("darkpool", StringComparison.OrdinalIgnoreCase) < 0)
						return; // join acks, heartbeats, other channels
					DispatchPayload(arr[1]);
				}
				return;
			}

			// Shape 2: {"channel":"off_lit_trades","data":...} / {"payload":...}
			Dictionary<string, object> obj = JsonLite.AsObj(root);
			if (obj != null)
			{
				object node;
				if (obj.TryGetValue("data", out node)) { DispatchPayload(node); return; }
				if (obj.TryGetValue("payload", out node)) { DispatchPayload(node); return; }
				DispatchPayload(obj); // bare trade object
			}
		}

		private void DispatchPayload(object payload)
		{
			List<object> list = JsonLite.AsArr(payload);
			if (list != null)
			{
				foreach (object item in list)
					DispatchOne(JsonLite.AsObj(item));
				return;
			}
			DispatchOne(JsonLite.AsObj(payload));
		}

		private void DispatchOne(Dictionary<string, object> d)
		{
			if (d == null) return;
			UwDarkPoolTrade t = UwApiClient.ParseTrade(d, null);
			if (t == null || string.IsNullOrEmpty(t.Ticker))
				return;
			string filter = tickerFilter;
			if (!string.IsNullOrEmpty(filter) && !string.Equals(t.Ticker, filter, StringComparison.OrdinalIgnoreCase))
				return;
			if (onTrade != null)
				onTrade(t);
		}

		public void Dispose()
		{
			disposed = true;
		}
	}

	#endregion

	#region Aggregation

	/// <summary>All knobs the aggregator needs, copied from indicator properties per rebuild.</summary>
	public sealed class AggregatorSettings
	{
		// Level construction
		public LevelGroupingMode GroupingMode;
		public int TickBucketSize;
		public double AtrBucketMultiplier;
		public double PercentBucketSize;        // percent, e.g. 0.05 = 0.05%
		public int MinPrintCountPerLevel;
		public decimal MinTotalPremiumPerLevel;
		public long MinTotalSizePerLevel;
		public long MinOffLitVolumePerLevel;
		public int MaxLevelsToRender;
		public int MaxCachedLevels;
		public bool MergeNearbyLevels;
		public int MergeDistanceTicks;
		public double DecayHalfLifeMinutes;
		public bool IgnoreCanceledTrades;

		// Scoring weights
		public double WeightPremium;
		public double WeightSize;
		public double WeightPrintCount;
		public double WeightOffLitVolume;
		public double WeightOffLitRatio;
		public double WeightRecency;
		public double WeightProximity;
		public double WeightAbsorption;
		public double StalePenalty;
		public double MinScoreToRender;          // 0..100 relative score
		public double HighConfidenceScoreThreshold;

		// Classification
		public int ProximityBandTicks;
		public double MarkerLookbackMinutes;
	}

	/// <summary>Per-rebuild context (market state sampled by the indicator).</summary>
	public sealed class AggregationContext
	{
		public DateTime NowUtc;
		public DateTime MinExecutedUtc;
		public double CurrentPrice;     // UW-instrument price space; 0 = resolve from latest print
		public double ChartPrice;       // chart-instrument price, used to rescale ATR/bars into UW space
		public double Atr;
		public double TickSize;
		public string PriceFormat = "0.00";
		public List<BarSample> RecentBars = new List<BarSample>();
		public AggregatorSettings Settings = new AggregatorSettings();
	}

	internal sealed class LevelAccumulator
	{
		public long Slot;
		public int PrintCount;
		public int CanceledCount;
		public long TotalSize;
		public decimal TotalPremium;
		public double DecayedPremium;
		public decimal PriceSizeSum;
		public long OffLitVolume;
		public long LitVolume;
		public int BidSideCount;
		public int AskSideCount;
		public int MidCount;
		public DateTime FirstSeenUtc = DateTime.MinValue;
		public DateTime LastSeenUtc = DateTime.MinValue;
	}

	/// <summary>
	/// Converts raw dark-pool prints + off/lit volume-by-price rows into scored,
	/// classified LiquidityLevel objects. Thread-safe: Ingest/SetVolumeLevels may be
	/// called from network threads while BuildSnapshot runs on a worker.
	/// </summary>
	public sealed class LiquidityAggregator
	{
		private readonly object sync = new object();
		private readonly List<UwDarkPoolTrade> trades = new List<UwDarkPoolTrade>();
		private readonly HashSet<string> seenKeys = new HashSet<string>(StringComparer.Ordinal);
		private readonly Queue<string> seenOrder = new Queue<string>();
		private List<UwOffLitPriceLevel> volumeLevels = new List<UwOffLitPriceLevel>();
		private readonly int maxCachedTrades;
		private readonly DiagnosticsState diag;
		private int dirtyFlag;

		public LiquidityAggregator(int maxCachedTrades, DiagnosticsState diag)
		{
			this.maxCachedTrades = Math.Max(500, maxCachedTrades);
			this.diag = diag ?? new DiagnosticsState();
		}

		public bool IsDirty { get { return Thread.VolatileRead(ref dirtyFlag) == 1; } }
		public int CachedTradeCount { get { lock (sync) return trades.Count; } }

		public int Ingest(IEnumerable<UwDarkPoolTrade> batch)
		{
			if (batch == null) return 0;
			int added = 0;
			lock (sync)
			{
				foreach (UwDarkPoolTrade t in batch)
				{
					if (t == null || t.Price <= 0 || t.Size <= 0)
						continue;
					string key = t.DedupKey();
					if (seenKeys.Contains(key))
						continue;
					seenKeys.Add(key);
					seenOrder.Enqueue(key);
					while (seenOrder.Count > maxCachedTrades * 2)
						seenKeys.Remove(seenOrder.Dequeue());
					trades.Add(t);
					added++;
				}
				if (trades.Count > maxCachedTrades)
				{
					trades.Sort(CompareByExecutedAt);
					trades.RemoveRange(0, trades.Count - maxCachedTrades);
				}
			}
			if (added > 0)
			{
				diag.NoteIngested(added);
				Interlocked.Exchange(ref dirtyFlag, 1);
			}
			return added;
		}

		public void SetVolumeLevels(List<UwOffLitPriceLevel> levels)
		{
			lock (sync)
				volumeLevels = levels ?? new List<UwOffLitPriceLevel>();
			Interlocked.Exchange(ref dirtyFlag, 1);
		}

		public void Clear()
		{
			lock (sync)
			{
				trades.Clear();
				seenKeys.Clear();
				seenOrder.Clear();
				volumeLevels = new List<UwOffLitPriceLevel>();
			}
			Interlocked.Exchange(ref dirtyFlag, 1);
		}

		private static int CompareByExecutedAt(UwDarkPoolTrade a, UwDarkPoolTrade b)
		{
			return a.ExecutedAtUtc.CompareTo(b.ExecutedAtUtc);
		}

		// =================================================================
		// Snapshot build: cluster -> score -> classify -> merge -> cap
		// =================================================================
		public LiquiditySnapshot BuildSnapshot(AggregationContext ctx)
		{
			Interlocked.Exchange(ref dirtyFlag, 0);
			if (ctx == null || ctx.Settings == null)
				return LiquiditySnapshot.Empty;
			AggregatorSettings s = ctx.Settings;

			List<UwDarkPoolTrade> tradeCopy;
			List<UwOffLitPriceLevel> volCopy;
			lock (sync)
			{
				tradeCopy = new List<UwDarkPoolTrade>(trades);
				volCopy = new List<UwOffLitPriceLevel>(volumeLevels);
			}

			ResolveReferenceFrame(ctx, tradeCopy, volCopy);

			decimal bucket = ComputeBucketWidth(ctx, tradeCopy);
			if (bucket <= 0)
				bucket = (decimal)Math.Max(ctx.TickSize, 0.01);

			DateTime now = ctx.NowUtc;
			var buckets = new Dictionary<long, LevelAccumulator>();
			UwDarkPoolTrade largest = null;
			var recentPrints = new List<UwDarkPoolTrade>();
			decimal tol = (decimal)Math.Max(ctx.TickSize, 0.0001);

			// ---- Pass 1: accumulate trades into price buckets ----
			foreach (UwDarkPoolTrade t in tradeCopy)
			{
				if (t.ExecutedAtUtc < ctx.MinExecutedUtc)
					continue;
				if (s.IgnoreCanceledTrades && t.Canceled)
					continue;

				long slot = (long)Math.Round(t.Price / bucket, MidpointRounding.AwayFromZero);
				LevelAccumulator acc;
				if (!buckets.TryGetValue(slot, out acc))
				{
					acc = new LevelAccumulator();
					acc.Slot = slot;
					buckets[slot] = acc;
				}

				double ageMin = Math.Max(0, (now - t.ExecutedAtUtc).TotalMinutes);
				double decay = Math.Pow(0.5, ageMin / Math.Max(1.0, s.DecayHalfLifeMinutes));

				acc.PrintCount++;
				acc.TotalSize += t.Size;
				acc.TotalPremium += t.Premium;
				acc.DecayedPremium += (double)t.Premium * decay;
				acc.PriceSizeSum += t.Price * t.Size;
				if (t.Canceled) acc.CanceledCount++;
				if (acc.FirstSeenUtc == DateTime.MinValue || t.ExecutedAtUtc < acc.FirstSeenUtc) acc.FirstSeenUtc = t.ExecutedAtUtc;
				if (t.ExecutedAtUtc > acc.LastSeenUtc) acc.LastSeenUtc = t.ExecutedAtUtc;

				// NBBO-relative side inference (never a guarantee of intent)
				if (t.NbboBid.HasValue && t.NbboAsk.HasValue && t.NbboAsk.Value > 0 && t.NbboBid.Value > 0)
				{
					if (t.Price <= t.NbboBid.Value + tol) acc.BidSideCount++;
					else if (t.Price >= t.NbboAsk.Value - tol) acc.AskSideCount++;
					else acc.MidCount++;
				}
				else
					acc.MidCount++;

				double recAgeMin = (now - t.ExecutedAtUtc).TotalMinutes;
				if (recAgeMin <= Math.Max(1.0, s.MarkerLookbackMinutes))
					recentPrints.Add(t);
				if (recAgeMin <= 30 && (largest == null || t.Premium > largest.Premium))
					largest = t;
			}

			// ---- Pass 2: fold in off/lit volume-by-price ----
			foreach (UwOffLitPriceLevel v in volCopy)
			{
				if (v == null || v.Price <= 0)
					continue;
				long slot = (long)Math.Round(v.Price / bucket, MidpointRounding.AwayFromZero);
				LevelAccumulator acc;
				if (!buckets.TryGetValue(slot, out acc))
				{
					acc = new LevelAccumulator();
					acc.Slot = slot;
					buckets[slot] = acc;
				}
				acc.OffLitVolume += Math.Max(0, v.OffLitVolume);
				acc.LitVolume += Math.Max(0, v.LitVolume);
			}

			if (buckets.Count == 0)
				return new LiquiditySnapshot(new List<LiquidityLevel>(), new List<UwDarkPoolTrade>(),
					now, ctx.CurrentPrice, tradeCopy.Count, largest, null, null);

			// ---- Normalization maxima ----
			double maxDecPrem = 1, maxSize = 1, maxCount = 1, maxOff = 1;
			foreach (LevelAccumulator a in buckets.Values)
			{
				if (a.DecayedPremium > maxDecPrem) maxDecPrem = a.DecayedPremium;
				if (a.TotalSize > maxSize) maxSize = a.TotalSize;
				if (a.PrintCount > maxCount) maxCount = a.PrintCount;
				if (a.OffLitVolume > maxOff) maxOff = a.OffLitVolume;
			}

			// ---- Pass 3: score + classify each bucket ----
			decimal half = bucket / 2m;
			double nearBand = Math.Max(ctx.TickSize * Math.Max(1, s.ProximityBandTicks), ctx.Atr * 0.25);
			var levels = new List<LiquidityLevel>();

			foreach (LevelAccumulator a in buckets.Values)
			{
				decimal price = a.TotalSize > 0 ? a.PriceSizeSum / a.TotalSize : a.Slot * bucket;

				bool passesTrades = a.PrintCount >= Math.Max(1, s.MinPrintCountPerLevel)
					&& a.TotalPremium >= s.MinTotalPremiumPerLevel
					&& a.TotalSize >= s.MinTotalSizePerLevel
					&& a.PrintCount > 0;
				bool passesVolumeOnly = a.OffLitVolume > 0
					&& a.OffLitVolume >= Math.Max(1, s.MinOffLitVolumePerLevel);
				if (!passesTrades && !passesVolumeOnly)
					continue;

				double ageMin = a.LastSeenUtc == DateTime.MinValue
					? Math.Max(1.0, s.DecayHalfLifeMinutes) * 2.0
					: Math.Max(0, (now - a.LastSeenUtc).TotalMinutes);
				double recency = Math.Pow(0.5, ageMin / Math.Max(1.0, s.DecayHalfLifeMinutes));

				double proximity = 0;
				double dist = 0;
				if (ctx.CurrentPrice > 0)
				{
					dist = (double)price - ctx.CurrentPrice;
					double scaleP = Math.Max(ctx.Atr * 3.0, ctx.CurrentPrice * 0.005);
					proximity = Math.Exp(-Math.Abs(dist) / Math.Max(scaleP, 0.0001));
				}

				long totVol = a.OffLitVolume + a.LitVolume;
				double offRatio = totVol > 0 ? (double)a.OffLitVolume / totVol : 0;

				// Touch / rejection / break confirmation from recent chart bars
				int touches = 0, rejections = 0, breaks = 0;
				decimal upper = price + half, lower = price - half;
				bool isBelowMarket = ctx.CurrentPrice > 0 && (double)price <= ctx.CurrentPrice;
				if (ctx.RecentBars != null)
				{
					for (int bi = 0; bi < ctx.RecentBars.Count; bi++)
					{
						BarSample b = ctx.RecentBars[bi];
						if ((decimal)b.Low > upper || (decimal)b.High < lower)
							continue;
						touches++;
						if (isBelowMarket && (decimal)b.Close > upper) rejections++;        // held as support
						else if (!isBelowMarket && (decimal)b.Close < lower) rejections++;  // rejected as resistance
						else if (isBelowMarket && (decimal)b.Close < lower) breaks++;
						else if (!isBelowMarket && (decimal)b.Close > upper) breaks++;
					}
				}
				double absorption = Math.Min(1.0, rejections / 5.0);
				double canceledRatio = a.PrintCount > 0 ? (double)a.CanceledCount / a.PrintCount : 0;
				double staleness = 1.0 - recency;

				double raw =
					  s.WeightPremium * (a.DecayedPremium / maxDecPrem)
					+ s.WeightSize * (a.TotalSize / maxSize)
					+ s.WeightPrintCount * (a.PrintCount / maxCount)
					+ s.WeightOffLitVolume * (a.OffLitVolume / maxOff)
					+ s.WeightOffLitRatio * offRatio
					+ s.WeightRecency * recency
					+ s.WeightProximity * proximity
					+ s.WeightAbsorption * absorption
					- s.StalePenalty * staleness
					- 0.25 * canceledRatio;
				if (raw < 0) raw = 0;

				var lvl = new LiquidityLevel();
				lvl.Price = price;
				lvl.ClusterWidth = bucket;
				lvl.RawScore = raw;
				lvl.TotalDarkPoolSize = a.TotalSize;
				lvl.TotalDarkPoolPremium = a.TotalPremium;
				lvl.OffLitVolume = a.OffLitVolume;
				lvl.LitVolume = a.LitVolume;
				lvl.OffLitShare = (decimal)offRatio;
				lvl.PrintCount = a.PrintCount;
				lvl.FirstSeenUtc = a.FirstSeenUtc;
				lvl.LastSeenUtc = a.LastSeenUtc;
				lvl.TouchCount = touches;
				lvl.RejectionCount = rejections;
				lvl.BreakCount = breaks;
				lvl.PremiumWeight = maxDecPrem > 0 ? Math.Min(1.0, a.DecayedPremium / maxDecPrem) : 0;
				lvl.IsFresh = a.LastSeenUtc != DateTime.MinValue
					&& ageMin <= Math.Max(5.0, s.DecayHalfLifeMinutes / 6.0);
				lvl.IsDecayed = recency < 0.15;
				lvl.IsNearCurrentPrice = ctx.CurrentPrice > 0 && Math.Abs(dist) <= nearBand * 2.0;

				// Side inference from NBBO counts
				if (a.BidSideCount > a.AskSideCount * 1.5 && a.BidSideCount >= 2)
					lvl.InferredSide = LiquidityLevelSide.BidSideInferred;
				else if (a.AskSideCount > a.BidSideCount * 1.5 && a.AskSideCount >= 2)
					lvl.InferredSide = LiquidityLevelSide.AskSideInferred;
				else if (a.BidSideCount + a.AskSideCount < Math.Max(1, a.MidCount))
					lvl.InferredSide = LiquidityLevelSide.MidpointOrUnknown;
				else
					lvl.InferredSide = LiquidityLevelSide.Mixed;

				// Type classification (inference only; labels say "Inferred")
				if (ctx.CurrentPrice <= 0)
					lvl.Type = LiquidityLevelType.NeutralCluster;
				else if (Math.Abs(dist) <= nearBand)
					lvl.Type = (a.PrintCount >= 5 || a.OffLitVolume >= maxOff * 0.3)
						? LiquidityLevelType.Magnet
						: LiquidityLevelType.NeutralCluster;
				else if (dist < 0)
				{
					if (breaks >= 1 && recency < 0.3) lvl.Type = LiquidityLevelType.Exhaustion;
					else if (rejections >= 3) lvl.Type = LiquidityLevelType.Absorption;
					else lvl.Type = LiquidityLevelType.Support;
				}
				else
				{
					if (breaks >= 1 && recency < 0.3) lvl.Type = LiquidityLevelType.Exhaustion;
					else if (rejections >= 3) lvl.Type = LiquidityLevelType.Absorption;
					else lvl.Type = LiquidityLevelType.Resistance;
				}

				levels.Add(lvl);
			}

			if (levels.Count == 0)
				return new LiquiditySnapshot(new List<LiquidityLevel>(), CapPrints(recentPrints),
					now, ctx.CurrentPrice, tradeCopy.Count, largest, null, null);

			// ---- Relative score (0..100 of strongest) + true percentile ----
			double maxRaw = 0;
			foreach (LiquidityLevel l in levels)
				if (l.RawScore > maxRaw) maxRaw = l.RawScore;
			if (maxRaw <= 0) maxRaw = 1;

			var sortedRaw = levels.OrderBy(delegate(LiquidityLevel l) { return l.RawScore; }).ToList();
			for (int i = 0; i < sortedRaw.Count; i++)
			{
				LiquidityLevel l = sortedRaw[i];
				l.Score = (decimal)Math.Round(100.0 * l.RawScore / maxRaw, 1);
				l.StrengthPercentile = sortedRaw.Count <= 1
					? 100m
					: (decimal)Math.Round(100.0 * i / (sortedRaw.Count - 1), 0);
			}

			// ---- Merge nearby levels (keep the stronger, absorb the weaker's stats) ----
			if (s.MergeNearbyLevels && levels.Count > 1)
				levels = MergeNearby(levels, (decimal)(ctx.TickSize * Math.Max(1, s.MergeDistanceTicks)));

			// ---- Filter + cap ----
			levels = levels
				.Where(delegate(LiquidityLevel l) { return (double)l.Score >= s.MinScoreToRender; })
				.OrderByDescending(delegate(LiquidityLevel l) { return l.Score; })
				.Take(Math.Min(Math.Max(1, s.MaxLevelsToRender), Math.Max(1, s.MaxCachedLevels)))
				.ToList();

			// ---- Labels + tooltips (precomputed so OnRender does no string work) ----
			LiquidityLevel bestSup = null, bestRes = null;
			foreach (LiquidityLevel l in levels)
			{
				BuildText(l, ctx, now);
				if ((l.Type == LiquidityLevelType.Support || (l.Type == LiquidityLevelType.Absorption && (double)l.Price <= ctx.CurrentPrice))
					&& (bestSup == null || l.Score > bestSup.Score))
					bestSup = l;
				if ((l.Type == LiquidityLevelType.Resistance || (l.Type == LiquidityLevelType.Absorption && (double)l.Price > ctx.CurrentPrice))
					&& (bestRes == null || l.Score > bestRes.Score))
					bestRes = l;
			}

			return new LiquiditySnapshot(levels, CapPrints(recentPrints), now, ctx.CurrentPrice,
				tradeCopy.Count, largest, bestSup, bestRes);
		}

		/// <summary>
		/// Anchors classification to the UW instrument's own price space. When the chart
		/// instrument differs from the UW ticker (e.g., MNQ chart mapped to QQQ),
		/// CurrentPrice arrives as 0 and is resolved from the latest print (fallback:
		/// densest volume-by-price row); ATR and confirmation bars sampled from the chart
		/// are then rescaled into UW space by the price ratio.
		/// </summary>
		private static void ResolveReferenceFrame(AggregationContext ctx, List<UwDarkPoolTrade> tradeCopy, List<UwOffLitPriceLevel> volCopy)
		{
			if (ctx.CurrentPrice <= 0)
			{
				DateTime newest = DateTime.MinValue;
				foreach (UwDarkPoolTrade t in tradeCopy)
				{
					if (t.ExecutedAtUtc >= newest)
					{
						newest = t.ExecutedAtUtc;
						ctx.CurrentPrice = (double)t.Price;
					}
				}
				if (ctx.CurrentPrice <= 0 && volCopy != null && volCopy.Count > 0)
				{
					long best = -1;
					foreach (UwOffLitPriceLevel v in volCopy)
					{
						if (v == null) continue;
						long tv = v.OffLitVolume + v.LitVolume;
						if (tv > best)
						{
							best = tv;
							ctx.CurrentPrice = (double)v.Price;
						}
					}
				}
			}

			if (ctx.ChartPrice > 0 && ctx.CurrentPrice > 0)
			{
				double ratio = ctx.CurrentPrice / ctx.ChartPrice;
				if (Math.Abs(1.0 - ratio) > 0.05)
				{
					ctx.Atr = ctx.Atr * ratio;
					if (ctx.RecentBars != null && ctx.RecentBars.Count > 0)
					{
						var scaled = new List<BarSample>(ctx.RecentBars.Count);
						for (int i = 0; i < ctx.RecentBars.Count; i++)
						{
							BarSample b = ctx.RecentBars[i];
							b.High *= ratio;
							b.Low *= ratio;
							b.Close *= ratio;
							scaled.Add(b);
						}
						ctx.RecentBars = scaled;
					}
				}
			}
		}

		private static List<UwDarkPoolTrade> CapPrints(List<UwDarkPoolTrade> prints)
		{
			return prints
				.OrderByDescending(delegate(UwDarkPoolTrade t) { return t.Premium; })
				.Take(150)
				.ToList();
		}

		private static List<LiquidityLevel> MergeNearby(List<LiquidityLevel> levels, decimal mergeDist)
		{
			if (mergeDist <= 0)
				return levels;
			var byPrice = levels.OrderBy(delegate(LiquidityLevel l) { return l.Price; }).ToList();
			var merged = new List<LiquidityLevel>();
			LiquidityLevel cur = byPrice[0];
			for (int i = 1; i < byPrice.Count; i++)
			{
				LiquidityLevel next = byPrice[i];
				if (next.Price - cur.Price <= mergeDist)
				{
					LiquidityLevel strong = next.Score >= cur.Score ? next : cur;
					LiquidityLevel weak = next.Score >= cur.Score ? cur : next;
					strong.TotalDarkPoolSize += weak.TotalDarkPoolSize;
					strong.TotalDarkPoolPremium += weak.TotalDarkPoolPremium;
					strong.OffLitVolume += weak.OffLitVolume;
					strong.LitVolume += weak.LitVolume;
					strong.PrintCount += weak.PrintCount;
					if (weak.FirstSeenUtc != DateTime.MinValue
						&& (strong.FirstSeenUtc == DateTime.MinValue || weak.FirstSeenUtc < strong.FirstSeenUtc))
						strong.FirstSeenUtc = weak.FirstSeenUtc;
					if (weak.LastSeenUtc > strong.LastSeenUtc)
						strong.LastSeenUtc = weak.LastSeenUtc;
					strong.ClusterWidth = strong.ClusterWidth + (next.Price - cur.Price);
					long tv = strong.OffLitVolume + strong.LitVolume;
					strong.OffLitShare = tv > 0 ? (decimal)strong.OffLitVolume / tv : 0;
					cur = strong;
				}
				else
				{
					merged.Add(cur);
					cur = next;
				}
			}
			merged.Add(cur);
			return merged;
		}

		private static void BuildText(LiquidityLevel l, AggregationContext ctx, DateTime now)
		{
			string typeText = TypeText(l.Type, (double)l.Price <= ctx.CurrentPrice);
			string priceText = l.Price.ToString(ctx.PriceFormat, CultureInfo.InvariantCulture);
			string age = l.LastSeenUtc == DateTime.MinValue ? "n/a" : Util.AgeText(now - l.LastSeenUtc);

			l.Label = priceText + "  " + TypeAbbrev(l.Type) + " " + ((int)l.Score).ToString(CultureInfo.InvariantCulture);

			var sb = new StringBuilder();
			sb.Append("Price: ").Append(priceText).Append('\n');
			sb.Append("Type: ").Append(typeText).Append('\n');
			sb.Append("Score: ").Append((int)l.StrengthPercentile).Append("th percentile (rel ").Append((int)l.Score).Append(")\n");
			sb.Append("Dark Pool Prints: ").Append(l.PrintCount).Append('\n');
			sb.Append("Dark-pool premium: ").Append(Util.FormatCompact((double)l.TotalDarkPoolPremium, true)).Append('\n');
			sb.Append("Dark-pool shares: ").Append(Util.FormatCompact(l.TotalDarkPoolSize, false)).Append('\n');
			sb.Append("Off-Lit Volume at/near price: ").Append(Util.FormatCompact(l.OffLitVolume, false)).Append('\n');
			sb.Append("Off-lit share: ").Append(((double)l.OffLitShare * 100).ToString("0", CultureInfo.InvariantCulture)).Append("%\n");
			sb.Append("Touches/Rejections/Breaks: ").Append(l.TouchCount).Append('/').Append(l.RejectionCount).Append('/').Append(l.BreakCount).Append('\n');
			sb.Append("Last seen: ").Append(age).Append('\n');
			sb.Append("Basis: clustered off-lit prints + volume-by-price + proximity + recency (inference, not resting orders)");
			l.Tooltip = sb.ToString();
		}

		public static string TypeText(LiquidityLevelType t, bool belowMarket)
		{
			switch (t)
			{
				case LiquidityLevelType.Support: return "Inferred Support";
				case LiquidityLevelType.Resistance: return "Inferred Resistance";
				case LiquidityLevelType.Magnet: return "Liquidity Zone (Magnet)";
				case LiquidityLevelType.Absorption: return belowMarket ? "Absorption (Support-side)" : "Absorption (Resistance-side)";
				case LiquidityLevelType.Exhaustion: return "Exhaustion Zone";
				default: return "Off-Lit Cluster";
			}
		}

		public static string TypeAbbrev(LiquidityLevelType t)
		{
			switch (t)
			{
				case LiquidityLevelType.Support: return "S";
				case LiquidityLevelType.Resistance: return "R";
				case LiquidityLevelType.Magnet: return "M";
				case LiquidityLevelType.Absorption: return "A";
				case LiquidityLevelType.Exhaustion: return "X";
				default: return "C";
			}
		}

		public static decimal ComputeBucketWidth(AggregationContext ctx, List<UwDarkPoolTrade> tradesForFallback)
		{
			double tick = Math.Max(ctx.TickSize, 0.0001);
			double price = ctx.CurrentPrice;
			if (price <= 0 && tradesForFallback != null && tradesForFallback.Count > 0)
				price = (double)tradesForFallback[tradesForFallback.Count - 1].Price;
			if (price <= 0)
				price = 100;
			AggregatorSettings s = ctx.Settings;
			double w;
			switch (s.GroupingMode)
			{
				case LevelGroupingMode.ExactPrice:
					w = tick;
					break;
				case LevelGroupingMode.TickBucket:
					w = tick * Math.Max(1, s.TickBucketSize);
					break;
				case LevelGroupingMode.AtrBucket:
					w = Math.Max(tick, ctx.Atr * Math.Max(0.01, s.AtrBucketMultiplier));
					break;
				case LevelGroupingMode.PercentBucket:
					w = Math.Max(tick, price * Math.Max(0.001, s.PercentBucketSize) / 100.0);
					break;
				default: // Auto: max(2 ticks, 0.03% of price, 0.05 * ATR(14))
					w = Math.Max(2.0 * tick, Math.Max(price * 0.0003, 0.05 * ctx.Atr));
					break;
			}
			return (decimal)w;
		}
	}

	#endregion

	#region Utilities

	public static class Util
	{
		public static string FormatCompact(double v, bool currency)
		{
			string prefix = currency ? "$" : "";
			double a = Math.Abs(v);
			string body;
			if (a >= 1e9) body = (v / 1e9).ToString("0.#", CultureInfo.InvariantCulture) + "B";
			else if (a >= 1e6) body = (v / 1e6).ToString("0.#", CultureInfo.InvariantCulture) + "M";
			else if (a >= 1e3) body = (v / 1e3).ToString("0.#", CultureInfo.InvariantCulture) + "K";
			else body = v.ToString("0.#", CultureInfo.InvariantCulture);
			return prefix + body;
		}

		public static string AgeText(TimeSpan age)
		{
			if (age.TotalSeconds < 0) age = TimeSpan.Zero;
			if (age.TotalSeconds < 90) return ((int)age.TotalSeconds) + "s ago";
			if (age.TotalMinutes < 90) return ((int)age.TotalMinutes) + "m ago";
			if (age.TotalHours < 36) return age.TotalHours.ToString("0.#", CultureInfo.InvariantCulture) + "h ago";
			return ((int)age.TotalDays) + "d ago";
		}

		public static string Truncate(string s, int max)
		{
			if (string.IsNullOrEmpty(s)) return "";
			s = s.Replace('\r', ' ').Replace('\n', ' ');
			return s.Length <= max ? s : s.Substring(0, max) + "…";
		}

		/// <summary>
		/// Lightweight XOR+Base64 obfuscation for workspace persistence of the API key.
		/// This is obfuscation, NOT encryption — NinjaScript cannot provide enterprise-grade
		/// secret storage. Documented to the user in README and property tooltips.
		/// </summary>
		public const string ObfuscationPrefix = "uwobf1:";
		private static readonly byte[] obfPad = Encoding.UTF8.GetBytes("UW-DPLM-NT8-LocalPad-2026");

		public static string Obfuscate(string plain)
		{
			if (string.IsNullOrEmpty(plain)) return "";
			byte[] b = Encoding.UTF8.GetBytes(plain);
			for (int i = 0; i < b.Length; i++)
				b[i] ^= obfPad[i % obfPad.Length];
			return ObfuscationPrefix + Convert.ToBase64String(b);
		}

		public static string Deobfuscate(string stored)
		{
			if (string.IsNullOrEmpty(stored)) return "";
			if (!stored.StartsWith(ObfuscationPrefix, StringComparison.Ordinal))
				return stored; // plaintext (user opted out of obfuscation)
			try
			{
				byte[] b = Convert.FromBase64String(stored.Substring(ObfuscationPrefix.Length));
				for (int i = 0; i < b.Length; i++)
					b[i] ^= obfPad[i % obfPad.Length];
				return Encoding.UTF8.GetString(b);
			}
			catch
			{
				return "";
			}
		}
	}

	#endregion
}
