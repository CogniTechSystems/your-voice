const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) {
    return "-";
  }
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${BYTE_UNITS[unit]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "-";
  }
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return minutes ? `${minutes}m ${remainder.toString().padStart(2, "0")}s` : `${remainder}s`;
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "-";
}

export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : value.toFixed(1);
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
