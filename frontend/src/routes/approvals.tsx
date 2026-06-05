import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api/client"
import { getErrorMessage } from "../lib/errors"
import { queryKeys } from "../lib/queryKeys"
import type {
  PendingResponse,
  StateSummary,
  Technique,
  TechniquesResponse,
} from "../types/api"

export const Route = createFileRoute("/approvals")({
  component: ApprovalsPage,
})

type ActionState = { techniqueId: string; kind: "approve" | "reject" } | null

type Toast = {
  id: number
  kind: "success" | "error"
  message: string
}

type SnapshotContext = {
  pendingSnapshot?: PendingResponse
  stateSnapshot?: StateSummary
  techniqueSnapshot?: Technique
  techniquesSnapshots?: [readonly unknown[], TechniquesResponse | undefined][]
}

const EMPTY_PENDING: Technique[] = []

function ApprovalsPage() {
  const queryClient = useQueryClient()

  const [activeAction, setActiveAction] = useState<ActionState>(null)
  const [selectedTechniqueId, setSelectedTechniqueId] = useState<string | null>(
    null,
  )
  const [inspectTechniqueId, setInspectTechniqueId] = useState<string | null>(
    null,
  )
  const [rejectingTechniqueId, setRejectingTechniqueId] = useState<
    string | null
  >(null)
  const [rejectReason, setRejectReason] = useState("")
  const [toasts, setToasts] = useState<Toast[]>([])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.pending,
    queryFn: api.getPending,
    refetchInterval: 5000,
  })

  const addToast = useCallback((kind: Toast["kind"], message: string) => {
    const id = Date.now() + Math.floor(Math.random() * 1000)
    setToasts((current) => [...current, { id, kind, message }])

    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 4200)
  }, [])

  const approveMutation = useMutation({
    mutationFn: (techniqueId: string) => api.approve(techniqueId),
    onMutate: async (techniqueId) => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: queryKeys.pending }),
        queryClient.cancelQueries({ queryKey: queryKeys.state }),
        queryClient.cancelQueries({
          queryKey: queryKeys.technique(techniqueId),
        }),
        queryClient.cancelQueries({ queryKey: ["techniques"] }),
      ])

      const pendingSnapshot = queryClient.getQueryData<PendingResponse>(
        queryKeys.pending,
      )
      const stateSnapshot = queryClient.getQueryData<StateSummary>(
        queryKeys.state,
      )
      const techniqueSnapshot = queryClient.getQueryData<Technique>(
        queryKeys.technique(techniqueId),
      )
      const techniquesSnapshots =
        queryClient.getQueriesData<TechniquesResponse>({
          queryKey: ["techniques"],
        })

      optimisticUpdateTechnique(queryClient, techniqueId, (technique) => {
        const total = (technique.total_rules ?? 0) + 1
        const enabled = (technique.enabled_rules ?? 0) + 1

        return {
          ...technique,
          pending_approval: false,
          approved: true,
          deployed: true,
          rejected: false,
          verdict: "COVERED",
          total_rules: total,
          enabled_rules: enabled,
          enabled_percentage: total > 0 ? round1((enabled / total) * 100) : 0,
        }
      })

      queryClient.setQueryData<StateSummary | undefined>(
        queryKeys.state,
        (current) => {
          if (!current) return current
          return {
            ...current,
            pending_approvals: Math.max(0, current.pending_approvals - 1),
          }
        },
      )

      return {
        pendingSnapshot,
        stateSnapshot,
        techniqueSnapshot,
        techniquesSnapshots,
      }
    },
    onError: (mutationError, techniqueId, context) => {
      restoreSnapshots(queryClient, techniqueId, context)
      addToast("error", getErrorMessage(mutationError, "Approval failed"))
    },
    onSuccess: (result) => {
      addToast("success", `Approved and deployed ${result.technique_id}`)
    },
    onSettled: async (_result, _error, techniqueId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.pending }),
        queryClient.invalidateQueries({ queryKey: queryKeys.state }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.technique(techniqueId),
        }),
        queryClient.invalidateQueries({ queryKey: ["techniques"] }),
      ])

      setActiveAction((current) =>
        current?.techniqueId === techniqueId ? null : current,
      )
      setRejectingTechniqueId((current) =>
        current === techniqueId ? null : current,
      )
      setRejectReason("")
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({
      techniqueId,
      reason,
    }: {
      techniqueId: string
      reason: string
    }) => api.reject(techniqueId, reason),
    onMutate: async ({ techniqueId }) => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: queryKeys.pending }),
        queryClient.cancelQueries({ queryKey: queryKeys.state }),
        queryClient.cancelQueries({
          queryKey: queryKeys.technique(techniqueId),
        }),
        queryClient.cancelQueries({ queryKey: ["techniques"] }),
      ])

      const pendingSnapshot = queryClient.getQueryData<PendingResponse>(
        queryKeys.pending,
      )
      const stateSnapshot = queryClient.getQueryData<StateSummary>(
        queryKeys.state,
      )
      const techniqueSnapshot = queryClient.getQueryData<Technique>(
        queryKeys.technique(techniqueId),
      )
      const techniquesSnapshots =
        queryClient.getQueriesData<TechniquesResponse>({
          queryKey: ["techniques"],
        })

      optimisticUpdateTechnique(queryClient, techniqueId, (technique) => ({
        ...technique,
        pending_approval: false,
        approved: false,
        deployed: false,
        rejected: true,
        generated_rule: null,
        rule_explanation: null,
        rule_confidence: null,
      }))

      queryClient.setQueryData<StateSummary | undefined>(
        queryKeys.state,
        (current) => {
          if (!current) return current
          return {
            ...current,
            pending_approvals: Math.max(0, current.pending_approvals - 1),
          }
        },
      )

      return {
        pendingSnapshot,
        stateSnapshot,
        techniqueSnapshot,
        techniquesSnapshots,
      }
    },
    onError: (mutationError, variables, context) => {
      restoreSnapshots(queryClient, variables.techniqueId, context)
      addToast("error", getErrorMessage(mutationError, "Rejection failed"))
    },
    onSuccess: (result, variables) => {
      const withReason = variables.reason
        ? ` (reason: ${variables.reason})`
        : ""
      addToast("success", `Rejected ${result.technique_id}${withReason}`)
    },
    onSettled: async (_result, _error, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.pending }),
        queryClient.invalidateQueries({ queryKey: queryKeys.state }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.technique(variables.techniqueId),
        }),
        queryClient.invalidateQueries({ queryKey: ["techniques"] }),
      ])

      setActiveAction((current) =>
        current?.techniqueId === variables.techniqueId ? null : current,
      )
      setRejectingTechniqueId((current) =>
        current === variables.techniqueId ? null : current,
      )
      setRejectReason("")
    },
  })

  const pending = data?.pending ?? EMPTY_PENDING
  const isMutating = approveMutation.isPending || rejectMutation.isPending
  const canInteract = !isMutating

  const selectedTechnique = useMemo(() => {
    if (!pending.length) return null
    return (
      pending.find((p) => p.technique_id === selectedTechniqueId) ?? pending[0]
    )
  }, [pending, selectedTechniqueId])

  const inspectedTechnique = useMemo(() => {
    if (!inspectTechniqueId) return null
    return pending.find((p) => p.technique_id === inspectTechniqueId) ?? null
  }, [inspectTechniqueId, pending])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!selectedTechnique || isMutating) return

      const target = event.target as HTMLElement | null
      const tag = (target?.tagName || "").toLowerCase()
      const isInputLike =
        tag === "input" ||
        tag === "textarea" ||
        target?.isContentEditable === true

      if (isInputLike) return

      if (event.key.toLowerCase() === "a") {
        event.preventDefault()
        setActiveAction({
          techniqueId: selectedTechnique.technique_id,
          kind: "approve",
        })
        approveMutation.mutate(selectedTechnique.technique_id)
      }

      if (event.key.toLowerCase() === "r") {
        event.preventDefault()
        setRejectingTechniqueId(selectedTechnique.technique_id)
        setRejectReason("")
      }
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [approveMutation, isMutating, selectedTechnique])

  if (isLoading) {
    return <p className="text-ink-secondary">Loading pending approvals…</p>
  }

  if (isError) {
    return (
      <p className="text-verdict-gap">
        {getErrorMessage(error, "Failed to load pending approvals")}
      </p>
    )
  }

  return (
    <section className="space-y-4">
      <header className="glass-card p-4 md:p-5">
        <p className="muted-label">Human Review</p>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold text-accent-glow">
            Approvals Queue
          </h1>
          <div className="rounded-md border border-surface-600/70 bg-surface-800/70 px-3 py-1.5 text-xs text-ink-secondary">
            <span className="mr-2 text-ink-muted">Pending rules</span>
            <span className="font-mono text-accent-glow">{pending.length}</span>
          </div>
        </div>
        <p className="mt-2 text-sm text-ink-secondary">
          Click technique ID/name to open the Technique Inspector.
        </p>
      </header>

      <div className="pointer-events-none fixed right-6 top-6 z-50 flex w-xs flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={[
              "pointer-events-auto rounded-lg border px-3 py-2 text-sm shadow-lg backdrop-blur",
              toast.kind === "success"
                ? "border-verdict-covered/50 bg-surface-800/95 text-verdict-covered"
                : "border-verdict-gap/50 bg-surface-800/95 text-verdict-gap",
            ].join(" ")}
          >
            {toast.message}
          </div>
        ))}
      </div>

      {!pending.length ? (
        <div className="glass-card p-5">
          <p className="text-base text-ink-secondary">
            No pending approvals right now.
          </p>
        </div>
      ) : (
        <>
          <div className="glass-card">
            <div className="scroll-soft max-h-[60vh] overflow-y-auto overflow-x-hidden">
              <table className="w-full table-fixed text-left text-sm">
                <thead className="sticky top-0 z-10 bg-surface-800/95 text-ink-secondary backdrop-blur">
                  <tr>
                    <th className="px-4 py-3 font-medium">Technique</th>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Generated SPL</th>
                    <th className="px-4 py-3 font-medium">Confidence</th>
                    <th className="px-4 py-3 font-medium">Provider</th>
                    <th className="px-4 py-3 text-right font-medium">
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {pending.map((technique) => {
                    const isBusy =
                      activeAction?.techniqueId === technique.technique_id
                    const isSelected =
                      selectedTechnique?.technique_id === technique.technique_id
                    const isRejecting =
                      rejectingTechniqueId === technique.technique_id
                    const inspectorUrl = `/techniques/${encodeURIComponent(technique.technique_id)}`

                    return (
                      <Fragment key={technique.technique_id}>
                        <tr
                          className={[
                            "border-t border-surface-600/70 align-top",
                            isSelected ? "bg-accent-primary/6" : "",
                          ].join(" ")}
                          onClick={() =>
                            setSelectedTechniqueId(technique.technique_id)
                          }
                        >
                          <td className="px-4 py-3">
                            <a
                              href={inspectorUrl}
                              className="font-mono text-accent-glow underline-offset-4 hover:underline"
                              onClick={(event) => event.stopPropagation()}
                            >
                              {technique.technique_id}
                            </a>
                          </td>

                          <td className="px-4 py-3">
                            <a
                              href={inspectorUrl}
                              className="text-ink-primary underline-offset-4 hover:text-accent-glow hover:underline"
                              onClick={(event) => event.stopPropagation()}
                            >
                              {technique.technique_name}
                            </a>
                            <p className="mt-1 text-xs text-ink-muted">
                              {technique.tactics?.join(", ") ||
                                "No tactic context"}
                            </p>
                          </td>

                          <td className="px-4 py-3">
                            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-surface-600/70 bg-surface-800/70 p-2 text-xs text-ink-secondary">
                              {truncateSPL(technique.generated_rule)}
                            </pre>
                          </td>

                          <td className="px-4 py-3 text-ink-secondary">
                            {formatConfidence(technique.rule_confidence)}
                          </td>

                          <td className="px-4 py-3 text-ink-secondary">
                            {formatProvider(technique.rule_provider)}
                          </td>

                          <td className="px-4 py-3">
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                className="cursor-pointer rounded-md border border-surface-600 px-2.5 py-1.5 text-xs text-ink-secondary transition hover:bg-surface-700/70 disabled:cursor-not-allowed disabled:opacity-50"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setInspectTechniqueId((current) =>
                                    current === technique.technique_id
                                      ? null
                                      : technique.technique_id,
                                  )
                                  setSelectedTechniqueId(technique.technique_id)
                                }}
                              >
                                {inspectTechniqueId === technique.technique_id
                                  ? "Close"
                                  : "Inspect"}
                              </button>

                              <button
                                type="button"
                                className="cursor-pointer rounded-md border border-verdict-covered/45 bg-verdict-covered/15 px-2.5 py-1.5 text-xs font-medium text-verdict-covered transition hover:bg-verdict-covered/25 disabled:cursor-not-allowed disabled:opacity-50"
                                disabled={!canInteract || isBusy}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setActiveAction({
                                    techniqueId: technique.technique_id,
                                    kind: "approve",
                                  })
                                  approveMutation.mutate(technique.technique_id)
                                }}
                              >
                                {isBusy && activeAction?.kind === "approve"
                                  ? "Approving..."
                                  : "Approve"}
                              </button>

                              <button
                                type="button"
                                className="cursor-pointer rounded-md border border-verdict-gap/45 bg-verdict-gap/15 px-2.5 py-1.5 text-xs font-medium text-verdict-gap transition hover:bg-verdict-gap/25 disabled:cursor-not-allowed disabled:opacity-50"
                                disabled={!canInteract || isBusy}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setRejectingTechniqueId(
                                    technique.technique_id,
                                  )
                                  setSelectedTechniqueId(technique.technique_id)
                                  setRejectReason("")
                                }}
                              >
                                Reject
                              </button>
                            </div>
                          </td>
                        </tr>

                        {isRejecting ? (
                          <tr className="border-t border-surface-600/60 bg-surface-800/40">
                            <td className="px-4 py-3" colSpan={6}>
                              <div className="space-y-2 rounded-md border border-surface-600/70 bg-surface-800/70 p-3">
                                <label className="block text-xs text-ink-secondary">
                                  Rejection reason
                                  <textarea
                                    value={rejectReason}
                                    onChange={(event) =>
                                      setRejectReason(event.target.value)
                                    }
                                    rows={3}
                                    className="mt-1 w-full rounded-md border border-surface-600 bg-surface-800 px-2 py-1.5 text-sm text-ink-primary outline-none ring-accent-primary/40 focus:ring"
                                    placeholder="Optional: explain why this rule should be rejected"
                                    disabled={!canInteract || isBusy}
                                  />
                                </label>

                                <div className="flex items-center justify-end gap-2">
                                  <button
                                    type="button"
                                    className="cursor-pointer rounded-md border border-verdict-gap/45 bg-verdict-gap/15 px-3 py-1.5 text-xs font-medium text-verdict-gap transition hover:bg-verdict-gap/25 disabled:cursor-not-allowed disabled:opacity-50"
                                    disabled={!canInteract || isBusy}
                                    onClick={() => {
                                      setActiveAction({
                                        techniqueId: technique.technique_id,
                                        kind: "reject",
                                      })
                                      rejectMutation.mutate({
                                        techniqueId: technique.technique_id,
                                        reason: rejectReason.trim(),
                                      })
                                    }}
                                  >
                                    {isBusy && activeAction?.kind === "reject"
                                      ? "Rejecting..."
                                      : "Confirm Reject"}
                                  </button>

                                  <button
                                    type="button"
                                    className="cursor-pointer rounded-md border border-surface-600 px-3 py-1.5 text-xs text-ink-secondary transition hover:bg-surface-700/70 disabled:cursor-not-allowed disabled:opacity-50"
                                    disabled={!canInteract || isBusy}
                                    onClick={() => {
                                      setRejectingTechniqueId(null)
                                      setRejectReason("")
                                    }}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {inspectedTechnique ? (
            <section className="glass-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="muted-label">SPL Inspector</p>
                  <p className="mt-1 font-mono text-accent-glow">
                    {inspectedTechnique.technique_id} —{" "}
                    {inspectedTechnique.technique_name}
                  </p>
                </div>
                <a
                  href={`/techniques/${encodeURIComponent(inspectedTechnique.technique_id)}`}
                  className="rounded-md border border-surface-600 px-3 py-1.5 text-xs text-ink-secondary hover:text-accent-glow"
                >
                  Open full Technique Inspector
                </a>
              </div>

              <p className="mt-3 text-sm text-ink-secondary">
                {inspectedTechnique.rule_explanation ||
                  "No explanation available for this generated rule."}
              </p>

              <pre className="scroll-soft mt-3 max-h-[34vh] whitespace-pre-wrap rounded-lg border border-surface-600/70 bg-surface-900/80 p-3 text-xs text-ink-primary">
                {inspectedTechnique.generated_rule ||
                  "No generated SPL available"}
              </pre>
            </section>
          ) : null}
        </>
      )}
    </section>
  )
}

