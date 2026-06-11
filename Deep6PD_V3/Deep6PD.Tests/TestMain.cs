//==============================================================================================
//  Deep6PD v3 offline tests (plan r2 Phase 0). Plain console runner, no framework deps:
//  every method named Test* runs; a failed assert prints and sets exit code 1.
//  Run: dotnet run --project Deep6PD.Tests   (or execute the built exe)
//==============================================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using Deep6PD.Core;

namespace Deep6PD.Tests
{
	public static class TestMain
	{
		private static int failures;
		private static string currentTest = "";

		public static int Main(string[] args)
		{
			RunAll();
			Console.WriteLine(failures == 0
				? "ALL TESTS PASSED"
				: failures + " ASSERTION FAILURE(S)");
			return failures == 0 ? 0 : 1;
		}

		private static void RunAll()
		{
			Run("PurityGuard", PurityGuard);
			Run("BarTouchLong", BarTouchLong);
			Run("BarTouchShort", BarTouchShort);
			Run("TapeTargetOnly", TapeTargetOnly);
			Run("TapeStopOnly", TapeStopOnly);
			Run("TapeAmbiguousBothTouched", TapeAmbiguousBothTouched);
			Run("TapeGapThroughStop", TapeGapThroughStop);
			Run("TapeGapThroughTarget", TapeGapThroughTarget);
			Run("TapeGapThroughBothLevels", TapeGapThroughBothLevels);
			Run("TapeTimeoutAtClose", TapeTimeoutAtClose);
			Run("TapeRunsOffEnd", TapeRunsOffEnd);
			Run("TapeShortSide", TapeShortSide);
			Run("ShadowRuleCases", ShadowRuleCases);
			Run("FailureRegistryThrottle", FailureRegistryThrottle);
			Run("PhaseTimerReport", PhaseTimerReport);
			Run("ManualClockDomains", ManualClockDomains);
			Run("AtomicFileNewAndReplace", AtomicFileNewAndReplace);
			Run("StateRoundTrip", StateRoundTrip);
			Run("StateCorruptLoad", StateCorruptLoad);
			Run("CredentialsMissingAndTemplate", CredentialsMissingAndTemplate);
			Run("CredentialsParse", CredentialsParse);
			Run("GexFixtureValid", GexFixtureValid);
			Run("GexFixtureStringNumbers", GexFixtureStringNumbers);
			Run("GexFixtureMissing", GexFixtureMissing);
			Run("GexFixtureMalformed", GexFixtureMalformed);
			Run("GexProviderOff", GexProviderOff);
			Run("CsvRowFormat", CsvRowFormat);
		}

		private static void Run(string name, Action test)
		{
			currentTest = name;
			try { test(); Console.WriteLine("  ok  " + name); }
			catch (Exception ex)
			{
				failures++;
				Console.WriteLine("FAIL  " + name + " — " + ex.Message);
			}
		}

		private static void Assert(bool cond, string what)
		{
			if (!cond) { failures++; Console.WriteLine("FAIL  " + currentTest + ": " + what); }
		}

		private static void AssertClose(double a, double b, string what)
		{
			if (Math.Abs(a - b) > 1e-9) { failures++; Console.WriteLine("FAIL  " + currentTest + ": " + what + " (" + a + " vs " + b + ")"); }
		}

		private static string TempDir()
		{
			string d = Path.Combine(Path.GetTempPath(), "deep6pd_tests_" + Guid.NewGuid().ToString("N"));
			Directory.CreateDirectory(d);
			return d;
		}

		// ---------- purity guard (plan r2 §2.1) ----------

		private static string AddOnsDir()
		{
			string env = Environment.GetEnvironmentVariable("NT_ADDONS_DEEP6PD");
			if (!string.IsNullOrEmpty(env)) return env;
			string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
			return Path.Combine(docs, "NinjaTrader 8", "bin", "Custom", "AddOns", "Deep6PD");
		}

