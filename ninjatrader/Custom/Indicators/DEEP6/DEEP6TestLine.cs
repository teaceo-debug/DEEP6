#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Globalization;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Media;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
	public class DEEP6TestLine : Indicator
	{
		private Timer _timer;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "DEEP6TestLine";
				Description = "Minimal test: reads gex_terminal_nt8.json and draws lines";
				Calculate = Calculate.OnEachTick;
				IsOverlay = true;
				DrawOnPricePanel = true;
				IsSuspendedWhileInactive = true;
				BarsRequiredToPlot = 0;

				JsonFilePath = @"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_terminal_nt8.json";
			}
			else if (State == State.DataLoaded)
			{
				_timer = new Timer(OnTick, null, 1000, 5000);
			}
			else if (State == State.Terminated)
			{
				if (_timer != null) { _timer.Dispose(); _timer = null; }
			}
		}

		protected override void OnBarUpdate()
		{
			if (BarsInProgress != 0 || CurrentBar < 1) return;
			ReadAndDraw();
		}

		private void OnTick(object state)
		{
			try
			{
				if (ChartControl != null)
				{
					ChartControl.Dispatcher.BeginInvoke(new Action(() =>
					{
						try { ReadAndDraw(); ChartControl.InvalidateVisual(); }
						catch { }
					}));
				}
			}
			catch { }
		}

		private void ReadAndDraw()
		{
			try
			{
				string path = JsonFilePath;
				if (string.IsNullOrEmpty(path) || !File.Exists(path))
				{
					Draw.TextFixed(this, "status", "JSON NOT FOUND: " + path, TextPosition.TopLeft,
						Brushes.Red, new SimpleFont("Consolas", 12), Brushes.Transparent, Brushes.Transparent, 0);
					return;
				}

				string json;
				using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
				using (var sr = new StreamReader(fs))
					json = sr.ReadToEnd();

				var ser = new JavaScriptSerializer();
				var data = ser.Deserialize<System.Collections.Generic.Dictionary<string, object>>(json);

				double flip = ToDouble(data, "gamma_flip");
				double cwall = ToDouble(data, "call_wall");
				double pwall = ToDouble(data, "put_wall");
				double swing = ToDouble(data, "swing_equilibrium");
				string bias = data.ContainsKey("bias_direction") ? data["bias_direction"].ToString() : "?";
				int conf = (int)ToDouble(data, "bias_confidence");

				string hud = string.Format("GEX TEST | {0} {1}%\nFlip:{2:N2} CW:{3:N2} PW:{4:N2}",
					bias, conf, flip, cwall, pwall);

				Draw.TextFixed(this, "status", hud, TextPosition.TopLeft,
					Brushes.Lime, new SimpleFont("Consolas", 11), Brushes.Transparent, Brushes.Transparent, 0);

				if (flip > 0)
					Draw.HorizontalLine(this, "test_flip", flip, Brushes.Gold, DashStyleHelper.Dash, 2);
				if (cwall > 0)
					Draw.HorizontalLine(this, "test_cwall", cwall, Brushes.Red, DashStyleHelper.Solid, 2);
				if (pwall > 0)
					Draw.HorizontalLine(this, "test_pwall", pwall, Brushes.Lime, DashStyleHelper.Solid, 2);
				if (swing > 0)
					Draw.HorizontalLine(this, "test_swing", swing, Brushes.Cyan, DashStyleHelper.Dash, 1);
			}
			catch (Exception ex)
			{
				Draw.TextFixed(this, "status", "ERROR: " + ex.Message, TextPosition.TopLeft,
					Brushes.Red, new SimpleFont("Consolas", 10), Brushes.Transparent, Brushes.Transparent, 0);
			}
		}

		private double ToDouble(System.Collections.Generic.Dictionary<string, object> data, string key)
		{
			if (!data.ContainsKey(key) || data[key] == null) return 0;
			try { return Convert.ToDouble(data[key], CultureInfo.InvariantCulture); }
			catch { return 0; }
		}

		[NinjaScriptProperty]
		[Display(Name = "JsonFilePath", Order = 1, GroupName = "Parameters")]
		[PropertyEditor("NinjaTrader.Gui.Tools.PathEditor")]
		public string JsonFilePath { get; set; }
	}
}
