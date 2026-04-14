/**
 * Fixed-capacity mutable ring buffer.
 * O(1) push, zero allocation on hot path.
 * Uses plain Array<T> with head/tail pointers so object identity is preserved
 * (React key={bar.id} works correctly).
 */
export class RingBuffer<T> {
  private buf: (T | undefined)[];
  private head = 0; // next write index
  private _size = 0;

  constructor(public readonly capacity: number) {
    if (capacity <= 0) throw new Error('RingBuffer capacity must be > 0');
    this.buf = new Array(capacity);
  }

  push(item: T): void {
    this.buf[this.head] = item;
    this.head = (this.head + 1) % this.capacity;
    if (this._size < this.capacity) this._size++;
  }

  get size(): number {
    return this._size;
  }

  /** Most recently pushed item, or undefined if empty. */
  get latest(): T | undefined {
    if (this._size === 0) return undefined;
    const idx = (this.head - 1 + this.capacity) % this.capacity;
    return this.buf[idx];
  }

  /**
   * Returns items in insertion order (oldest first, newest last).
   * Allocates — call sparingly; prefer forEachNewest for Canvas draw loops.
   */
  toArray(): T[] {
    if (this._size === 0) return [];
    if (this._size < this.capacity) {
      return this.buf.slice(0, this._size) as T[];
    }
    // Buffer is full: head points to oldest
    return [...this.buf.slice(this.head), ...this.buf.slice(0, this.head)] as T[];
  }

  /**
   * Zero-alloc iteration newest→oldest (for Canvas draw loops).
   * @param fn callback(item, index) — index 0 = newest
   * @param limit max items to iterate
   */
  forEachNewest(fn: (v: T, i: number) => void, limit = this._size): void {
    const n = Math.min(limit, this._size);
    for (let i = 0; i < n; i++) {
      fn(this.buf[(this.head - 1 - i + this.capacity) % this.capacity] as T, i);
    }
  }

  /** Reset to empty. */
  clear(): void {
    this.buf = new Array(this.capacity);
    this.head = 0;
    this._size = 0;
  }
}
