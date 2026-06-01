import { createRootRoute, Outlet } from '@tanstack/react-router'

export const Route = createRootRoute({
  component: () => (
    <div className="w-full h-screen bg-surface-900 text-ink-primary font-body overflow-hidden">
      <Outlet />
    </div>
  ),
})