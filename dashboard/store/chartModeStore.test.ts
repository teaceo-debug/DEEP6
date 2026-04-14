import { describe, it, expect, beforeEach } from 'vitest';
import { useChartModeStore } from './chartModeStore';

describe('chartModeStore', () => {
  beforeEach(() => {
    // Reset to default before each test
    useChartModeStore.getState().setMode('numbers');
  });

  it('defaults to "numbers" mode', () => {
    expect(useChartModeStore.getState().mode).toBe('numbers');
  });

  it('setMode("wings") updates state', () => {
    useChartModeStore.getState().setMode('wings');
    expect(useChartModeStore.getState().mode).toBe('wings');
  });

  it('setMode("heatmap") updates state', () => {
    useChartModeStore.getState().setMode('heatmap');
    expect(useChartModeStore.getState().mode).toBe('heatmap');
  });

  it('setMode("numbers") reverts to numbers', () => {
    useChartModeStore.getState().setMode('heatmap');
    useChartModeStore.getState().setMode('numbers');
    expect(useChartModeStore.getState().mode).toBe('numbers');
  });
});
