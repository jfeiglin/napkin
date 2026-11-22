import { describe, expect, it } from 'vitest';
import { reading } from './format';
import { project } from './geo';
import { spread } from './map';
import points from './places.json';

describe('service reading units', () => {
  it('preserves a genuine zero and expresses fractions as percentages', () => {
    expect(reading(0, 'Mgal')).toBe('0 million gallons');
    expect(reading(0.235, 'fraction')).toBe('23.5%');
    expect(reading(0.0000042, 'USD2025_bn')).toBe('4,200 USD (2025)');
    expect(reading(3, 'person*days')).toBe('3 person-days');
    expect(reading(2.5, 'facility_hours')).toBe('2.5 facility-hours');
  });
});
describe('the map', () => {
  it('lets each listed service area be selected', () => {
    const locations = Object.keys(points).map((key) => {
      const xy = project(key);
      expect(xy).not.toBeNull();
      return { key, name: key, systems: 1, x: xy![0], y: xy![1] };
    });
    const markers = spread(locations, 1, 0, 10);
    for (let i = 0; i < markers.length; i++) {
      for (const other of markers.slice(i + 1)) {
        expect(Math.hypot(markers[i].x - other.x, markers[i].y - other.y)).toBeGreaterThanOrEqual(20);
      }
    }
  });
});
