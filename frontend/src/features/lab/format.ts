// Only display labels are rounded; experiment arrays and exports stay untouched.
export function formatFrequency(value: number): string {
  return Number(value.toFixed(6)).toString();
}
