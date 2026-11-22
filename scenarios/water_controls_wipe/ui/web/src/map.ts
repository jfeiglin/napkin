import type { Point } from './types';

export const MX = 0;

interface Marker {
  p: Point;
  ax: number;
  ay: number;
  x: number;
  y: number;
  r: number;
}

// Markers that would touch move apart, each by half of the overlap, until none touch.
export function spread(points: Point[], s: number, my: number, radius = 7): Marker[] {
  const pts = points.map((p) => {
    const x = MX + p.x * s;
    const y = my + p.y * s;
    return { p, ax: x, ay: y, x, y, r: radius };
  });
  for (let it = 0; it < 120; it++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i];
        const b = pts[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dd = Math.hypot(dx, dy) || 0.01;
        const want = a.r + b.r + 3;
        if (dd < want) {
          const push = (want - dd) / 2 + 0.2;
          const ux = dx / dd;
          const uy = dy / dd;
          a.x -= ux * push;
          a.y -= uy * push;
          b.x += ux * push;
          b.y += uy * push;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  return pts;
}
