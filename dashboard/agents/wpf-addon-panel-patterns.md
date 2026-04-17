I have enough. Now let me synthesize the comprehensive WPF/XAML reference.

---

# DEEP6 — NinjaTrader 8 Modern WPF/XAML AddOn & Panel Reference

The "chrome layer" companion to the SharpDX rendering reference. Everything you need to make NT8 stop looking like Win95 and start looking like Linear/Stripe/Quantower while persisting cleanly into NT8 workspaces.

---

## 0. The Mental Model

NT8 is a multi-UI-thread WPF host. It exposes three layers your code can attach to:

| Layer | What it is | Your hook |
|---|---|---|
| **AddOn** | Cross-cutting, runs whenever NT is up | `AddOnBase` subclass. Singleton-ish per assembly. |
| **NTWindow** | A top-level themed Window equivalent to Control Center / Chart / SuperDOM | `class : NTWindow, IWorkspacePersistence` |
| **NTTabPage** | A movable, persistable tab inside an NTWindow (or ANY NT window) | `class : NTTabPage` with optional `IInstrumentProvider`/`IIntervalProvider` |

Critical NT8-specific quirks every AddOn must respect:

1. **Multiple UI threads.** NT spawns one UI thread per logical CPU core. `Core.Globals.RandomDispatcher` picks one at random; `someWindow.Dispatcher` targets that window's thread. If you touch a Brush/Visual that lives on thread A from thread B, you crash.
2. **Custom brushes must be `.Freeze()`d.** From NT's "Working with Brushes" docs: "Anytime you create a custom brush that will be used by NinjaTrader rendering it must be frozen using the `.Freeze()` method due to the multi-threaded nature of NinjaTrader."
3. **Skin = ResourceDictionary on disk.** `Documents\NinjaTrader 8\templates\Skins\{Light,Dark,SlateGrey,SlateLight,SlateDark}\BluePrint.xaml`. Use `DynamicResource` for *every* brush so theme switching at runtime just works.
4. **`Caption`, not `Title`.** NT manages `Title` to combine selected tab header + window caption for the taskbar. Setting `Title` directly fights NT.
5. **Default constructor required** on any class that participates in workspace persistence. Cannot be a nested type.
6. **Visual Studio designer can't render NT controls/skins.** Run inside NT to actually see styling. Workaround: keep a parallel "preview" Window in the project with hardcoded brushes for design iteration.

---

## 1. AddOnBase — Lifecycle and Window Detection

`AddOnBase` is the entry point. NT calls `OnStateChange` (`SetDefaults` → `Configure` → `Active` → `Terminated`) on every reload, then forwards `OnWindowCreated` / `OnWindowDestroyed` for every NTWindow that comes into existence.

```csharp
using System;
using System.Windows;
using System.Windows.Controls;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core;

namespace NinjaTrader.NinjaScript.AddOns.Deep6
{
    public class Deep6AddOn : AddOnBase
    {
        private NTMenuItem deep6RootMenu;
        private NTMenuItem newMenuItem;          // injected under Control Center "New"
        private NTMenuItem existingNewMenu;      // cached reference to NT's "New" submenu

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "DEEP6";
                Description = "DEEP6 footprint auto-trading shell";
            }
            else if (State == State.Terminated)
            {
                // Defensive — OnWindowDestroyed normally handles this, but
                // if NT is shutting down hard we may not get the destroy callback.
                TearDownMenu();
            }
        }

        protected override void OnWindowCreated(Window window)
        {
            // ControlCenter is the only window we want to mutate the menu of.
            ControlCenter cc = window as ControlCenter;
            if (cc == null) return;

            existingNewMenu = cc.FindFirst("ControlCenterMenuItemNew") as NTMenuItem;
            if (existingNewMenu == null) return;

            newMenuItem = new NTMenuItem
            {
                Header = "DEEP6 Dashboard",
                Style  = Application.Current.TryFindResource("MainMenuItem") as Style
            };
            newMenuItem.Click += OnDashboardClick;

            existingNewMenu.Items.Add(newMenuItem);
        }

        protected override void OnWindowDestroyed(Window window)
        {
            // Only act when the SPECIFIC ControlCenter that we attached to is closed.
            if (window is ControlCenter && newMenuItem != null)
                TearDownMenu();
        }

        private void TearDownMenu()
        {
            if (newMenuItem == null) return;
            newMenuItem.Click -= OnDashboardClick;
            if (existingNewMenu != null && existingNewMenu.Items.Contains(newMenuItem))
                existingNewMenu.Items.Remove(newMenuItem);
            newMenuItem      = null;
            existingNewMenu  = null;
        }

        private void OnDashboardClick(object sender, RoutedEventArgs e)
        {
            // Always launch new windows via a UI dispatcher.
            // Use the dispatcher of the window that emitted the click — guarantees
            // the new window lives on a known UI thread.
            var dispatcher = (sender as DependencyObject)?.Dispatcher
                              ?? Globals.RandomDispatcher;
            dispatcher.InvokeAsync(() => new Deep6DashboardWindow().Show());
        }
    }
}
```

**Sequence for every window:** `OnWindowCreated` fires in *that window's* UI thread. Cast aggressively. Common types you'll see flow past:

```csharp
if (window is ControlCenter cc)              { ... }
else if (window is Chart chart)              { ... }   // NinjaTrader.Gui.Chart.Chart
else if (window is NinjaTrader.Gui.SuperDom.SuperDom dom) { ... }
else if (window is NinjaTrader.Gui.NinjaScript.StrategyAnalyzer.StrategyAnalyzer sa) { ... }
```

**Hot-reload** — when you press F5 in NinjaScript Editor, NT unloads and reloads the assembly. `Terminated` runs, then a fresh `OnStateChange` cycle. If you didn't unsubscribe in `OnWindowDestroyed` / `Terminated`, you leak event handlers and your menu items duplicate.

**`Globals.RandomDispatcher` vs window dispatcher** — *always prefer the window's own dispatcher when you have one.* `RandomDispatcher` picks any UI thread, which means a new top-level window can land on a thread different from the one its parent control thinks it lives on. From NT support: BeginInvoke can lock the UI thread; **prefer `InvokeAsync`** for fire-and-forget work, and `Invoke` only when you genuinely must block.

---

## 2. NTWindow + IWorkspacePersistence — The Container

The minimum viable, workspace-persistable NTWindow:

```csharp
using System;
using System.Windows;
using System.Windows.Controls;
using System.Xml.Linq;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;

namespace NinjaTrader.NinjaScript.AddOns.Deep6
{
    public class Deep6DashboardWindow : NTWindow, IWorkspacePersistence
    {
        public Deep6DashboardWindow() : base()
        {
            // 1. Theming — we MUST use Caption, not Title.
            Caption = "DEEP6 Dashboard";
            Width   = 1280;
            Height  = 800;

            // 2. Pull NT8 themed app resources into our window scope so the
            //    designer-time XAML in our DataTemplates picks them up.
            Resources.MergedDictionaries.Add(
                new ResourceDictionary
                {
                    Source = new Uri(
                        "/NinjaTrader.Custom;component/AddOns/Deep6/Themes/Deep6.xaml",
                        UriKind.Relative)
                });

            // 3. TabControl as content (matches NT8 native look — every NT window is tabbed)
            var tc = new TabControl();
            TabControlManager.SetIsMovable(tc, true);
            TabControlManager.SetCanAddTabs(tc, true);
            TabControlManager.SetCanRemoveTabs(tc, true);
            TabControlManager.SetFactory(tc, new Deep6TabFactory());
            Content = tc;

            // 4. Seed with a default tab
            tc.AddNTTabPage(new SignalMonitorTab());

            // 5. Workspace identity. The GUID portion makes the window unique per
            //    instance so multiple copies persist independently.
            Loaded += (_, __) =>
            {
                if (WorkspaceOptions == null)
                    WorkspaceOptions = new WorkspaceOptions(
                        "Deep6Dashboard-" + Guid.NewGuid().ToString("N"), this);
            };
        }

        // --- IWorkspacePersistence ------------------------------------------------
        public WorkspaceOptions WorkspaceOptions { get; set; }

        public void Save(XDocument document, XElement element)
        {
            if (MainTabControl != null)
                MainTabControl.SaveToXElement(element);

            // Persist additional state by appending children to `element`
            element.Add(new XElement("Deep6State",
                new XAttribute("ActiveStrategy", _activeStrategy ?? "")));
        }

        public void Restore(XDocument document, XElement element)
        {
            if (MainTabControl != null)
                MainTabControl.RestoreFromXElement(element);

            var st = element.Element("Deep6State");
            if (st != null) _activeStrategy = (string)st.Attribute("ActiveStrategy");
        }

        private string _activeStrategy;
    }
}
```

**Critical rules** (these are all enforced by NT and will silently break workspace recall if violated):

| Rule | Why |
|---|---|
| **Default (parameterless) constructor required** | NT instantiates the type via reflection during workspace restore |
| **Cannot be a nested class** | Same reason |
| **Use `Caption`, not `Title`** | NT composes `Title` from the active tab + caption to drive the Windows taskbar text |
| **Set `WorkspaceOptions` in `Loaded`, not the ctor** | At ctor time WPF hasn't assigned a Dispatcher to the window yet; some skin resources aren't bound either |
| **Use a unique GUID-suffixed key** | Otherwise two instances clobber each other's persistence |
| **Add `MergedDictionaries` early** | DataTemplates inside tabs resolve `DynamicResource` lookups from the window's resource scope |
| **`MainTabControl` is read-only on NTWindow** and is automatically populated when you set `Content = tc` where `tc` is a `TabControl` |

**Z-order / always-on-top:** `Topmost = true` works as standard WPF. NT respects it. Good for Connection Status mini-panels.

**Multi-monitor recovery:** NT persists position via `WorkspaceOptions`. To survive monitor disconnect, override `OnSourceInitialized` and clamp to `SystemParameters.VirtualScreenLeft/Top/Width/Height` before showing.

```csharp
protected override void OnSourceInitialized(EventArgs e)
{
    base.OnSourceInitialized(e);
    var vsLeft   = SystemParameters.VirtualScreenLeft;
    var vsTop    = SystemParameters.VirtualScreenTop;
    var vsRight  = vsLeft + SystemParameters.VirtualScreenWidth;
    var vsBottom = vsTop  + SystemParameters.VirtualScreenHeight;
    if (Left + 100 > vsRight  || Left + Width  - 100 < vsLeft) Left = vsLeft + 40;
    if (Top  + 40  > vsBottom || Top  + Height - 100 < vsTop)  Top  = vsTop  + 40;
}
```

---

