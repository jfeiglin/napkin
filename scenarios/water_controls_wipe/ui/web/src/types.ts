export interface Summary {
  key: string;
  name: string;
  systems: number;
}
export interface Point extends Summary {
  x: number;
  y: number;
}
export interface Place {
  key: string;
  name: string;
  what: string;
  model_hash: string;
  horizon: number;
  systems: { id: string; name: string }[];
  runs: { id: string; name: string }[];
  featured: string;
}
export interface Frame {
  run: string;
  horizon: number;
  hours: number[];
  model_hash: string;
  readings: Record<string, { unit: string; values: number[] }>;
}
