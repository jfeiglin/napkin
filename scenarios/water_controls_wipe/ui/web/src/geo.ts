// The map's outline and where each place is on it. The outline is us-atlas's states-albers-10m (the US Census
// Bureau's cartographic boundaries, projected with d3's geoAlbersUsa at scale 1300 in a 975 x 610 frame), and
// each place's point (places.json) is projected the same way.

import { geoAlbersUsa, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';
import states from 'us-atlas/states-albers-10m.json';
import points from './places.json';

export const FRAME: [number, number] = [975, 610];

type Atlas = Topology<{ nation: GeometryCollection; states: GeometryCollection }>;
const atlas = states as unknown as Atlas;
const path = geoPath(); // the outline is projected already
const round = (s: string | null) => (s ?? '').replace(/(\d+\.\d)\d+/g, '$1');

export const nation = round(path(feature(atlas, atlas.objects.nation)));
export const borders = round(path(mesh(atlas, atlas.objects.states, (a, b) => a !== b)));

const projection = geoAlbersUsa().scale(1300).translate([487.5, 305]);

// Where a place is on the frame of the map, or null when the projection has no point for it.
export function project(key: string): [number, number] | null {
  const point = (points as Record<string, { lon: number; lat: number }>)[key];
  return point ? projection([point.lon, point.lat]) : null;
}
