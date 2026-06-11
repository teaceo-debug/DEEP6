// =====================================================================================
// DEEP6DarkPoolLevels.cs
// NinjaTrader 8 indicator: Unusual Whales dark-pool / off-lit liquidity map.
//
// Ingests UW dark-pool prints (REST /api/darkpool/{ticker}, optional WebSocket
// off_lit_trades stream) and off/lit volume-by-price
// (/api/stock/{ticker}/stock-volume-price-levels), clusters them into scored
// liquidity levels, and renders inferred support/resistance/magnet/absorption/
// exhaustion zones with SharpDX.
//
// IMPORTANT: All labels say "Inferred ...", "Dark Pool Prints", "Off-Lit Volume",
// or "Liquidity Zone". This is post-trade inference, NOT a hidden order book and
// NOT guaranteed resting orders. Analytical tool only — not financial advice.
//
// Companion file (required): UWDarkPoolCore.cs (namespace UWLiquidityMap.Core).
// Written against C# 5 language features so it compiles on NT 8.0 and NT 8.1.
// =====================================================================================

#region Using declarations
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using UWLiquidityMap.Core;
using D2D = SharpDX.Direct2D1;
using DW = SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
	public class DEEP6DarkPoolLevels : Indicator
	{
		#region Private state

		// Services (created in DataLoaded / Realtime, torn down in Terminated)
		private DiagnosticsState diagnostics;
		private LiquidityAggregator aggregator;
		private UwApiClient apiClient;
		private UwWebSocketClient wsClient;
		private CancellationTokenSource cts;
		private ConcurrentQueue<UwDarkPoolTrade> incomingQueue;
		private volatile LiquiditySnapshot latestSnapshot;
		private volatile bool servicesStarted;
		private volatile bool authFailed;

		// Market state sampled on the NinjaScript thread (x64: double reads/writes atomic)
		private double lastPrice;
		private double atrValue;
		private ATR atrInd;
		private readonly object barLock = new object();
		private List<BarSample> barWindow;

		// Polling bookkeeping
		private DateTime lastTradeUtc = DateTime.MinValue;
		private DateTime lastVolumeFetchUtc = DateTime.MinValue;
		private DateTime lastBuildUtc = DateTime.MinValue;
		private DateTime lastRefreshUtc = DateTime.MinValue;
		private DateTime lastFallbackDrawUtc = DateTime.MinValue;

		// Symbol mapping
		private string resolvedTicker = "";
		private string chartSymbol = "";
		private bool needsMapping;          // UW ticker differs from chart instrument -> project prices by ratio
		private string futuresWarning = "";
		private string priceFormat = "0.00";
		private TimeZoneInfo easternTz;

		// Alerts
		private Dictionary<string, LevelAlertState> alertStates;
		private string lastLargePrintKey = "";

		private sealed class RadarWall
		{
			public double Price;
			public string Side;
			public long Size;
			public string Intent;
			public string State;
			public string Classification;
			public double Quality;
			public double Spoof;
		}
		private volatile List<RadarWall> radarWalls;
		private DateTime radarGeneratedUtc = DateTime.MinValue;
		private DateTime radarLastFileWriteUtc = DateTime.MinValue;
		private DateTime radarLastCheckUtc = DateTime.MinValue;
		private string radarSourceQuality = "";
		private string radarStatus = "off";
		private int radarConfluenceCount;

		// DirectX resources
		private readonly Dictionary<Color4, D2D.SolidColorBrush> dxBrushCache = new Dictionary<Color4, D2D.SolidColorBrush>();
		private D2D.StrokeStyle dashStroke;
		private DW.TextFormat labelFormat;
		private DW.TextFormat smallFormat;
		private DW.TextFormat titleFormat;
		private readonly List<float> usedLabelYs = new List<float>();
		private readonly List<float> usedTagYs = new List<float>();
		private readonly List<RenderLevel> renderLevels = new List<RenderLevel>();

		private struct RenderLevel
		{
			public LiquidityLevel Level;
			public double MappedPrice;
			public float YTop, YBot, YMid;
			public float XStart, XEnd;
			public Color4 BaseColor;
			public float Conf;
			public bool Stale;
			public int Tier;
			public RadarWall Confluence;
		}

		// Fallback (non-SharpDX) draw object tags
		private readonly HashSet<string> fallbackTags = new HashSet<string>();

		private sealed class LevelAlertState
		{
			public bool InZone;
			public bool Broken;
			public DateTime BrokenAtUtc = DateTime.MinValue;
			public bool Retested;
			public bool NewLevelAlerted;
			public DateTime LastAlertUtc = DateTime.MinValue;
		}

		private struct UwTheme
		{
			public Color4 Support;
			public Color4 Resistance;
			public Color4 Magnet;
			public Color4 Exhaustion;
			public Color4 Text;
			public Color4 PanelBg;
			public Color4 PanelBorder;
			public Color4 Marker;
		}

		#endregion

		#region OnStateChange

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Unusual Whales dark-pool / off-lit liquidity map with Depth Radar V6 MBO wall confluence. Plots inferred support, "
					+ "resistance, magnet, absorption and exhaustion zones from dark-pool prints and "
					+ "off/lit volume-by-price. Highlights Depth Radar V6 wall confluence. Post-trade inference — not resting orders, not financial advice.";
				Name = "Deep6 DarkPool Levels";
				Calculate = Calculate.OnPriceChange;
				IsOverlay = true;
				DisplayInDataBox = false;
				DrawOnPricePanel = true;
				PaintPriceMarkers = false;
				IsSuspendedWhileInactive = false;
				IsChartOnly = true;
				BarsRequiredToPlot = 0;

				// ---- Connection ----
				ApiKey = "";
				StoreApiKeyObfuscated = true;
				UseTickerOverride = false;
				UwTickerOverride = "";
				EnableRestSnapshot = true;
				EnableWebSocketStreaming = false;
				PollIntervalSeconds = 15;
				RequestTimeoutSeconds = 15;
				MaxRetries = 3;
				BackoffMode = UwBackoffMode.Exponential;
				LogLevel = UwLogLevel.Warning;

				// ---- Data filters ----
				LookbackTradingDays = 1;
				IntradayOnly = true;
				IncludeExtendedHours = true;
				MinPremium = 0;
				MaxPremium = 0;
				MinSize = 0;
				MaxSize = 0;
				MinVolume = 0;
				MaxTradesPerRequest = 500;
				IgnoreCanceledTrades = true;
				SaleConditionFilter = "";
				TradeCodeFilter = "";
				SessionDateOverride = "";

				// ---- Level construction ----
				GroupingMode = LevelGroupingMode.Auto;
				TickBucketSize = 4;
				AtrBucketMultiplier = 0.10;
				PercentBucketSize = 0.05;
				MinPrintCountPerLevel = 1;
				MinTotalPremiumPerLevel = 50000;
				MinTotalSizePerLevel = 0;
				MinOffLitVolumePerLevel = 0;
				MaxLevelsToRender = 10;
				MergeNearbyLevels = true;
				MergeDistanceTicks = 12;
				DecayHalfLifeMinutes = 90;
				HistoricalDecayDays = 3;

				// ---- Advanced scoring ----
				WeightPremium = 0.20;
				WeightSize = 0.15;
				WeightPrintCount = 0.10;
				WeightOffLitVolume = 0.20;
				WeightOffLitRatio = 0.10;
				WeightRecency = 0.10;
				WeightProximity = 0.10;
				WeightAbsorption = 0.05;
				StalePenalty = 0.20;
				MinScoreToRender = 25;
				HighConfidenceScoreThreshold = 75;

				// ---- Visual ----
				ThemePreset = UwThemePreset.DarkInstitutional;
				ShowZones = true;
				ShowLines = true;
				ShowLabels = true;
				ShowPrintMarkers = true;
				ShowDashboard = true;
				ShowTooltips = true;
				ShowConfidenceLegend = true;
				ZoneOpacityMin = 0.06;
				ZoneOpacityMax = 0.16;
				LineWidthMin = 1;
				LineWidthMax = 4;
				LabelMode = LabelDisplayMode.Compact;
				ExtendLevelsRight = true;
				ExtendLevelsLeft = false;
				FadeStaleLevels = true;
				UseSharpDxRendering = true;
				DashboardPosition = DashboardCorner.TopLeft;
				MarkerLookbackMinutes = 120;
				CustomSupportBrush = Brushes.Teal;
				CustomResistanceBrush = Brushes.IndianRed;
				CustomMagnetBrush = Brushes.SlateGray;
				CustomTextBrush = Brushes.Gainsboro;

				// ---- Depth Radar V6 ----
				EnableDepthRadar = true;
				DepthRadarJsonPath = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "NinjaTrader 8", "templates", "DEEP6", "depth_radar_walls.json");
				RadarConfluenceTicks = 8;
				RadarStaleSec = 90;
				RadarMinQuality = 40;
				HighlightConfluence = true;

				// ---- Alerts ----
				EnableAlerts = false;
				AlertOnNewHighConfidenceLevel = true;
				AlertOnPriceApproachLevel = true;
				AlertDistanceTicks = 8;
				AlertOnBreak = true;
				AlertOnRetest = true;
				AlertOnLargePrint = false;
				AlertLargePrintMinPremium = 1000000;
				AlertSound = "Alert2.wav";
				AlertCooldownSeconds = 120;
				AlertMessageTemplate = "{ticker} {event} {type} {price} | score {score} | off-lit {offlit}";

				// ---- Performance / diagnostics ----
				MaxCachedTrades = 5000;
				MaxCachedLevels = 400;
				RenderThrottleMs = 250;
				AggregationThrottleMs = 1000;
				UseConcurrentQueue = true;
				UseLockFreeSnapshotForRender = true;
				EnableDiagnostics = true;
				EnableFixtureMode = false;
				FixtureDirectory = "";
				VolumeLevelsRefreshSeconds = 300;
			}
			else if (State == State.Configure)
			{
				// Static validation only — no I/O, no service construction.
				PollIntervalSeconds = Math.Max(5, PollIntervalSeconds);
				RequestTimeoutSeconds = Math.Max(5, RequestTimeoutSeconds);
				MaxRetries = Math.Max(0, Math.Min(10, MaxRetries));
				MaxTradesPerRequest = Math.Max(10, Math.Min(500, MaxTradesPerRequest));
				MaxLevelsToRender = Math.Max(1, Math.Min(100, MaxLevelsToRender));
				MaxCachedTrades = Math.Max(500, MaxCachedTrades);
				AggregationThrottleMs = Math.Max(250, AggregationThrottleMs);
				RenderThrottleMs = Math.Max(100, RenderThrottleMs);
				if (ZoneOpacityMax < ZoneOpacityMin) ZoneOpacityMax = ZoneOpacityMin;
				if (LineWidthMax < LineWidthMin) LineWidthMax = LineWidthMin;
				RadarConfluenceTicks = Math.Max(1, Math.Min(200, RadarConfluenceTicks));
				RadarStaleSec = Math.Max(5, Math.Min(3600, RadarStaleSec));
				if (RadarMinQuality < 0) RadarMinQuality = 0;
				if (RadarMinQuality > 100) RadarMinQuality = 100;
			}
			else if (State == State.DataLoaded)
			{
				ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;

				diagnostics = new DiagnosticsState();
				aggregator = new LiquidityAggregator(MaxCachedTrades, diagnostics);
				incomingQueue = new ConcurrentQueue<UwDarkPoolTrade>();
				barWindow = new List<BarSample>(512);
				alertStates = new Dictionary<string, LevelAlertState>();
				latestSnapshot = LiquiditySnapshot.Empty;
				atrInd = ATR(14);
				priceFormat = BuildPriceFormat(TickSize);
				try { easternTz = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"); }
				catch { easternTz = null; }
				resolvedTicker = ResolveTicker();
				chartSymbol = CleanTicker(Instrument != null && Instrument.MasterInstrument != null
					? Instrument.MasterInstrument.Name : "");
				needsMapping = !string.Equals(resolvedTicker, chartSymbol, StringComparison.OrdinalIgnoreCase);
				diagnostics.SetStatus(string.IsNullOrEmpty(ApiKey) && !EnableFixtureMode
					? "No API key — set ApiKey in indicator properties"
					: "Waiting for realtime…");

				try
				{
					DW.Factory dwf = Core.Globals.DirectWriteFactory;
					labelFormat = new DW.TextFormat(dwf, "Segoe UI", 11f);
					smallFormat = new DW.TextFormat(dwf, "Segoe UI", 10f);
					titleFormat = new DW.TextFormat(dwf, "Segoe UI", DW.FontWeight.SemiBold, DW.FontStyle.Normal, 12f);
				}
				catch (Exception ex)
				{
					LogMsg(UwLogLevel.Error, "TextFormat init failed: " + ex.Message);
				}
			}
			else if (State == State.Realtime)
			{
				StartServices();
			}
			else if (State == State.Terminated)
			{
				StopServices();
				DisposeDeviceBrushes();
				if (dashStroke != null) { try { dashStroke.Dispose(); } catch { } dashStroke = null; }
				if (labelFormat != null) { try { labelFormat.Dispose(); } catch { } labelFormat = null; }
				if (smallFormat != null) { try { smallFormat.Dispose(); } catch { } smallFormat = null; }
				if (titleFormat != null) { try { titleFormat.Dispose(); } catch { } titleFormat = null; }
			}
		}

		#endregion

		#region Service lifecycle

		private void StartServices()
		{
			if (servicesStarted)
				return;
			servicesStarted = true;
			cts = new CancellationTokenSource();
			CancellationToken ct = cts.Token;

			if (EnableFixtureMode)
			{
				diagnostics.SetStatus("Fixture mode (offline)");
				Task.Run(delegate { return LoadFixturesAsync(ct); });
			}
			else if (string.IsNullOrWhiteSpace(ApiKey))
			{
				diagnostics.SetStatus("No API key — set ApiKey in indicator properties");
				LogMsg(UwLogLevel.Warning, "No API key configured; data services not started.");
			}
			else
			{
				apiClient = new UwApiClient(ApiKey, RequestTimeoutSeconds, MaxRetries, BackoffMode, diagnostics);
				if (EnableRestSnapshot || EnableWebSocketStreaming)
				{
					Task.Run(delegate { return RestLoopAsync(ct); });
				}
				else
				{
					diagnostics.SetStatus("Both REST and WebSocket disabled — enable a data source");
				}
				if (EnableWebSocketStreaming)
				{
					wsClient = new UwWebSocketClient(ApiKey, resolvedTicker, OnWsTrade, diagnostics);
					Task.Run(delegate { return wsClient.RunAsync(ct); });
				}
			}

			Task.Run(delegate { return AggregationLoopAsync(ct); });
		}

		private void StopServices()
		{
			servicesStarted = false;
			try { if (cts != null) cts.Cancel(); } catch { }
			try { if (apiClient != null) apiClient.Dispose(); } catch { }
			try { if (wsClient != null) wsClient.Dispose(); } catch { }
			apiClient = null;
			wsClient = null;
			// cts intentionally not disposed immediately: in-flight loops may still observe
			// the token for a few ms after Cancel; GC reclaims it safely.
		}

		#endregion

		#region REST polling

		private async Task RestLoopAsync(CancellationToken ct)
		{
			try
			{
				if (EnableRestSnapshot)
				{
					await FetchVolumeLevelsAsync(ct).ConfigureAwait(false);
					await FetchDarkPoolAsync(true, ct).ConfigureAwait(false);
				}

				while (!ct.IsCancellationRequested)
				{
					await Task.Delay(TimeSpan.FromSeconds(Math.Max(5, PollIntervalSeconds)), ct).ConfigureAwait(false);
					if (authFailed)
						continue; // status shown on dashboard; do not hammer the API
					if (diagnostics.IsRateLimited)
					{
						diagnostics.SetStatus("Rate limited — backing off until "
							+ diagnostics.RateLimitedUntilUtc.ToLocalTime().ToString("HH:mm:ss", CultureInfo.InvariantCulture));
						continue;
					}
					if (!EnableRestSnapshot)
						continue;

					bool wsHealthy = wsClient != null && wsClient.IsStreaming;
					if (!wsHealthy)
						await FetchDarkPoolAsync(false, ct).ConfigureAwait(false);

					if ((DateTime.UtcNow - lastVolumeFetchUtc).TotalSeconds >= Math.Max(60, VolumeLevelsRefreshSeconds))
						await FetchVolumeLevelsAsync(ct).ConfigureAwait(false);
				}
			}
			catch (OperationCanceledException) { }
			catch (Exception ex)
			{
				diagnostics.SetError("REST loop: " + ex.Message);
				LogMsg(UwLogLevel.Error, "REST loop terminated: " + ex.Message);
			}
		}

		private async Task FetchDarkPoolAsync(bool initial, CancellationToken ct)
		{
			try
			{
				int totalFetched = 0;
				int totalAdded = 0;
				DateTime cutoff = ComputeLookbackCutoffUtc();
				DateTime? olderThan = null;

				if (initial)
				{
					for (int page = 0; page < 10; page++)
					{
						ct.ThrowIfCancellationRequested();
						var q = new UwDarkPoolQuery();
						q.Limit = MaxTradesPerRequest;
						if (!string.IsNullOrWhiteSpace(SessionDateOverride))
						{
							q.Date = SessionDateOverride.Trim();
						}
						else if (IntradayOnly)
						{
							// Without a date param the UW API returns the last trading date (yesterday).
							// When IntradayOnly=true we need today's prints, so send today's ET date explicitly.
							try
							{
								DateTime etNow = easternTz != null
									? TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, easternTz)
									: DateTime.UtcNow;
								q.Date = etNow.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
							}
							catch
							{
								q.Date = DateTime.UtcNow.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
							}
						}
						if (MinPremium > 0) q.MinPremium = MinPremium;
						if (MaxPremium > 0) q.MaxPremium = MaxPremium;
						if (MinSize > 0) q.MinSize = MinSize;
						if (MaxSize > 0) q.MaxSize = MaxSize;
						if (MinVolume > 0) q.MinVolume = MinVolume;
						if (olderThan.HasValue)
							q.OlderThanUtc = olderThan;

						List<UwDarkPoolTrade> list = await apiClient.GetDarkPoolTradesAsync(resolvedTicker, q, ct).ConfigureAwait(false);
						totalFetched += list.Count;

						DateTime oldestInPage = DateTime.MaxValue;
						if (list.Count > 0)
						{
							var filtered = new List<UwDarkPoolTrade>(list.Count);
							foreach (UwDarkPoolTrade t in list)
							{
								if (t.ExecutedAtUtc > lastTradeUtc)
									lastTradeUtc = t.ExecutedAtUtc;
								if (t.ExecutedAtUtc < oldestInPage)
									oldestInPage = t.ExecutedAtUtc;
								if (PassesLocalFilters(t))
									filtered.Add(t);
							}
							totalAdded += aggregator.Ingest(filtered);
						}

						if (list.Count < MaxTradesPerRequest)
							break;
						if (oldestInPage == DateTime.MaxValue || oldestInPage <= cutoff)
							break;
						olderThan = oldestInPage.AddSeconds(-1);
					}
				}
				else
				{
					var q = new UwDarkPoolQuery();
					q.Limit = MaxTradesPerRequest;
					if (!string.IsNullOrWhiteSpace(SessionDateOverride))
					{
						q.Date = SessionDateOverride.Trim();
					}
					else if (IntradayOnly)
					{
						// Without a date param the UW API returns the last trading date (yesterday).
						// When IntradayOnly=true we need today's prints, so send today's ET date explicitly.
						try
						{
							DateTime etNow = easternTz != null
								? TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, easternTz)
								: DateTime.UtcNow;
							q.Date = etNow.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
						}
						catch
						{
							q.Date = DateTime.UtcNow.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
						}
					}
					if (MinPremium > 0) q.MinPremium = MinPremium;
					if (MaxPremium > 0) q.MaxPremium = MaxPremium;
					if (MinSize > 0) q.MinSize = MinSize;
					if (MaxSize > 0) q.MaxSize = MaxSize;
					if (MinVolume > 0) q.MinVolume = MinVolume;
					if (!initial && lastTradeUtc > DateTime.MinValue)
						q.NewerThanUtc = lastTradeUtc;

					List<UwDarkPoolTrade> list = await apiClient.GetDarkPoolTradesAsync(resolvedTicker, q, ct).ConfigureAwait(false);
					totalFetched = list.Count;
					int added = 0;
					if (list.Count > 0)
					{
						var filtered = new List<UwDarkPoolTrade>(list.Count);
						foreach (UwDarkPoolTrade t in list)
						{
							if (t.ExecutedAtUtc > lastTradeUtc)
								lastTradeUtc = t.ExecutedAtUtc;
							if (PassesLocalFilters(t))
								filtered.Add(t);
						}
						added = aggregator.Ingest(filtered);
					}
					totalAdded = added;
				}

				bool wsHealthy = wsClient != null && wsClient.IsStreaming;
				diagnostics.SetStatus((wsHealthy ? "Streaming + polling OK" : "Polling OK")
					+ " — " + totalFetched + " prints (" + totalAdded + " new)");
				if (initial && totalFetched == 0)
					diagnostics.SetStatus("Connected, but no dark-pool prints for '" + resolvedTicker
						+ "'. Check ticker mapping / session date.");
			}
			catch (OperationCanceledException) { throw; }
			catch (UwApiException ex) { HandleApiError(ex); }
			catch (Exception ex)
			{
				diagnostics.SetError("Dark-pool fetch: " + ex.Message);
				LogMsg(UwLogLevel.Warning, "Dark-pool fetch failed: " + ex.Message);
			}
		}

		private async Task FetchVolumeLevelsAsync(CancellationToken ct)
		{
			try
			{
				string date = string.IsNullOrWhiteSpace(SessionDateOverride) ? null : SessionDateOverride.Trim();
				List<UwOffLitPriceLevel> levels = await apiClient.GetVolumePriceLevelsAsync(resolvedTicker, date, ct).ConfigureAwait(false);
				aggregator.SetVolumeLevels(levels);
				lastVolumeFetchUtc = DateTime.UtcNow;
				LogMsg(UwLogLevel.Info, "Volume-by-price refreshed: " + levels.Count + " rows.");
			}
			catch (OperationCanceledException) { throw; }
			catch (UwApiException ex) { HandleApiError(ex); lastVolumeFetchUtc = DateTime.UtcNow; }
			catch (Exception ex)
			{
				diagnostics.SetError("Volume levels: " + ex.Message);
				lastVolumeFetchUtc = DateTime.UtcNow;
			}
		}

		private void HandleApiError(UwApiException ex)
		{
			diagnostics.SetError(ex.Message);
			switch (ex.Kind)
			{
				case UwApiErrorKind.Auth:
					authFailed = true;
					diagnostics.SetStatus("Auth/API plan issue — polling stopped. Fix ApiKey, then reload chart.");
					LogMsg(UwLogLevel.Error, "401/403 from Unusual Whales. Polling stopped.");
					break;
				case UwApiErrorKind.NotFound:
					diagnostics.SetStatus("Ticker not supported or no data: " + resolvedTicker
						+ (string.IsNullOrEmpty(futuresWarning) ? "" : " — " + futuresWarning));
					break;
				case UwApiErrorKind.Validation:
					diagnostics.SetStatus("Parameter validation error (422) — check date/filters.");
					LogMsg(UwLogLevel.Warning, ex.Message);
					break;
				case UwApiErrorKind.RateLimited:
					diagnostics.SetStatus("Rate limited (429) — backing off.");
					break;
				default:
					diagnostics.SetStatus("Network/server issue — retrying. " + Util.Truncate(ex.Message, 80));
					break;
			}
		}

		#endregion

		#region WebSocket + filters

		private void OnWsTrade(UwDarkPoolTrade t)
		{
			try
			{
				if (!PassesLocalFilters(t))
					return;
				if (t.ExecutedAtUtc > lastTradeUtc)
					lastTradeUtc = t.ExecutedAtUtc;
				if (UseConcurrentQueue)
					incomingQueue.Enqueue(t);
				else
					aggregator.Ingest(new List<UwDarkPoolTrade> { t });
			}
			catch { diagnostics.NoteDropped(); }
		}

		private bool PassesLocalFilters(UwDarkPoolTrade t)
		{
			if (t == null) return false;
			if (IgnoreCanceledTrades && t.Canceled) return false;
			if (MinPremium > 0 && t.Premium < MinPremium) return false;
			if (MaxPremium > 0 && t.Premium > MaxPremium) return false;
			if (MinSize > 0 && t.Size < MinSize) return false;
			if (MaxSize > 0 && t.Size > MaxSize) return false;
			if (!PassesCodeFilter(SaleConditionFilter, t.SaleConditionCodes)) return false;
			if (!PassesCodeFilter(TradeCodeFilter, t.TradeCode)) return false;
			if (!IncludeExtendedHours && !IsRegularHoursEt(t.ExecutedAtUtc)) return false;
			return true;
		}

		// Include-only filter: empty filter = allow all; otherwise the trade's code string
		// must contain at least one of the comma-separated tokens.
		private static bool PassesCodeFilter(string filter, string codes)
		{
			if (string.IsNullOrWhiteSpace(filter))
				return true;
			if (string.IsNullOrEmpty(codes))
				return false;
			string[] tokens = filter.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
			for (int i = 0; i < tokens.Length; i++)
			{
				string tok = tokens[i].Trim();
				if (tok.Length > 0 && codes.IndexOf(tok, StringComparison.OrdinalIgnoreCase) >= 0)
					return true;
			}
			return false;
		}

		private bool IsRegularHoursEt(DateTime utc)
		{
			if (easternTz == null)
				return true; // can't resolve tz — fail open
			DateTime et = TimeZoneInfo.ConvertTimeFromUtc(utc, easternTz);
			int mins = et.Hour * 60 + et.Minute;
			return mins >= 9 * 60 + 30 && mins < 16 * 60;
		}

		#endregion

		#region Aggregation loop

		private async Task AggregationLoopAsync(CancellationToken ct)
		{
			try
			{
				while (!ct.IsCancellationRequested)
				{
					await Task.Delay(Math.Max(250, AggregationThrottleMs), ct).ConfigureAwait(false);

					// Drain the WS queue into the aggregator
					if (incomingQueue != null && !incomingQueue.IsEmpty)
					{
						var drained = new List<UwDarkPoolTrade>();
						UwDarkPoolTrade t;
						while (incomingQueue.TryDequeue(out t))
							drained.Add(t);
						if (drained.Count > 0)
							aggregator.Ingest(drained);
					}

					// Rebuild on new data, or every 15s so decay/proximity stay current
					bool due = (DateTime.UtcNow - lastBuildUtc).TotalSeconds > 15;
					if (!aggregator.IsDirty && !due)
						continue;

					AggregationContext ctx = BuildContext();
					DateTime t0 = DateTime.UtcNow;
					LiquiditySnapshot snap = aggregator.BuildSnapshot(ctx);
					double elapsedMs = (DateTime.UtcNow - t0).TotalMilliseconds;
					if (elapsedMs > 50)
						LogMsg(UwLogLevel.Debug, "Aggregation took " + elapsedMs.ToString("0", CultureInfo.InvariantCulture) + "ms");

					latestSnapshot = snap;
					lastBuildUtc = DateTime.UtcNow;
					RequestChartRefresh();
				}
			}
			catch (OperationCanceledException) { }
			catch (Exception ex)
			{
				diagnostics.SetError("Aggregation loop: " + ex.Message);
				LogMsg(UwLogLevel.Error, "Aggregation loop terminated: " + ex.Message);
			}
		}

		private AggregationContext BuildContext()
		{
			var ctx = new AggregationContext();
			ctx.NowUtc = DateTime.UtcNow;
			// When the UW ticker differs from the chart instrument (futures chart + ETF
			// override), classification must run in the UW instrument's price space: the
			// aggregator resolves CurrentPrice from the latest print and rescales ATR/bars.
			ctx.CurrentPrice = needsMapping ? 0 : lastPrice;
			ctx.ChartPrice = lastPrice;
			ctx.Atr = atrValue;
			ctx.TickSize = needsMapping ? 0.01 : TickSize;
			ctx.PriceFormat = needsMapping ? "0.00" : priceFormat;
			ctx.MinExecutedUtc = ComputeLookbackCutoffUtc();
			lock (barLock)
				ctx.RecentBars = new List<BarSample>(barWindow);

			var s = new AggregatorSettings();
			s.GroupingMode = GroupingMode;
			s.TickBucketSize = TickBucketSize;
			s.AtrBucketMultiplier = AtrBucketMultiplier;
			s.PercentBucketSize = PercentBucketSize;
			s.MinPrintCountPerLevel = MinPrintCountPerLevel;
			s.MinTotalPremiumPerLevel = MinTotalPremiumPerLevel;
			s.MinTotalSizePerLevel = MinTotalSizePerLevel;
			s.MinOffLitVolumePerLevel = MinOffLitVolumePerLevel;
			s.MaxLevelsToRender = MaxLevelsToRender;
			s.MaxCachedLevels = MaxCachedLevels;
			s.MergeNearbyLevels = MergeNearbyLevels;
			s.MergeDistanceTicks = MergeDistanceTicks;
			s.DecayHalfLifeMinutes = IntradayOnly ? DecayHalfLifeMinutes : Math.Max(60, HistoricalDecayDays * 1440.0);
			s.IgnoreCanceledTrades = IgnoreCanceledTrades;
			s.WeightPremium = WeightPremium;
			s.WeightSize = WeightSize;
			s.WeightPrintCount = WeightPrintCount;
			s.WeightOffLitVolume = WeightOffLitVolume;
			s.WeightOffLitRatio = WeightOffLitRatio;
			s.WeightRecency = WeightRecency;
			s.WeightProximity = WeightProximity;
			s.WeightAbsorption = WeightAbsorption;
			s.StalePenalty = StalePenalty;
			s.MinScoreToRender = MinScoreToRender;
			s.HighConfidenceScoreThreshold = HighConfidenceScoreThreshold;
			s.ProximityBandTicks = 8;
			s.MarkerLookbackMinutes = MarkerLookbackMinutes;
			ctx.Settings = s;
			return ctx;
		}

		private DateTime ComputeLookbackCutoffUtc()
		{
			if (IntradayOnly)
			{
				if (easternTz != null)
				{
					DateTime etNow = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, easternTz);
					return TimeZoneInfo.ConvertTimeToUtc(etNow.Date, easternTz);
				}
				return DateTime.UtcNow.Date;
			}
			int days = Math.Max(1, LookbackTradingDays);
			DateTime d = DateTime.UtcNow.Date;
			int walked = 0;
			while (walked < days)
			{
				d = d.AddDays(-1);
				if (d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday)
					walked++;
			}
			return d;
		}

		private void RequestChartRefresh()
		{
			if ((DateTime.UtcNow - lastRefreshUtc).TotalMilliseconds < Math.Max(100, RenderThrottleMs))
				return;
			lastRefreshUtc = DateTime.UtcNow;
			ChartControl cc = ChartControl;
			if (cc == null)
				return;
			try
			{
				cc.Dispatcher.InvokeAsync((Action)delegate
				{
					try { ForceRefresh(); } catch { }
				});
			}
			catch { }
		}

		#endregion

		#region Fixture mode (offline integration testing)

		private async Task LoadFixturesAsync(CancellationToken ct)
		{
			try
			{
				string dir = string.IsNullOrWhiteSpace(FixtureDirectory)
					? System.IO.Path.Combine(Core.Globals.UserDataDir, "UWFixtures")
					: FixtureDirectory;

				string dpPath = System.IO.Path.Combine(dir, "darkpool.json");
				string volPath = System.IO.Path.Combine(dir, "volume_levels.json");

				if (System.IO.File.Exists(dpPath))
				{
					string json = System.IO.File.ReadAllText(dpPath);
					List<UwDarkPoolTrade> list = UwApiClient.ParseDarkPoolTrades(json, resolvedTicker, diagnostics);
					var filtered = list.Where(PassesLocalFilters).ToList();
					aggregator.Ingest(filtered);
					diagnostics.SetStatus("Fixture mode — " + filtered.Count + " prints loaded");
				}
				else
					diagnostics.SetStatus("Fixture mode — missing " + dpPath);

				if (System.IO.File.Exists(volPath))
				{
					string json = System.IO.File.ReadAllText(volPath);
					aggregator.SetVolumeLevels(UwApiClient.ParseVolumePriceLevels(json, diagnostics));
				}
				await Task.Delay(100, ct).ConfigureAwait(false);
			}
			catch (OperationCanceledException) { }
			catch (Exception ex)
			{
				diagnostics.SetError("Fixture load: " + ex.Message);
			}
		}

		#endregion

		#region Depth Radar V6

		private void TryReadRadarJson()
		{
			radarLastCheckUtc = DateTime.UtcNow;

			if (string.IsNullOrWhiteSpace(DepthRadarJsonPath))
			{
				radarWalls = null;
				radarGeneratedUtc = DateTime.MinValue;
				radarLastFileWriteUtc = DateTime.MinValue;
				radarSourceQuality = "";
				radarStatus = "missing";
				return;
			}

			if (!System.IO.File.Exists(DepthRadarJsonPath))
			{
				radarWalls = null;
				radarGeneratedUtc = DateTime.MinValue;
				radarLastFileWriteUtc = DateTime.MinValue;
				radarSourceQuality = "";
				radarStatus = "missing";
				return;
			}

			try
			{
				DateTime lastWriteUtc = System.IO.File.GetLastWriteTimeUtc(DepthRadarJsonPath);
				if (lastWriteUtc == radarLastFileWriteUtc)
				{
					if (string.IsNullOrEmpty(radarStatus) || radarStatus == "off")
						radarStatus = "ok";
					return;
				}

				string json = System.IO.File.ReadAllText(DepthRadarJsonPath);
				Dictionary<string, object> root = JsonLite.AsObj(JsonLite.Parse(json));
				if (root == null)
				{
					radarStatus = "error: invalid root";
					return;
				}

				object wallsObj;
				List<object> wallsArr = null;
				if (root.TryGetValue("walls", out wallsObj))
					wallsArr = JsonLite.AsArr(wallsObj);

				var newWalls = new List<RadarWall>();
				if (wallsArr != null)
				{
					for (int i = 0; i < wallsArr.Count; i++)
					{
						Dictionary<string, object> wallObj = JsonLite.AsObj(wallsArr[i]);
						if (wallObj == null)
							continue;

						decimal? priceDec = JsonLite.GetDecimal(wallObj, "price");
						if (!priceDec.HasValue)
							continue;

						double quality = 0.0;
						decimal? qualityDec = JsonLite.GetDecimal(wallObj, "quality");
						if (qualityDec.HasValue)
							quality = (double)qualityDec.Value;
						if (quality < RadarMinQuality)
							continue;

						string classification = JsonLite.GetString(wallObj, "classification") ?? "";
						string intent = JsonLite.GetString(wallObj, "intent") ?? "";
						if (string.Equals(classification, "SPOOF", StringComparison.OrdinalIgnoreCase))
							continue;
						if (string.Equals(intent, "SPOOF_LIKE", StringComparison.OrdinalIgnoreCase))
							continue;

						long size = 0;
						decimal? sizeDec = JsonLite.GetDecimal(wallObj, "size");
						if (sizeDec.HasValue)
						{
							try { size = (long)Math.Round(sizeDec.Value); }
							catch (OverflowException) { size = 0; }
						}

						double spoof = 0.0;
						decimal? spoofDec = JsonLite.GetDecimal(wallObj, "spoof");
						if (spoofDec.HasValue)
							spoof = (double)spoofDec.Value;

						var wall = new RadarWall();
						wall.Price = (double)priceDec.Value;
						wall.Side = JsonLite.GetString(wallObj, "side") ?? "";
						wall.Size = size;
						wall.Intent = intent;
						wall.State = JsonLite.GetString(wallObj, "state") ?? "";
						wall.Classification = classification;
						wall.Quality = quality;
						wall.Spoof = spoof;
						newWalls.Add(wall);
					}
				}

				DateTime? generated = JsonLite.GetUtcTime(root, "generated_at_utc");
				radarWalls = newWalls;
				radarGeneratedUtc = generated.HasValue ? generated.Value : lastWriteUtc;
				radarLastFileWriteUtc = lastWriteUtc;
				radarSourceQuality = JsonLite.GetString(root, "source_quality") ?? "";
				radarStatus = "ok";
			}
			catch (Exception ex)
			{
				radarStatus = "error: " + ShortRadarMessage(ex.Message);
			}
		}

		private RadarWall FindRadarConfluence(double price)
		{
			List<RadarWall> walls = radarWalls;
			if (walls == null || walls.Count == 0)
				return null;

			double maxDistance = RadarConfluenceTicks * TickSize;
			for (int i = 0; i < walls.Count; i++)
			{
				RadarWall wall = walls[i];
				if (Math.Abs(wall.Price - price) <= maxDistance)
					return wall;
			}
			return null;
		}

		private bool IsRadarStale()
		{
			if (radarGeneratedUtc == DateTime.MinValue)
				return true;
			return (DateTime.UtcNow - radarGeneratedUtc).TotalSeconds > RadarStaleSec;
		}

		private string ShortRadarMessage(string msg)
		{
			if (string.IsNullOrEmpty(msg))
				return "unknown";
			msg = msg.Replace('\r', ' ').Replace('\n', ' ').Trim();
			if (msg.Length > 64)
				msg = msg.Substring(0, 64);
			return msg;
		}

		#endregion

		#region OnBarUpdate (light-weight: sampling + alerts only)

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0)
				return;

			lastPrice = Close[0];
			if (atrInd != null && CurrentBar >= 14)
				atrValue = atrInd[0];

			if (IsFirstTickOfBar && CurrentBar >= 1)
			{
				var sample = new BarSample();
				sample.TimeUtc = Time[1].ToUniversalTime();
				sample.High = High[1];
				sample.Low = Low[1];
				sample.Close = Close[1];
				lock (barLock)
				{
					barWindow.Add(sample);
					if (barWindow.Count > 500)
						barWindow.RemoveRange(0, barWindow.Count - 500);
				}
			}

			if (State != State.Realtime)
				return;

			if (EnableDepthRadar)
			{
				if ((DateTime.UtcNow - radarLastCheckUtc).TotalSeconds >= 2)
					TryReadRadarJson();
			}
			else
				radarStatus = "off";

			if (EnableAlerts)
			{
				try { EvaluateAlerts(); }
				catch (Exception ex) { LogMsg(UwLogLevel.Warning, "Alert evaluation: " + ex.Message); }
			}

			if (!UseSharpDxRendering && (DateTime.UtcNow - lastFallbackDrawUtc).TotalSeconds >= 5)
			{
				lastFallbackDrawUtc = DateTime.UtcNow;
				try { UpdateFallbackDrawObjects(); }
				catch (Exception ex) { LogMsg(UwLogLevel.Warning, "Fallback draw: " + ex.Message); }
			}
		}

		#endregion

		#region Alerts

		private void EvaluateAlerts()
		{
			LiquiditySnapshot snap = latestSnapshot;
			if (snap == null || snap.Levels.Count == 0)
				return;

			double close = Close[0];
			double prevClose = CurrentBar >= 1 ? Close[1] : close;
			double tick = Math.Max(TickSize, 0.0001);
			double mapScale = GetMapScale(snap); // project UW prices into chart space for comparisons
			DateTime now = DateTime.UtcNow;

			foreach (LiquidityLevel lvl in snap.Levels)
			{
				if ((double)lvl.Score < HighConfidenceScoreThreshold)
					continue;
				if (lvl.Type == LiquidityLevelType.NeutralCluster || lvl.Type == LiquidityLevelType.Exhaustion)
					continue;

				string key = lvl.Price.ToString(priceFormat, CultureInfo.InvariantCulture);
				LevelAlertState st;
				if (!alertStates.TryGetValue(key, out st))
				{
					st = new LevelAlertState();
					alertStates[key] = st;
				}

				double p = (double)lvl.Price * mapScale;
				double distTicks = Math.Abs(close - p) / tick;

				if (AlertOnNewHighConfidenceLevel && !st.NewLevelAlerted
					&& lvl.FirstSeenUtc != DateTime.MinValue
					&& (now - lvl.FirstSeenUtc).TotalMinutes <= 10)
				{
					st.NewLevelAlerted = true;
					FireAlert("new UW level:", lvl, st, key);
				}

				if (AlertOnPriceApproachLevel)
				{
					if (distTicks <= AlertDistanceTicks && !st.InZone)
					{
						st.InZone = true;
						FireAlert("approaching UW inferred", lvl, st, key);
					}
					else if (distTicks > AlertDistanceTicks * 2)
						st.InZone = false;
				}

				if (AlertOnBreak && !st.Broken)
				{
					if (prevClose >= p && close < p - tick)
					{
						st.Broken = true;
						st.BrokenAtUtc = now;
						FireAlert("broke below UW liquidity", lvl, st, key);
					}
					else if (prevClose <= p && close > p + tick)
					{
						st.Broken = true;
						st.BrokenAtUtc = now;
						FireAlert("broke above UW liquidity", lvl, st, key);
					}
				}

				if (AlertOnRetest && st.Broken && !st.Retested
					&& (now - st.BrokenAtUtc).TotalSeconds > 60
					&& distTicks <= AlertDistanceTicks)
				{
					st.Retested = true;
					FireAlert("retesting prior UW liquidity", lvl, st, key);
				}
			}

			// Large individual print
			if (AlertOnLargePrint && snap.LargestRecentPrint != null)
			{
				UwDarkPoolTrade lp = snap.LargestRecentPrint;
				string lpKey = lp.DedupKey();
				if (lpKey != lastLargePrintKey && lp.Premium >= AlertLargePrintMinPremium)
				{
					lastLargePrintKey = lpKey;
					string msg = resolvedTicker + " large off-lit print: "
						+ Util.FormatCompact((double)lp.Premium, true) + " @ "
						+ lp.Price.ToString(priceFormat, CultureInfo.InvariantCulture);
					RaiseNtAlert("UWDP_LP_" + lpKey, msg);
				}
			}

			if (alertStates.Count > 600)
				alertStates.Clear(); // bounded memory; states rebuild naturally
		}

		private void FireAlert(string evt, LiquidityLevel lvl, LevelAlertState st, string key)
		{
			DateTime now = DateTime.UtcNow;
			if ((now - st.LastAlertUtc).TotalSeconds < Math.Max(5, AlertCooldownSeconds))
				return;
			st.LastAlertUtc = now;

			string typeText = LiquidityAggregator.TypeText(lvl.Type,
				(double)lvl.Price * GetMapScale(latestSnapshot) <= lastPrice);
			string msg = (AlertMessageTemplate ?? "")
				.Replace("{ticker}", resolvedTicker)
				.Replace("{event}", evt)
				.Replace("{type}", typeText)
				.Replace("{price}", lvl.Price.ToString(priceFormat, CultureInfo.InvariantCulture))
				.Replace("{score}", ((int)lvl.Score).ToString(CultureInfo.InvariantCulture))
				.Replace("{offlit}", Util.FormatCompact(lvl.OffLitVolume, false))
				.Replace("{premium}", Util.FormatCompact((double)lvl.TotalDarkPoolPremium, true));
			if (string.IsNullOrWhiteSpace(msg))
				msg = resolvedTicker + " " + evt + " " + typeText + " " + lvl.Price.ToString(priceFormat, CultureInfo.InvariantCulture);

			RaiseNtAlert("UWDP_" + evt.GetHashCode().ToString("X", CultureInfo.InvariantCulture) + "_" + key, msg);
		}

		private void RaiseNtAlert(string id, string message)
		{
			try
			{
				string sound = string.IsNullOrWhiteSpace(AlertSound)
					? ""
					: System.IO.Path.Combine(Core.Globals.InstallDir, "sounds", AlertSound);
				Alert(id, Priority.Medium, message, sound, Math.Max(5, AlertCooldownSeconds),
					Brushes.DimGray, Brushes.White);
				LogMsg(UwLogLevel.Info, "ALERT: " + message);
			}
			catch (Exception ex)
			{
				LogMsg(UwLogLevel.Warning, "Alert failed: " + ex.Message);
			}
		}

		#endregion

		#region Fallback rendering (standard draw objects, UseSharpDxRendering = false)

		private void UpdateFallbackDrawObjects()
		{
			LiquiditySnapshot snap = latestSnapshot;
			if (snap == null)
				return;

			var newTags = new HashSet<string>();
			UwTheme theme = ResolveTheme();
			double mapScale = GetMapScale(snap);
			int i = 0;
			foreach (LiquidityLevel lvl in snap.Levels.Take(10))
			{
				string tag = "UWDP_FB_" + i;
				newTags.Add(tag);
				newTags.Add(tag + "_L");
				double half = (double)lvl.ClusterWidth / 2.0 * mapScale;
				double pm = (double)lvl.Price * mapScale;
				Brush area = MediaBrushFromColor4(ColorForLevel(lvl, snap, theme));
				int opacity = (int)(Lerp((float)ZoneOpacityMin, (float)ZoneOpacityMax, (float)((double)lvl.Score / 100.0)) * 100);
				Draw.RegionHighlightY(this, tag, false, pm - half, pm + half,
					Brushes.Transparent, area, Math.Max(2, Math.Min(40, opacity)));
				Draw.HorizontalLine(this, tag + "_L", pm, area,
					lvl.IsDecayed && FadeStaleLevels ? DashStyleHelper.Dash : DashStyleHelper.Solid,
					(int)Math.Max(1, Math.Round(Lerp((float)LineWidthMin, (float)LineWidthMax, (float)lvl.PremiumWeight))));
				i++;
			}

			foreach (string old in fallbackTags)
				if (!newTags.Contains(old))
					RemoveDrawObject(old);
			fallbackTags.Clear();
			foreach (string t in newTags)
				fallbackTags.Add(t);
		}

		#endregion

		#region SharpDX rendering

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (RenderTarget == null || chartControl == null || chartScale == null || ChartPanel == null)
				return;
			if (IsInHitTest)
				return;

			LiquiditySnapshot snap = latestSnapshot;
			UwTheme theme = ResolveTheme();
			double mapScale = GetMapScale(snap);
			float panelX = ChartPanel.X;
			float panelY = ChartPanel.Y;
			float panelW = ChartPanel.W;
			float panelH = ChartPanel.H;

			if (UseSharpDxRendering && snap != null && snap.Levels.Count > 0)
			{
				radarConfluenceCount = 0;
				double minP = chartScale.MinValue;
				double maxP = chartScale.MaxValue;
				usedLabelYs.Clear();
				usedTagYs.Clear();

				// ---- Collect visible levels with pre-computed render data ----
				renderLevels.Clear();
				foreach (LiquidityLevel lvl in snap.Levels)
				{
					double hp = (double)lvl.ClusterWidth / 2.0 * mapScale;
					double pm = (double)lvl.Price * mapScale;
					if (pm + hp < minP || pm - hp > maxP)
						continue;

					float yt = chartScale.GetYByValue(pm + hp);
					float yb = chartScale.GetYByValue(pm - hp);
					if (yb - yt < 2f)
					{
						float mid = (yt + yb) / 2f;
						yt = mid - 1f;
						yb = mid + 1f;
					}

					Color4 baseColor = ColorForLevel(lvl, snap, theme);
					baseColor = RecolorNeutralBySide(baseColor, lvl.Type, pm, theme);
					bool st = lvl.IsDecayed && FadeStaleLevels;

					float xs = panelX;
					if (!ExtendLevelsLeft && lvl.FirstSeenUtc != DateTime.MinValue)
						xs = Math.Max(panelX, chartControl.GetXByTime(lvl.FirstSeenUtc.ToLocalTime()));
					float xe = panelX + panelW;
					if (!ExtendLevelsRight && lvl.LastSeenUtc != DateTime.MinValue)
						xe = Math.Min(panelX + panelW, chartControl.GetXByTime(lvl.LastSeenUtc.ToLocalTime()));
					if (xe - xs < 8f)
						xe = Math.Min(panelX + panelW, xs + 8f);

					RadarWall wall = null;
					if (EnableDepthRadar && HighlightConfluence && !IsRadarStale())
						wall = FindRadarConfluence(pm);

					RenderLevel rl;
					rl.Level = lvl;
					rl.MappedPrice = pm;
					rl.YTop = yt;
					rl.YBot = yb;
					rl.YMid = (yt + yb) / 2f;
					rl.XStart = xs;
					rl.XEnd = xe;
					rl.BaseColor = baseColor;
					rl.Conf = (float)Math.Max(0.0, Math.Min(1.0, (double)lvl.Score / 100.0));
					rl.Stale = st;
					rl.Tier = 0;
					rl.Confluence = wall;
					renderLevels.Add(rl);
				}

				// ---- Sort by score descending, assign tiers ----
				renderLevels.Sort(delegate(RenderLevel a, RenderLevel b)
				{
					return ((double)b.Level.Score).CompareTo((double)a.Level.Score);
				});
				for (int ti = 0; ti < renderLevels.Count; ti++)
				{
					RenderLevel tmp = renderLevels[ti];
					if (ti < 3)
						tmp.Tier = 1;
					else if ((double)tmp.Level.Score >= 50.0)
						tmp.Tier = 2;
					else
						tmp.Tier = 3;
					renderLevels[ti] = tmp;
				}

				// ---- Pixel-space declutter: skip levels within 8px of higher-score sibling ----
				// (list is already sorted by score descending, so higher-score levels win)
				usedLabelYs.Clear(); // reuse for declutter tracking
				for (int ri = 0; ri < renderLevels.Count; ri++)
				{
					RenderLevel rl = renderLevels[ri];
					bool tooClose = false;
					for (int ai = 0; ai < usedLabelYs.Count; ai++)
					{
						if (Math.Abs(usedLabelYs[ai] - rl.YMid) < 8f)
						{
							tooClose = true;
							break;
						}
					}
					if (tooClose)
						continue;
					usedLabelYs.Add(rl.YMid);

					LiquidityLevel lvl = rl.Level;
					Color4 baseColor = rl.BaseColor;
					bool stale = rl.Stale;
					float yMid = rl.YMid;
					float yTop = rl.YTop;
					float yBot = rl.YBot;
					float xStart = rl.XStart;
					float xEnd = rl.XEnd;
					bool hasConfluence = rl.Confluence != null;

					if (hasConfluence)
						radarConfluenceCount++;

					// ==== TIER 1 (top 3): zone + line + pill label + right-edge tag ====
					if (rl.Tier == 1)
					{
						// Zone: anchored from xStart, capped opacity, crisp edge lines
						if (ShowZones)
						{
							float zoneAlpha = Lerp((float)ZoneOpacityMin, (float)ZoneOpacityMax, rl.Conf);
							if (stale)
								zoneAlpha *= 0.45f;
							RenderTarget.FillRectangle(
								new RectangleF(xStart, yTop, xEnd - xStart, yBot - yTop),
								GetDxBrush(new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, zoneAlpha)));
							// 1px brighter edge at zone boundaries
							D2D.SolidColorBrush edgeBrush = GetDxBrush(
								new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, 0.35f));
							RenderTarget.DrawLine(new Vector2(xStart, yTop), new Vector2(xEnd, yTop), edgeBrush, 1f);
							RenderTarget.DrawLine(new Vector2(xStart, yBot), new Vector2(xEnd, yBot), edgeBrush, 1f);
						}

						// Line: 2-3px, full opacity
						if (ShowLines)
						{
							float lw = Lerp(2f, 3f, (float)lvl.PremiumWeight);
							float lineAlpha = stale ? 0.55f : 1f;
							if (lvl.IsFresh && !stale)
								lineAlpha = 1f;
							D2D.SolidColorBrush lineBrush = GetDxBrush(
								new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, lineAlpha));
							D2D.StrokeStyle ss = stale ? GetDashStroke() : null;
							if (ss != null)
								RenderTarget.DrawLine(new Vector2(xStart, yMid), new Vector2(xEnd, yMid), lineBrush, lw, ss);
							else
								RenderTarget.DrawLine(new Vector2(xStart, yMid), new Vector2(xEnd, yMid), lineBrush, lw);

							// Fresh edge glow
							if (lvl.IsFresh && !stale)
							{
								D2D.SolidColorBrush glow = GetDxBrush(
									new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, lineAlpha * 0.30f));
								RenderTarget.DrawLine(new Vector2(xStart, yMid - lw - 1f),
									new Vector2(xEnd, yMid - lw - 1f), glow, 1f);
								RenderTarget.DrawLine(new Vector2(xStart, yMid + lw + 1f),
									new Vector2(xEnd, yMid + lw + 1f), glow, 1f);
							}
						}

						// Confluence: 3px white-gold vertical accent bar at xStart
						if (hasConfluence)
						{
							float accentH = Math.Max(12f, yBot - yTop);
							float accentY = yMid - accentH / 2f;
							RenderTarget.FillRectangle(
								new RectangleF(xStart, accentY, 3f, accentH),
								GetDxBrush(new Color4(1f, 0.843f, 0.51f, 0.92f)));
						}

						// Pill label on left side (max 3 on screen)
						if (ShowLabels && LabelMode != LabelDisplayMode.None)
							DrawPillLabel(lvl, yMid, panelX, panelY, baseColor, theme,
								rl.MappedPrice, hasConfluence);

						// Right-edge price tag (shifted left to avoid fib tool collision)
						DrawRightEdgeTag(rl.MappedPrice, yMid, panelX, panelW, baseColor);
					}
					// ==== TIER 2 (score >= 50): line only, optional tag ====
					else if (rl.Tier == 2)
					{
						if (ShowLines)
						{
							D2D.SolidColorBrush lineBrush = GetDxBrush(
								new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, 0.55f));
							D2D.StrokeStyle ss = stale ? GetDashStroke() : null;
							if (ss != null)
								RenderTarget.DrawLine(new Vector2(xStart, yMid), new Vector2(xEnd, yMid), lineBrush, 1f, ss);
							else
								RenderTarget.DrawLine(new Vector2(xStart, yMid), new Vector2(xEnd, yMid), lineBrush, 1f);
						}

						// Confluence accent for Tier 2
						if (hasConfluence)
						{
							float accentH = Math.Max(12f, yBot - yTop);
							float accentY = yMid - accentH / 2f;
							RenderTarget.FillRectangle(
								new RectangleF(xStart, accentY, 3f, accentH),
								GetDxBrush(new Color4(1f, 0.843f, 0.51f, 0.65f)));
						}

						// Right-edge tag only for high-confidence Tier 2
						if ((double)lvl.Score >= HighConfidenceScoreThreshold)
							DrawRightEdgeTag(rl.MappedPrice, yMid, panelX, panelW, baseColor);
					}
					// ==== TIER 3 (rest): 6px tick on right edge rail only ====
					else
					{
						float railX = panelX + panelW - 8f;
						D2D.SolidColorBrush tickBrush = GetDxBrush(
							new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, 0.45f));
						RenderTarget.DrawLine(
							new Vector2(railX, yMid), new Vector2(railX + 6f, yMid),
							tickBrush, 1f);
					}
				}

				if (ShowPrintMarkers)
					DrawPrintMarkers(snap, chartControl, chartScale, theme, panelX, panelY, panelW, panelH, mapScale);
			}

			if (ShowDashboard)
				DrawDashboard(snap, theme, panelX, panelY, panelW, panelH);

			if (ShowConfidenceLegend)
				DrawLegend(theme, panelX, panelY, panelW, panelH);
		}

		private void DrawLevelLabel(LiquidityLevel lvl, float yMid, float panelX, float panelW, UwTheme theme, bool stale, double uwRefPrice)
		{
			if (labelFormat == null)
				return;

			// Collision avoidance: skip labels stacked within 13px of an already-drawn one
			for (int i = 0; i < usedLabelYs.Count; i++)
				if (Math.Abs(usedLabelYs[i] - yMid) < 13f)
					return;
			usedLabelYs.Add(yMid);

			string text;
			if (LabelMode == LabelDisplayMode.Full)
			{
				text = lvl.Label
					+ "  ·  Σ" + Util.FormatCompact((double)lvl.TotalDarkPoolPremium, true)
					+ " · off-lit " + Util.FormatCompact(lvl.OffLitVolume, false)
					+ " (" + ((double)lvl.OffLitShare * 100).ToString("0", CultureInfo.InvariantCulture) + "%)"
					+ " · " + lvl.PrintCount + "p"
					+ " · " + (lvl.LastSeenUtc == DateTime.MinValue ? "n/a" : Util.AgeText(DateTime.UtcNow - lvl.LastSeenUtc));
				if (ShowTooltips)
					text += "  ·  " + LiquidityAggregator.TypeText(lvl.Type, (double)lvl.Price <= uwRefPrice);
			}
			else
				text = lvl.Label;

			float maxW = Math.Min(560f, panelW * 0.6f);
			using (var layout = new DW.TextLayout(Core.Globals.DirectWriteFactory, text, labelFormat, maxW, 16f))
			{
				float tw = layout.Metrics.Width;
				float x = panelX + panelW - tw - 72f;
				if (x < panelX + 4f)
					x = panelX + 4f;
				float alpha = stale ? 0.45f : 0.9f;
				Color4 tc = theme.Text;
				RenderTarget.DrawTextLayout(new Vector2(x, yMid - 14f), layout,
					GetDxBrush(new Color4(tc.Red, tc.Green, tc.Blue, alpha)));
			}
		}

		private void DrawRightEdgeTag(double displayPrice, float yMid, float panelX, float panelW, Color4 baseColor)
		{
			for (int i = 0; i < usedTagYs.Count; i++)
				if (Math.Abs(usedTagYs[i] - yMid) < 15f)
					return;
			usedTagYs.Add(yMid);

			float tagW = 62f, tagH = 15f;
			float x = panelX + panelW - tagW - 72f;
			var rect = new RectangleF(x, yMid - tagH / 2f, tagW, tagH);
			RenderTarget.FillRectangle(rect, GetDxBrush(new Color4(baseColor.Red, baseColor.Green, baseColor.Blue, 0.82f)));
			if (smallFormat != null)
				RenderTarget.DrawText(
					displayPrice.ToString(priceFormat, CultureInfo.InvariantCulture),
					smallFormat,
					new RectangleF(x + 3f, yMid - tagH / 2f + 1f, tagW - 4f, tagH),
					GetDxBrush(new Color4(1f, 1f, 1f, 0.95f)));
		}

		private void DrawPillLabel(LiquidityLevel lvl, float yMid, float panelX, float panelY,
			Color4 levelColor, UwTheme theme, double displayPrice, bool hasConfluence)
		{
			if (smallFormat == null)
				return;

			string typeLetter;
			switch (lvl.Type)
			{
				case LiquidityLevelType.Support: typeLetter = "S"; break;
				case LiquidityLevelType.Resistance: typeLetter = "R"; break;
				case LiquidityLevelType.Magnet: typeLetter = "M"; break;
				case LiquidityLevelType.NeutralCluster: typeLetter = "N"; break;
				case LiquidityLevelType.Absorption: typeLetter = "A"; break;
				case LiquidityLevelType.Exhaustion: typeLetter = "E"; break;
				default: typeLetter = "?"; break;
			}

			string priceText = displayPrice.ToString(priceFormat, CultureInfo.InvariantCulture);
			string text = priceText + " \u00B7 " + typeLetter
				+ ((int)lvl.Score).ToString(CultureInfo.InvariantCulture);
			if (hasConfluence)
				text += " \u2691";

			float pillH = 14f;
			float pillX = panelX + 6f;
			float pillY = yMid - pillH - 8f;
			if (pillY < panelY + 16f)
				pillY = yMid + 8f;

			using (DW.TextLayout layout = new DW.TextLayout(
				Core.Globals.DirectWriteFactory, text, smallFormat, 220f, pillH))
			{
				float tw = layout.Metrics.Width;
				float pillW = tw + 10f;
				RectangleF pillRect = new RectangleF(pillX, pillY, pillW, pillH);

				Color4 bg = theme.PanelBg;
				RenderTarget.FillRectangle(pillRect,
					GetDxBrush(new Color4(bg.Red, bg.Green, bg.Blue, 0.85f)));
				RenderTarget.DrawRectangle(pillRect,
					GetDxBrush(new Color4(levelColor.Red, levelColor.Green, levelColor.Blue, 0.9f)), 1f);

				Color4 tc = theme.Text;
				RenderTarget.DrawTextLayout(new Vector2(pillX + 5f, pillY),
					layout, GetDxBrush(new Color4(tc.Red, tc.Green, tc.Blue, 0.95f)));
			}
		}

		private void DrawPrintMarkers(LiquiditySnapshot snap, ChartControl chartControl, ChartScale chartScale,
			UwTheme theme, float panelX, float panelY, float panelW, float panelH, double mapScale)
		{
			if (snap.RecentPrints.Count == 0)
				return;
			decimal maxPrem = 1;
			foreach (UwDarkPoolTrade t in snap.RecentPrints)
				if (t.Premium > maxPrem)
					maxPrem = t.Premium;

			foreach (UwDarkPoolTrade t in snap.RecentPrints)
			{
				float x = chartControl.GetXByTime(t.ExecutedAtUtc.ToLocalTime());
				if (x < panelX || x > panelX + panelW)
					continue;
				float y = chartScale.GetYByValue((double)t.Price * mapScale);
				if (y < panelY || y > panelY + panelH)
					continue;
				float norm = (float)Math.Sqrt((double)(t.Premium / maxPrem));
				float r = 2.5f + 9f * norm;
				var ell = new D2D.Ellipse(new Vector2(x, y), r, r);
				Color4 mc = theme.Marker;
				RenderTarget.FillEllipse(ell, GetDxBrush(new Color4(mc.Red, mc.Green, mc.Blue, 0.20f)));
				RenderTarget.DrawEllipse(ell, GetDxBrush(new Color4(mc.Red, mc.Green, mc.Blue, 0.55f)), 1f);
			}
		}

		private void DrawDashboard(LiquiditySnapshot snap, UwTheme theme, float panelX, float panelY, float panelW, float panelH)
		{
			if (smallFormat == null || titleFormat == null)
				return;

			var lines = new List<string>();
			lines.Add("DEEP6 DarkPool Levels — " + (string.IsNullOrEmpty(resolvedTicker) ? "?" : resolvedTicker));
			string status = diagnostics != null ? diagnostics.Status : "…";
			string ws = diagnostics != null ? diagnostics.WsStatus : "Off";
			lines.Add("Status: " + status);
			if (EnableWebSocketStreaming)
				lines.Add("WS: " + ws + (diagnostics != null && diagnostics.LastWsMessageUtc > DateTime.MinValue
					? " · last msg " + Util.AgeText(DateTime.UtcNow - diagnostics.LastWsMessageUtc)
					: ""));
			if (snap != null && snap.GeneratedUtc > DateTime.MinValue)
			{
				int fresh = 0;
				foreach (LiquidityLevel l in snap.Levels)
					if (l.IsFresh) fresh++;
				lines.Add("Levels: " + snap.Levels.Count + " active · " + fresh + " fresh · "
					+ snap.TradeCountCached + " prints cached");
				if (EnableDepthRadar)
				{
					List<RadarWall> walls = radarWalls;
					int wallCount = walls != null ? walls.Count : 0;
					bool staleRadar = IsRadarStale();
					lines.Add("Radar: " + (staleRadar ? "STALE " : "") + radarStatus + " · " + wallCount + " walls · "
						+ radarConfluenceCount + " confluence · " + radarSourceQuality);
				}
				if (needsMapping && snap.CurrentPrice > 0 && lastPrice > 0)
					lines.Add("Mapping: " + resolvedTicker + " → " + chartSymbol + "  ×"
						+ (lastPrice / snap.CurrentPrice).ToString("0.###", CultureInfo.InvariantCulture));
				lines.Add("Updated: " + Util.AgeText(DateTime.UtcNow - snap.GeneratedUtc));
				if (snap.StrongestSupport != null)
					lines.Add("Strongest support: " + snap.StrongestSupport.Price.ToString(priceFormat, CultureInfo.InvariantCulture)
						+ " (" + (int)snap.StrongestSupport.Score + ")");
				if (snap.StrongestResistance != null)
					lines.Add("Strongest resistance: " + snap.StrongestResistance.Price.ToString(priceFormat, CultureInfo.InvariantCulture)
						+ " (" + (int)snap.StrongestResistance.Score + ")");
				if (snap.LargestRecentPrint != null)
					lines.Add("Largest 30m print: " + Util.FormatCompact((double)snap.LargestRecentPrint.Premium, true)
						+ " @ " + snap.LargestRecentPrint.Price.ToString(priceFormat, CultureInfo.InvariantCulture));
			}
			if (diagnostics != null && diagnostics.IsRateLimited)
				lines.Add("API: rate limited — backing off");
			if (!string.IsNullOrEmpty(futuresWarning))
				lines.Add("⚠ " + futuresWarning);
			if (EnableDiagnostics && diagnostics != null)
			{
				lines.Add("REST ok: " + (diagnostics.LastRestSuccessUtc > DateTime.MinValue
						? Util.AgeText(DateTime.UtcNow - diagnostics.LastRestSuccessUtc) : "never")
					+ " · rc " + diagnostics.ReconnectCount
					+ " · perr " + diagnostics.ParseErrorCount
					+ " · in " + diagnostics.TradesIngested);
				if (!string.IsNullOrEmpty(diagnostics.LastError))
					lines.Add("Last error: " + Util.Truncate(diagnostics.LastError, 46));
			}

			float lineH = 15f, pad = 8f, width = 340f;
			float height = pad * 2f + lineH * lines.Count + 4f;
			float x, y;
			switch (DashboardPosition)
			{
				case DashboardCorner.TopRight: x = panelX + panelW - width - 8f; y = panelY + 8f; break;
				case DashboardCorner.BottomLeft: x = panelX + 8f; y = panelY + panelH - height - 8f; break;
				case DashboardCorner.BottomRight: x = panelX + panelW - width - 8f; y = panelY + panelH - height - 8f; break;
				default: x = panelX + 8f; y = panelY + 8f; break;
			}

			var bg = new RectangleF(x, y, width, height);
			RenderTarget.FillRectangle(bg, GetDxBrush(theme.PanelBg));
			RenderTarget.DrawRectangle(bg, GetDxBrush(theme.PanelBorder), 1f);

			float ty = y + pad;
			for (int i = 0; i < lines.Count; i++)
			{
				DW.TextFormat fmt = i == 0 ? titleFormat : smallFormat;
				RenderTarget.DrawText(lines[i], fmt,
					new RectangleF(x + pad, ty, width - pad * 2f, lineH + 2f),
					GetDxBrush(theme.Text));
				ty += lineH + (i == 0 ? 4f : 0f);
			}
		}

		private void DrawLegend(UwTheme theme, float panelX, float panelY, float panelW, float panelH)
		{
			if (smallFormat == null)
				return;
			float x = panelX + 8f;
			float y = panelY + panelH - 52f;
			if (ShowDashboard && (DashboardPosition == DashboardCorner.BottomLeft))
				x = panelX + 290f;

			// swatches
			DrawSwatch(x, y + 3f, theme.Support);
			RenderTarget.DrawText("inferred support", smallFormat, new RectangleF(x + 12f, y, 130f, 14f), GetDxBrush(theme.Text));
			DrawSwatch(x + 118f, y + 3f, theme.Resistance);
			RenderTarget.DrawText("inferred resistance", smallFormat, new RectangleF(x + 130f, y, 140f, 14f), GetDxBrush(theme.Text));
			DrawSwatch(x + 252f, y + 3f, theme.Magnet);
			RenderTarget.DrawText("magnet/neutral", smallFormat, new RectangleF(x + 264f, y, 120f, 14f), GetDxBrush(theme.Text));

			Color4 tc = theme.Text;
			D2D.SolidColorBrush dim = GetDxBrush(new Color4(tc.Red, tc.Green, tc.Blue, 0.65f));
			RenderTarget.DrawText("opacity = confidence · line width = dark-pool $ premium · dashed = stale",
				smallFormat, new RectangleF(x, y + 16f, 460f, 14f), dim);
			RenderTarget.DrawText("Dark Pool Prints / Off-Lit Volume — post-trade inference, not resting orders",
				smallFormat, new RectangleF(x, y + 31f, 480f, 14f), dim);
		}

		private void DrawSwatch(float x, float y, Color4 c)
		{
			RenderTarget.FillRectangle(new RectangleF(x, y, 8f, 8f),
				GetDxBrush(new Color4(c.Red, c.Green, c.Blue, 0.9f)));
		}

		#endregion

		#region DirectX resource management

		private D2D.SolidColorBrush GetDxBrush(Color4 color)
		{
			D2D.SolidColorBrush b;
			if (dxBrushCache.TryGetValue(color, out b) && b != null && !b.IsDisposed)
				return b;
			b = new D2D.SolidColorBrush(RenderTarget, color);
			dxBrushCache[color] = b;
			return b;
		}

		private D2D.StrokeStyle GetDashStroke()
		{
			if (dashStroke == null || dashStroke.IsDisposed)
			{
				var props = new D2D.StrokeStyleProperties();
				props.DashStyle = D2D.DashStyle.Dash;
				dashStroke = new D2D.StrokeStyle(Core.Globals.D2DFactory, props);
			}
			return dashStroke;
		}

		public override void OnRenderTargetChanged()
		{
			// Device-dependent resources must be rebuilt against the new RenderTarget.
			DisposeDeviceBrushes();
			base.OnRenderTargetChanged();
		}

		private void DisposeDeviceBrushes()
		{
			foreach (KeyValuePair<Color4, D2D.SolidColorBrush> kv in dxBrushCache)
			{
				try { if (kv.Value != null && !kv.Value.IsDisposed) kv.Value.Dispose(); }
				catch { }
			}
			dxBrushCache.Clear();
		}

		#endregion

		#region Theme

		private static Color4 C4(int r, int g, int b)
		{
			return new Color4(r / 255f, g / 255f, b / 255f, 1f);
		}

		private static Color4 C4A(int r, int g, int b, float a)
		{
			return new Color4(r / 255f, g / 255f, b / 255f, a);
		}

		private UwTheme ResolveTheme()
		{
			var t = new UwTheme();
			switch (ThemePreset)
			{
				case UwThemePreset.LightInstitutional:
					t.Support = C4(0, 121, 107);
					t.Resistance = C4(183, 60, 57);
					t.Magnet = C4(84, 99, 110);
					t.Exhaustion = C4(140, 140, 140);
					t.Text = C4(33, 37, 41);
					t.PanelBg = C4A(250, 250, 250, 0.88f);
					t.PanelBorder = C4A(120, 120, 120, 0.6f);
					t.Marker = C4(84, 110, 122);
					break;
				case UwThemePreset.BloombergLike:
					t.Support = C4(0, 168, 107);
					t.Resistance = C4(255, 84, 84);
					t.Magnet = C4(120, 120, 110);
					t.Exhaustion = C4(110, 110, 110);
					t.Text = C4(255, 178, 0);
					t.PanelBg = C4A(8, 8, 8, 0.90f);
					t.PanelBorder = C4A(255, 178, 0, 0.45f);
					t.Marker = C4(255, 178, 0);
					break;
				case UwThemePreset.Minimal:
					t.Support = C4(96, 125, 139);
					t.Resistance = C4(96, 125, 139);
					t.Magnet = C4(96, 125, 139);
					t.Exhaustion = C4(120, 120, 120);
					t.Text = C4(170, 178, 184);
					t.PanelBg = C4A(20, 22, 26, 0.85f);
					t.PanelBorder = C4A(96, 125, 139, 0.45f);
					t.Marker = C4(96, 125, 139);
					break;
				case UwThemePreset.ColorblindSafe:
					// Okabe–Ito palette
					t.Support = C4(0, 114, 178);
					t.Resistance = C4(230, 159, 0);
					t.Magnet = C4(110, 117, 124);
					t.Exhaustion = C4(130, 130, 130);
					t.Text = C4(225, 228, 232);
					t.PanelBg = C4A(16, 18, 22, 0.88f);
					t.PanelBorder = C4A(110, 117, 124, 0.55f);
					t.Marker = C4(86, 180, 233);
					break;
				case UwThemePreset.Custom:
					t.Support = ColorFromMediaBrush(CustomSupportBrush, C4(38, 166, 154));
					t.Resistance = ColorFromMediaBrush(CustomResistanceBrush, C4(239, 83, 80));
					t.Magnet = ColorFromMediaBrush(CustomMagnetBrush, C4(120, 144, 156));
					t.Exhaustion = C4(130, 130, 130);
					t.Text = ColorFromMediaBrush(CustomTextBrush, C4(222, 226, 230));
					t.PanelBg = C4A(16, 20, 26, 0.88f);
					t.PanelBorder = C4A(120, 144, 156, 0.55f);
					t.Marker = t.Magnet;
					break;
				default: // DarkInstitutional
					t.Support = C4(38, 166, 154);
					t.Resistance = C4(239, 83, 80);
					t.Magnet = C4(120, 144, 156);
					t.Exhaustion = C4(130, 130, 130);
					t.Text = C4(222, 226, 230);
					t.PanelBg = C4A(16, 20, 26, 0.88f);
					t.PanelBorder = C4A(120, 144, 156, 0.55f);
					t.Marker = C4(144, 164, 174);
					break;
			}
			return t;
		}

		private static Color4 ColorFromMediaBrush(Brush brush, Color4 fallback)
		{
			var scb = brush as SolidColorBrush;
			if (scb == null)
				return fallback;
			return new Color4(scb.Color.R / 255f, scb.Color.G / 255f, scb.Color.B / 255f, 1f);
		}

		private static Brush MediaBrushFromColor4(Color4 c)
		{
			var b = new SolidColorBrush(System.Windows.Media.Color.FromArgb(
				255, (byte)(c.Red * 255), (byte)(c.Green * 255), (byte)(c.Blue * 255)));
			b.Freeze();
			return b;
		}

		private Color4 ColorForLevel(LiquidityLevel lvl, LiquiditySnapshot snap, UwTheme theme)
		{
			switch (lvl.Type)
			{
				case LiquidityLevelType.Support: return theme.Support;
				case LiquidityLevelType.Resistance: return theme.Resistance;
				case LiquidityLevelType.Magnet: return theme.Magnet;
				case LiquidityLevelType.Exhaustion: return theme.Exhaustion;
				case LiquidityLevelType.Absorption:
					return (double)lvl.Price <= snap.CurrentPrice ? theme.Support : theme.Resistance;
				default: return theme.Magnet;
			}
		}

		/// <summary>
		/// For Magnet/NeutralCluster levels, recolors by side relative to current price
		/// so they read as tinted support/resistance instead of flat gray. Returns original
		/// color unchanged for all other level types.
		/// </summary>
		private Color4 RecolorNeutralBySide(Color4 original, LiquidityLevelType type, double mappedPrice, UwTheme theme)
		{
			if (type != LiquidityLevelType.Magnet && type != LiquidityLevelType.NeutralCluster)
				return original;
			Color4 side = mappedPrice <= lastPrice ? theme.Support : theme.Resistance;
			// 85% side-color + 15% gray midpoint = desaturated tint that yields to true S/R
			return new Color4(
				side.Red * 0.85f + 0.075f,
				side.Green * 0.85f + 0.075f,
				side.Blue * 0.85f + 0.075f,
				side.Alpha);
		}

		/// <summary>
		/// Live projection factor from UW price space to chart price space (e.g., QQQ -> MNQ).
		/// Returns 1.0 when the chart instrument and the UW ticker are the same symbol.
		/// </summary>
		private double GetMapScale(LiquiditySnapshot snap)
		{
			if (!needsMapping || snap == null || snap.CurrentPrice <= 0 || lastPrice <= 0)
				return 1.0;
			return lastPrice / snap.CurrentPrice;
		}

		private static float Lerp(float a, float b, float t)
		{
			if (t < 0f) t = 0f;
			if (t > 1f) t = 1f;
			return a + (b - a) * t;
		}

		#endregion

		#region Symbol mapping + helpers

		private string ResolveTicker()
		{
			if (UseTickerOverride && !string.IsNullOrWhiteSpace(UwTickerOverride))
				return CleanTicker(UwTickerOverride);

			string name = "";
			if (Instrument != null && Instrument.MasterInstrument != null)
				name = Instrument.MasterInstrument.Name;
			string t = CleanTicker(name);

			if (Instrument != null && Instrument.MasterInstrument != null
				&& Instrument.MasterInstrument.InstrumentType == InstrumentType.Future)
			{
				string hint = FuturesHint(t);
				futuresWarning = "Futures '" + t + "' likely has no UW dark-pool data. Set UwTickerOverride"
					+ (hint != null ? " (e.g., " + hint + ")" : "") + ".";
				LogMsg(UwLogLevel.Warning, futuresWarning);
			}
			return t;
		}

		private static string CleanTicker(string raw)
		{
			if (string.IsNullOrWhiteSpace(raw))
				return "";
			string s = raw.Trim().ToUpperInvariant();
			int space = s.IndexOf(' ');
			if (space > 0)
				s = s.Substring(0, space); // strips "ES 09-26" -> "ES"
			var sb = new System.Text.StringBuilder(s.Length);
			for (int i = 0; i < s.Length; i++)
			{
				char c = s[i];
				if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-')
					sb.Append(c);
			}
			return sb.ToString();
		}

		private static string FuturesHint(string t)
		{
			switch (t)
			{
				case "ES": case "MES": return "SPY or SPX";
				case "NQ": case "MNQ": return "QQQ or NDX";
				case "YM": case "MYM": return "DIA";
				case "RTY": case "M2K": return "IWM";
				default: return null;
			}
		}

		private static string BuildPriceFormat(double tickSize)
		{
			string s = tickSize.ToString("0.##########", CultureInfo.InvariantCulture);
			int dot = s.IndexOf('.');
			int decimals = dot < 0 ? 0 : s.Length - dot - 1;
			if (decimals <= 0)
				return "0";
			return "0." + new string('0', Math.Min(10, decimals));
		}

		private void LogMsg(UwLogLevel level, string msg)
		{
			if ((int)level > (int)LogLevel)
				return;
			try
			{
				Print("[UW_DPLM " + resolvedTicker + " " + level + "] " + msg);
				if (level == UwLogLevel.Error)
					Log("DEEP6DarkPoolLevels: " + msg, NinjaTrader.Cbi.LogLevel.Error);
			}
			catch { }
		}

		#endregion

		#region Properties — Connection

		[XmlIgnore]
		[Display(Name = "API key", Description = "Unusual Whales API key (Bearer token). Never printed to the Output window. See StoreApiKeyObfuscated for persistence behavior.", Order = 1, GroupName = "01) Connection")]
		public string ApiKey { get; set; }

		[Browsable(false)]
		public string ApiKeySerialize
		{
			get { return StoreApiKeyObfuscated ? Util.Obfuscate(ApiKey) : ApiKey; }
			set { ApiKey = Util.Deobfuscate(value); }
		}

		[Display(Name = "Store API key obfuscated", Description = "When true the key is XOR/Base64-obfuscated in the workspace file. This is obfuscation, NOT encryption — NinjaScript cannot provide enterprise-grade secret storage. When false the key is stored in plaintext.", Order = 2, GroupName = "01) Connection")]
		public bool StoreApiKeyObfuscated { get; set; }

		[Display(Name = "Use ticker override", Order = 3, GroupName = "01) Connection")]
		public bool UseTickerOverride { get; set; }

		[Display(Name = "UW ticker override", Description = "Maps the chart instrument to a UW ticker (e.g., ES chart -> SPY). Always takes precedence when 'Use ticker override' is on.", Order = 4, GroupName = "01) Connection")]
		public string UwTickerOverride { get; set; }

		[Display(Name = "Enable REST snapshot/polling", Order = 5, GroupName = "01) Connection")]
		public bool EnableRestSnapshot { get; set; }

		[Display(Name = "Enable WebSocket streaming", Description = "Requires a UW plan with WebSocket access. Falls back to REST polling automatically on failure.", Order = 6, GroupName = "01) Connection")]
		public bool EnableWebSocketStreaming { get; set; }

		[Range(5, 3600)]
		[Display(Name = "Poll interval (s)", Order = 7, GroupName = "01) Connection")]
		public int PollIntervalSeconds { get; set; }

		[Range(5, 120)]
		[Display(Name = "Request timeout (s)", Order = 8, GroupName = "01) Connection")]
		public int RequestTimeoutSeconds { get; set; }

		[Range(0, 10)]
		[Display(Name = "Max retries", Order = 9, GroupName = "01) Connection")]
		public int MaxRetries { get; set; }

		[Display(Name = "Backoff mode", Order = 10, GroupName = "01) Connection")]
		public UwBackoffMode BackoffMode { get; set; }

		[Display(Name = "Log level", Order = 11, GroupName = "01) Connection")]
		public UwLogLevel LogLevel { get; set; }

		#endregion

		#region Properties — Data filters

		[Range(1, 30)]
		[Display(Name = "Lookback trading days", Order = 1, GroupName = "02) Data Filters")]
		public int LookbackTradingDays { get; set; }

		[Display(Name = "Intraday only", Description = "When true, only today's (ET) prints are aggregated and the intraday decay half-life is used.", Order = 2, GroupName = "02) Data Filters")]
		public bool IntradayOnly { get; set; }

		[Display(Name = "Include extended hours", Order = 3, GroupName = "02) Data Filters")]
		public bool IncludeExtendedHours { get; set; }

		[Range(0, double.MaxValue)]
		[Display(Name = "Min premium ($)", Order = 4, GroupName = "02) Data Filters")]
		public double MinPremiumDouble { get { return (double)MinPremium; } set { MinPremium = (decimal)value; } }

		[Browsable(false)]
		[XmlIgnore]
		public decimal MinPremium { get; set; }

		[Range(0, double.MaxValue)]
		[Display(Name = "Max premium ($, 0 = off)", Order = 5, GroupName = "02) Data Filters")]
		public double MaxPremiumDouble { get { return (double)MaxPremium; } set { MaxPremium = (decimal)value; } }

		[Browsable(false)]
		[XmlIgnore]
		public decimal MaxPremium { get; set; }

		[Range(0, long.MaxValue)]
		[Display(Name = "Min size (shares)", Order = 6, GroupName = "02) Data Filters")]
		public long MinSize { get; set; }

		[Range(0, long.MaxValue)]
		[Display(Name = "Max size (shares, 0 = off)", Order = 7, GroupName = "02) Data Filters")]
		public long MaxSize { get; set; }

		[Range(0, long.MaxValue)]
		[Display(Name = "Min daily volume (API filter, 0 = off)", Order = 8, GroupName = "02) Data Filters")]
		public long MinVolume { get; set; }

		[Range(10, 500)]
		[Display(Name = "Max trades per request", Order = 9, GroupName = "02) Data Filters")]
		public int MaxTradesPerRequest { get; set; }

		[Display(Name = "Ignore canceled trades", Order = 10, GroupName = "02) Data Filters")]
		public bool IgnoreCanceledTrades { get; set; }

		[Display(Name = "Sale condition filter (include-only, comma-sep)", Order = 11, GroupName = "02) Data Filters")]
		public string SaleConditionFilter { get; set; }

		[Display(Name = "Trade code filter (include-only, comma-sep)", Order = 12, GroupName = "02) Data Filters")]
		public string TradeCodeFilter { get; set; }

		[Display(Name = "Session date override (yyyy-MM-dd)", Description = "Load a prior session's prints/volume instead of today. Leave empty for live.", Order = 13, GroupName = "02) Data Filters")]
		public string SessionDateOverride { get; set; }

		#endregion

		#region Properties — Level construction

		[Display(Name = "Grouping mode", Description = "Auto = max(2 ticks, 0.03% of price, 0.05 * ATR(14))", Order = 1, GroupName = "03) Level Construction")]
		public LevelGroupingMode GroupingMode { get; set; }

		[Range(1, 200)]
		[Display(Name = "Tick bucket size", Order = 2, GroupName = "03) Level Construction")]
		public int TickBucketSize { get; set; }

		[Range(0.01, 5)]
		[Display(Name = "ATR bucket multiplier", Order = 3, GroupName = "03) Level Construction")]
		public double AtrBucketMultiplier { get; set; }

		[Range(0.001, 5)]
		[Display(Name = "Percent bucket size (%)", Order = 4, GroupName = "03) Level Construction")]
		public double PercentBucketSize { get; set; }

		[Range(1, 100)]
		[Display(Name = "Min print count per level", Order = 5, GroupName = "03) Level Construction")]
		public int MinPrintCountPerLevel { get; set; }

		[Range(0, double.MaxValue)]
		[Display(Name = "Min total premium per level ($)", Order = 6, GroupName = "03) Level Construction")]
		public double MinTotalPremiumDouble { get { return (double)MinTotalPremiumPerLevel; } set { MinTotalPremiumPerLevel = (decimal)value; } }

		[Browsable(false)]
		[XmlIgnore]
		public decimal MinTotalPremiumPerLevel { get; set; }

		[Range(0, long.MaxValue)]
		[Display(Name = "Min total size per level (shares)", Order = 7, GroupName = "03) Level Construction")]
		public long MinTotalSizePerLevel { get; set; }

		[Range(0, long.MaxValue)]
		[Display(Name = "Min off-lit volume per level (volume-only levels)", Order = 8, GroupName = "03) Level Construction")]
		public long MinOffLitVolumePerLevel { get; set; }

		[Range(1, 100)]
		[Display(Name = "Max levels to render", Order = 9, GroupName = "03) Level Construction")]
		public int MaxLevelsToRender { get; set; }

		[Display(Name = "Merge nearby levels", Order = 10, GroupName = "03) Level Construction")]
		public bool MergeNearbyLevels { get; set; }

		[Range(1, 100)]
		[Display(Name = "Merge distance (ticks)", Order = 11, GroupName = "03) Level Construction")]
		public int MergeDistanceTicks { get; set; }

		[Range(1, 100000)]
		[Display(Name = "Decay half-life (minutes, intraday)", Order = 12, GroupName = "03) Level Construction")]
		public double DecayHalfLifeMinutes { get; set; }

		[Range(1, 60)]
		[Display(Name = "Historical decay (trading days, multi-day mode)", Order = 13, GroupName = "03) Level Construction")]
		public int HistoricalDecayDays { get; set; }

		#endregion

		#region Properties — Advanced scoring

		[Range(0, 1)] [Display(Name = "Weight: dark-pool premium", Order = 1, GroupName = "04) Advanced Scoring")]
		public double WeightPremium { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: dark-pool share size", Order = 2, GroupName = "04) Advanced Scoring")]
		public double WeightSize { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: print count", Order = 3, GroupName = "04) Advanced Scoring")]
		public double WeightPrintCount { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: off-lit volume at price", Order = 4, GroupName = "04) Advanced Scoring")]
		public double WeightOffLitVolume { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: off-lit ratio", Order = 5, GroupName = "04) Advanced Scoring")]
		public double WeightOffLitRatio { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: recency", Order = 6, GroupName = "04) Advanced Scoring")]
		public double WeightRecency { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: proximity to price", Order = 7, GroupName = "04) Advanced Scoring")]
		public double WeightProximity { get; set; }

		[Range(0, 1)] [Display(Name = "Weight: absorption behavior", Order = 8, GroupName = "04) Advanced Scoring")]
		public double WeightAbsorption { get; set; }

		[Range(0, 1)] [Display(Name = "Stale decay penalty", Order = 9, GroupName = "04) Advanced Scoring")]
		public double StalePenalty { get; set; }

		[Range(0, 100)] [Display(Name = "Min score to render (0-100)", Order = 10, GroupName = "04) Advanced Scoring")]
		public double MinScoreToRender { get; set; }

		[Range(0, 100)] [Display(Name = "High-confidence threshold (0-100)", Order = 11, GroupName = "04) Advanced Scoring")]
		public double HighConfidenceScoreThreshold { get; set; }

		#endregion

		#region Properties — Visual

		[Display(Name = "Theme preset", Order = 1, GroupName = "05) Visual")]
		public UwThemePreset ThemePreset { get; set; }

		[Display(Name = "Show zones", Order = 2, GroupName = "05) Visual")]
		public bool ShowZones { get; set; }

		[Display(Name = "Show lines", Order = 3, GroupName = "05) Visual")]
		public bool ShowLines { get; set; }

		[Display(Name = "Show labels", Order = 4, GroupName = "05) Visual")]
		public bool ShowLabels { get; set; }

		[Display(Name = "Show print markers", Order = 5, GroupName = "05) Visual")]
		public bool ShowPrintMarkers { get; set; }

		[Display(Name = "Show dashboard", Order = 6, GroupName = "05) Visual")]
		public bool ShowDashboard { get; set; }

		[Display(Name = "Show tooltips (type text in Full labels)", Order = 7, GroupName = "05) Visual")]
		public bool ShowTooltips { get; set; }

		[Display(Name = "Show confidence legend", Order = 8, GroupName = "05) Visual")]
		public bool ShowConfidenceLegend { get; set; }

		[Range(0.0, 1.0)]
		[Display(Name = "Zone opacity min", Order = 9, GroupName = "05) Visual")]
		public double ZoneOpacityMin { get; set; }

		[Range(0.0, 1.0)]
		[Display(Name = "Zone opacity max", Order = 10, GroupName = "05) Visual")]
		public double ZoneOpacityMax { get; set; }

		[Range(1, 10)]
		[Display(Name = "Line width min", Order = 11, GroupName = "05) Visual")]
		public int LineWidthMin { get; set; }

		[Range(1, 10)]
		[Display(Name = "Line width max", Order = 12, GroupName = "05) Visual")]
		public int LineWidthMax { get; set; }

		[Display(Name = "Label mode", Order = 13, GroupName = "05) Visual")]
		public LabelDisplayMode LabelMode { get; set; }

		[Display(Name = "Extend levels right", Order = 14, GroupName = "05) Visual")]
		public bool ExtendLevelsRight { get; set; }

		[Display(Name = "Extend levels left", Order = 15, GroupName = "05) Visual")]
		public bool ExtendLevelsLeft { get; set; }

		[Display(Name = "Fade stale levels", Order = 16, GroupName = "05) Visual")]
		public bool FadeStaleLevels { get; set; }

		[Display(Name = "Use SharpDX rendering", Description = "When false, falls back to standard draw objects (top 10 levels only, lower fidelity).", Order = 17, GroupName = "05) Visual")]
		public bool UseSharpDxRendering { get; set; }

		[Display(Name = "Dashboard position", Order = 18, GroupName = "05) Visual")]
		public DashboardCorner DashboardPosition { get; set; }

		[Range(1, 1440)]
		[Display(Name = "Print marker lookback (minutes)", Order = 19, GroupName = "05) Visual")]
		public double MarkerLookbackMinutes { get; set; }

		[XmlIgnore]
		[Display(Name = "Custom: support brush", Order = 20, GroupName = "05) Visual")]
		public Brush CustomSupportBrush { get; set; }

		[Browsable(false)]
		public string CustomSupportBrushSerialize
		{
			get { return Serialize.BrushToString(CustomSupportBrush); }
			set { CustomSupportBrush = Serialize.StringToBrush(value); }
		}

		[XmlIgnore]
		[Display(Name = "Custom: resistance brush", Order = 21, GroupName = "05) Visual")]
		public Brush CustomResistanceBrush { get; set; }

		[Browsable(false)]
		public string CustomResistanceBrushSerialize
		{
			get { return Serialize.BrushToString(CustomResistanceBrush); }
			set { CustomResistanceBrush = Serialize.StringToBrush(value); }
		}

		[XmlIgnore]
		[Display(Name = "Custom: magnet brush", Order = 22, GroupName = "05) Visual")]
		public Brush CustomMagnetBrush { get; set; }

		[Browsable(false)]
		public string CustomMagnetBrushSerialize
		{
			get { return Serialize.BrushToString(CustomMagnetBrush); }
			set { CustomMagnetBrush = Serialize.StringToBrush(value); }
		}

		[XmlIgnore]
		[Display(Name = "Custom: text brush", Order = 23, GroupName = "05) Visual")]
		public Brush CustomTextBrush { get; set; }

		[Browsable(false)]
		public string CustomTextBrushSerialize
		{
			get { return Serialize.BrushToString(CustomTextBrush); }
			set { CustomTextBrush = Serialize.StringToBrush(value); }
		}

		#endregion

		#region Properties — Alerts

		[Display(Name = "Enable alerts", Order = 1, GroupName = "06) Alerts")]
		public bool EnableAlerts { get; set; }

		[Display(Name = "Alert: new high-confidence level", Order = 2, GroupName = "06) Alerts")]
		public bool AlertOnNewHighConfidenceLevel { get; set; }

		[Display(Name = "Alert: price approaching level", Order = 3, GroupName = "06) Alerts")]
		public bool AlertOnPriceApproachLevel { get; set; }

		[Range(1, 500)]
		[Display(Name = "Alert distance (ticks)", Order = 4, GroupName = "06) Alerts")]
		public int AlertDistanceTicks { get; set; }

		[Display(Name = "Alert: level break", Order = 5, GroupName = "06) Alerts")]
		public bool AlertOnBreak { get; set; }

		[Display(Name = "Alert: level retest", Order = 6, GroupName = "06) Alerts")]
		public bool AlertOnRetest { get; set; }

		[Display(Name = "Alert: large single print", Order = 7, GroupName = "06) Alerts")]
		public bool AlertOnLargePrint { get; set; }

		[Range(0, double.MaxValue)]
		[Display(Name = "Large print min premium ($)", Order = 8, GroupName = "06) Alerts")]
		public double AlertLargePrintMinPremiumDouble { get { return (double)AlertLargePrintMinPremium; } set { AlertLargePrintMinPremium = (decimal)value; } }

		[Browsable(false)]
		[XmlIgnore]
		public decimal AlertLargePrintMinPremium { get; set; }

		[Display(Name = "Alert sound (file in NT sounds folder)", Order = 9, GroupName = "06) Alerts")]
		public string AlertSound { get; set; }

		[Range(5, 3600)]
		[Display(Name = "Alert cooldown (s)", Order = 10, GroupName = "06) Alerts")]
		public int AlertCooldownSeconds { get; set; }

		[Display(Name = "Alert message template", Description = "Tokens: {ticker} {event} {type} {price} {score} {offlit} {premium}", Order = 11, GroupName = "06) Alerts")]
		public string AlertMessageTemplate { get; set; }

		#endregion

		#region Properties — Performance / Diagnostics

		[Range(500, 200000)]
		[Display(Name = "Max cached trades", Order = 1, GroupName = "07) Performance")]
		public int MaxCachedTrades { get; set; }

		[Range(10, 5000)]
		[Display(Name = "Max cached levels", Order = 2, GroupName = "07) Performance")]
		public int MaxCachedLevels { get; set; }

		[Range(100, 5000)]
		[Display(Name = "Render throttle (ms)", Order = 3, GroupName = "07) Performance")]
		public int RenderThrottleMs { get; set; }

		[Range(250, 60000)]
		[Display(Name = "Aggregation throttle (ms)", Order = 4, GroupName = "07) Performance")]
		public int AggregationThrottleMs { get; set; }

		[Display(Name = "Use concurrent queue for WS trades", Order = 5, GroupName = "07) Performance")]
		public bool UseConcurrentQueue { get; set; }

		[Display(Name = "Use lock-free snapshot for render", Description = "Informational: snapshots are always immutable + volatile-published; this flag is reserved for future tuning.", Order = 6, GroupName = "07) Performance")]
		public bool UseLockFreeSnapshotForRender { get; set; }

		[Display(Name = "Enable diagnostics (dashboard extras + debug logs)", Order = 7, GroupName = "07) Performance")]
		public bool EnableDiagnostics { get; set; }

		[Display(Name = "Fixture mode (offline JSON fixtures, no API)", Order = 8, GroupName = "07) Performance")]
		public bool EnableFixtureMode { get; set; }

		[Display(Name = "Fixture directory", Description = "Folder containing darkpool.json and volume_levels.json. Empty = Documents\\NinjaTrader 8\\UWFixtures", Order = 9, GroupName = "07) Performance")]
		public string FixtureDirectory { get; set; }

		[Range(60, 3600)]
		[Display(Name = "Volume-by-price refresh (s)", Order = 10, GroupName = "07) Performance")]
		public int VolumeLevelsRefreshSeconds { get; set; }

		#endregion

		#region Properties — Depth Radar V6

		[Display(Name = "Enable Depth Radar", Order = 1, GroupName = "08) Depth Radar V6")]
		public bool EnableDepthRadar { get; set; }

		[Display(Name = "Radar JSON path", Order = 2, GroupName = "08) Depth Radar V6")]
		public string DepthRadarJsonPath { get; set; }

		[Range(1, 200)]
		[Display(Name = "Radar confluence (ticks)", Order = 3, GroupName = "08) Depth Radar V6")]
		public int RadarConfluenceTicks { get; set; }

		[Range(5, 3600)]
		[Display(Name = "Radar stale (s)", Order = 4, GroupName = "08) Depth Radar V6")]
		public int RadarStaleSec { get; set; }

		[Range(0, 100)]
		[Display(Name = "Radar min quality", Order = 5, GroupName = "08) Depth Radar V6")]
		public double RadarMinQuality { get; set; }

		[Display(Name = "Highlight confluence", Order = 6, GroupName = "08) Depth Radar V6")]
		public bool HighlightConfluence { get; set; }

		#endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6.DEEP6DarkPoolLevels[] cacheDEEP6DarkPoolLevels;
		public DEEP6.DEEP6DarkPoolLevels DEEP6DarkPoolLevels()
		{
			return DEEP6DarkPoolLevels(Input);
		}

		public DEEP6.DEEP6DarkPoolLevels DEEP6DarkPoolLevels(ISeries<double> input)
		{
			if (cacheDEEP6DarkPoolLevels != null)
				for (int idx = 0; idx < cacheDEEP6DarkPoolLevels.Length; idx++)
					if (cacheDEEP6DarkPoolLevels[idx] != null &&  cacheDEEP6DarkPoolLevels[idx].EqualsInput(input))
						return cacheDEEP6DarkPoolLevels[idx];
			return CacheIndicator<DEEP6.DEEP6DarkPoolLevels>(new DEEP6.DEEP6DarkPoolLevels(), input, ref cacheDEEP6DarkPoolLevels);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6.DEEP6DarkPoolLevels DEEP6DarkPoolLevels()
		{
			return indicator.DEEP6DarkPoolLevels(Input);
		}

		public Indicators.DEEP6.DEEP6DarkPoolLevels DEEP6DarkPoolLevels(ISeries<double> input )
		{
			return indicator.DEEP6DarkPoolLevels(input);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6.DEEP6DarkPoolLevels DEEP6DarkPoolLevels()
		{
			return indicator.DEEP6DarkPoolLevels(Input);
		}

		public Indicators.DEEP6.DEEP6DarkPoolLevels DEEP6DarkPoolLevels(ISeries<double> input )
		{
			return indicator.DEEP6DarkPoolLevels(input);
		}
	}
}

#endregion
