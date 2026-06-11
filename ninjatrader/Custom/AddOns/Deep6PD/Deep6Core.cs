//==============================================================================================
//  Deep6Core.cs — PURE logic for Deep6PremiumDiscountV3 (build-out plan r2, Phase 0).
//----------------------------------------------------------------------------------------------
//  PURITY RULE (enforced by the test project's guard test): this file must contain NO
//  NinjaTrader.* and NO SharpDX.* types. Time is injected via IClock; GEX via IGexProvider;
//  logging via delegates. Everything here must be unit-testable on plain .NET Framework 4.8.
//  C# syntax is kept conservative (C# 5) so the file compiles under both the NinjaTrader 8
//  in-platform compiler and the framework csc used by the offline test harness.
//==============================================================================================

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using Newtonsoft.Json.Linq;

namespace Deep6PD.Core
{
	#region Clock

	/// <summary>
	/// All trading logic time (timeouts, cooldowns, session windows, CSV timestamps) comes from
	/// ExchangeBarTime. Wall UTC is ONLY for GEX fetch-age bookkeeping and archive filenames.
	/// </summary>
	public interface IClock
	{
		DateTime ExchangeBarTime { get; }
		DateTime UtcWall { get; }
	}

	/// <summary>
	/// Shell-owned clock. The indicator pushes the primary bar time on every OnBarUpdate;
	/// the wall source is injectable so tests and Playback parity runs are deterministic.
	/// </summary>
	public sealed class ManualClock : IClock
	{
		private DateTime barTime;
		private readonly Func<DateTime> wallSource;

		public ManualClock(Func<DateTime> wallSource)
		{
			this.wallSource = wallSource ?? DefaultWall;
		}

		private static DateTime DefaultWall() { return DateTime.UtcNow; }

		public void SetBarTime(DateTime t) { barTime = t; }

		public DateTime ExchangeBarTime { get { return barTime; } }
		public DateTime UtcWall { get { return wallSource(); } }
	}

	#endregion

	#region FailureRegistry

	public sealed class FailureRecord
	{
		public string Category;
		public int Count;
		public DateTime FirstUtc;
		public DateTime LastUtc;
		public string LastMessage;
	}

	/// <summary>
	/// Replaces every silent catch {}. Counts failures per category, keeps first/last time and
	/// last message, and throttles logging to once per category per throttleMinutes.
	/// Report(...) returns true when the caller should emit a log line now.
	/// Not thread-safe by itself: callers on non-data threads must lock or marshal.
	/// </summary>
	public sealed class FailureRegistry
	{
		private readonly Dictionary<string, FailureRecord> records = new Dictionary<string, FailureRecord>();
		private readonly Dictionary<string, DateTime> lastLogged = new Dictionary<string, DateTime>();
		private readonly double throttleMinutes;
		private readonly object gate = new object();

		public FailureRegistry(double throttleMinutes)
		{
			this.throttleMinutes = Math.Max(0, throttleMinutes);
		}

		public bool Report(string category, string message, DateTime utcNow)
		{
			lock (gate)
			{
				FailureRecord rec;
				if (!records.TryGetValue(category, out rec))
				{
					rec = new FailureRecord { Category = category, FirstUtc = utcNow };
					records[category] = rec;
				}
				rec.Count++;
				rec.LastUtc = utcNow;
				rec.LastMessage = message;

				DateTime last;
				if (!lastLogged.TryGetValue(category, out last) || (utcNow - last).TotalMinutes >= throttleMinutes)
				{
					lastLogged[category] = utcNow;
					return true;
				}
				return false;
			}
		}

		public int TotalCount
		{
			get
			{
				lock (gate)
				{
					int n = 0;
					foreach (FailureRecord r in records.Values) n += r.Count;
					return n;
				}
			}
		}

		public List<FailureRecord> Snapshot()
		{
			lock (gate)
			{
				var list = new List<FailureRecord>();
				foreach (FailureRecord r in records.Values)
					list.Add(new FailureRecord
					{
						Category = r.Category, Count = r.Count, FirstUtc = r.FirstUtc,
						LastUtc = r.LastUtc, LastMessage = r.LastMessage
					});
				list.Sort(CompareByLastUtcDesc);
				return list;
			}
		}

		private static int CompareByLastUtcDesc(FailureRecord a, FailureRecord b)
		{
			return b.LastUtc.CompareTo(a.LastUtc);
		}
	}

	#endregion

	#region Signal tape (bar-level lifecycle resolution)

	public enum TapeExit { None = 0, Target = 1, Stop = 2, Timeout = 3 }

	/// <summary>Single-bar touch test — the one source of truth for target/stop hits.</summary>
	public static class BarTouch
	{
		public static void Evaluate(double high, double low, bool isLong, double target, double stop,
			out bool targetHit, out bool stopHit)
		{
			targetHit = isLong ? high >= target : low <= target;
			stopHit   = isLong ? low  <= stop   : high >= stop;
		}
	}

