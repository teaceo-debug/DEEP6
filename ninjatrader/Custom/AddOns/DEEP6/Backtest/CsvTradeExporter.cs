// CsvTradeExporter: Exports BacktestResult trades to CSV for vectorbt consumption.
// NT8-API-free — no NinjaTrader.Cbi/Data/NinjaScript usings.
// Phase quick-260415-u6v

using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest
{
    /// <summary>
    /// Writes completed trades to a CSV file suitable for pandas/vectorbt consumption.
    /// </summary>
    public static class CsvTradeExporter
    {
        // CSV column order (14 columns)
        private const string Header =
            "EntryBar,ExitBar,EntryPrice,ExitPrice,Direction,PnlTicks,PnlDollars," +
            "SignalId,Tier,Score,Narrative,ExitReason,DurationBars,CategoriesFiring";

        /// <summary>
        /// Export all trades from <paramref name="result"/> to a CSV file at <paramref name="outputPath"/>.
        /// Numeric fields are formatted with InvariantCulture.
        /// CategoriesFiring is pipe-delimited to avoid breaking CSV structure.
        /// Narrative is quoted if it contains commas; internal quotes are escaped.
        /// </summary>
        public static void Export(BacktestResult result, string outputPath)
        {
            var lines = new List<string>(result.Trades.Count + 1);
            lines.Add(Header);

            foreach (var t in result.Trades)
            {
                lines.Add(TradeToLine(t));
            }

            File.WriteAllLines(outputPath, lines, Encoding.UTF8);
        }

        private static string TradeToLine(Trade t)
        {
            var sb = new StringBuilder();

            // EntryBar, ExitBar (int)
            sb.Append(t.EntryBar.ToString(CultureInfo.InvariantCulture));
            sb.Append(',');
            sb.Append(t.ExitBar.ToString(CultureInfo.InvariantCulture));
            sb.Append(',');

            // EntryPrice, ExitPrice (double)
            sb.Append(t.EntryPrice.ToString("G", CultureInfo.InvariantCulture));
            sb.Append(',');
            sb.Append(t.ExitPrice.ToString("G", CultureInfo.InvariantCulture));
            sb.Append(',');

            // Direction (int)
            sb.Append(t.Direction.ToString(CultureInfo.InvariantCulture));
            sb.Append(',');

            // PnlTicks, PnlDollars (double)
            sb.Append(t.PnlTicks.ToString("G", CultureInfo.InvariantCulture));
            sb.Append(',');
            sb.Append(t.PnlDollars.ToString("G", CultureInfo.InvariantCulture));
            sb.Append(',');

            // SignalId (string — no escaping needed, IDs never contain commas)
            sb.Append(t.SignalId ?? string.Empty);
            sb.Append(',');

            // Tier (enum name)
            sb.Append(t.Tier.ToString());
            sb.Append(',');

            // Score (double)
            sb.Append(t.Score.ToString("G", CultureInfo.InvariantCulture));
            sb.Append(',');

            // Narrative (may contain commas — quote it)
            sb.Append(CsvQuote(t.Narrative ?? string.Empty));
            sb.Append(',');

            // ExitReason
            sb.Append(t.ExitReason ?? string.Empty);
            sb.Append(',');

            // DurationBars
            sb.Append(t.DurationBars.ToString(CultureInfo.InvariantCulture));
            sb.Append(',');

            // CategoriesFiring — pipe-delimited
            string cats = t.CategoriesFiring != null
                ? string.Join("|", t.CategoriesFiring)
                : string.Empty;
            sb.Append(cats);

            return sb.ToString();
        }

        /// <summary>
        /// Wrap value in double-quotes if it contains commas or double-quotes.
        /// Internal double-quotes are escaped by doubling ("" convention).
        /// </summary>
        private static string CsvQuote(string value)
        {
            if (value == null) return string.Empty;
            bool needsQuoting = value.IndexOf(',') >= 0
                             || value.IndexOf('"') >= 0
                             || value.IndexOf('\n') >= 0;
            if (!needsQuoting) return value;
            return "\"" + value.Replace("\"", "\"\"") + "\"";
        }
    }
}
