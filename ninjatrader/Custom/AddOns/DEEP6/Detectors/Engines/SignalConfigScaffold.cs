// SignalConfigScaffold: ENG-07 centralized signal configuration constants.
//
// Python reference: deep6/engines/signal_config.py
//
// Purpose:
//   Single source of truth for tunable signal parameters across all 44 detectors.
//   Provides static default instances of each detector config class.
//   In Phase 18+, these defaults will be loaded from a JSON config file or
//   optimized via the ML parameter sweep (Optuna).
//
// Usage:
//   var config = SignalConfigScaffold.Default;
//   var detector = new TrespassDetector(config.Trespass);
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines
{
    /// <summary>
    /// ENG-07: Centralized signal configuration scaffold.
    ///
    /// Provides factory method to create a complete set of default detector configurations.
    /// All config instances are mutable — callers may adjust individual parameters
    /// after calling Default before constructing detector instances.
    ///
    /// Python reference: deep6/engines/signal_config.py
    ///
    /// Phase 18 extension point:
    ///   Replace Default with a JSON-backed factory:
    ///   <c>SignalConfigScaffold.FromJson("signal_config.json")</c>
    /// </summary>
    public sealed class SignalConfigScaffold
    {
        // -----------------------------------------------------------------------
        // Engine detector configurations (ENG-02..07)
        // -----------------------------------------------------------------------

        /// <summary>ENG-02 TrespassDetector configuration.</summary>
        public TrespassConfig     Trespass    { get; set; }

        /// <summary>ENG-03 CounterSpoofDetector configuration.</summary>
        public CounterSpoofConfig CounterSpoof { get; set; }

        /// <summary>ENG-04 IcebergDetector configuration.</summary>
        public IcebergConfig      Iceberg     { get; set; }

        /// <summary>ENG-05 MicroProbDetector configuration.</summary>
        public MicroProbConfig    MicroProb   { get; set; }

        /// <summary>ENG-06 VPContextDetector configuration.</summary>
        public VPContextConfig    VPContext   { get; set; }

        // -----------------------------------------------------------------------
        // Factory
        // -----------------------------------------------------------------------

        /// <summary>
        /// Create a SignalConfigScaffold populated with all default configurations.
        /// Equivalent to Python signal_config.py default instantiation.
        /// </summary>
        public static SignalConfigScaffold Default => new SignalConfigScaffold
        {
            Trespass     = new TrespassConfig(),
            CounterSpoof = new CounterSpoofConfig(),
            Iceberg      = new IcebergConfig(),
            MicroProb    = new MicroProbConfig(),
            VPContext    = new VPContextConfig(),
        };

        /// <summary>
        /// Create a complete set of detectors in the required registration order.
        ///
        /// Registration order is critical:
        ///   1. TrespassDetector   (ENG-02) — writes LastTrespassProbability/Direction
        ///   2. CounterSpoofDetector (ENG-03) — independent
        ///   3. IcebergDetector    (ENG-04) — writes LastIcebergSignals; implements IAbsorptionZoneReceiver
        ///   4. VPContextDetector  (ENG-06) — reads SessionPocPrice
        ///   5. MicroProbDetector  (ENG-05) — MUST BE LAST: reads all above session fields
        ///
        /// Python reference: deep6/engines/micro_prob.py (ordering note in class docstring)
        /// RESEARCH.md §ENG-05 Registration Order
        /// </summary>
        public (
            TrespassDetector     Trespass,
            CounterSpoofDetector CounterSpoof,
            IcebergDetector      Iceberg,
            VPContextDetector    VPContext,
            MicroProbDetector    MicroProb
        ) BuildDetectors()
        {
            return (
                new TrespassDetector(Trespass),
                new CounterSpoofDetector(CounterSpoof),
                new IcebergDetector(Iceberg),
                new VPContextDetector(VPContext),
                new MicroProbDetector(MicroProb)  // LAST
            );
        }
    }
}
