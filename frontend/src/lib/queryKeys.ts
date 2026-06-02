export const queryKeys = {
  health: ["health"] as const,
  state: ["state"] as const,
  techniques: (verdict?: string) => ["techniques", verdict ?? "ALL"] as const,
  technique: (techniqueId: string) => ["technique", techniqueId] as const,
  pending: ["pending"] as const,
}
