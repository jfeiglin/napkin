const numbers = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 6 });
const units: Record<string, string> = {
  'person*days': 'person-days',
  facility_hours: 'facility-hours',
  Mgal: 'million gallons',
  'Mgal/h': 'million gallons per hour',
  people: 'people',
  work_h: 'work-hours',
};
export function reading(value: number, unit: string): string {
  if (unit === 'USD2025_bn') return numbers.format(value * 1e9) + ' USD (2025)';
  if (unit === 'fraction') return numbers.format(100 * value) + '%';
  if (unit === '1' || !unit) return numbers.format(value);
  return numbers.format(value) + ' ' + (units[unit] ?? unit);
}
export function when(hour: number): string {
  return numbers.format(hour) + ' h';
}
