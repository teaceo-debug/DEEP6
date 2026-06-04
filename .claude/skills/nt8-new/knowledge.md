# NinjaScript Code Generation Reference

## DEEP6 Workflow

1. Write source under `C:\Users\Tea\DEEP6\ninjatrader\Custom\[Type]\DEEP6\[Name].cs`
2. Deploy to `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\[Type]\DEEP6\[Name].cs`
3. Compile with `ninjatrader/scripts/nt8-compile.ps1`
4. Fix with `ninjatrader/scripts/nt8-ai-loop.ps1` if needed

## DEEP6 Naming

- Use `DEEP6*.cs`
- Keep the indicator/strategy namespace under `NinjaTrader.NinjaScript.Indicators.DEEP6` or `NinjaTrader.NinjaScript.Strategies.DEEP6`

## Enum Rule

If a public property uses an enum type, place the enum at global namespace level before any `namespace` block.

Reference: `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\@BlockVolume.cs`

## Minimal Generation Flow

1. Clarify indicator vs strategy vs AddOn
2. Use a DEEP6 template as structural reference
3. Generate only the requested feature
4. Save in repo source first, then deploy, compile, and fix

## DEEP6 Namespace Conventions

```csharp
namespace NinjaTrader.NinjaScript.Indicators.DEEP6 { }
namespace NinjaTrader.NinjaScript.Strategies.DEEP6 { }
```
