//==============================================================================================
//  Deep6Persistence.cs — PURE persistence for Deep6PremiumDiscountV3 (plan r2, Phase 0).
//----------------------------------------------------------------------------------------------
//  Same purity rule as Deep6Core.cs: NO NinjaTrader.*, NO SharpDX.*. Paths, logger delegate and
//  clock are injected by the shell. Newtonsoft is pinned to the major version NinjaTrader ships
//  (13.x at the time of writing).
//  Phase 0 scope: atomic writes (tmp + File.Replace), schema-versioned state DTO, credentials
//  loading. Fingerprint gating, checksum, corrupt-archive recovery arrive in Phase 1.
//==============================================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using Newtonsoft.Json;

namespace Deep6PD.Core
{
	#region Atomic file writes

	public static class AtomicFile
	{
		/// <summary>
		/// Serialize-to-temp then File.Replace — atomic on local NTFS, leaves a free .bak.
		/// First-ever write (no destination yet) falls back to File.Move.
		/// </summary>
		public static void WriteAllText(string path, string contents)
		{
			string tmp = path + ".tmp";
			File.WriteAllText(tmp, contents);
			if (File.Exists(path))
				File.Replace(tmp, path, path + ".bak");
			else
				File.Move(tmp, path);
		}
	}

	#endregion

	#region State DTO + persistence

	/// <summary>
	/// Phase 0 persisted shape: v2-compatible cell payload plus schema/code version fields.
	/// Serialized fields only — no derived getters (plan r2 Phase 1.3 rule, honored early).
	/// </summary>
	public sealed class PersistedStateDto
	{
		[JsonProperty("schemaVersion")] public string SchemaVersion = "3.0.0-p0";
		[JsonProperty("codeVersion")]   public string CodeVersion = "";
		[JsonProperty("calibratedThroughUtc")] public string CalibratedThroughUtc = "";
		[JsonProperty("cells")] public Dictionary<string, double[]> Cells = new Dictionary<string, double[]>();
	}

	public sealed class StatePersistence
	{
		private readonly Action<string> log;

		public StatePersistence(Action<string> log)
		{
			this.log = log ?? NoLog;
		}

		private static void NoLog(string s) { }

		public bool TrySave(string path, PersistedStateDto dto, out string error)
		{
			try
			{
				AtomicFile.WriteAllText(path, JsonConvert.SerializeObject(dto, Formatting.Indented));
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				error = ex.Message;
				log("Deep6PD state save failed: " + ex.Message);
				return false;
			}
		}

		/// <summary>
		/// Phase 0: a corrupt or unreadable file returns false with the reason; the shell prints
		/// it and starts fresh WITHOUT overwriting the bad file (Phase 1 adds archive + restore).
		/// </summary>
		public bool TryLoad(string path, out PersistedStateDto dto, out string error)
		{
			dto = null;
			try
			{
				if (!File.Exists(path)) { error = "no state file"; return false; }
				dto = JsonConvert.DeserializeObject<PersistedStateDto>(File.ReadAllText(path));
				if (dto == null) { error = "state file deserialized to null"; return false; }
				if (dto.Cells == null) { error = "state file has no cells"; dto = null; return false; }
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				dto = null;
				error = ex.Message;
				log("Deep6PD state load failed: " + ex.Message);
				return false;
			}
		}
	}

	#endregion

	#region Credentials

	/// <summary>
	/// Secrets live in Documents\NinjaTrader 8\Deep6PD\credentials.json, NEVER in workspace XML
	/// (plan r2 Phase 0.4). Shape: { "uwToken": "...", "flashAlphaUrl": "..." }.
	/// </summary>
	public sealed class CredentialsDto
	{
		[JsonProperty("uwToken")]       public string UwToken = "";
		[JsonProperty("flashAlphaUrl")] public string FlashAlphaUrl = "";
	}

	public static class CredentialStore
	{
		public static bool TryLoad(string path, out CredentialsDto creds, out string error)
		{
			creds = null;
			try
			{
				if (!File.Exists(path)) { error = "credentials file not found: " + path; return false; }
				creds = JsonConvert.DeserializeObject<CredentialsDto>(File.ReadAllText(path));
				if (creds == null) { error = "credentials file deserialized to null"; return false; }
				if (creds.UwToken == null) creds.UwToken = "";
				if (creds.FlashAlphaUrl == null) creds.FlashAlphaUrl = "";
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				creds = null;
				error = "credentials parse failed: " + ex.Message;
				return false;
			}
		}

		/// <summary>Writes a template so the user knows the expected shape. Never overwrites.</summary>
		public static void WriteTemplateIfMissing(string path)
		{
			if (File.Exists(path)) return;
			var dto = new CredentialsDto { UwToken = "", FlashAlphaUrl = "" };
			AtomicFile.WriteAllText(path, JsonConvert.SerializeObject(dto, Formatting.Indented));
		}
	}

	#endregion

	#region Signals CSV schema (Phase 0 slice)

	/// <summary>
	/// Phase 0 telemetry contract: schema comment line + header + one row per OPEN/CLOSE event,
	/// each row carrying a SignalId so pairing is programmatic from day one. The full Phase 6
	/// column set extends this header; the validator script checks against this constant.
	/// </summary>
	public static class SignalsCsvSchema
	{
		public const string SchemaVersion = "3.0-p0";
		public const string CommentLine = "# deep6 signals schema=3.0-p0";
		public const string Header =
			"schemaVersion,signalId,utcWall,exchangeBarTime,codeVersion,instrument,barPeriod," +
			"evt,tf,regime,dir,entry,target,stop,exitPrice,exitReason,ambiguous,note";

		public static string FormatRow(string signalId, DateTime utcWall, DateTime exchangeBarTime,
			string codeVersion, string instrument, string barPeriod, string evt, string tf,
			string regime, string dir, double entry, double target, double stop,
			double exitPrice, string exitReason, bool ambiguous, string note)
		{
			return string.Join(",", new[]
			{
				SchemaVersion,
				signalId,
				utcWall.ToString("o", CultureInfo.InvariantCulture),
				exchangeBarTime.ToString("o", CultureInfo.InvariantCulture),
				codeVersion,
				instrument,
				barPeriod,
				evt,
				tf,
				regime,
				dir,
				entry.ToString("R", CultureInfo.InvariantCulture),
				target.ToString("R", CultureInfo.InvariantCulture),
				stop.ToString("R", CultureInfo.InvariantCulture),
				double.IsNaN(exitPrice) ? "" : exitPrice.ToString("R", CultureInfo.InvariantCulture),
				exitReason ?? "",
				ambiguous ? "1" : "0",
				(note ?? "").Replace(',', ';')
			});
		}
	}

	#endregion
}