## 3. Control Center Menu Integration

You can add to any of these submenus by Automation ID — these are confirmed by NT support:

| Automation ID | Where it appears |
|---|---|
| `ControlCenterMenuItemNew` | The **New** menu (recommended for "open a window") |
| `toolsMenuItem` | Tools menu |
| `workspacesMenuItem` | Workspaces menu |
| `connectionsMenuItem` | Connections menu |
| `helpMenuItem` | Help menu |

Two important style resources:

| Style | Purpose |
|---|---|
| `MainMenuItem` | A regular click menu item, themed |
| `MainMenuToggleButton` | A toggleable item (checked/unchecked state) |

UX rules:

- **Anything that opens a window goes under New** — that's the convention NT users have learned.
- **Anything that mutates global state goes under Tools.**
- **Submenu vs flat:** if you have ≤2 entries, put them flat under Tools. If you have 3+, group them under a single `DEEP6 ▸` parent submenu.
- **Icons:** prefer a **glyph font** (Segoe Fluent Icons is on every Win10/11 box; or ship Lucide Icons as a font). Don't use `BitmapImage` — it doesn't respect theme switches and looks wrong at high DPI.

Sub-menu pattern with a glyph font icon:

```csharp
var deep6Root = new NTMenuItem
{
    Header = "DEEP6",
    Style  = Application.Current.TryFindResource("MainMenuItem") as Style
};

var dash = new NTMenuItem { Header = BuildHeader("\uE7C3", "Dashboard"), Style = miStyle };
var sigs = new NTMenuItem { Header = BuildHeader("\uE9F5", "Signal Monitor"), Style = miStyle };
var risk = new NTMenuItem { Header = BuildHeader("\uE7BA", "Risk Manager"), Style = miStyle };

deep6Root.Items.Add(dash);
deep6Root.Items.Add(sigs);
deep6Root.Items.Add(risk);
existingNewMenu.Items.Add(deep6Root);

// Helper — produces a horizontal StackPanel of [glyph][text] for the menu Header
static object BuildHeader(string glyph, string text)
{
    var sp = new StackPanel { Orientation = Orientation.Horizontal };
    sp.Children.Add(new TextBlock {
        Text = glyph, FontFamily = new FontFamily("Segoe Fluent Icons"),
        Width = 18, Margin = new Thickness(0,0,8,0), VerticalAlignment = VerticalAlignment.Center
    });
    sp.Children.Add(new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center });
    return sp;
}
```

---

## 4. NTTabPage + INTTabFactory — Movable Tabs

The reason to use `NTTabPage` instead of a plain WPF `TabItem`: **the user can drag your tab between any NT windows that opt into tab movement**, and NT will reconstruct it via your `INTTabFactory.CreateTabPage(typeName, true)` call. This is the same mechanism that lets you tear a chart into its own window.

```csharp
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;

public class Deep6TabFactory : INTTabFactory
{
    public NTWindow CreateParentWindow() => new Deep6DashboardWindow();

    public NTTabPage CreateTabPage(string typeName, bool isTrue)
    {
        switch (typeName)
        {
            case nameof(SignalMonitorTab):  return new SignalMonitorTab();
            case nameof(TradeJournalTab):   return new TradeJournalTab();
            case nameof(ReplayScrubberTab): return new ReplayScrubberTab();
            case nameof(PositionManagerTab):return new PositionManagerTab();
            case nameof(RiskDashboardTab):  return new RiskDashboardTab();
            default:                        return new SignalMonitorTab();
        }
    }
}
```

A tab that participates in instrument linking (the colored circle in the top-right of native NT tabs) and interval linking:

```csharp
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui.Tools;

public class SignalMonitorTab : NTTabPage, IInstrumentProvider, IIntervalProvider
{
    private Instrument _instrument;
    private BarsPeriod _barsPeriod;
    private SignalMonitorView _view;

    public SignalMonitorTab()
    {
        TabName = "Signals";
        _view = new SignalMonitorView();
        Content = _view;
    }

    // --- IInstrumentProvider ---
    // NOTE: hide the base Instrument property. Setter must call PropagateInstrumentChange.
    public new Instrument Instrument
    {
        get => _instrument;
        set
        {
            if (_instrument != null) UnsubscribeFromInstrument(_instrument);
            _instrument = value;
            if (_instrument != null) SubscribeToInstrument(_instrument);

            PropagateInstrumentChange(value); // <-- this is what colors the dot
            RefreshHeader();                  // <-- updates the tab title with the symbol
            _view.ViewModel.Instrument = value;
        }
    }

    // --- IIntervalProvider ---
    public new BarsPeriod BarsPeriod
    {
        get => _barsPeriod;
        set
        {
            _barsPeriod = value;
            PropagateIntervalChange(value);
            RefreshHeader();
            _view.ViewModel.BarsPeriod = value;
        }
    }

    // --- Persistence per-tab ---
    protected override string GetHeaderPart() => _instrument?.MasterInstrument?.Name ?? "Signals";

    private void SubscribeToInstrument(Instrument i)   { /* attach Cbi.MarketData handlers */ }
    private void UnsubscribeFromInstrument(Instrument i){ /* detach */ }
}
```

**Tab linkage colors** — when the user picks a colored circle (red/blue/green/yellow/orange) in the native NT tab, that color is a *channel*. All tabs (across all NT windows) sharing the same color receive `PropagateInstrumentChange` notifications when *any* of them changes instrument. Implement `IInstrumentProvider` and call `PropagateInstrumentChange(value)` in your setter — NT handles the channel routing internally. You don't render the color circle yourself; it appears automatically because you implement the interface.

**Per-tab persistence** — `NTTabPage` has its own `Save`/`Restore` overload signature that the parent's `MainTabControl.SaveToXElement` / `RestoreFromXElement` will fan out to. Override these on your tab class to save filter state, sort order, etc.

---

## 5. WPF MVVM Inside NinjaScript

NT8 ships .NET Framework 4.8 (cannot use newer). That means **CommunityToolkit.Mvvm 8.x** works — just drop the DLL into `Documents\NinjaTrader 8\bin\Custom\` and add the reference via *Right-click → References* in NinjaScript Editor.

If you want zero external dependencies, hand-roll it. Here's a minimal toolkit you can paste into one file:

```csharp
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Input;

namespace NinjaTrader.NinjaScript.AddOns.Deep6.Mvvm
{
    public abstract class ViewModelBase : INotifyPropertyChanged
    {
        public event PropertyChangedEventHandler PropertyChanged;

        protected bool Set<T>(ref T field, T value, [CallerMemberName] string name = null)
        {
            if (EqualityComparer<T>.Default.Equals(field, value)) return false;
            field = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
            return true;
        }

        protected void Raise([CallerMemberName] string name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    public sealed class RelayCommand : ICommand
    {
        private readonly Action<object> _exec;
        private readonly Predicate<object> _can;
        public RelayCommand(Action<object> exec, Predicate<object> can = null)
        { _exec = exec; _can = can; }

        public bool CanExecute(object p) => _can?.Invoke(p) ?? true;
        public void Execute(object p)    => _exec(p);

        public event EventHandler CanExecuteChanged
        {
            add    { CommandManager.RequerySuggested += value; }
            remove { CommandManager.RequerySuggested -= value; }
        }
        public void Raise() => CommandManager.InvalidateRequerySuggested();
    }
}
```

**Threading discipline** — this is where 99% of NT8 WPF panels die. The signal engine pushes 1000+ updates/sec. If every push hits `ObservableCollection.Add` on a background thread, WPF crashes. Two patterns:

### Pattern A — `BindingOperations.EnableCollectionSynchronization` (simple; up to ~100 updates/sec)

```csharp
private readonly object _signalsLock = new object();
public ObservableCollection<SignalRow> Signals { get; } = new ObservableCollection<SignalRow>();

public SignalsViewModel()
{
    BindingOperations.EnableCollectionSynchronization(Signals, _signalsLock);
}

// Called from Rithmic worker thread — safe!
public void OnSignalDetected(SignalRow row)
{
    lock (_signalsLock) { Signals.Insert(0, row); }
}
```

### Pattern B — Producer batching with a 30 Hz UI flush (correct for 1000+ updates/sec)

```csharp
private readonly ConcurrentQueue<SignalRow> _pending = new ConcurrentQueue<SignalRow>();
private readonly DispatcherTimer _flushTimer;

public SignalsViewModel(Dispatcher dispatcher)
{
    _flushTimer = new DispatcherTimer(DispatcherPriority.Background, dispatcher)
    {
        Interval = TimeSpan.FromMilliseconds(33) // ~30 Hz
    };
    _flushTimer.Tick += FlushPending;
    _flushTimer.Start();
}

// Called from any thread — never touches UI
public void Enqueue(SignalRow row) => _pending.Enqueue(row);

// UI thread, batched
private void FlushPending(object s, EventArgs e)
{
    var batch = new List<SignalRow>(64);
    while (_pending.TryDequeue(out var r) && batch.Count < 256) batch.Add(r);
    if (batch.Count == 0) return;

    // Insert in one shot; suppress per-add notifications by using AddRange via a derived class
    foreach (var r in batch) Signals.Insert(0, r);
    while (Signals.Count > 5000) Signals.RemoveAt(Signals.Count - 1); // cap memory
}
```

**Decision:** for tape/signal feeds use Pattern B. The 30 Hz batching gives you smooth visual updates without the `INotifyCollectionChanged` storm.

---

## 6. The Theme System — Resource Dictionary with Design Tokens

This is where you stop looking like NT8 and start looking like Linear. Build a single `Themes/Deep6.xaml` and reference *only* `DynamicResource` in your XAML. When NT user switches skin, your panel switches with it.

### `Themes/Deep6.xaml` — design tokens

```xml
<ResourceDictionary
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    xmlns:sys="clr-namespace:System;assembly=mscorlib">

    <!-- ============================================================ -->
    <!-- COLOR PRIMITIVES — change these and the whole UI shifts     -->
    <!-- ============================================================ -->
    <Color x:Key="Color.Surface.0">#0B0E14</Color>  <!-- canvas       -->
    <Color x:Key="Color.Surface.1">#11151C</Color>  <!-- card         -->
    <Color x:Key="Color.Surface.2">#1A1F29</Color>  <!-- raised       -->
    <Color x:Key="Color.Surface.3">#242A36</Color>  <!-- hovered      -->
    <Color x:Key="Color.Border.Subtle">#1F2530</Color>
    <Color x:Key="Color.Border.Strong">#2E3645</Color>

