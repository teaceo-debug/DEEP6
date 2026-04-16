// Global usings that NT8 provides implicitly via .NET Framework references.
// In .NET 8+ these need to be explicit.
//
// NT8's NinjaScript compiler adds implicit usings for all NinjaTrader namespaces
// and several System namespaces. The generated code regions (#region NinjaScript
// generated code) rely on these being available without explicit using directives.
global using System.Drawing;
global using NinjaTrader.Data;
global using NinjaTrader.Cbi;
global using NinjaTrader.NinjaScript;
global using NinjaTrader.Gui.NinjaScript;
