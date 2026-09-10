/**
 * Tiny deterministic PRNG so the whole world regenerates identically every
 * load (stable placement, no hydration flicker, reproducible tweaking).
 */

/** mulberry32 — fast, seedable, good enough for scatter jitter. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** A small bundle of helpers around a raw `random()`. */
export interface Rng {
  next(): number
  range(min: number, max: number): number
  int(min: number, max: number): number
  chance(p: number): boolean
  pick<T>(items: readonly T[]): T
}

export function makeRng(seed: number): Rng {
  const r = mulberry32(seed)
  return {
    next: r,
    range: (min, max) => min + r() * (max - min),
    int: (min, max) => Math.floor(min + r() * (max - min + 1)),
    chance: (p) => r() < p,
    pick: (items) => items[Math.floor(r() * items.length)],
  }
}
