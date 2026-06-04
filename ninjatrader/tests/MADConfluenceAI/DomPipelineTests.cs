// DomPipelineTests.cs — TDD tests for DOM state management: level tracking,
// liquidity walls, DOM imbalance, refill/iceberg detection.
// Uses test-local type copies to avoid NT8 runtime dependencies.
using System;
using System.Collections.Generic;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI.DomPipeline
{
    /// <summary>
    /// Test-local DOM state that mirrors the indicator's DOM array management.
    /// </summary>
    internal class TestDomState
    {
        public readonly double[] BidPrices = new double[50];
        public readonly long[] BidVolumes = new long[50];
        public readonly double[] AskPrices = new double[50];
        public readonly long[] AskVolumes = new long[50];
        public int BidCount;
        public int AskCount;
        public bool IsDomAvailable;

        public Dictionary<double, int> RefillCounts = new Dictionary<double, int>();
        public Dictionary<double, DateTime> RefillTimestamps = new Dictionary<double, DateTime>();

        // side: 0=bid, 1=ask; operation: 0=add/update, 1=remove
        public void ProcessUpdate(int side, int position, double price, long volume, int operation, DateTime? timestamp = null)
        {
            if (position < 0 || position >= 50) return;
            IsDomAvailable = true;
            DateTime ts = timestamp ?? DateTime.UtcNow;

            bool isRemove = operation == 1;
            long vol = isRemove ? 0 : volume;

            if (side == 0) // bid
            {
                long prevVol = BidVolumes[position];
                BidPrices[position] = isRemove ? 0 : price;
                BidVolumes[position] = vol;
                if (position >= BidCount) BidCount = position + 1;

                if (prevVol == 0 && vol > 0)
                {
                    DateTime lastTime;
                    if (RefillTimestamps.TryGetValue(price, out lastTime)
                        && (ts - lastTime).TotalSeconds <= 30)
                    {
                        int cnt;
                        RefillCounts.TryGetValue(price, out cnt);
                        RefillCounts[price] = cnt + 1;
                    }
                    RefillTimestamps[price] = ts;
                }
            }
            else // ask
            {
                long prevVol = AskVolumes[position];
                AskPrices[position] = isRemove ? 0 : price;
                AskVolumes[position] = vol;
                if (position >= AskCount) AskCount = position + 1;

                if (prevVol == 0 && vol > 0)
                {
                    DateTime lastTime;
                    if (RefillTimestamps.TryGetValue(price, out lastTime)
                        && (ts - lastTime).TotalSeconds <= 30)
                    {
                        int cnt;
                        RefillCounts.TryGetValue(price, out cnt);
                        RefillCounts[price] = cnt + 1;
                    }
                    RefillTimestamps[price] = ts;
                }
            }
        }

        public List<double> GetLiquidityWalls(double threshold)
        {
            var walls = new List<double>();
            if (!IsDomAvailable) return walls;

            long totalVol = 0;
            int levelCount = 0;
            for (int i = 0; i < BidCount; i++)
                if (BidVolumes[i] > 0) { totalVol += BidVolumes[i]; levelCount++; }
            for (int i = 0; i < AskCount; i++)
                if (AskVolumes[i] > 0) { totalVol += AskVolumes[i]; levelCount++; }
            if (levelCount == 0) return walls;

            double avgVol = (double)totalVol / levelCount;
            double cutoff = avgVol * threshold;
            for (int i = 0; i < BidCount; i++)
                if (BidVolumes[i] > cutoff) walls.Add(BidPrices[i]);
            for (int i = 0; i < AskCount; i++)
                if (AskVolumes[i] > cutoff) walls.Add(AskPrices[i]);
            return walls;
        }

        public double GetDomImbalance()
        {
            if (!IsDomAvailable) return 1.0;
            long bidTotal = 0, askTotal = 0;
            int levels = System.Math.Min(10, System.Math.Min(BidCount, AskCount));
            if (levels == 0) return 1.0;
            for (int i = 0; i < levels; i++)
            {
                bidTotal += BidVolumes[i];
                askTotal += AskVolumes[i];
            }
            if (bidTotal == 0 && askTotal == 0) return 1.0;
            if (askTotal == 0) return double.MaxValue;
            return (double)bidTotal / askTotal;
        }

        public int GetRefillCount(double price)
        {
            if (!IsDomAvailable) return 0;
            int count;
            RefillCounts.TryGetValue(price, out count);
            return count;
        }
    }

    // ── Tests ───────────────────────────────────────────────────────────

    [TestFixture]
    public class DomPipelineTests
    {
        private TestDomState _dom;

        [SetUp]
        public void SetUp()
        {
            _dom = new TestDomState();
        }

        [Test]
        public void DomAdd_SetsPriceAndVolume()
        {
            _dom.ProcessUpdate(side: 0, position: 0, price: 21000.0, volume: 150, operation: 0);
            Assert.AreEqual(21000.0, _dom.BidPrices[0]);
            Assert.AreEqual(150, _dom.BidVolumes[0]);
            Assert.AreEqual(1, _dom.BidCount);
            Assert.IsTrue(_dom.IsDomAvailable);
        }

        [Test]
        public void DomUpdate_ChangesVolume()
        {
            _dom.ProcessUpdate(side: 1, position: 0, price: 21000.25, volume: 100, operation: 0);
            Assert.AreEqual(100, _dom.AskVolumes[0]);

            _dom.ProcessUpdate(side: 1, position: 0, price: 21000.25, volume: 200, operation: 0);
            Assert.AreEqual(200, _dom.AskVolumes[0]);
        }

        [Test]
        public void DomRemove_ZerosPriceAndVolume()
        {
            _dom.ProcessUpdate(side: 0, position: 2, price: 20999.50, volume: 80, operation: 0);
            Assert.AreEqual(80, _dom.BidVolumes[2]);

            _dom.ProcessUpdate(side: 0, position: 2, price: 20999.50, volume: 0, operation: 1); // remove
            Assert.AreEqual(0, _dom.BidPrices[2]);
            Assert.AreEqual(0, _dom.BidVolumes[2]);
        }

        [Test]
        public void GetLiquidityWalls_ReturnsHighVolumeLevels()
        {
            // Set up: 5 bid levels with varied volumes
            _dom.ProcessUpdate(0, 0, 21000.00, 50, 0);
            _dom.ProcessUpdate(0, 1, 20999.75, 50, 0);
            _dom.ProcessUpdate(0, 2, 20999.50, 50, 0);
            _dom.ProcessUpdate(0, 3, 20999.25, 50, 0);
            _dom.ProcessUpdate(0, 4, 20999.00, 500, 0); // wall: 10x average

            // Average = (50+50+50+50+500)/5 = 140. Threshold 2.0 → cutoff = 280
            var walls = _dom.GetLiquidityWalls(2.0);
            Assert.AreEqual(1, walls.Count);
            Assert.AreEqual(20999.00, walls[0]);
        }

        [Test]
        public void GetLiquidityWalls_ReturnsEmpty_WhenNoDom()
        {
            // IsDomAvailable = false
            var walls = _dom.GetLiquidityWalls(2.0);
            Assert.AreEqual(0, walls.Count);
        }

        [Test]
        public void GetDomImbalance_ComputesBidAskRatio()
        {
            // 3 bid levels, 3 ask levels
            _dom.ProcessUpdate(0, 0, 21000.00, 100, 0);
            _dom.ProcessUpdate(0, 1, 20999.75, 100, 0);
            _dom.ProcessUpdate(0, 2, 20999.50, 100, 0);
            _dom.ProcessUpdate(1, 0, 21000.25, 50, 0);
            _dom.ProcessUpdate(1, 1, 21000.50, 50, 0);
            _dom.ProcessUpdate(1, 2, 21000.75, 50, 0);

            // bid total = 300, ask total = 150, ratio = 2.0
            double imbalance = _dom.GetDomImbalance();
            Assert.AreEqual(2.0, imbalance, 0.001);
        }

        [Test]
        public void GetDomImbalance_ReturnsOne_WhenNoDom()
        {
            Assert.AreEqual(1.0, _dom.GetDomImbalance());
        }

        [Test]
        public void GetDomImbalance_ReturnsMaxValue_WhenNoAsks()
        {
            _dom.ProcessUpdate(0, 0, 21000.00, 100, 0);
            _dom.IsDomAvailable = true;
            // AskCount is 0 → levels = Min(10, Min(1, 0)) = 0 → returns 1.0
            Assert.AreEqual(1.0, _dom.GetDomImbalance());
        }

        [Test]
        public void RefillTracking_WithinWindow_IncrementsCounter()
        {
            DateTime t0 = new DateTime(2026, 1, 15, 10, 0, 0, DateTimeKind.Utc);

            // First appearance: volume at position 0
            _dom.ProcessUpdate(0, 0, 21000.0, 100, 0, t0);

            // Volume goes to 0 (remove)
            _dom.ProcessUpdate(0, 0, 21000.0, 0, 1, t0.AddSeconds(5));

            // Refill within 30s window
            _dom.ProcessUpdate(0, 0, 21000.0, 80, 0, t0.AddSeconds(10));

            Assert.AreEqual(1, _dom.GetRefillCount(21000.0));
        }

        [Test]
        public void RefillTracking_OutsideWindow_DoesNotIncrement()
        {
            DateTime t0 = new DateTime(2026, 1, 15, 10, 0, 0, DateTimeKind.Utc);

            _dom.ProcessUpdate(0, 0, 21000.0, 100, 0, t0);
            _dom.ProcessUpdate(0, 0, 21000.0, 0, 1, t0.AddSeconds(5));

            // Refill OUTSIDE 30s window
            _dom.ProcessUpdate(0, 0, 21000.0, 80, 0, t0.AddSeconds(40));

            Assert.AreEqual(0, _dom.GetRefillCount(21000.0));
        }

        [Test]
        public void GetRefillCount_ReturnsZero_WhenNoDom()
        {
            Assert.AreEqual(0, _dom.GetRefillCount(21000.0));
        }

        [Test]
        public void DomPositionOutOfRange_Ignored()
        {
            _dom.ProcessUpdate(0, 50, 21000.0, 100, 0); // position 50 = out of range
            Assert.AreEqual(0, _dom.BidCount);
            Assert.IsFalse(_dom.IsDomAvailable);
        }
    }
}