    <Color x:Key="Color.Text.Primary">#E6EAF2</Color>
    <Color x:Key="Color.Text.Secondary">#9AA3B2</Color>
    <Color x:Key="Color.Text.Tertiary">#5E6675</Color>
    <Color x:Key="Color.Text.OnAccent">#0B0E14</Color>

    <Color x:Key="Color.Accent">#7C5CFF</Color>     <!-- DEEP6 violet -->
    <Color x:Key="Color.Accent.Hover">#8E72FF</Color>
    <Color x:Key="Color.Long">#26D195</Color>       <!-- bid green    -->
    <Color x:Key="Color.Short">#FF5577</Color>      <!-- ask red      -->
    <Color x:Key="Color.Warning">#FFB547</Color>
    <Color x:Key="Color.Danger">#FF4D6A</Color>

    <!-- ============================================================ -->
    <!-- BRUSHES — every UI element references these via DynamicResource -->
    <!-- ============================================================ -->
    <SolidColorBrush x:Key="Brush.Surface.0" Color="{DynamicResource Color.Surface.0}"/>
    <SolidColorBrush x:Key="Brush.Surface.1" Color="{DynamicResource Color.Surface.1}"/>
    <SolidColorBrush x:Key="Brush.Surface.2" Color="{DynamicResource Color.Surface.2}"/>
    <SolidColorBrush x:Key="Brush.Surface.3" Color="{DynamicResource Color.Surface.3}"/>
    <SolidColorBrush x:Key="Brush.Border.Subtle" Color="{DynamicResource Color.Border.Subtle}"/>
    <SolidColorBrush x:Key="Brush.Border.Strong" Color="{DynamicResource Color.Border.Strong}"/>
    <SolidColorBrush x:Key="Brush.Text.Primary" Color="{DynamicResource Color.Text.Primary}"/>
    <SolidColorBrush x:Key="Brush.Text.Secondary" Color="{DynamicResource Color.Text.Secondary}"/>
    <SolidColorBrush x:Key="Brush.Text.Tertiary" Color="{DynamicResource Color.Text.Tertiary}"/>
    <SolidColorBrush x:Key="Brush.Accent" Color="{DynamicResource Color.Accent}"/>
    <SolidColorBrush x:Key="Brush.Accent.Hover" Color="{DynamicResource Color.Accent.Hover}"/>
    <SolidColorBrush x:Key="Brush.Long"  Color="{DynamicResource Color.Long}"/>
    <SolidColorBrush x:Key="Brush.Short" Color="{DynamicResource Color.Short}"/>

    <!-- ============================================================ -->
    <!-- TYPOGRAPHY                                                   -->
    <!-- ============================================================ -->
    <FontFamily x:Key="Font.Sans">
        pack://application:,,,/NinjaTrader.Custom;component/AddOns/Deep6/Fonts/#Inter
    </FontFamily>
    <FontFamily x:Key="Font.Mono">
        pack://application:,,,/NinjaTrader.Custom;component/AddOns/Deep6/Fonts/#JetBrains Mono
    </FontFamily>
    <FontFamily x:Key="Font.Icon">Segoe Fluent Icons</FontFamily>

    <sys:Double x:Key="Font.Size.Xs">11</sys:Double>
    <sys:Double x:Key="Font.Size.Sm">12</sys:Double>
    <sys:Double x:Key="Font.Size.Md">13</sys:Double>
    <sys:Double x:Key="Font.Size.Lg">15</sys:Double>
    <sys:Double x:Key="Font.Size.Xl">20</sys:Double>
    <sys:Double x:Key="Font.Size.Display">32</sys:Double>

    <!-- ============================================================ -->
    <!-- SPACING (4-pt grid)                                          -->
    <!-- ============================================================ -->
    <Thickness x:Key="Pad.Xs">4</Thickness>
    <Thickness x:Key="Pad.Sm">8</Thickness>
    <Thickness x:Key="Pad.Md">12</Thickness>
    <Thickness x:Key="Pad.Lg">16</Thickness>
    <Thickness x:Key="Pad.Xl">24</Thickness>

    <CornerRadius x:Key="Radius.Sm">4</CornerRadius>
    <CornerRadius x:Key="Radius.Md">6</CornerRadius>
    <CornerRadius x:Key="Radius.Lg">10</CornerRadius>
    <CornerRadius x:Key="Radius.Pill">999</CornerRadius>

    <!-- ============================================================ -->
    <!-- SHADOWS — used as DropShadowEffect                          -->
    <!-- ============================================================ -->
    <DropShadowEffect x:Key="Shadow.Sm" BlurRadius="6"  ShadowDepth="2"  Opacity="0.25" Color="Black"/>
    <DropShadowEffect x:Key="Shadow.Md" BlurRadius="14" ShadowDepth="4"  Opacity="0.32" Color="Black"/>
    <DropShadowEffect x:Key="Shadow.Lg" BlurRadius="26" ShadowDepth="8"  Opacity="0.40" Color="Black"/>

    <!-- ============================================================ -->
    <!-- MOTION                                                      -->
    <!-- ============================================================ -->
    <Duration x:Key="Motion.Fast">0:0:0.12</Duration>
    <Duration x:Key="Motion.Med">0:0:0.20</Duration>
    <Duration x:Key="Motion.Slow">0:0:0.36</Duration>