	public sealed class TapeResult
	{
		public TapeExit Exit;       // None = ran off the end of the supplied bars
		public int ExitBar;         // absolute index into the supplied arrays
		public bool Win;            // Target and not Stop on the exit bar
		public bool Ambiguous;      // target and stop both touched inside the exit bar
		public double ExitPrice;    // gap-through priced at bar OPEN beyond the level
	}

	/// <summary>
	/// Conservative primary-bar lifecycle over plain OHLC arrays. This is the Phase 0 "bar tape"
	/// harness: the same rule the shell uses live, runnable as a fast deterministic unit test.
	/// Rules (plan r2 Phase 2.2/2.3 realism, conservative variant):
	///  - both target and stop inside one bar => STOP, Ambiguous = true (true order unknown);
	///  - gap-through exits are priced at the bar OPEN beyond the level, not at the level;
	///  - timeout resolves at the timeout bar close.
	/// </summary>
	public static class SignalTape
	{
		/// <summary>
		/// One bar's worth of the conservative rule. Exit = None when neither level was touched.
		/// The shell's live path and the array harness below both go through here.
		/// </summary>
		public static TapeResult EvaluateBar(double open, double high, double low, double close,
			bool isLong, double target, double stop)
		{
			var res = new TapeResult { Exit = TapeExit.None, ExitBar = -1, ExitPrice = double.NaN };
			bool targetHit, stopHit;
			BarTouch.Evaluate(high, low, isLong, target, stop, out targetHit, out stopHit);

			if (stopHit)
			{
				res.Exit = TapeExit.Stop;
				res.Win = false;
				res.Ambiguous = targetHit;
				// gap through the stop: the bar opened beyond it -> exit at the open, not the stop
				bool gapped = isLong ? open < stop : open > stop;
				res.ExitPrice = gapped ? open : stop;
				return res;
			}
			if (targetHit)
			{
				res.Exit = TapeExit.Target;
				res.Win = true;
				res.Ambiguous = false;
				bool gapped = isLong ? open > target : open < target;
				res.ExitPrice = gapped ? open : target;
				return res;
			}
			return res;
		}

		public static TapeResult Resolve(double[] open, double[] high, double[] low, double[] close,
			int openedBar, bool isLong, double target, double stop, int timeoutBars)
		{
			if (open == null || high == null || low == null || close == null)
				throw new ArgumentNullException("open/high/low/close");
			int n = close.Length;
			if (high.Length != n || low.Length != n || open.Length != n)
				throw new ArgumentException("OHLC arrays must share one length");
			if (openedBar < 0 || openedBar >= n)
				throw new ArgumentOutOfRangeException("openedBar");

			for (int i = openedBar + 1; i < n; i++)
			{
				TapeResult bar = EvaluateBar(open[i], high[i], low[i], close[i], isLong, target, stop);
				if (bar.Exit != TapeExit.None)
				{
					bar.ExitBar = i;
					return bar;
				}
				if (i - openedBar >= timeoutBars)
				{
					return new TapeResult
					{
						Exit = TapeExit.Timeout, ExitBar = i, Win = false,
						Ambiguous = false, ExitPrice = close[i]
					};
				}
			}
			return new TapeResult { Exit = TapeExit.None, ExitBar = -1, ExitPrice = double.NaN };
		}
	}

	#endregion

	#region Shadow rule

	/// <summary>
	/// The single SHADOW predicate (plan r2 Phase 0.5): used by BOTH the composite weighting
	/// and the dashboard so they can never disagree again.
	/// </summary>
	public static class ShadowRule
	{
		public static bool IsShadow(double cellN, int minSamples, double lo90, double breakeven)
		{
			return cellN < minSamples || lo90 < breakeven;
		}
	}

	#endregion

	#region Measurement harness

	/// <summary>
	/// Stopwatch wrapper for calibration phases (plan r2 Phase 0.13). Start(name) implicitly
	/// stops the previous phase; Report() prints a table the shell writes to the output window
	/// and the calibration report.
	/// </summary>
	public sealed class PhaseTimer
	{
		private sealed class Entry { public string Name; public double Ms; }

		private readonly List<Entry> entries = new List<Entry>();
		private readonly Stopwatch watch = new Stopwatch();
		private string current;

		public void Start(string name)
		{
			Stop();
			current = name;
			watch.Restart();
		}

		public void Stop()
		{
			if (current == null) return;
			watch.Stop();
			entries.Add(new Entry { Name = current, Ms = watch.Elapsed.TotalMilliseconds });
			current = null;
		}

		public double TotalMs
		{
			get
			{
				double t = 0;
				foreach (Entry e in entries) t += e.Ms;
				return t;
			}
		}

		public List<string> ReportLines(string title)
		{
			Stop();
			var lines = new List<string>();
			lines.Add(title);
			foreach (Entry e in entries)
				lines.Add(string.Format(CultureInfo.InvariantCulture, "   {0,-32} {1,9:F1} ms", e.Name, e.Ms));
			lines.Add(string.Format(CultureInfo.InvariantCulture, "   {0,-32} {1,9:F1} ms", "TOTAL", TotalMs));
			return lines;
		}
	}