		private static void PurityGuard()
		{
			string dir = AddOnsDir();
			Assert(Directory.Exists(dir), "AddOns\\Deep6PD not found at " + dir);
			if (!Directory.Exists(dir)) return;
			var blockComment = new Regex(@"/\*.*?\*/", RegexOptions.Singleline);
			var lineComment  = new Regex(@"//[^\r\n]*");
			var stringLit    = new Regex("@?\"(?:[^\"\\\\]|\\\\.)*\"");
			var banned       = new Regex(@"\b(NinjaTrader|SharpDX)\s*\.");
			foreach (string file in Directory.GetFiles(dir, "*.cs"))
			{
				string src = File.ReadAllText(file);
				src = blockComment.Replace(src, "");
				src = lineComment.Replace(src, "");
				src = stringLit.Replace(src, "\"\"");
				Match m = banned.Match(src);
				Assert(!m.Success, Path.GetFileName(file) + " references " + m.Value + " — purity violated");
			}
		}

		// ---------- BarTouch ----------

		private static void BarTouchLong()
		{
			bool t, s;
			BarTouch.Evaluate(105, 99, true, 105, 99, out t, out s);
			Assert(t && s, "both levels touched at extremes");
			BarTouch.Evaluate(104, 100, true, 105, 99, out t, out s);
			Assert(!t && !s, "neither touched inside");
			BarTouch.Evaluate(106, 100, true, 105, 99, out t, out s);
			Assert(t && !s, "target only");
		}

		private static void BarTouchShort()
		{
			bool t, s;
			BarTouch.Evaluate(101, 94, false, 95, 101, out t, out s);
			Assert(t && s, "short: both touched");
			BarTouch.Evaluate(100, 96, false, 95, 101, out t, out s);
			Assert(!t && !s, "short: neither");
		}

		// ---------- SignalTape ----------
		// bars: index 0 is the opening bar; resolution starts at index 1

		private static void TapeTargetOnly()
		{
			double[] o = { 100, 101 }, h = { 100, 106 }, l = { 100, 100.5 }, c = { 100, 105 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.Target && r.Win && !r.Ambiguous && r.ExitBar == 1, "clean target");
			AssertClose(r.ExitPrice, 105, "exit at target level");
		}

		private static void TapeStopOnly()
		{
			double[] o = { 100, 99 }, h = { 100, 100 }, l = { 100, 94 }, c = { 100, 96 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.Stop && !r.Win && !r.Ambiguous, "clean stop");
			AssertClose(r.ExitPrice, 95, "exit at stop level");
		}

		private static void TapeAmbiguousBothTouched()
		{
			double[] o = { 100, 100 }, h = { 100, 106 }, l = { 100, 94 }, c = { 100, 100 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.Stop && !r.Win && r.Ambiguous, "both-touched counts the stop, flagged ambiguous");
		}

		private static void TapeGapThroughStop()
		{
			// long, stop 95, next bar OPENS at 92 — exit priced at the open, not the stop
			double[] o = { 100, 92 }, h = { 100, 93 }, l = { 100, 91 }, c = { 100, 92.5 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.Stop, "gap-down is a stop exit");
			AssertClose(r.ExitPrice, 92, "stop gap priced at bar open");
		}

		private static void TapeGapThroughTarget()
		{
			double[] o = { 100, 107 }, h = { 100, 108 }, l = { 100, 106 }, c = { 100, 107.5 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.Target && r.Win, "gap-up through target wins");
			AssertClose(r.ExitPrice, 107, "favorable gap priced at bar open");
		}

		private static void TapeGapThroughBothLevels()
		{
			// edge-case taxonomy (plan r2 Phase 0.15): bar gaps BELOW the stop and its range
			// spans both levels. Conservative: stop, ambiguous, priced at the open beyond the stop.
			double[] o = { 100, 92 }, h = { 100, 106 }, l = { 100, 91 }, c = { 100, 100 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.Stop && r.Ambiguous, "gap through both = stop + ambiguous");
			AssertClose(r.ExitPrice, 92, "priced at open beyond stop");
		}