    <CubicEase x:Key="Ease.Out" EasingMode="EaseOut"/>
    <CubicEase x:Key="Ease.InOut" EasingMode="EaseInOut"/>
</ResourceDictionary>
```

**Why `DynamicResource` everywhere:** NT changes skin by swapping the merged resource dictionary at runtime. `StaticResource` snapshots the value at parse time and never updates.

**Bridging to NT's own brushes:** when you want your panel to *automatically* match NT's chart background or volume column color, alias them in your dictionary so consumers never reference both:

```xml
<!-- inside Deep6.xaml -->
<SolidColorBrush x:Key="Brush.Chart.Background"
                 Color="{Binding Color, Source={DynamicResource immutableBrushChartBackground}}"/>
```

(NT's known internal keys include `BorderThinBrush`, `immutableBrushVolumeColumnForeground`, `WindowBottomGradientStopColor`, `BackgroundCaptionBar`, `BackgroundCaptionBarInactive`. Inspect `Documents\NinjaTrader 8\templates\Skins\Dark\BluePrint.xaml` for the full list.)

---

## 7. Modern Button, ScrollBar, and Borderless Window — The Style Replacements

### Modern Button

```xml
<Style x:Key="Btn.Primary" TargetType="Button">
    <Setter Property="Background"      Value="{DynamicResource Brush.Accent}"/>
    <Setter Property="Foreground"      Value="{DynamicResource Brush.Text.OnAccent}"/>
    <Setter Property="FontFamily"      Value="{DynamicResource Font.Sans}"/>
    <Setter Property="FontSize"        Value="{DynamicResource Font.Size.Sm}"/>
    <Setter Property="FontWeight"      Value="SemiBold"/>
    <Setter Property="Padding"         Value="14,8"/>
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="Cursor"          Value="Hand"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="TextOptions.TextFormattingMode" Value="Display"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Border x:Name="Bd"
                        Background="{TemplateBinding Background}"
                        CornerRadius="{DynamicResource Radius.Md}"
                        SnapsToDevicePixels="True">
                    <ContentPresenter HorizontalAlignment="Center"
                                      VerticalAlignment="Center"
                                      Margin="{TemplateBinding Padding}"
                                      RecognizesAccessKey="True"/>
                </Border>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Setter TargetName="Bd" Property="Background"
                                Value="{DynamicResource Brush.Accent.Hover}"/>
                    </Trigger>
                    <Trigger Property="IsPressed" Value="True">
                        <Setter TargetName="Bd" Property="RenderTransform">
                            <Setter.Value><ScaleTransform ScaleX="0.98" ScaleY="0.98"/></Setter.Value>
                        </Setter>
                        <Setter TargetName="Bd" Property="RenderTransformOrigin" Value="0.5,0.5"/>
                    </Trigger>
                    <Trigger Property="IsEnabled" Value="False">
                        <Setter TargetName="Bd" Property="Opacity" Value="0.4"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>

<Style x:Key="Btn.Ghost" TargetType="Button" BasedOn="{StaticResource Btn.Primary}">
    <Setter Property="Background" Value="Transparent"/>
    <Setter Property="Foreground" Value="{DynamicResource Brush.Text.Primary}"/>
    <Setter Property="BorderBrush" Value="{DynamicResource Brush.Border.Strong}"/>
    <Setter Property="BorderThickness" Value="1"/>
</Style>
```

### Modern ScrollBar (thin, hover-reveal)

```xml
<Style x:Key="ModernScrollThumb" TargetType="Thumb">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Thumb">
                <Border CornerRadius="3"
                        Background="{DynamicResource Brush.Border.Strong}"
                        Margin="2"/>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>

<Style TargetType="ScrollBar">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="Width" Value="6"/>
    <Setter Property="MinWidth" Value="6"/>
    <Setter Property="Background" Value="Transparent"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="ScrollBar">
                <Grid>
                    <Track Name="PART_Track" IsDirectionReversed="True">
                        <Track.Thumb>
                            <Thumb Style="{StaticResource ModernScrollThumb}"/>
                        </Track.Thumb>
                        <!-- No RepeatButtons — kills the arrows -->
                        <Track.IncreaseRepeatButton>
                            <RepeatButton Command="ScrollBar.PageDownCommand" Opacity="0"/>
                        </Track.IncreaseRepeatButton>
                        <Track.DecreaseRepeatButton>
                            <RepeatButton Command="ScrollBar.PageUpCommand" Opacity="0"/>
                        </Track.DecreaseRepeatButton>
                    </Track>
                </Grid>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Setter Property="Width" Value="10"/>
                    </Trigger>
                    <Trigger Property="Orientation" Value="Horizontal">
                        <Setter Property="Width" Value="Auto"/>
                        <Setter Property="Height" Value="6"/>
                        <Setter Property="MinHeight" Value="6"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### Borderless NTWindow with custom chrome

NTWindow inherits from `Window`, so `WindowChrome` works. Don't set `WindowStyle="None"` *and* keep `ResizeMode="CanResize"` — combine `WindowChrome` for proper aero-snap, drag-to-maximize, and shake-to-minimize behavior preserved.

```xml
<shell:WindowChrome.WindowChrome>
    <shell:WindowChrome
        CaptionHeight="36"
        CornerRadius="0"
        GlassFrameThickness="0"
        ResizeBorderThickness="6"
        UseAeroCaptionButtons="False"/>
</shell:WindowChrome.WindowChrome>
```

Then in your `Style` for the window template, build your own title bar:

```xml
<Border Background="{DynamicResource Brush.Surface.1}" Height="36"
        VerticalAlignment="Top" Panel.ZIndex="100">
    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <TextBlock Text="{TemplateBinding Caption}"
                   Foreground="{DynamicResource Brush.Text.Primary}"
                   FontSize="{DynamicResource Font.Size.Sm}"
                   VerticalAlignment="Center" Margin="14,0,0,0"/>
        <StackPanel Grid.Column="1" Orientation="Horizontal"
                    shell:WindowChrome.IsHitTestVisibleInChrome="True">
            <Button Style="{StaticResource Btn.Ghost}" Content="—" Click="Minimize"/>
            <Button Style="{StaticResource Btn.Ghost}" Content="□" Click="MaxRestore"/>
            <Button Style="{StaticResource Btn.Ghost}" Content="✕" Click="CloseW"/>
        </StackPanel>
    </Grid>
</Border>
```

The `IsHitTestVisibleInChrome="True"` is the trick — it carves your buttons out of the drag area.

### Acrylic / Mica on Windows 11

```csharp
[DllImport("dwmapi.dll")]
static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int val, int sz);

protected override void OnSourceInitialized(EventArgs e)
{
    base.OnSourceInitialized(e);
    var hwnd = new WindowInteropHelper(this).Handle;

    // Enable dark mode (DWMWA_USE_IMMERSIVE_DARK_MODE)
    int dark = 1;
    DwmSetWindowAttribute(hwnd, 20, ref dark, sizeof(int));

    // Enable Mica backdrop (DWMWA_SYSTEMBACKDROP_TYPE)
    int backdrop = 2; // 2 = Mica, 3 = Acrylic, 4 = Tabbed
    DwmSetWindowAttribute(hwnd, 38, ref backdrop, sizeof(int));
}
```

`Background` on the window must be `Transparent` and you must clear the WPF chrome via `WindowChrome` for the backdrop to show through. **Important caveat from MSFT issue tracker:** calling `DwmExtendFrameIntoClientArea` *after* setting the backdrop turns it opaque — call it with empty MARGINS first or skip it entirely when using Mica.

---

## 8. Library Decision Tables

### UI framework integration

| Library | Use it for | Risks in NT8 |
|---|---|---|
| **MahApps.Metro** | Pre-built modern Windows UI controls (toggles, accents, dialogs). Fast to ship. | Pulls `ControlzEx` and `Microsoft.Xaml.Behaviors.Wpf`. Version conflicts if NT updates its own bundled assemblies. Adds ~2.5 MB of DLLs to ship. |
| **ModernWpf (Kinnara)** | WinUI-look styles for stock WPF controls. ToggleSwitch, NavigationView. | Less actively maintained (last meaningful release 2022). Solid for WinUI 2 look but no Windows 11 Mica/Fluent v2 polish. |
| **HandyControl** | Broad control set, Chinese-origin docs but solid quality. | Big surface area; you'll only use 5%. |
| **Roll your own** | DEEP6's signature controls (signal monitor, scrubber, KPI). | More work upfront, but zero version risk and you control every pixel. |

**Recommendation for DEEP6:** roll your own for the hero panels (the 7 specific recipes in §15). Use one of the libraries *only* for "background plumbing" controls (NumberBox, ColorPicker) you don't want to template.

### Charts inside panels (not the chart window)

| Library | License | Best for | Verdict |
|---|---|---|---|
| **LiveCharts2** | MIT (free); Pro plan unlocks more | Real-time OHLC, financial series, smooth animations | **Default pick.** Designed for live data, modern API. |
| **OxyPlot** | MIT | Static / low-update-rate technical plots | Avoid for tick rates above ~10 Hz; CPU-only render. |
| **ScottPlot** | MIT | Scientific plots, dense scatter, fast rendering | Good for backtest analytics tabs; less polished for live. |
| **InteractiveDataDisplay (D3)** | MIT (Microsoft Research) | Educational / prototyping | Stale, avoid for production. |
| **SciChart** | Commercial ($800+/dev/yr) | When you need DirectX-fast charts on top of LiveCharts2's level | Only if perf becomes a bottleneck — DEEP6's chart window already uses SharpDX so this is overkill in panels. |

For DEEP6 specifically: **LiveCharts2 in panels** for KPI sparklines, P&L curves, latency graphs. The main chart window uses your custom SharpDX renderer.

---

## 9. Panel Recipes

### 9.1 Signal Monitor — virtualized scrolling list with hot-row highlight

```xml
<UserControl x:Class="NinjaTrader.NinjaScript.AddOns.Deep6.Views.SignalMonitorView"
             xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
             xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
             xmlns:vm="clr-namespace:NinjaTrader.NinjaScript.AddOns.Deep6.ViewModels"
             Background="{DynamicResource Brush.Surface.0}"
             TextOptions.TextFormattingMode="Display"
             TextOptions.TextRenderingMode="ClearType"
             FontFamily="{DynamicResource Font.Sans}">

    <UserControl.DataContext>
        <vm:SignalMonitorViewModel/>
    </UserControl.DataContext>

    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/> <!-- header     -->
            <RowDefinition Height="*"/>    <!-- list       -->
            <RowDefinition Height="Auto"/> <!-- statusbar  -->
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <Border Grid.Row="0" Padding="14,10"
                Background="{DynamicResource Brush.Surface.1}"
                BorderThickness="0,0,0,1"
                BorderBrush="{DynamicResource Brush.Border.Subtle}">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
                    <Ellipse Width="8" Height="8" Margin="0,0,8,0"
                             Fill="{DynamicResource Brush.Long}"/>
                    <TextBlock Text="Signals — Live"
                               FontSize="{DynamicResource Font.Size.Md}"
                               FontWeight="SemiBold"
                               Foreground="{DynamicResource Brush.Text.Primary}"/>
                </StackPanel>
                <ToggleButton Grid.Column="1" Style="{StaticResource Toggle.Modern}"
                              IsChecked="{Binding ShowAbsorptionsOnly}"
                              Content="Absorptions only"/>
            </Grid>
        </Border>

        <!-- LIST -->
        <ListBox Grid.Row="1"
                 ItemsSource="{Binding Signals}"
                 Background="Transparent"
                 BorderThickness="0"
                 ScrollViewer.HorizontalScrollBarVisibility="Disabled"
                 ScrollViewer.VerticalScrollBarVisibility="Auto"
                 VirtualizingPanel.IsVirtualizing="True"
                 VirtualizingPanel.VirtualizationMode="Recycling"
                 VirtualizingPanel.ScrollUnit="Pixel">
            <ListBox.ItemContainerStyle>
                <Style TargetType="ListBoxItem">
                    <Setter Property="OverridesDefaultStyle" Value="True"/>
                    <Setter Property="Padding" Value="0"/>
                    <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
                    <Setter Property="Template">
                        <Setter.Value>
                            <ControlTemplate TargetType="ListBoxItem">
                                <Border x:Name="Bd"
                                        Background="Transparent"
                                        BorderBrush="{DynamicResource Brush.Border.Subtle}"
                                        BorderThickness="0,0,0,1">
                                    <ContentPresenter/>
                                </Border>
                                <ControlTemplate.Triggers>
                                    <Trigger Property="IsMouseOver" Value="True">
                                        <Setter TargetName="Bd" Property="Background"
                                                Value="{DynamicResource Brush.Surface.2}"/>
                                    </Trigger>
                                </ControlTemplate.Triggers>
                            </ControlTemplate>
                        </Setter.Value>
                    </Setter>
                </Style>
            </ListBox.ItemContainerStyle>

            <ListBox.ItemTemplate>
                <DataTemplate>
                    <Grid Height="44" Margin="14,0">
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="6"/>      <!-- side bar -->
                            <ColumnDefinition Width="80"/>     <!-- time      -->
                            <ColumnDefinition Width="60"/>     <!-- symbol    -->
                            <ColumnDefinition Width="*"/>      <!-- type      -->
                            <ColumnDefinition Width="60"/>     <!-- conf      -->
                            <ColumnDefinition Width="80"/>     <!-- price     -->
                        </Grid.ColumnDefinitions>

                        <!-- side accent bar -->
                        <Rectangle Width="3" Margin="0,8" RadiusX="2" RadiusY="2"
                                   HorizontalAlignment="Left">
                            <Rectangle.Style>
                                <Style TargetType="Rectangle">
                                    <Setter Property="Fill" Value="{DynamicResource Brush.Accent}"/>
                                    <Style.Triggers>
                                        <DataTrigger Binding="{Binding Side}" Value="Long">
                                            <Setter Property="Fill" Value="{DynamicResource Brush.Long}"/>
                                        </DataTrigger>
                                        <DataTrigger Binding="{Binding Side}" Value="Short">
                                            <Setter Property="Fill" Value="{DynamicResource Brush.Short}"/>
                                        </DataTrigger>
                                    </Style.Triggers>
                                </Style>
                            </Rectangle.Style>
                        </Rectangle>

                        <TextBlock Grid.Column="1"
                                   Text="{Binding Timestamp, StringFormat=HH:mm:ss}"
                                   FontFamily="{DynamicResource Font.Mono}"
                                   FontSize="{DynamicResource Font.Size.Sm}"
                                   Foreground="{DynamicResource Brush.Text.Tertiary}"
                                   VerticalAlignment="Center" Margin="6,0,0,0"/>
                        <TextBlock Grid.Column="2"
                                   Text="{Binding Symbol}"
                                   FontWeight="SemiBold"
                                   Foreground="{DynamicResource Brush.Text.Primary}"
                                   VerticalAlignment="Center"/>
                        <TextBlock Grid.Column="3"
                                   Text="{Binding TypeLabel}"
                                   Foreground="{DynamicResource Brush.Text.Primary}"
                                   VerticalAlignment="Center"/>
                        <Border Grid.Column="4" Padding="6,2" CornerRadius="3"
                                Background="{DynamicResource Brush.Surface.3}"
                                HorizontalAlignment="Right" VerticalAlignment="Center">
                            <TextBlock Text="{Binding Confidence, StringFormat={}{0:P0}}"
                                       FontFamily="{DynamicResource Font.Mono}"
                                       FontSize="{DynamicResource Font.Size.Xs}"
                                       Foreground="{DynamicResource Brush.Text.Secondary}"/>
                        </Border>
                        <TextBlock Grid.Column="5"
                                   Text="{Binding Price, StringFormat={}{0:N2}}"
                                   FontFamily="{DynamicResource Font.Mono}"
                                   TextAlignment="Right"
                                   Foreground="{DynamicResource Brush.Text.Primary}"
                                   VerticalAlignment="Center"/>
                    </Grid>
                </DataTemplate>
            </ListBox.ItemTemplate>
        </ListBox>

        <!-- STATUS BAR -->
        <Border Grid.Row="2" Padding="14,6"
                Background="{DynamicResource Brush.Surface.1}"
                BorderThickness="0,1,0,0"
                BorderBrush="{DynamicResource Brush.Border.Subtle}">
            <TextBlock Text="{Binding StatusLine}"
                       FontFamily="{DynamicResource Font.Mono}"
                       FontSize="{DynamicResource Font.Size.Xs}"
                       Foreground="{DynamicResource Brush.Text.Tertiary}"/>
        </Border>
    </Grid>
</UserControl>
```

ViewModel skeleton:

```csharp
public sealed class SignalRow
{
    public DateTime Timestamp { get; set; }
    public string   Symbol    { get; set; }
    public string   TypeLabel { get; set; }   // "Absorption / Bid"
    public string   Side      { get; set; }   // "Long" | "Short"
    public double   Confidence{ get; set; }
    public double   Price     { get; set; }
}

public sealed class SignalMonitorViewModel : ViewModelBase
{
    private readonly object _lock = new object();
    public ObservableCollection<SignalRow> Signals { get; } = new ObservableCollection<SignalRow>();

    private bool _showAbsOnly;
    public bool ShowAbsorptionsOnly { get => _showAbsOnly; set => Set(ref _showAbsOnly, value); }

    private string _statusLine = "0 sig/s · ready";
    public string StatusLine { get => _statusLine; set => Set(ref _statusLine, value); }

    public SignalMonitorViewModel()
    {
        BindingOperations.EnableCollectionSynchronization(Signals, _lock);
    }
}
```

### 9.2 Trade Journal — sortable DataGrid with P&L heatmap rows

```xml
<DataGrid ItemsSource="{Binding Trades}"
          AutoGenerateColumns="False"
          CanUserAddRows="False"
          CanUserDeleteRows="False"
          GridLinesVisibility="None"
          HeadersVisibility="Column"
          SelectionMode="Extended"
          Background="Transparent"
          BorderThickness="0"
          RowHeight="32"
          VirtualizingPanel.IsVirtualizing="True"
          VirtualizingPanel.VirtualizationMode="Recycling"
          EnableRowVirtualization="True"
          EnableColumnVirtualization="True">

    <DataGrid.ColumnHeaderStyle>
        <Style TargetType="DataGridColumnHeader">
            <Setter Property="Background" Value="{DynamicResource Brush.Surface.1}"/>
            <Setter Property="Foreground" Value="{DynamicResource Brush.Text.Secondary}"/>
            <Setter Property="FontSize"   Value="{DynamicResource Font.Size.Xs}"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Padding"    Value="10,8"/>
            <Setter Property="BorderBrush" Value="{DynamicResource Brush.Border.Subtle}"/>
            <Setter Property="BorderThickness" Value="0,0,0,1"/>
            <Setter Property="HorizontalContentAlignment" Value="Left"/>
        </Style>
    </DataGrid.ColumnHeaderStyle>

    <DataGrid.RowStyle>
        <Style TargetType="DataGridRow">
            <Setter Property="Background" Value="Transparent"/>
            <Style.Triggers>
                <!-- Heatmap by P&L -->
                <DataTrigger Binding="{Binding PnLBucket}" Value="BigWin">
                    <Setter Property="Background">
                        <Setter.Value>
                            <SolidColorBrush Color="#26D195" Opacity="0.20"/>
                        </Setter.Value>
                    </Setter>
                </DataTrigger>
                <DataTrigger Binding="{Binding PnLBucket}" Value="Win">
                    <Setter Property="Background">
                        <Setter.Value><SolidColorBrush Color="#26D195" Opacity="0.08"/></Setter.Value>
                    </Setter>
                </DataTrigger>
                <DataTrigger Binding="{Binding PnLBucket}" Value="Loss">
                    <Setter Property="Background">
                        <Setter.Value><SolidColorBrush Color="#FF5577" Opacity="0.08"/></Setter.Value>
                    </Setter>
                </DataTrigger>
                <DataTrigger Binding="{Binding PnLBucket}" Value="BigLoss">
                    <Setter Property="Background">
                        <Setter.Value><SolidColorBrush Color="#FF5577" Opacity="0.20"/></Setter.Value>
                    </Setter>
                </DataTrigger>
                <Trigger Property="IsMouseOver" Value="True">
                    <Setter Property="Background" Value="{DynamicResource Brush.Surface.2}"/>
                </Trigger>
            </Style.Triggers>
        </Style>
    </DataGrid.RowStyle>

    <DataGrid.CellStyle>
        <Style TargetType="DataGridCell">
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Padding" Value="10,0"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="Foreground" Value="{DynamicResource Brush.Text.Primary}"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="DataGridCell">
                        <Border Background="{TemplateBinding Background}"
                                Padding="{TemplateBinding Padding}">
                            <ContentPresenter VerticalAlignment="Center"/>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </DataGrid.CellStyle>

    <DataGrid.Columns>
        <DataGridTextColumn Header="Time" Width="120"
            Binding="{Binding EntryTime, StringFormat=yyyy-MM-dd HH:mm:ss}"/>
        <DataGridTextColumn Header="Sym"  Width="60"  Binding="{Binding Symbol}"/>
        <DataGridTextColumn Header="Side" Width="50"  Binding="{Binding Side}"/>
        <DataGridTextColumn Header="Qty"  Width="50"  Binding="{Binding Qty}"/>
        <DataGridTextColumn Header="Entry" Width="80" Binding="{Binding Entry, StringFormat=N2}"/>
        <DataGridTextColumn Header="Exit"  Width="80" Binding="{Binding Exit,  StringFormat=N2}"/>
        <DataGridTextColumn Header="P&amp;L" Width="90"
            Binding="{Binding PnL, StringFormat=$#,##0.00;-$#,##0.00}">
            <DataGridTextColumn.ElementStyle>
                <Style TargetType="TextBlock">
                    <Setter Property="HorizontalAlignment" Value="Right"/>
                    <Setter Property="FontFamily" Value="{DynamicResource Font.Mono}"/>
                    <Style.Triggers>
                        <DataTrigger Binding="{Binding IsWin}" Value="True">
                            <Setter Property="Foreground" Value="{DynamicResource Brush.Long}"/>
                        </DataTrigger>
                        <DataTrigger Binding="{Binding IsWin}" Value="False">
                            <Setter Property="Foreground" Value="{DynamicResource Brush.Short}"/>
                        </DataTrigger>
                    </Style.Triggers>
                </Style>
            </DataGridTextColumn.ElementStyle>
        </DataGridTextColumn>
    </DataGrid.Columns>
</DataGrid>
```

The `PnLBucket` enum-like string is computed in your `TradeRow` viewmodel based on z-score-of-PnL — gives you the heatmap effect Linear/Stripe-style.

### 9.3 Replay Scrubber

```xml
<Border Padding="16" Background="{DynamicResource Brush.Surface.1}"
        CornerRadius="{DynamicResource Radius.Lg}"
        Effect="{DynamicResource Shadow.Md}">
    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- Transport controls -->
        <StackPanel Orientation="Horizontal" Margin="0,0,0,12">
            <Button Style="{StaticResource Btn.Ghost}" Content="⏮" Command="{Binding StepBackCommand}"/>
            <Button Style="{StaticResource Btn.Primary}" Content="{Binding PlayPauseGlyph}"
                    Command="{Binding PlayPauseCommand}" Width="44" Margin="6,0"/>
            <Button Style="{StaticResource Btn.Ghost}" Content="⏭" Command="{Binding StepForwardCommand}"/>
            <ComboBox ItemsSource="{Binding Speeds}"
                      SelectedItem="{Binding Speed}"
                      Margin="16,0,0,0" Width="80"/>
            <TextBlock Text="{Binding CurrentTime, StringFormat=yyyy-MM-dd HH:mm:ss.fff}"
                       FontFamily="{DynamicResource Font.Mono}"
                       Foreground="{DynamicResource Brush.Text.Secondary}"
                       VerticalAlignment="Center" Margin="20,0,0,0"/>
        </StackPanel>

        <!-- Timeline -->
        <Grid Grid.Row="1" Height="56">
            <Border Background="{DynamicResource Brush.Surface.0}"
                    CornerRadius="{DynamicResource Radius.Sm}"/>
            <!-- Bookmark markers (Canvas overlay positioned by ViewModel) -->
            <ItemsControl ItemsSource="{Binding Bookmarks}">
                <ItemsControl.ItemsPanel>
                    <ItemsPanelTemplate><Canvas/></ItemsPanelTemplate>
                </ItemsControl.ItemsPanel>
                <ItemsControl.ItemContainerStyle>
                    <Style TargetType="ContentPresenter">
                        <Setter Property="Canvas.Left" Value="{Binding X}"/>
                        <Setter Property="Canvas.Top"  Value="0"/>
                    </Style>
                </ItemsControl.ItemContainerStyle>
                <ItemsControl.ItemTemplate>
                    <DataTemplate>
                        <Rectangle Width="2" Height="56"
                                   Fill="{DynamicResource Brush.Accent}" Opacity="0.7"
                                   ToolTip="{Binding Label}"/>
                    </DataTemplate>
                </ItemsControl.ItemTemplate>
            </ItemsControl>
            <!-- Slider on top -->
            <Slider Minimum="{Binding StartUnix}" Maximum="{Binding EndUnix}"
                    Value="{Binding CurrentUnix, Mode=TwoWay}"
                    Style="{StaticResource Slider.Modern}"
                    VerticalAlignment="Center" Margin="0,16"/>
        </Grid>
    </Grid>
</Border>
```

### 9.4 KPI card with sparkline

```xml
<Border Padding="20" Background="{DynamicResource Brush.Surface.1}"
        CornerRadius="{DynamicResource Radius.Lg}"
        Effect="{DynamicResource Shadow.Sm}"
        Width="240">
    <StackPanel>
        <TextBlock Text="{Binding Label}"
                   FontSize="{DynamicResource Font.Size.Xs}"
                   Foreground="{DynamicResource Brush.Text.Secondary}"
                   FontWeight="SemiBold"
                   TextOptions.TextFormattingMode="Display"/>
        <TextBlock Text="{Binding ValueText}"
                   FontFamily="{DynamicResource Font.Mono}"
                   FontSize="{DynamicResource Font.Size.Display}"
                   FontWeight="Light"
                   Foreground="{DynamicResource Brush.Text.Primary}"
                   Margin="0,4,0,0"/>
        <StackPanel Orientation="Horizontal" Margin="0,4,0,12">
            <TextBlock Text="{Binding DeltaArrow}"
                       Foreground="{Binding DeltaBrush}"
                       FontSize="{DynamicResource Font.Size.Sm}"
                       FontWeight="SemiBold"/>
            <TextBlock Text="{Binding DeltaText}" Margin="4,0,0,0"
                       Foreground="{Binding DeltaBrush}"
                       FontFamily="{DynamicResource Font.Mono}"
                       FontSize="{DynamicResource Font.Size.Sm}"/>
            <TextBlock Text=" vs prev" Margin="6,0,0,0"
                       Foreground="{DynamicResource Brush.Text.Tertiary}"
                       FontSize="{DynamicResource Font.Size.Sm}"/>
        </StackPanel>
        <!-- Sparkline via LiveCharts2 -->
        <lvc:CartesianChart Height="40" Series="{Binding SparkSeries}"
                            DrawMargin="0,0,0,0" TooltipPosition="Hidden"
                            XAxes="{Binding HiddenAxes}" YAxes="{Binding HiddenAxes}"/>
    </StackPanel>
</Border>
```

The animated number counter is a converter on `ValueText`:

```csharp
public class AnimatedDoubleConverter : IValueConverter
{
    // Use Storyboard with DoubleAnimation targeting a wrapper DependencyProperty
    // Smoothly tween from previous to new value over 250ms with CubicEase
    // (full implementation ~30 lines — bind via attached property on TextBlock)
}
```

For text smoothing without a converter, a simpler approach is `Storyboard` triggered by a `Trigger` on the property change, animating opacity (fade-in old → fade-in new at 0.15s).

### 9.5 Modern toggle switch

```xml
<Style x:Key="Toggle.Modern" TargetType="ToggleButton">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="Foreground" Value="{DynamicResource Brush.Text.Primary}"/>
    <Setter Property="FontSize" Value="{DynamicResource Font.Size.Sm}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="ToggleButton">
                <StackPanel Orientation="Horizontal">
                    <Border x:Name="Track"
                            Width="36" Height="20"
                            CornerRadius="10"
                            Background="{DynamicResource Brush.Surface.3}">
                        <Border x:Name="Knob"
                                Width="14" Height="14"
                                CornerRadius="7"
                                Margin="3"
                                HorizontalAlignment="Left"
                                Background="{DynamicResource Brush.Text.Primary}">
                            <Border.RenderTransform>
                                <TranslateTransform x:Name="KnobX" X="0"/>
                            </Border.RenderTransform>
                        </Border>
                    </Border>
                    <ContentPresenter Margin="10,0,0,0" VerticalAlignment="Center"/>
                </StackPanel>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsChecked" Value="True">
                        <Trigger.EnterActions>
                            <BeginStoryboard>
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="KnobX"
                                                     Storyboard.TargetProperty="X"
                                                     To="16" Duration="{DynamicResource Motion.Fast}">
                                        <DoubleAnimation.EasingFunction>
                                            <CubicEase EasingMode="EaseOut"/>
                                        </DoubleAnimation.EasingFunction>
                                    </DoubleAnimation>
                                    <ColorAnimation Storyboard.TargetName="Track"
                                                    Storyboard.TargetProperty="Background.Color"
                                                    To="#7C5CFF" Duration="{DynamicResource Motion.Fast}"/>
                                </Storyboard>
                            </BeginStoryboard>
                        </Trigger.EnterActions>
                        <Trigger.ExitActions>
                            <BeginStoryboard>
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="KnobX"
                                                     Storyboard.TargetProperty="X"
                                                     To="0" Duration="{DynamicResource Motion.Fast}"/>
                                    <ColorAnimation Storyboard.TargetName="Track"
                                                    Storyboard.TargetProperty="Background.Color"
                                                    To="#242A36" Duration="{DynamicResource Motion.Fast}"/>
                                </Storyboard>
                            </BeginStoryboard>
                        </Trigger.ExitActions>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### 9.6 Position Manager card

```xml
<Border Padding="16" Background="{DynamicResource Brush.Surface.1}"
        CornerRadius="{DynamicResource Radius.Lg}">
    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <StackPanel Orientation="Horizontal">
            <TextBlock Text="{Binding Symbol}"
                       FontSize="{DynamicResource Font.Size.Lg}"
                       FontWeight="SemiBold"/>
            <Border Margin="10,2,0,0" Padding="6,2" CornerRadius="3"
                    Background="{Binding SideBrush}">
                <TextBlock Text="{Binding SideLabel}" FontSize="{DynamicResource Font.Size.Xs}"
                           Foreground="{DynamicResource Brush.Text.OnAccent}"/>
            </Border>
        </StackPanel>

