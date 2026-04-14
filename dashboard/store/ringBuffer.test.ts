import { describe, it, expect, beforeEach } from 'vitest';
import { RingBuffer } from './ringBuffer';

describe('RingBuffer', () => {
  it('Test 1: initial state — size 0, capacity set, latest undefined', () => {
    const rb = new RingBuffer<number>(3);
    expect(rb.size).toBe(0);
    expect(rb.capacity).toBe(3);
    expect(rb.latest).toBeUndefined();
  });

  it('Test 2: push 1,2,3 — toArray returns [1,2,3], latest === 3', () => {
    const rb = new RingBuffer<number>(3);
    rb.push(1);
    rb.push(2);
    rb.push(3);
    expect(rb.toArray()).toEqual([1, 2, 3]);
    expect(rb.latest).toBe(3);
  });

  it('Test 3: push 4 into capacity-3 buffer — toArray returns [2,3,4], size still 3', () => {
    const rb = new RingBuffer<number>(3);
    rb.push(1);
    rb.push(2);
    rb.push(3);
    rb.push(4);
    expect(rb.toArray()).toEqual([2, 3, 4]);
    expect(rb.size).toBe(3);
  });

  it('Test 4: push 5 — toArray returns [3,4,5]', () => {
    const rb = new RingBuffer<number>(3);
    rb.push(1);
    rb.push(2);
    rb.push(3);
    rb.push(4);
    rb.push(5);
    expect(rb.toArray()).toEqual([3, 4, 5]);
  });

  it('Test 5: clear() resets size to 0, latest undefined', () => {
    const rb = new RingBuffer<number>(3);
    rb.push(1);
    rb.push(2);
    rb.clear();
    expect(rb.size).toBe(0);
    expect(rb.latest).toBeUndefined();
    expect(rb.toArray()).toEqual([]);
  });
});
