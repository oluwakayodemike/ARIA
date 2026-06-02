import type { ReactNode } from "react"
import { Link, Outlet, createRootRoute } from "@tanstack/react-router"

const navBaseClass = "nav-pill"
const navActiveClass = `${navBaseClass} nav-pill-active`
const navInactiveClass = `${navBaseClass} nav-pill-idle`

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <div className="app-frame font-body text-ink-primary">
      <div className="app-shell">
        <aside className="left-rail">
          <div className="mb-8">
            <p className="font-mono text-2xl tracking-tight text-accent-glow">
              ARIA
            </p>
          </div>

          <nav className="space-y-1.5">
            <Link
              to="/"
              activeProps={{ className: navActiveClass }}
              inactiveProps={{ className: navInactiveClass }}
            >
              <OverviewIcon />
              <span>Overview</span>
            </Link>
            <Link
              to="/techniques"
              activeProps={{ className: navActiveClass }}
              inactiveProps={{ className: navInactiveClass }}
            >
              <TechniquesIcon />
              <span>Techniques</span>
            </Link>
            <Link
              to="/approvals"
              activeProps={{ className: navActiveClass }}
              inactiveProps={{ className: navInactiveClass }}
            >
              <ApprovalsIcon />
              <span>Approvals</span>
            </Link>
          </nav>
        </aside>

        <main className="main-region">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function IconWrapper({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-flex h-4 w-4 items-center justify-center text-current"
      aria-hidden
    >
      {children}
    </span>
  )
}

function OverviewIcon() {
  return (
    <IconWrapper>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="h-4 w-4"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <rect x="3" y="4" width="8" height="7" rx="1.5" />
        <rect x="13" y="4" width="8" height="4" rx="1.5" />
        <rect x="13" y="10" width="8" height="10" rx="1.5" />
        <rect x="3" y="13" width="8" height="7" rx="1.5" />
      </svg>
    </IconWrapper>
  )
}

function TechniquesIcon() {
  return (
    <IconWrapper>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="h-4 w-4"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M4 6h16" />
        <path d="M4 12h16" />
        <path d="M4 18h10" />
        <circle cx="17" cy="18" r="2" />
      </svg>
    </IconWrapper>
  )
}

function ApprovalsIcon() {
  return (
    <IconWrapper>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="h-4 w-4"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="M9 12.5l2 2 4-4" />
        <rect x="4" y="4" width="16" height="16" rx="2" />
      </svg>
    </IconWrapper>
  )
}