        <TextBlock Grid.Row="1"
                   Text="{Binding UnrealizedPnL, StringFormat=$#,##0.00;-$#,##0.00}"
                   Foreground="{Binding PnLBrush}"
                   FontFamily="{DynamicResource Font.Mono}"
                   FontSize="{DynamicResource Font.Size.Display}"
                   FontWeight="Light" Margin="0,8,0,0"/>

        <Grid Grid.Row="2" Margin="0,12,0,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>
            <StackPanel>
                <TextBlock Text="QTY" FontSize="{DynamicResource Font.Size.Xs}"
                           Foreground="{DynamicResource Brush.Text.Tertiary}"/>
                <TextBlock Text="{Binding Qty}" FontFamily="{DynamicResource Font.Mono}"/>
            </StackPanel>
            <StackPanel Grid.Column="1">
                <TextBlock Text="AVG" FontSize="{DynamicResource Font.Size.Xs}"
                           Foreground="{DynamicResource Brush.Text.Tertiary}"/>
                <TextBlock Text="{Binding AvgPrice, StringFormat=N2}"
                           FontFamily="{DynamicResource Font.Mono}"/>
            </StackPanel>
            <StackPanel Grid.Column="2">
                <TextBlock Text="R/R" FontSize="{DynamicResource Font.Size.Xs}"
                           Foreground="{DynamicResource Brush.Text.Tertiary}"/>
                <TextBlock Text="{Binding RrText}"
                           FontFamily="{DynamicResource Font.Mono}"/>
            </StackPanel>
        </Grid>

