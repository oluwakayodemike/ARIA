import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api/client"
import { getErrorMessage } from "../lib/errors"
import { queryKeys } from "../lib/queryKeys"
import type { Technique } from "../types/api"

export const Route = createFileRoute("/approvals")({
  component: ApprovalsPage,
})

type ActionState = { techniqueId: string; kind: "approve" | "reject" } | null

type ToastKind = "success" | "error" | "info" | "loading"

type Toast = {
  id: number
  kind: ToastKind
  title: string
  message?: string
  sticky?: boolean
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

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const pushToast = useCallback(
    ({ kind, title, message, sticky = false }: Omit<Toast, "id">) => {
      const id = Date.now() + Math.floor(Math.random() * 1000)
      setToasts((current) => [...current, { id, kind, title, message, sticky }])

      if (!sticky) {
        window.setTimeout(() => {
          dismissToast(id)
        }, 4500)
      }

      return id
    },
    [dismissToast],
  )

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

      const loadingToastId = pushToast({
        kind: "loading",
        title: "Approving rule",
        message: `Deploying ${techniqueId} to Splunk...`,
        sticky: true,
      })

      return { loadingToastId }
    },
    onError: (mutationError, techniqueId, context) => {
      if (context?.loadingToastId) dismissToast(context.loadingToastId)
      pushToast({
        kind: "error",
        title: "Approval failed",
        message: getErrorMessage(
          mutationError,
          `Failed to approve ${techniqueId}`,
        ),
      })
    },
    onSuccess: (result, _techniqueId, context) => {
      if (context?.loadingToastId) dismissToast(context.loadingToastId)
      pushToast({
        kind: "success",
        title: "Rule approved",
        message: `${result.technique_id} deployed successfully`,
      })
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

      const loadingToastId = pushToast({
        kind: "loading",
        title: "Rejecting rule",
        message: `Processing rejection for ${techniqueId}...`,
        sticky: true,
      })

      return { loadingToastId }
    },
    onError: (mutationError, variables, context) => {
      if (context?.loadingToastId) dismissToast(context.loadingToastId)
      pushToast({
        kind: "error",
        title: "Rejection failed",
        message: getErrorMessage(
          mutationError,
          `Failed to reject ${variables.techniqueId}`,
        ),
      })
    },
    onSuccess: (result, variables, context) => {
      if (context?.loadingToastId) dismissToast(context.loadingToastId)
      const withReason = variables.reason ? ` (${variables.reason})` : ""
      pushToast({
        kind: "info",
        title: "Rule rejected",
        message: `${result.technique_id}${withReason}`,
      })
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

      <div className="pointer-events-none fixed right-6 top-6 z-50 flex w-sm flex-col gap-2">
        {toasts.map((toast) => (
          <article
            key={toast.id}
            className="pointer-events-auto rounded-xl border border-surface-600/80 bg-surface-800/95 p-3 shadow-[0_14px_34px_rgba(0,0,0,0.35)] backdrop-blur"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={toastAccentClass(toast.kind)}>
                    {toastIcon(toast.kind)}
                  </span>
                  <p className="text-base text-accent-glow">{toast.title}</p>
                </div>
                {toast.message ? (
                  <p className="mt-1 text-sm text-ink-secondary">
                    {toast.message}
                  </p>
                ) : null}
              </div>

              <button
                type="button"
                aria-label="Dismiss notification"
                className="cursor-pointer rounded-md p-1 text-ink-muted transition hover:bg-surface-700/70 hover:text-ink-secondary"
                onClick={() => dismissToast(toast.id)}
              >
                ✕
              </button>
            </div>
          </article>
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

function toastIcon(kind: ToastKind) {
  if (kind === "success") {
    return (
      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
        <path
          d="M20 7L9.5 17.5 4 12"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }

  if (kind === "error") {
    return (
      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
        <path
          d="M15 9L9 15M9 9l6 6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }

  if (kind === "loading") {
    return (
      <svg
        viewBox="0 0 24 24"
        className="h-3.5 w-3.5 animate-spin"
        fill="none"
        aria-hidden
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          stroke="currentColor"
          strokeOpacity="0.28"
          strokeWidth="2"
        />
        <path
          d="M12 3a9 9 0 019 9"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <path
        d="M12 10.5V16M12 7.5h.01"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function toastAccentClass(kind: ToastKind) {
  if (kind === "success") {
    return "inline-flex h-5 w-5 items-center justify-center rounded-full border border-verdict-covered/55 text-verdict-covered"
  }

  if (kind === "error") {
    return "inline-flex h-5 w-5 items-center justify-center rounded-full border border-verdict-gap/55 text-verdict-gap"
  }

  if (kind === "loading") {
    return "inline-flex h-5 w-5 items-center justify-center rounded-full border border-verdict-partial/55 text-verdict-partial"
  }

  return "inline-flex h-5 w-5 items-center justify-center rounded-full border border-accent-primary/55 text-accent-primary"
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
