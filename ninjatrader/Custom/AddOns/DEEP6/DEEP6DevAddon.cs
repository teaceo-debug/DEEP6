// DEEP6DevAddon.cs — Lightweight HTTP dev-API server running inside NT8.
//
// Exposes localhost:19206 with these endpoints:
//   GET  /health   → {"ok":true}
//   GET  /status   → NT8 state, last compile timestamp, DLL mtime
//   GET  /errors   → JSON array of Output Window text lines containing errors
//   POST /compile  → triggers compile via Dispatcher (F5 equivalent)
//   GET  /log      → last N lines from NT8 trace log (?lines=50)
//
// Deploy: nt8-deploy.ps1 -Target AddOns
// Then F5 in NT8 NinjaScript Editor.  Port 19206 = DEEP6.

#region Using declarations
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public class DEEP6DevAddon : AddOnBase
    {
        // ── constants ────────────────────────────────────────────────────────────
        private const int    Port       = 19206;
        private const string Prefix     = "http://localhost:19206/";
        private const int    MaxBufLines = 2000;

        // ── state ────────────────────────────────────────────────────────────────
        private HttpListener         _listener;
        private Thread               _listenerThread;
        private volatile bool        _running;
        private readonly object      _bufLock = new object();
        private readonly LinkedList<string> _buf = new LinkedList<string>();

        // ── NT8 AddOn lifecycle ──────────────────────────────────────────────────

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 HTTP dev-API server on localhost:19206";
                Name        = "DEEP6DevAddon";
            }
            else if (State == State.Active)
            {
                StartServer();
            }
            else if (State == State.Terminated)
            {
                StopServer();
            }
        }

        // ── server lifecycle ─────────────────────────────────────────────────────

        private void StartServer()
        {
            if (!HttpListener.IsSupported)
            {
                Print("DEEP6DevAddon: HttpListener not supported.");
                return;
            }
            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add(Prefix);
                _listener.Start();
                _running        = true;
                _listenerThread = new Thread(ListenerLoop) { IsBackground = true, Name = "DEEP6-DevAPI" };
                _listenerThread.Start();
                Print("DEEP6DevAddon: HTTP server started on " + Prefix);
            }
            catch (Exception ex)
            {
                Print("DEEP6DevAddon: Failed to start — " + ex.Message);
            }
        }

        private void StopServer()
        {
            _running = false;
            try { if (_listener != null) _listener.Stop(); }  catch { }
            try { if (_listener != null) _listener.Close(); } catch { }
            _listener = null;
        }

        // ── listener loop (background thread) ────────────────────────────────────

        private void ListenerLoop()
        {
            while (_running)
            {
                try
                {
                    HttpListenerContext ctx = _listener.GetContext();
                    ThreadPool.QueueUserWorkItem(delegate { HandleRequest(ctx); });
                }
                catch (HttpListenerException)
                {
                    if (!_running) break;
                }
                catch (Exception ex)
                {
                    if (_running)
                    {
                        Print("DEEP6DevAddon: Listener error — " + ex.Message);
                        Thread.Sleep(200);
                    }
                }
            }
        }

        // ── request dispatcher ───────────────────────────────────────────────────

        private void HandleRequest(HttpListenerContext ctx)
        {
            HttpListenerRequest  req  = ctx.Request;
            HttpListenerResponse resp = ctx.Response;
            try
            {
                string path   = req.Url != null ? req.Url.AbsolutePath.TrimEnd('/') : "/";
                string method = req.HttpMethod != null ? req.HttpMethod.ToUpperInvariant() : "GET";
                if (path == "") path = "/";

                string json;
                if      (path == "/health"  && method == "GET")  json = HandleHealth();
                else if (path == "/status"  && method == "GET")  json = HandleStatus();
                else if (path == "/errors"  && method == "GET")  json = HandleErrors();
                else if (path == "/compile" && method == "POST") json = HandleCompile();
                else if (path == "/log"     && method == "GET")  json = HandleLog(req.QueryString["lines"]);
                else
                {
                    resp.StatusCode = 404;
                    json = "{\"error\":\"not found\"}";
                }

                byte[] body = Encoding.UTF8.GetBytes(json);
                resp.ContentType     = "application/json; charset=utf-8";
                resp.ContentLength64 = body.Length;
                resp.Headers["Access-Control-Allow-Origin"] = "*";
                resp.OutputStream.Write(body, 0, body.Length);
            }
            catch (Exception ex)
            {
                try
                {
                    byte[] err = Encoding.UTF8.GetBytes("{\"error\":" + JsonStr(ex.Message) + "}");
                    resp.StatusCode      = 500;
                    resp.ContentLength64 = err.Length;
                    resp.OutputStream.Write(err, 0, err.Length);
                }
                catch { }
            }
            finally
            {
                try { resp.OutputStream.Close(); } catch { }
            }
        }

        // ── endpoint handlers ────────────────────────────────────────────────────

        private string HandleHealth()
        {
            return "{\"ok\":true,\"port\":19206}";
        }

        private string HandleStatus()
        {
            string dllMtime    = "";
            string lastCompile = "";

            try
            {
                string dllPath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8", "bin", "Custom", "NinjaTrader.Custom.dll");
                if (File.Exists(dllPath))
                    dllMtime = new FileInfo(dllPath).LastWriteTimeUtc.ToString("o", CultureInfo.InvariantCulture);
            }
            catch { }

            try
            {
                string xmlPath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8", "log", "Install.xml");
                if (File.Exists(xmlPath))
                {
                    string txt   = File.ReadAllText(xmlPath);
                    int    start = txt.IndexOf("<CompiledCustomAssembly>", StringComparison.Ordinal);
                    int    end   = txt.IndexOf("</CompiledCustomAssembly>", StringComparison.Ordinal);
                    if (start >= 0 && end > start)
                        lastCompile = txt.Substring(start + 24, end - start - 24).Trim();
                }
            }
            catch { }

            return "{\"nt8_running\":true,\"last_compile\":" + JsonStr(lastCompile)
                 + ",\"dll_mtime\":" + JsonStr(dllMtime) + "}";
        }

        private string HandleErrors()
        {
            var lines = new List<string>();
            try
            {
                Application.Current.Dispatcher.Invoke(
                    new Action(delegate { WalkWindowsForText(lines); }),
                    TimeSpan.FromSeconds(3));
            }
            catch { }

            if (lines.Count == 0)
                TailLogForErrors(lines);

            var sb = new StringBuilder();
            sb.Append("[");
            for (int i = 0; i < lines.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append(JsonStr(lines[i]));
            }
            sb.Append("]");
            return sb.ToString();
        }

        private string HandleCompile()
        {
            try
            {
                Application.Current.Dispatcher.BeginInvoke(
                    new Action(delegate { TriggerCompile(); }));
                return "{\"triggered\":true}";
            }
            catch (Exception ex)
            {
                return "{\"triggered\":false,\"error\":" + JsonStr(ex.Message) + "}";
            }
        }

        private string HandleLog(string linesParam)
        {
            int n = 50;
            if (!string.IsNullOrEmpty(linesParam)) int.TryParse(linesParam, out n);
            if (n < 1)  n = 1;
            if (n > 500) n = 500;

            var recent = new List<string>();
            lock (_bufLock)
            {
                var node = _buf.Last;
                int count = 0;
                while (node != null && count < n)
                {
                    recent.Insert(0, node.Value);
                    node = node.Previous;
                    count++;
                }
            }

            // Also try to read last n lines from trace log file
            if (recent.Count == 0)
            {
                try
                {
                    string traceDir = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                        "NinjaTrader 8", "trace");
                    string best = FindLatestFile(traceDir, "*.txt");
                    if (best != null)
                    {
                        using (var fs = new FileStream(best, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                        using (var sr = new StreamReader(fs))
                        {
                            string line;
                            while ((line = sr.ReadLine()) != null)
                            {
                                recent.Add(line);
                                if (recent.Count > n * 2) recent.RemoveAt(0);
                            }
                        }
                        if (recent.Count > n) recent = recent.GetRange(recent.Count - n, n);
                    }
                }
                catch { }
            }

            var sb = new StringBuilder();
            sb.Append("[");
            for (int i = 0; i < recent.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append(JsonStr(recent[i]));
            }
            sb.Append("]");
            return sb.ToString();
        }

        // ── helpers ──────────────────────────────────────────────────────────────

        private void WalkWindowsForText(List<string> results)
        {
            // Walk all open NT8 windows looking for text controls that contain error lines
            foreach (Window win in Application.Current.Windows)
            {
                if (win == null) continue;
                try { WalkElement(win, results); }
                catch { }
                if (results.Count >= 200) break;
            }
        }

        private void WalkElement(DependencyObject element, List<string> results)
        {
            if (element == null || results.Count >= 200) return;

            string text = null;
            if (element is TextBox tb)
                text = tb.Text;
            else if (element is RichTextBox rtb)
                text = new System.Windows.Documents.TextRange(rtb.Document.ContentStart, rtb.Document.ContentEnd).Text;
            else if (element is TextBlock tbl)
                text = tbl.Text;
            else if (element is ListBox lb)
            {
                foreach (object item in lb.Items)
                {
                    string s = item != null ? item.ToString() : null;
                    if (!string.IsNullOrEmpty(s) && IsErrorLine(s))
                        results.Add(s);
                }
            }

            if (text != null)
            {
                foreach (string line in text.Split('\n'))
                {
                    string trimmed = line.Trim();
                    if (!string.IsNullOrEmpty(trimmed) && IsErrorLine(trimmed))
                        results.Add(trimmed);
                }
            }

            int childCount = VisualTreeHelper.GetChildrenCount(element);
            for (int i = 0; i < childCount; i++)
            {
                DependencyObject child = VisualTreeHelper.GetChild(element, i);
                WalkElement(child, results);
            }
        }

        private static bool IsErrorLine(string line)
        {
            return line.IndexOf("error", StringComparison.OrdinalIgnoreCase) >= 0
                || line.IndexOf("CS0", StringComparison.Ordinal) >= 0
                || line.IndexOf("CS1", StringComparison.Ordinal) >= 0
                || line.IndexOf("warning", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private void TailLogForErrors(List<string> results)
        {
            try
            {
                string logDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8", "log");
                string best = FindLatestFile(logDir, "*.txt");
                if (best == null) return;
                using (var fs = new FileStream(best, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var sr = new StreamReader(fs))
                {
                    string line;
                    while ((line = sr.ReadLine()) != null)
                    {
                        if (IsErrorLine(line)) results.Add(line);
                    }
                }
                // Keep last 50
                if (results.Count > 50) results.RemoveRange(0, results.Count - 50);
            }
            catch { }
        }

        private void TriggerCompile()
        {
            // Try to invoke compile via reflection on the NinjaScript editor window
            try
            {
                foreach (Window win in Application.Current.Windows)
                {
                    if (win == null) continue;
                    string typeName = win.GetType().FullName ?? "";
                    if (typeName.IndexOf("NinjaScript", StringComparison.OrdinalIgnoreCase) >= 0
                     && typeName.IndexOf("Editor",     StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        // Try reflection: CompileAll, Compile, or Build
                        foreach (string methodName in new[] { "CompileAll", "Compile", "Build" })
                        {
                            MethodInfo m = win.GetType().GetMethod(methodName,
                                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                            if (m != null) { m.Invoke(win, null); return; }
                        }
                    }
                }
            }
            catch { }
        }

        private static string FindLatestFile(string dir, string pattern)
        {
            FileInfo best = null;
            try
            {
                foreach (FileInfo fi in new DirectoryInfo(dir).GetFiles(pattern))
                    if (best == null || fi.LastWriteTimeUtc > best.LastWriteTimeUtc)
                        best = fi;
            }
            catch { }
            return best != null ? best.FullName : null;
        }

        private void BufferLine(string line)
        {
            lock (_bufLock)
            {
                _buf.AddLast(line);
                while (_buf.Count > MaxBufLines) _buf.RemoveFirst();
            }
        }

        private static string JsonStr(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder(s.Length + 4);
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"':  sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b");  break;
                    case '\f': sb.Append("\\f");  break;
                    case '\n': sb.Append("\\n");  break;
                    case '\r': sb.Append("\\r");  break;
                    case '\t': sb.Append("\\t");  break;
                    default:
                        if (c < 0x20)
                            sb.Append("\\u").Append(((int)c).ToString("X4", CultureInfo.InvariantCulture));
                        else
                            sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
            return sb.ToString();
        }
    }
}