        <StackPanel Grid.Column="1" Grid.RowSpan="3" Orientation="Vertical"
                    VerticalAlignment="Center" Margin="20,0,0,0">
            <Button Content="Flatten" Style="{StaticResource Btn.Primary}"
                    Command="{Binding FlattenCommand}" Width="110" Margin="0,0,0,8"/>
            <Button Content="Reverse" Style="{StaticResource Btn.Ghost}"
                    Command="{Binding ReverseCommand}" Width="110"/>
        </StackPanel>
    </Grid>
</Border>
```

### 9.7 Connection Status (latency mini-graph)

A LiveCharts2 line chart bound to a sliding-window `ObservableCollection<double>` with cap=120 (last 2 minutes at 1 Hz). Updates throttled to 1 Hz max. The card shows the current value as the headline KPI and the line as ambient context.

---

## 10. Performance Rules for Live Data

| Rule | Why |
|---|---|
| **Use `VirtualizationMode="Recycling"`** on every list/grid touching live data | 4-5× faster scroll; reuses containers |
| **`VirtualizingPanel.ScrollUnit="Pixel"`** on lists with variable-height rows | Smoother scroll, fewer layout passes |
| **Never set `CanContentScroll="False"`** on a ScrollViewer wrapping a virtualized list | Silently disables virtualization |
| **Never wrap a DataGrid in another ScrollViewer** | Same — disables virtualization, loads all rows |
| **Set explicit `Height` on every virtualized container** | Otherwise it measures Infinity and renders all items |
| **`.Freeze()` every custom Brush/Geometry** | Required for NT's multi-thread render |
| **Use `BindingOperations.EnableCollectionSynchronization`** for collections written from non-UI threads | Prevents `NotSupportedException` crashes |
| **Batch updates at 30 Hz** (~33ms tick) for tape feeds via `DispatcherTimer` at `DispatcherPriority.Background` | Keeps UI responsive without dropping data |
| **Prefer `RenderTransform` over `LayoutTransform`** | RenderTransform doesn't trigger re-layout |
| **Set `TextOptions.TextFormattingMode="Display"`** on every text-heavy panel root | Pixel-aligned glyphs; massive readability win at 12-13pt |
| **Set `RenderOptions.BitmapScalingMode="HighQuality"`** on icon images | Removes the blurry default |
| **Avoid `Effect="..."` (DropShadow/Blur) on items inside an `ItemsControl`** | Render cost multiplies per item; apply effects on the *container* only |
| **Cap collection size** with a sliding window (e.g., `while (Signals.Count > 5000) RemoveAt(Last)`) | Prevents unbounded memory growth |
| **Use `CompositionTarget.Rendering` only for per-frame canvas redraws (60 Hz)**, not for property updates | DispatcherTimer at Background is correct for data binding |

**Decision: DispatcherTimer vs CompositionTarget.Rendering**

| Use case | Pick |
|---|---|
| Throttled data binding flush (signals, P&L, KPIs) | `DispatcherTimer` @ `Background` priority, 33ms |
| Custom Canvas drawing per frame (heatmap, ladder pulse) | `CompositionTarget.Rendering` |
| Anything else | DispatcherTimer |

`CompositionTarget.Rendering` fires on every WPF render pass — sometimes 4-6 times per visual frame, often irregular. It's wrong for data binding flushes because you'll over-update.

---

## 11. Modal vs Modeless

| Pattern | When |
|---|---|
| `Window.ShowDialog()` | Confirmations the user must answer before continuing (e.g., "Cancel all open orders?") |
| `Window.Show()` | Side panels, secondary monitors, dashboards |
| Custom modal overlay (semi-transparent backdrop inside the parent NTWindow) | Lightweight confirmations that shouldn't pop a new OS window |
| Toast notification (transient overlay, 3-5s, auto-dismiss) | "Order filled", "Connection lost", "Signal triggered" |

Toast pattern (simplified — uses a `Popup` anchored to the window's top-right):

```xml
<Popup IsOpen="{Binding IsToastVisible}"
       Placement="Relative" PlacementTarget="{Binding ElementName=Root}"
       HorizontalOffset="-340" VerticalOffset="60"
       AllowsTransparency="True">
    <Border Width="320" Padding="14,10"
            Background="{DynamicResource Brush.Surface.2}"
            BorderBrush="{DynamicResource Brush.Accent}" BorderThickness="0,0,0,2"
            CornerRadius="{DynamicResource Radius.Md}"
            Effect="{DynamicResource Shadow.Lg}">
        <StackPanel>
            <TextBlock Text="{Binding ToastTitle}" FontWeight="SemiBold"/>
            <TextBlock Text="{Binding ToastMessage}" Margin="0,4,0,0"
                       Foreground="{DynamicResource Brush.Text.Secondary}"/>
        </StackPanel>
    </Border>
</Popup>
```

Drive `IsToastVisible` from the ViewModel with a `DispatcherTimer` that flips it back after 4 seconds.

---

## 12. Settings Persistence

NT8 ships **Newtonsoft.Json 11.0.2** (older versions are incompatible — script breaks on construction). Don't bring your own; reference the bundled assembly via *NinjaScript Editor → References → Add → `Newtonsoft.Json.dll` from `Documents\NinjaTrader 8\bin`.*

Two storage tiers:

| Tier | Where | Lifetime |
|---|---|---|
| **User preferences** (theme, default symbol, hotkeys) | `Documents\NinjaTrader 8\addons\Deep6\settings.json` | Forever, across NT versions |
| **Workspace state** (open windows, tab layout, sort order) | NT workspace XML via `IWorkspacePersistence.Save/Restore` | Per workspace |
| **Session state** (current selections, scratch values) | In-memory only | Process lifetime |

```csharp
public static class Deep6Settings
{
    private static readonly string Dir =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                     "NinjaTrader 8", "addons", "Deep6");
    private static readonly string Path = System.IO.Path.Combine(Dir, "settings.json");

