export function formatDuration(us: number | null | undefined): string {
  if (us == null || !Number.isFinite(us)) return '-'
  if (us >= 1_000_000) return `${(us / 1_000_000).toFixed(1)}s`
  if (us >= 1_000) return `${(us / 1_000).toFixed(1)}ms`
  return `${Math.round(us)}μs`
}
