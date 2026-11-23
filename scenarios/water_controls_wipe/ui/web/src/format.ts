// The words and numbers of the board, and the reading of a sampled series at a time.

import type { Series } from './types';

// A time since the attack: minutes, hours up to two days, then days.
export function when(h: number): string {
  if (h < 1) return Math.round(h * 60) + ' min';
  if (h < 48) return Math.round(h) + ' h';
  const d = h / 24;
  return (d < 10 ? Math.round(d * 10) / 10 : Math.round(d)) + ' days';
}

// A count in words: 3,400, 1.2 million.
export function count(n: number): string {
  if (n >= 1e6) return Math.round(n / 1e5) / 10 + ' million';
  return Math.round(n).toLocaleString('en-US');
}

export function dollars(bn: number): string {
  const v = bn * 1e9;
  if (v <= 0) return '$0';
  if (v >= 1e9) return '$' + Math.round(v / 1e8) / 10 + ' billion';
  if (v >= 1e6) return '$' + (v >= 1e8 ? Math.round(v / 1e6) : Math.round(v / 1e5) / 10) + ' million';
  return '$' + (Math.round(v / 1e3) * 1e3).toLocaleString('en-US');
}

// A water amount in words: whole numbers from 100, one decimal from 1, two below.
export function amount(v: number): string {
  if (Math.abs(v) < 0.005) return '0';
  if (v >= 100) return Math.round(v).toLocaleString('en-US');
  return String(v >= 1 ? Math.round(v * 10) / 10 : Math.round(v * 100) / 100);
}

// A sampled series at time t: stepped (the last point at or before t) or straight between points.
export function sample<T>(pts: Series<T> | undefined, t: number, straight = false): T | null {
  if (!pts || !pts.length) return null;
  if (t <= pts[0][0]) return pts[0][1];
  let lo = 0;
  let hi = pts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (pts[mid][0] <= t) lo = mid;
    else hi = mid - 1;
  }
  if (!straight || lo === pts.length - 1) return pts[lo][1];
  const a = pts[lo] as [number, number];
  const b = pts[lo + 1] as [number, number];
  return (a[1] + ((b[1] - a[1]) * (t - a[0])) / (b[0] - a[0])) as T;
}

// A round number at or above v for the top of an axis: 1, 2, 2.5 or 5 times a power of ten.
export function niceUp(v: number): number {
  const e = Math.pow(10, Math.floor(Math.log10(v)));
  const m = v / e;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * e;
}

export const r1 = (x: number) => Math.round(x * 10) / 10;
export const px = (x: number) => r1(x) + 'px';

// An inline style written as CSS text ('left: 4px; top: 2px;'), as React takes it.
const parsed = new Map<string, Record<string, string>>();
export function css(text: string): Record<string, string> {
  let found = parsed.get(text);
  if (!found) {
    found = {};
    for (const part of text.split(';')) {
      const i = part.indexOf(':');
      if (i < 0) continue;
      const key = part.slice(0, i).trim().replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());
      if (key) found[key] = part.slice(i + 1).trim();
    }
    parsed.set(text, found);
  }
  return found;
}