		private static void TapeTimeoutAtClose()
		{
			double[] o = { 100, 100, 100, 100 }, h = { 100, 101, 101, 101 }, l = { 100, 99, 99, 99 }, c = { 100, 100, 100, 100.5 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 3);
			Assert(r.Exit == TapeExit.Timeout && r.ExitBar == 3, "timeout fires on bar openedBar+timeout");
			AssertClose(r.ExitPrice, 100.5, "timeout resolves at that bar's close");
		}

		private static void TapeRunsOffEnd()
		{
			double[] o = { 100, 100 }, h = { 100, 101 }, l = { 100, 99 }, c = { 100, 100 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, true, 105, 95, 100);
			Assert(r.Exit == TapeExit.None && r.ExitBar == -1, "no exit when data ends first");
		}

		private static void TapeShortSide()
		{
			// short: target 95 below, stop 105 above; bar gaps UP through the stop
			double[] o = { 100, 107 }, h = { 100, 108 }, l = { 100, 106 }, c = { 100, 107 };
			TapeResult r = SignalTape.Resolve(o, h, l, c, 0, false, 95, 105, 100);
			Assert(r.Exit == TapeExit.Stop, "short stop on gap up");
			AssertClose(r.ExitPrice, 107, "short stop gap priced at open");
		}

		// ---------- ShadowRule ----------

		private static void ShadowRuleCases()
		{
			Assert(ShadowRule.IsShadow(10, 100, 0.9, 0.52), "n below MinSamples is SHADOW even with great lo90");
			Assert(ShadowRule.IsShadow(200, 100, 0.50, 0.52), "lo90 below breakeven is SHADOW");
			Assert(!ShadowRule.IsShadow(200, 100, 0.55, 0.52), "passes both gates");
		}

		// ---------- FailureRegistry ----------

		private static void FailureRegistryThrottle()
		{
			var reg = new FailureRegistry(5);
			DateTime t0 = new DateTime(2026, 6, 9, 12, 0, 0, DateTimeKind.Utc);
			Assert(reg.Report("X", "first", t0), "first report logs");
			Assert(!reg.Report("X", "second", t0.AddMinutes(1)), "second within window throttled");
			Assert(reg.Report("X", "third", t0.AddMinutes(6)), "after window logs again");
			Assert(reg.Report("Y", "other category", t0.AddMinutes(1)), "different category not throttled");
			Assert(reg.TotalCount == 4, "total count = 4, got " + reg.TotalCount);
			List<FailureRecord> snap = reg.Snapshot();
			Assert(snap.Count == 2, "two categories in snapshot");
			foreach (FailureRecord r in snap)
				if (r.Category == "X")
				{
					Assert(r.Count == 3, "X count 3");
					Assert(r.LastMessage == "third", "last message kept");
					Assert(r.FirstUtc == t0, "first time kept");
				}
		}

		// ---------- PhaseTimer ----------

		private static void PhaseTimerReport()
		{
			var pt = new PhaseTimer();
			pt.Start("a");
			System.Threading.Thread.Sleep(5);
			pt.Start("b");
			System.Threading.Thread.Sleep(5);
			pt.Stop();
			List<string> lines = pt.ReportLines("TIMING");
			Assert(lines.Count == 4, "title + 2 phases + total");
			Assert(pt.TotalMs > 0, "nonzero total");
		}

		// ---------- ManualClock ----------

		private static void ManualClockDomains()
		{
			DateTime wall = new DateTime(2026, 6, 9, 20, 0, 0, DateTimeKind.Utc);
			var clk = new ManualClock(delegate { return wall; });
			DateTime bar = new DateTime(2026, 6, 9, 9, 31, 0);
			clk.SetBarTime(bar);
			Assert(clk.ExchangeBarTime == bar, "bar time domain");
			Assert(clk.UtcWall == wall, "wall domain injected");
		}