function restoreSnapshots(
  queryClient: ReturnType<typeof useQueryClient>,
  techniqueId: string,
  context: SnapshotContext | undefined,
) {
  if (!context) return

  queryClient.setQueryData(queryKeys.pending, context.pendingSnapshot)
  queryClient.setQueryData(queryKeys.state, context.stateSnapshot)
  queryClient.setQueryData(
    queryKeys.technique(techniqueId),
    context.techniqueSnapshot,
  )

  for (const [key, value] of context.techniquesSnapshots ?? []) {
    queryClient.setQueryData(key, value)
  }
}

function optimisticUpdateTechnique(
  queryClient: ReturnType<typeof useQueryClient>,
  techniqueId: string,
  update: (technique: Technique) => Technique,
) {
  queryClient.setQueryData<PendingResponse | undefined>(
    queryKeys.pending,
    (current) => {
      if (!current) return current
      return {
        pending: current.pending.filter((t) => t.technique_id !== techniqueId),
        count: Math.max(0, current.count - 1),
      }
    },
  )

  queryClient.setQueriesData<TechniquesResponse | undefined>(
    { queryKey: ["techniques"] },
    (current) => {
      if (!current) return current
      return {
        ...current,
        techniques: current.techniques.map((t) =>
          t.technique_id === techniqueId ? update(t) : t,
        ),
      }
    },
  )

  queryClient.setQueryData<Technique | undefined>(
    queryKeys.technique(techniqueId),
    (current) => (current ? update(current) : current),
  )
}

function formatConfidence(confidence: number | null) {
  if (confidence === null) return "N/A"
  return `${Math.round(confidence * 100)}%`
}

function formatProvider(provider: string | null) {
  if (!provider) return "N/A"
  if (provider === "splunk_ai_assistant_mcp") return "Splunk AI (MCP)"
  if (provider === "gemini") return "Gemini"
  return provider
}

function truncateSPL(spl: string | null) {
  if (!spl) return "No generated SPL available"
  if (spl.length <= 220) return spl
  return `${spl.slice(0, 220)}...`
}

function round1(value: number) {
  return Math.round(value * 10) / 10
}
