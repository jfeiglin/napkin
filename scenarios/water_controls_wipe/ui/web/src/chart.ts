// The story under the board: the people without their normal water (the area) and under a boil-water advisory
// (the line) from the attack to the end of the story, with a mark for each moment and the time on the slider.

import { count, niceUp, px, r1, sample, when } from './format';
import type { Frame, Place } from './types';

const STEPS = [1, 2, 3, 6, 12, 24, 48, 72, 120, 168, 240, 336, 480, 720, 1440];

// The step of the time axis: the smallest of STEPS that gives six ticks or fewer over tMax hours.
export function tickStep(tMax: number): number {
  return STEPS.find((h) => tMax / h <= 6) ?? 1440;
}

export function chart(place: Place, res: Frame, now: number | null) {
  const X0 = 112;
  const X1 = 816;
  const Y0 = 782;
  const Y1 = 912;
  const tMax = res.t_end;
  const maxAdv = Math.max(...res.adv.map((p) => p[1]));
  const top = niceUp(Math.max(1, res.peak, maxAdv));
  const xs = (t: number) => X0 + (Math.max(0, Math.min(t, tMax)) / tMax) * (X1 - X0);
  const ys = (v: number) => Y1 - (v / top) * (Y1 - Y0);
  const inside = (pts: [number, number][]) => pts.filter((p) => p[0] <= tMax + 1e-9);
  const out = inside(res.out);
  const adv = inside(res.adv);
  const line = out.map((p, i) => (i ? 'L ' : 'M ') + r1(xs(p[0])) + ' ' + r1(ys(p[1]))).join(' ');
  const area = out.length ? line + ' L ' + r1(xs(out[out.length - 1][0])) + ' ' + Y1 + ' L ' + r1(xs(out[0][0])) + ' ' + Y1 + ' Z' : '';
  let step = adv.map((p, i) => (i ? 'H ' + r1(xs(p[0])) + ' V ' + r1(ys(p[1])) : 'M ' + r1(xs(p[0])) + ' ' + r1(ys(p[1])))).join(' ');
  if (adv.length) step += ' H ' + X1;
  const tick = tickStep(tMax);
  const ticks: string[] = [];
  const labels: { text: string; css: string }[] = [];
  for (let t = 0; t <= tMax + 1e-9; t += tick) {
    ticks.push('M ' + r1(xs(t)) + ' ' + Y1 + ' V ' + (Y1 + 4));
    labels.push({ text: t === 0 ? 'Attack' : when(t), css: 'left: ' + px(xs(t) - 40) + '; top: ' + px(Y1 + 7) + '; width: 80px; text-align: center;' });
  }
  labels.push({ text: count(top), css: 'left: 40px; top: ' + px(Y0 - 7) + '; width: 64px; text-align: right;' });
  labels.push({ text: '0', css: 'left: 40px; top: ' + px(Y1 - 7) + '; width: 64px; text-align: right;' });
  const seen = new Set<number>();
  const marks: string[] = [];
  res.moments.forEach((m) => {
    if (m.t > tMax) return;
    const x = Math.round(xs(m.t));
    if (seen.has(x)) return;
    seen.add(x);
    marks.push('M ' + x + ' ' + (Y0 - 10) + ' V ' + (Y0 - 4));
  });
  const outNow = now === null ? 0 : (sample(res.out, now) ?? 0);
  const advNow = now === null ? 0 : (sample(res.adv, now) ?? 0);
  return {
    grid: 'M ' + X0 + ' ' + Y0 + ' H ' + X1 + ' M ' + X0 + ' ' + Y1 + ' H ' + X1,
    area,
    out: line,
    adv: step,
    ticks: ticks.join(' '),
    moments: marks.join(' '),
    labels,
    play: now === null ? '' : 'M ' + r1(xs(now)) + ' ' + (Y0 - 12) + ' V ' + Y1,
    outText: (place.outputs.people_interrupted_now || 'People without their normal water service') + ': ' + count(outNow),
    advText: (place.outputs.people_under_advisory || 'People under a boil-water advisory') + ': ' + count(advNow),
  };
}