		// ---------- persistence ----------

		private static void AtomicFileNewAndReplace()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "x.json");
			AtomicFile.WriteAllText(f, "one");
			Assert(File.ReadAllText(f) == "one", "first write");
			AtomicFile.WriteAllText(f, "two");
			Assert(File.ReadAllText(f) == "two", "replace write");
			Assert(File.Exists(f + ".bak"), "bak left by File.Replace");
			Assert(!File.Exists(f + ".tmp"), "tmp cleaned up");
			Directory.Delete(dir, true);
		}

		private static void StateRoundTrip()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "state.json");
			var sp = new StatePersistence(null);
			var dto = new PersistedStateDto { CodeVersion = "3.0.0-p0", CalibratedThroughUtc = "2026-06-09T20:00:00Z" };
			dto.Cells["H4|REVERT"] = new[] { 12.0, 7.0, 3.0 };
			string err;
			Assert(sp.TrySave(f, dto, out err), "save ok");
			PersistedStateDto back;
			Assert(sp.TryLoad(f, out back, out err), "load ok");
			Assert(back.Cells.Count == 1, "one cell");
			AssertClose(back.Cells["H4|REVERT"][0], 12.0, "alpha round trip");
			Assert(back.SchemaVersion == "3.0.0-p0", "schema version");
			Directory.Delete(dir, true);
		}

		private static void StateCorruptLoad()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "state.json");
			File.WriteAllText(f, "{ this is not json !!");
			var sp = new StatePersistence(null);
			PersistedStateDto dto; string err;
			Assert(!sp.TryLoad(f, out dto, out err), "corrupt load fails");
			Assert(dto == null, "dto null on corrupt");
			Assert(!string.IsNullOrEmpty(err), "error populated");
			Assert(File.Exists(f), "bad file left in place for inspection (Phase 0 contract)");
			Directory.Delete(dir, true);
		}

		private static void CredentialsMissingAndTemplate()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "credentials.json");
			CredentialsDto creds; string err;
			Assert(!CredentialStore.TryLoad(f, out creds, out err), "missing file fails");
			CredentialStore.WriteTemplateIfMissing(f);
			Assert(File.Exists(f), "template written");
			Assert(CredentialStore.TryLoad(f, out creds, out err), "template loads");
			Assert(creds.UwToken == "", "template token empty");
			string before = File.ReadAllText(f);
			CredentialStore.WriteTemplateIfMissing(f);
			Assert(File.ReadAllText(f) == before, "never overwrites existing");
			Directory.Delete(dir, true);
		}

		private static void CredentialsParse()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "credentials.json");
			File.WriteAllText(f, "{ \"uwToken\": \"abc123\", \"flashAlphaUrl\": \"https://x.test/gex\" }");
			CredentialsDto creds; string err;
			Assert(CredentialStore.TryLoad(f, out creds, out err), "valid file loads");
			Assert(creds.UwToken == "abc123", "token parsed");
			Assert(creds.FlashAlphaUrl == "https://x.test/gex", "url parsed");
			File.WriteAllText(f, "not json");
			Assert(!CredentialStore.TryLoad(f, out creds, out err), "corrupt credentials fail");
			Directory.Delete(dir, true);
		}

		// ---------- GEX fixture provider ----------

		private static void GexFixtureValid()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "gex.json");
			File.WriteAllText(f,
				"[ { \"date\": \"2026-06-05\", \"call_gamma\": 5.0, \"put_gamma\": -2.0 }," +
				"  { \"date\": \"2026-06-08\", \"call_gamma\": 1.0, \"put_gamma\": -4.0 } ]");
			var p = new FileFixtureGexProvider(f);
			DateTime now = DateTime.UtcNow;
			GexReading r; string err;
			Assert(p.TryGetLatest(now, out r, out err), "latest ok");
			Assert(r.DataSessionDate == new DateTime(2026, 6, 8), "latest by session date");
			AssertClose(r.Net, -3.0, "net = call + put");
			Assert(r.Sign == -1, "sign from net");
			AssertClose(r.RawCallGamma, 1.0, "raw call kept for audit");
			Dictionary<DateTime, int> hist;
			Assert(p.TryGetHistory(now, out hist, out err), "history ok");
			Assert(hist.Count == 2, "two sessions");
			Assert(hist[new DateTime(2026, 6, 5)] == 1, "first session positive");
			Directory.Delete(dir, true);
		}

		private static void GexFixtureStringNumbers()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "gex.json");
			File.WriteAllText(f, "[ { \"date\": \"2026-06-08\", \"call_gamma\": \"2.5\", \"put_gamma\": \"-1.0\" } ]");
			var p = new FileFixtureGexProvider(f);
			GexReading r; string err;
			Assert(p.TryGetLatest(DateTime.UtcNow, out r, out err), "string-typed numbers parse (UW tier quirk)");
			AssertClose(r.Net, 1.5, "net from strings");
			Directory.Delete(dir, true);
		}

		private static void GexFixtureMissing()
		{
			var p = new FileFixtureGexProvider(Path.Combine(TempDir(), "nope.json"));
			GexReading r; string err;
			Assert(!p.TryGetLatest(DateTime.UtcNow, out r, out err), "missing fixture fails");
			Assert(err.Contains("not found"), "reason says not found");
		}

		private static void GexFixtureMalformed()
		{
			string dir = TempDir();
			string f = Path.Combine(dir, "gex.json");
			File.WriteAllText(f, "{ \"not\": \"an array\" }");
			var p = new FileFixtureGexProvider(f);
			GexReading r; string err;
			Assert(!p.TryGetLatest(DateTime.UtcNow, out r, out err), "malformed fixture fails");
			Assert(!string.IsNullOrEmpty(err), "error populated");
			Directory.Delete(dir, true);
		}

		private static void GexProviderOff()
		{
			var p = new OffGexProvider();
			GexReading r; string err;
			Assert(!p.TryGetLatest(DateTime.UtcNow, out r, out err), "off provider returns nothing");
			Dictionary<DateTime, int> hist;
			Assert(!p.TryGetHistory(DateTime.UtcNow, out hist, out err), "off provider has no history");
		}

		// ---------- CSV schema ----------

		private static void CsvRowFormat()
		{
			DateTime wall = new DateTime(2026, 6, 9, 20, 0, 0, DateTimeKind.Utc);
			DateTime bar = new DateTime(2026, 6, 9, 9, 31, 0);
			string row = SignalsCsvSchema.FormatRow("abc", wall, bar, "3.0.0-p0", "NQ", "1m",
				"CLOSE", "H4", "REVERT", "L", 100.25, 105.5, 95.0, 105.5, "TARGET", false, "WIN, extra");
			string[] parts = row.Split(',');
			string[] header = SignalsCsvSchema.Header.Split(',');
			Assert(parts.Length == header.Length, "row column count matches header (" + parts.Length + " vs " + header.Length + ")");
			Assert(parts[0] == SignalsCsvSchema.SchemaVersion, "schema version first");
			Assert(parts[1] == "abc", "signalId present");
			Assert(row.Contains("WIN; extra"), "commas in note escaped");
			Assert(parts[11] == "100.25", "invariant culture decimal");
			// OPEN rows: NaN exit price serializes empty
			string openRow = SignalsCsvSchema.FormatRow("abc", wall, bar, "3.0.0-p0", "NQ", "1m",
				"OPEN", "H4", "REVERT", "L", 100.25, 105.5, 95.0, double.NaN, "", false, "");
			Assert(openRow.Split(',').Length == header.Length, "open row column count");
		}
	}
}