    public static UserPrefs Load()
    {
        try
        {
            if (!File.Exists(Path)) return new UserPrefs();
            var json = File.ReadAllText(Path);
            return JsonConvert.DeserializeObject<UserPrefs>(json) ?? new UserPrefs();
        }
        catch { return new UserPrefs(); }
    }

    public static void Save(UserPrefs p)
    {
        Directory.CreateDirectory(Dir);
        File.WriteAllText(Path,
            JsonConvert.SerializeObject(p, Newtonsoft.Json.Formatting.Indented));
    }
}
```

---

## 13. Accessibility & Keyboard Navigation

NT8 traders frequently keyboard-drive everything. Accessibility helpers:

```xml
<Button x:Name="FlattenBtn"
        Content="_Flatten"
        AutomationProperties.Name="Flatten position"
        AutomationProperties.HelpText="Closes the open position at market"
        TabIndex="10"
        ToolTip="Flatten (F9)"/>
```

- Use `_X` in Content for Alt+X access keys.
- Set `TabIndex` deliberately — don't rely on visual order.
- Replace the dotted-rectangle focus visual:

```xml
<Style x:Key="ModernFocusVisual">
    <Setter Property="Control.Template">
        <Setter.Value>
            <ControlTemplate>
                <Rectangle Margin="-2" StrokeThickness="2"
                           Stroke="{DynamicResource Brush.Accent}"
                           StrokeDashArray="0" RadiusX="4" RadiusY="4"/>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>

<!-- Apply to every interactive control -->
<Style TargetType="Button" BasedOn="{StaticResource Btn.Primary}">
    <Setter Property="FocusVisualStyle" Value="{StaticResource ModernFocusVisual}"/>
</Style>
```

Detect high contrast via `SystemParameters.HighContrast` and swap to a higher-contrast brush set.

---

## 14. Interop with the Chart

Triggering a chart action from a panel — open chart at instrument/time:

```csharp
// From a panel button click handler:
var instrument = Cbi.Instrument.GetInstrument("NQ 03-26");
var chart = new NinjaTrader.Gui.Chart.Chart();
chart.WorkspaceOptions = new WorkspaceOptions("Deep6Chart-" + Guid.NewGuid().ToString("N"), chart);
// (NT chart construction is non-trivial — typically you don't *create* charts from code,
// you locate an existing chart by enumerating Application.Current.Windows and bringing it
// to the front, then push the desired symbol via its IInstrumentProvider.)
```

A more reliable pattern: enumerate live windows and dispatch into the matching chart's UI thread:

```csharp
foreach (Window w in Application.Current.Windows)
{
    if (w is NinjaTrader.Gui.Chart.Chart c)
    {
        c.Dispatcher.InvokeAsync(() =>
        {
            // mutate c.ActiveChartControl.Instrument or push a marker
        });
    }
}
```

Receiving chart click events into a panel — subscribe in your tab's lifecycle:

```csharp
// In SignalMonitorTab when a chart is identified
chart.ChartControl.ChartPanels[0].MouseDown += OnChartClick;

private void OnChartClick(object sender, MouseButtonEventArgs e)
{
    var panel = (ChartPanel)sender;
    var pt    = e.GetPosition(panel);
    var dpiPt = ChartingExtensions.ConvertToHorizontalPixelsBasedOnDpi(pt);
    int slot  = chart.ChartControl.GetSlotIndexByX((int)dpiPt.X);
    var time  = chart.ChartControl.GetTimeBySlotIndex(chart.ActiveChartControl, slot);
    // Push selection into ViewModel
    _vm.SelectedChartTime = time;
}
```

Always **unsubscribe in `OnDestroy`** or NT will leak the tab when the chart closes.

---

## 15. Anti-Patterns Specific to NT8 WPF Panels

| Anti-pattern | Symptom | Fix |
|---|---|---|
| Using `<Window>` instead of `NTWindow` | Window doesn't theme, doesn't persist into workspace, doesn't move tabs | Always inherit `NTWindow` |
| Setting `Title` instead of `Caption` | Taskbar text fights with NT's tab compositing | Use `Caption` |
| Nested AddOn / NTWindow class | Workspace restore silently fails | Move to top-level type |
| No default constructor | Same | Add one |
| Setting `WorkspaceOptions` in ctor | Some skin lookups fail | Set it in `Loaded` |
| Brushes not `.Freeze()`d | Random `InvalidOperationException` from render thread | Freeze every custom brush |
| `StaticResource` for theme brushes | Skin switch leaves panel half-themed | Use `DynamicResource` |
| Direct background-thread writes to `ObservableCollection` | `NotSupportedException` | `EnableCollectionSynchronization` or batch via DispatcherTimer |
| Per-tick `INotifyPropertyChanged` raises | UI starvation, dropped frames | Batch + flush at 30 Hz |
| Forgetting `OnWindowDestroyed` cleanup | Menu items duplicate on F5 reload; events leak | Mirror every subscription with an unsubscribe |
| WPF `DropShadowEffect` on virtualized items | Scrolling jank | Apply only to outer container |
| `ScrollViewer` wrapping a `DataGrid` | All rows materialize, RAM blow-up | Let DataGrid own its scroll |
| Ignoring DPI | Panel renders at 1x on a 4K monitor | Set `UseLayoutRounding="True"` and never use pixel-fixed widths for everything; combine with WPF auto-DPI |
| Hardcoded WinForms colors / `System.Drawing.Color` | Looks like NT 7 | Always use `DynamicResource` brushes |
| One giant XAML file | Hot-reload becomes painful | Split per view + a single shared `Themes/Deep6.xaml` |
| `BeginInvoke` instead of `InvokeAsync` for fire-and-forget | UI thread can lock (per NT support) | `InvokeAsync` everywhere |
| Subscribing to `ChartControl.MouseMove` without unsubscribing | Memory leak on chart close | Unsubscribe in destroy callback |

---

## 16. Decision Tables

### Where does this UI live?

| Need | Use |
|---|---|
| Top-level dashboard window | `NTWindow + IWorkspacePersistence` |
| Tab inside *any* NT window | `NTTabPage + INTTabFactory` |
| Floating, transient, non-persistent (e.g., quick confirm) | Plain `Window` with NT8 brushes merged in |
| Inside the chart canvas | Indicator with custom render or `UserControlCollection` |

### Which control for which list?

| Volume / interactivity | Control |
|---|---|
| ≤ 100 rows, sortable, filterable, simple | `ListBox` with virtualization |
| ≤ 100k rows, columnar, sortable | `DataGrid` (recycling mode) |
| ≥ 100k rows, live updating | DataGrid + custom `ICollectionView` with backing store + windowed virtual collection |
| Tree of arbitrary depth | `TreeView` (also virtualizable) |
| Free-form layout (timeline, heatmap, ladder) | `ItemsControl` with `Canvas` ItemsPanel |

### Which library should I drop in?

| Need | Pick | Reason |
|---|---|---|
| Pre-built modern WPF controls | **MahApps.Metro** | Most mature, biggest community, MIT |
| Just want WinUI-look on stock controls | **ModernWpf** | Smaller surface, drop-in styles |
| Real-time financial chart in a panel | **LiveCharts2** | Designed for live OHLC, MIT |
| Backtest analytics (static dense scatter) | **ScottPlot** | Faster than OxyPlot for big static plots |
| Toast notifications | **Custom Popup pattern** above | No dependency, ~30 LOC |
| JSON serialization | **Newtonsoft.Json (NT-bundled v11.0.2)** | Already loaded; using a different version breaks |
| MVVM toolkit | **CommunityToolkit.Mvvm 8.x** OR hand-rolled (§5) | Either works; toolkit saves boilerplate |

---

## 17. Folder & File Layout

```
Documents/NinjaTrader 8/bin/Custom/AddOns/Deep6/
├── Deep6AddOn.cs                  # AddOnBase
├── Deep6DashboardWindow.cs        # NTWindow
├── Deep6TabFactory.cs             # INTTabFactory
├── Mvvm/
│   ├── ViewModelBase.cs
│   └── RelayCommand.cs
├── Themes/
│   ├── Deep6.xaml                 # design tokens (§6)
│   ├── Buttons.xaml
│   ├── Toggles.xaml
│   ├── ScrollBars.xaml
│   └── DataGrid.xaml
├── Fonts/
│   ├── Inter-Variable.ttf
│   └── JetBrainsMono-Regular.ttf
├── Views/
│   ├── SignalMonitorView.xaml(.cs)
│   ├── TradeJournalView.xaml(.cs)
│   ├── ReplayScrubberView.xaml(.cs)
│   ├── PositionManagerView.xaml(.cs)
│   ├── ConnectionStatusView.xaml(.cs)
│   └── RiskDashboardView.xaml(.cs)
├── ViewModels/
│   ├── SignalMonitorViewModel.cs
│   ├── TradeJournalViewModel.cs
│   ├── ReplayScrubberViewModel.cs
│   └── ...
└── Tabs/
    ├── SignalMonitorTab.cs
    ├── TradeJournalTab.cs
    ├── ReplayScrubberTab.cs
    └── ...
```

Every `Deep6*Window` constructor merges `Themes/Deep6.xaml` + the per-style files into its `Resources.MergedDictionaries` so `DynamicResource` lookups resolve from the window scope down. NT's own skin sits at `Application.Current.Resources` — so theme tokens you don't override fall through to NT's, and skin switching still propagates.

---

## 18. Putting It All Together — The First-Run Flow

1. User installs `Deep6.dll` in `bin/Custom/`. NT compiles and discovers `Deep6AddOn : AddOnBase`.
2. NT creates the AddOn singleton; `OnStateChange(State.SetDefaults)` → `Configure` → `Active`.
3. ControlCenter opens. NT raises `OnWindowCreated(controlCenter)` on the AddOn.
4. AddOn finds `ControlCenterMenuItemNew`, injects "DEEP6 Dashboard" with `MainMenuItem` style.
5. User clicks. AddOn calls `controlCenter.Dispatcher.InvokeAsync(() => new Deep6DashboardWindow().Show())`.
6. `Deep6DashboardWindow` constructor sets `Caption`, merges `Themes/Deep6.xaml`, builds a `TabControl` with `Deep6TabFactory`, seeds `SignalMonitorTab`.
7. `Loaded` fires → `WorkspaceOptions = new WorkspaceOptions("Deep6Dashboard-" + Guid, this)`.
8. `SignalMonitorTab` constructor builds `SignalMonitorView` with its `SignalMonitorViewModel`.
9. ViewModel calls `BindingOperations.EnableCollectionSynchronization(Signals, _lock)`, starts the 30 Hz flush timer.
10. The DEEP6 signal engine pushes `SignalRow` instances onto the queue from a Rithmic worker thread.
11. The DispatcherTimer drains the queue every 33ms and inserts rows into `Signals` — virtualized list scrolls smoothly, themed rows light up by side, `IsMouseOver` triggers fire.
12. User saves workspace → NT calls `Deep6DashboardWindow.Save` → `MainTabControl.SaveToXElement` fans out to each tab's `Save` → workspace XML records every panel's state.
13. User reopens NT, restores workspace → reflection-instantiates `Deep6DashboardWindow` (default ctor), then `Restore` rebuilds the tabs via the factory.
14. User F5s in NinjaScript Editor → `OnWindowDestroyed` for the ControlCenter → menu unhooked → `Terminated` → reload → menu re-injected. No leaks.

---

## Sources

- [NinjaScript: Creating Your Own AddOn Window (NT docs)](https://ninjatrader.com/support/helpguides/nt8/creating_your_own_addon_window.htm)
- [NinjaScript: NTWindow](https://ninjatrader.com/support/helpguides/nt8/ntwindow.htm)
- [NinjaScript: IWorkspacePersistence Interface](https://ninjatrader.com/support/helpGuides/nt8/iworkspacepersistence_interface.htm)
- [NinjaScript: NTMenuItem](https://ninjatrader.com/support/helpGuides/nt8/ntmenuitem.htm)
- [NinjaScript: ControlCenter](https://ninjatrader.com/support/helpGuides/nt8/controlcenter.htm)
- [NinjaScript: INTTabFactory Interface](https://ninjatrader.com/support/helpGuides/nt8/inttabfactory_class.htm)
- [NinjaScript: INTTabFactory.CreateTabPage](https://ninjatrader.com/support/helpGuides/nt8/createtabpage.htm)
- [NinjaScript: IInstrumentProvider.Instrument](https://ninjatrader.com/support/helpguides/nt8/iinstrumentprovider_instrument.htm)
- [NinjaScript: TabControl](https://ninjatrader.com/support/helpguides/nt8/tabcontrol.htm)
- [NinjaScript: OnWindowDestroyed](https://ninjatrader.com/support/helpguides/nt8/onwindowdestroyed.htm)
- [NinjaScript: ChartControl](https://ninjatrader.com/support/helpguides/nt8/chartcontrol.htm)
- [NinjaScript: Working with Brushes](https://ninjatrader.com/support/helpGuides/nt8/working_with_brushes.htm)
- [NinjaScript: Multi-Threading Considerations](https://ninjatrader.com/support/helpGuides/nt8/multi-threading.htm)
- [NinjaScript: AddOn Development Overview](https://ninjatrader.com/support/helpguides/nt8/addon_development_overview.htm)
- [NinjaScript: UserControlCollection](https://ninjatrader.com/support/helpguides/nt8/usercontrolcollection.htm)
- [NT Forum: Example Adding AddOn to Control Center Tools Menu](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1091353-example-adding-addon-to-control-center-tools-menu)
- [NT Forum: Create a toolbar in a custom NTWindow](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/95850-create-a-toolbar-in-a-custom-ntwindow)
- [NT Forum: How do I create an NT8 themed WPF form?](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1105004-how-do-i-create-an-nt8-themed-wpf-form)
- [NT Forum: What is Core.Globals.RandomDispatcher?](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1188914-what-is-core-globals-randomdispatcher)
- [NT Forum: InvokeAsync and Invoke for Dispatcher](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1318379-invokeasync-and-invoke-for-dispatcher)
- [NT Forum: Capture chart mouse events from Add-On](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/102567-capture-chart-mouse-events-from-add-on)
- [NT Forum: NTTabPage lifecycle hooks](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1229251-nttabpage-lifecycle-hooks-for-tab-page-creation-and-destruction)
- [NT Forum: AddOn vs NinjaTrader Exit/Shutdown](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1134378-addon-vs-ninjatrader-exit-shutdown)
- [NT Forum: How to make window workspace specific](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1155781-how-to-make-window-workspace-specific)
- [NT Forum: Custom WPF control to adjust to NT skin](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/103630-custom-wpf-control-to-adjust-to-nt-skin)
- [NT Forum: Custom & dynamic WPF controls or chart trader elements](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1283335-custom-dynamic-wpf-controls-or-chart-trader-elements)
- [NT Forum: Getting Resource Values for UI](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1183358-getting-resource-values-for-ui)
- [GitHub: samuelcaldas/NinjaTraderAddOnProject](https://github.com/samuelcaldas/NinjaTraderAddOnProject)
- [GitHub: samuelcaldas/AddonShellProject](https://github.com/samuelcaldas/AddonShellProject)
- [Microsoft Learn: WindowChrome Class](https://learn.microsoft.com/en-us/dotnet/api/system.windows.shell.windowchrome)
- [Microsoft Learn: WPF Styles and Templates](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/controls/styles-templates-overview)
- [Microsoft Learn: WPF DataGrid](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/controls/datagrid)
- [Microsoft Learn: Group, Sort, Filter DataGrid](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/controls/how-to-group-sort-and-filter-data-in-the-datagrid-control)
- [Microsoft Learn: Data Templating Overview](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/data/data-templating-overview)
- [Microsoft Learn: Easing Functions WPF](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/graphics-multimedia/easing-functions)
- [Microsoft Learn: ScrollBar Styles and Templates](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/controls/scrollbar-styles-and-templates)
- [Microsoft Learn: Packaging Fonts with Applications](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/advanced/packaging-fonts-with-applications)
- [Microsoft Learn: BindingOperations.EnableCollectionSynchronization](https://learn.microsoft.com/en-us/dotnet/api/system.windows.data.bindingoperations.enablecollectionsynchronization)
- [Microsoft Learn: Styling for Focus and FocusVisualStyle](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/advanced/styling-for-focus-in-controls-and-focusvisualstyle)
- [Microsoft Learn: WPF Accessibility Improvements](https://github.com/microsoft/dotnet/blob/main/Documentation/compatibility/wpf-accessibility-improvements.MD)
- [Microsoft Learn: Acrylic Material](https://learn.microsoft.com/en-us/windows/apps/design/style/acrylic)
- [Microsoft Learn: System Backdrops (Mica/Acrylic)](https://learn.microsoft.com/en-us/windows/apps/develop/ui/system-backdrops)
- [Microsoft Learn: RelayCommand attribute (CommunityToolkit.Mvvm)](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/mvvm/generators/relaycommand)
- [MahApps.Metro Home](https://mahapps.com/)
- [GitHub: MahApps/MahApps.Metro](https://github.com/MahApps/MahApps.Metro)
- [GitHub: Kinnara/ModernWpf](https://github.com/Kinnara/ModernWpf)
- [Kinnara/ModernWpf ToggleSwitch.xaml](https://github.com/Kinnara/ModernWpf/blob/master/ModernWpf.Controls/ToggleSwitch/ToggleSwitch.xaml)
- [LiveCharts2 Home](https://livecharts.dev/)
- [LiveCharts2 vs OxyPlot comparison](https://www.libhunt.com/compare-LiveCharts2-vs-oxyplot)
- [LiveCharts2 vs ScottPlot comparison](https://www.libhunt.com/compare-LiveCharts2-vs-ScottPlot)
- [Apply Mica to a WPF app on Windows 11](https://tvc-16.science/mica-wpf.html)
- [GitHub: vbobroff-app/FluentWpfChromes](https://github.com/vbobroff-app/FluentWpfChromes)
- [GitHub: Aldaviva/DarkNet (dark titlebars)](https://github.com/Aldaviva/DarkNet)
- [GitHub: sourcechord/FluentWPF (ScrollBar.xaml)](https://github.com/sourcechord/FluentWPF/blob/master/FluentWPF/Styles/ScrollBar.xaml)
- [GitHub: Cysharp/ObservableCollections](https://github.com/Cysharp/ObservableCollections)
- [Roland Weigelt: WPF, Text Rendering and the Blues](https://weblogs.asp.net/rweigelt/wpf-text-rendering-and-the-blues/)
- [WPF Tutorial: text rendering](https://wpf-tutorial.com/control-concepts/text-rendering/)
- [Benoit Blanchon: WPF/MVVM How to deal with fast changing properties](https://blog.benoitblanchon.fr/wpf-high-speed-mvvm/)
- [Evan's Code Clunkers: Efficient Per-Frame Eventing in WPF](https://evanl.wordpress.com/2009/12/06/efficient-optimal-per-frame-eventing-in-wpf/)
- [Building an iOS Style Toggle Button in WPF and XAML (Mark Harwood)](https://it-delinquent.medium.com/building-an-ios-style-toggle-button-in-wpf-and-xaml-678939f7e7ef)
- [Implementing a Custom Window Title Bar in WPF (David Rickard)](https://engy.us/blog/2020/01/01/implementing-a-custom-window-title-bar-in-wpf/)
- [Nikolay Vasilev: Creating a custom WPF window](https://www.nvasilev.me/blog/custom-wpf-window)
- [Markodevcic: Changing WPF themes dynamically](https://www.markodevcic.com/post/changing_wpf_themes_dynamically/)
- [Jetbrains Mono](https://www.jetbrains.com/lp/mono/)
- [Toxigon: WPF MVVM Pattern Guide 2025](https://toxigon.com/wpf-mvvm-pattern-guide)
