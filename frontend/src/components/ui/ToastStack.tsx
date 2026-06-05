import {
  CheckCircleIcon,
  CloseIcon,
  ErrorCircleIcon,
  InfoCircleIcon,
  SpinnerIcon,
} from "../../icons"

export type ToastKind = "success" | "error" | "info" | "loading"

export type ToastItem = {
  id: number
  kind: ToastKind
  title: string
  message?: string
  sticky?: boolean
}

interface ToastStackProps {
  toasts: ToastItem[]
  onDismiss: (id: number) => void
}

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  if (!toasts.length) return null

  return (
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
                <p className="mt-1 text-sm text-ink-secondary">{toast.message}</p>
              ) : null}
            </div>

            <button
              type="button"
              aria-label="Dismiss notification"
              className="cursor-pointer rounded-md p-1 text-ink-muted transition hover:bg-surface-700/70 hover:text-ink-secondary"
              onClick={() => onDismiss(toast.id)}
            >
              <CloseIcon />
            </button>
          </div>
        </article>
      ))}
    </div>
  )
}

function toastIcon(kind: ToastKind) {
  if (kind === "success") return <CheckCircleIcon />
  if (kind === "error") return <ErrorCircleIcon />
  if (kind === "loading") return <SpinnerIcon />
  return <InfoCircleIcon />
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
