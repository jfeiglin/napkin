// The board's own arithmetic, against straight computations and properties: the reading of a series at a time,
// the top of an axis, its ticks, the lanes of the sales and the markers of the map.

import { describe, expect, it } from 'vitest';
import { tickStep } from './chart';
import { niceUp, sample } from './format';
import { project } from './geo';
import { lanes } from './graph';
import { MX, spread } from './map';
import points from './places.json';
import type { Series, Tie } from './types';

// A small generator of numbers, so that each run of the tests reads the same cases.
function random(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

describe('sample', () => {
  it('reads a stepped series as its last point at or before the time', () => {
    const next = random(1);
    for (let n = 0; n < 200; n++) {
      const series: Series = [];
      let t = 0;
      for (let k = 0; k < 1 + Math.floor(next() * 12); k++) {
        t += next() * 5;
        series.push([t, Math.round(next() * 10)]);
      }
      const at = next() * (t + 2) - 1;
      const before = series.filter((p) => p[0] <= at);
      expect(sample(series, at)).toBe(before.length ? before[before.length - 1][1] : series[0][1]);
    }
  });

  it('reads a straight series on the line between its two points', () => {
    const next = random(2);
    for (let n = 0; n < 200; n++) {
      const t0 = next() * 10;
      const t1 = t0 + 0.1 + next() * 10;
      const v0 = next() * 100;
      const v1 = next() * 100;
      const w = next();
      const at = t0 + w * (t1 - t0);
      const series: Series = [[t0, v0], [t1, v1]];
      expect(sample(series, at, true)).toBeCloseTo(v0 * (1 - w) + v1 * w, 9);
    }
  });
});

describe('niceUp', () => {
  it('gives the least of 1, 2, 2.5, 5 and 10 times a power of ten that is at least the value', () => {
    const next = random(3);
    for (let n = 0; n < 500; n++) {
      const v = Math.pow(10, next() * 12 - 3);
      const top = niceUp(v);
      const power = Math.pow(10, Math.floor(Math.log10(v)));
      const candidates = [1, 2, 2.5, 5, 10].map((m) => m * power).filter((c) => c >= v * (1 - 1e-12));
      expect(top).toBeCloseTo(Math.min(...candidates), 9);
    }
  });
});

describe('tickStep', () => {
  it('gives six ticks or fewer, and more than six with the next smaller step', () => {
    const steps = [1, 2, 3, 6, 12, 24, 48, 72, 120, 168, 240, 336, 480, 720, 1440];
    for (let tMax = 1; tMax <= 2160; tMax += 7) {
      const step = tickStep(tMax);
      expect(tMax / step).toBeLessThanOrEqual(6);
      const smaller = steps.filter((s) => s < step);
      if (smaller.length) expect(tMax / smaller[smaller.length - 1]).toBeGreaterThan(6);
    }
  });
});

describe('lanes', () => {
  it('gives each sale its own lane, and counts each system’s sales in and out', () => {
    const next = random(4);
    for (let n = 0; n < 100; n++) {
      const order = Array.from({ length: 2 + Math.floor(next() * 5) }, (_, i) => 's' + i);
      const ties: Tie[] = [];
      for (let b = 1; b < order.length; b++) {
        for (let a = 0; a < b; a++) {
          if (next() < 0.4) ties.push({ id: a + '-' + b, seller: order[a], buyer: order[b], capacity: 1 });
        }
      }
      const found = lanes(order, ties);
      expect(new Set(found.lanes.map((l) => l.x)).size).toBe(ties.length);
      order.forEach((s, i) => {
        expect(found.nIn[i]).toBe(ties.filter((t) => t.buyer === s).length);
        expect(found.nOut[i]).toBe(ties.filter((t) => t.seller === s).length);
      });
      // A buyer lower down takes a lane further out.
      for (const a of found.lanes) {
        for (const b of found.lanes) {
          if (a.buyer < b.buyer) expect(a.x).toBeGreaterThan(b.x);
        }
      }
    }
  });
});

describe('the map', () => {
  it('has a point on the map for each place, and its markers do not touch', () => {
    const keys = Object.keys(points);
    const placed = keys.map((key) => {
      const xy = project(key);
      expect(xy).not.toBeNull();
      return { key, name: key, systems: 1, x: xy![0], y: xy![1] };
    });
    const markers = spread(placed, 704 / 975, 176);
    for (let i = 0; i < markers.length; i++) {
      expect(markers[i].x).toBeGreaterThan(MX - 20);
      for (let j = i + 1; j < markers.length; j++) {
        const d = Math.hypot(markers[i].x - markers[j].x, markers[i].y - markers[j].y);
        expect(d).toBeGreaterThanOrEqual(markers[i].r + markers[j].r);
      }
    }
  });
});
