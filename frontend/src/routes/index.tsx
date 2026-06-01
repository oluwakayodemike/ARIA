import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: Index,
})

function Index() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <h1 className="text-4xl font-mono text-accent-glow animate-pulse">ARIA War Room is Online</h1>
    </div>
  )
}