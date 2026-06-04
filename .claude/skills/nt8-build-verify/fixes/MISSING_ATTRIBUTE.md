# MISSING_ATTRIBUTE — Missing required property attributes

## Pattern
NT8 compile warning or runtime serialization error:
```
warning: Public property 'X' of type 'Series<T>' is missing [Browsable(false)] attribute
warning: Public property 'X' is missing [XmlIgnore] attribute
```
Or at runtime: NT8 throws a serialization exception when saving/loading a workspace that includes the indicator.

These are not always CS#### compile errors — they may appear as NT8 Output Window warnings or as runtime crashes. Treat them as errors that must be fixed before deployment.

## Root Causes (ordered by likelihood)
1. A public `Series<T>` property was added to an indicator without `[Browsable(false)]` and `[XmlIgnore]` — NT8 tries to serialize it and fails
2. A derived indicator property that should be hidden from the NT8 UI is missing `[Browsable(false)]`
3. A NinjaScript input property that should appear in the NT8 indicator dialog is missing `[NinjaScriptProperty]`
4. A property was promoted from `private` to `public` without adding the required attributes

## Fix Strategies

### Strategy 1: Add [Browsable(false)] + [XmlIgnore] to Series<T> properties
- **Detect**: A public property returns `Series<T>` (e.g., `Series<double>`, `Series<FootprintBar>`) and lacks both `[Browsable(false)]` and `[XmlIgnore]`. NT8 requires both attributes on all public `Series<T>` properties to prevent serialization errors.
- **Lookup**: Search the file for `public Series<` or `public ISeries<`. Every such property must have both attributes immediately above the property declaration.
- **Fix**: Add `[Browsable(false)]` and `[XmlIgnore]` on the two lines immediately before the property declaration. The `using` directives for `System.ComponentModel` and `System.Xml.Serialization` must also be present.
- **Verify**: Every public `Series<T>` property has both attributes. The file compiles and the indicator loads in NT8 without a serialization exception.

```csharp
// Required usings
using System.ComponentModel;
using System.Xml.Serialization;

// Required attributes on every public Series<T> property
[Browsable(false)]
[XmlIgnore]
public Series<double> BidVolume { get; set; }

[Browsable(false)]
[XmlIgnore]
public Series<double> AskVolume { get; set; }
```

### Strategy 2: Add [Browsable(false)] to hide a property from the NT8 indicator dialog
- **Detect**: A public property appears in the NT8 indicator settings dialog but should not be user-configurable. It may be an internal state property or a computed value.
- **Lookup**: Any public property without `[Browsable(false)]` will appear in the NT8 indicator dialog. If the property is not a user input, it should be hidden.
- **Fix**: Add `[Browsable(false)]` above the property declaration. If the property also holds a reference type or collection, add `[XmlIgnore]` as well to prevent serialization issues.
- **Verify**: The property no longer appears in the NT8 indicator settings dialog after recompile and re-add to chart.

### Strategy 3: Add [NinjaScriptProperty] to user-configurable inputs
- **Detect**: A public property is intended to appear in the NT8 indicator dialog (user-configurable input) but is missing `[NinjaScriptProperty]`. NT8 may not persist the value correctly across workspace saves.
- **Lookup**: User-configurable properties (like `Period`, `Threshold`, `Multiplier`) should have `[NinjaScriptProperty]` to ensure NT8 serializes and restores them correctly.
- **Fix**: Add `[NinjaScriptProperty]` above the property declaration. Keep `[Display(...)]` for the dialog label and ordering.
- **Verify**: The property appears in the NT8 dialog, its value persists after saving and reloading the workspace, and the indicator compiles cleanly.

```csharp
[NinjaScriptProperty]
[Display(Name = "Absorption Threshold", Order = 1, GroupName = "Parameters")]
public double AbsorptionThreshold { get; set; }
```

### Strategy 4: Promoted property missing attributes
- **Detect**: A property was recently changed from `private` or `protected` to `public` (e.g., to expose it to a strategy or another indicator). The promotion didn't include the required attributes.
- **Lookup**: Check the git diff or the property declaration. If it's `public` and returns a `Series<T>`, a collection, or a complex type, it needs `[Browsable(false)]` and `[XmlIgnore]`. If it's a simple value type intended for the dialog, it needs `[NinjaScriptProperty]`.
- **Fix**: Add the appropriate attributes based on the property's purpose (see Strategies 1-3 above).
- **Verify**: The property has the correct attributes for its intended visibility and serialization behavior.

## NT8 Attribute Reference

| Attribute | Namespace | When to Use |
|-----------|-----------|-------------|
| `[Browsable(false)]` | `System.ComponentModel` | Hide property from NT8 indicator dialog |
| `[XmlIgnore]` | `System.Xml.Serialization` | Prevent NT8 from serializing the property to workspace XML |
| `[NinjaScriptProperty]` | `NinjaTrader.NinjaScript` | Mark property as a user-configurable input (persisted in workspace) |
| `[Display(...)]` | `System.ComponentModel.DataAnnotations` | Control label, order, and group in the NT8 dialog |
| `[Range(min, max)]` | `System.ComponentModel.DataAnnotations` | Validate numeric input range in the NT8 dialog |

## Required Usings for Attributes

```csharp
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Xml.Serialization;
using NinjaTrader.NinjaScript;
```

## Example Fix

```diff
  namespace NinjaTrader.NinjaScript.Indicators.DEEP6
  {
      public class DEEP6Footprint : Indicator
      {
+         [Browsable(false)]
+         [XmlIgnore]
          public Series<double> BidVolume { get; set; }

+         [Browsable(false)]
+         [XmlIgnore]
          public Series<double> AskVolume { get; set; }

+         [NinjaScriptProperty]
+         [Display(Name = "Tick Size", Order = 1, GroupName = "Parameters")]
          public double TickSize { get; set; }
      }
  }
```