	#endregion

	#region GEX provider

	/// <summary>Immutable GEX observation. Raw components kept for the sign-convention audit trail.</summary>
	public sealed class GexReading
	{
		public readonly double Net;
		public readonly int Sign;
		public readonly DateTime DataSessionDate;   // staleness axis = sessions, not minutes (plan r2 #5)
		public readonly DateTime UtcFetched;
		public readonly string Source;
		public readonly double RawCallGamma;
		public readonly double RawPutGamma;

		public GexReading(double net, DateTime dataSessionDate, DateTime utcFetched, string source,
			double rawCallGamma, double rawPutGamma)
		{
			Net = net;
			Sign = net > 0 ? 1 : net < 0 ? -1 : 0;
			DataSessionDate = dataSessionDate;
			UtcFetched = utcFetched;
			Source = source;
			RawCallGamma = rawCallGamma;
			RawPutGamma = rawPutGamma;
		}
	}

	/// <summary>
	/// Three modes (plan r2 Phase 0.12): live HTTP (implemented in the shell — it owns threading),
	/// file fixture keyed by session date (here, for Playback/tests), and Off.
	/// OfflineMode in the shell hard-fails any HTTP attempt; Playback must never poll live GEX.
	/// </summary>
	public interface IGexProvider
	{
		string Name { get; }
		bool TryGetLatest(DateTime utcNow, out GexReading reading, out string error);
		bool TryGetHistory(DateTime utcNow, out Dictionary<DateTime, int> signBySessionDate, out string error);
	}

	public sealed class OffGexProvider : IGexProvider
	{
		public string Name { get { return "OFF"; } }

		public bool TryGetLatest(DateTime utcNow, out GexReading reading, out string error)
		{
			reading = null; error = "GEX disabled"; return false;
		}

		public bool TryGetHistory(DateTime utcNow, out Dictionary<DateTime, int> signBySessionDate, out string error)
		{
			signBySessionDate = null; error = "GEX disabled"; return false;
		}
	}

	/// <summary>
	/// Reads a JSON fixture shaped like the UW greek-exposure rows:
	///   [ { "date": "yyyy-MM-dd", "call_gamma": 1.23, "put_gamma": -4.56 }, ... ]
	/// Values may be JSON numbers or strings (UW sends strings for some tiers).
	/// </summary>
	public sealed class FileFixtureGexProvider : IGexProvider
	{
		private readonly string path;
		private List<GexReading> cache;
		private string cacheError;

		public FileFixtureGexProvider(string fixturePath)
		{
			path = fixturePath;
		}

		public string Name { get { return "FIXTURE"; } }

		private bool EnsureLoaded(DateTime utcNow, out string error)
		{
			if (cache != null) { error = null; return true; }
			if (cacheError != null) { error = cacheError; return false; }
			try
			{
				if (!File.Exists(path))
				{
					cacheError = "fixture not found: " + path;
					error = cacheError;
					return false;
				}
				var rows = new List<GexReading>();
				JArray arr = JArray.Parse(File.ReadAllText(path));
				foreach (JToken tok in arr)
				{
					string dateText = (string)tok["date"];
					if (string.IsNullOrEmpty(dateText)) continue;
					DateTime d = DateTime.ParseExact(dateText, "yyyy-MM-dd", CultureInfo.InvariantCulture);
					double cg = ParseNumber(tok["call_gamma"]);
					double pg = ParseNumber(tok["put_gamma"]);
					rows.Add(new GexReading(cg + pg, d, utcNow, "FIXTURE", cg, pg));
				}
				rows.Sort(CompareBySessionDate);
				if (rows.Count == 0)
				{
					cacheError = "fixture has no usable rows: " + path;
					error = cacheError;
					return false;
				}
				cache = rows;
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				cacheError = "fixture parse failed: " + ex.Message;
				error = cacheError;
				return false;
			}
		}

		private static int CompareBySessionDate(GexReading a, GexReading b)
		{
			return a.DataSessionDate.CompareTo(b.DataSessionDate);
		}

		private static double ParseNumber(JToken tok)
		{
			if (tok == null) return 0;
			if (tok.Type == JTokenType.Float || tok.Type == JTokenType.Integer) return (double)tok;
			double v;
			if (double.TryParse((string)tok, NumberStyles.Float, CultureInfo.InvariantCulture, out v)) return v;
			return 0;
		}

		public bool TryGetLatest(DateTime utcNow, out GexReading reading, out string error)
		{
			reading = null;
			if (!EnsureLoaded(utcNow, out error)) return false;
			reading = cache[cache.Count - 1];
			return true;
		}

		public bool TryGetHistory(DateTime utcNow, out Dictionary<DateTime, int> signBySessionDate, out string error)
		{
			signBySessionDate = null;
			if (!EnsureLoaded(utcNow, out error)) return false;
			var map = new Dictionary<DateTime, int>();
			foreach (GexReading r in cache) map[r.DataSessionDate] = r.Sign > 0 ? 1 : -1;
			signBySessionDate = map;
			return true;
		}
	}

	#endregion
}
