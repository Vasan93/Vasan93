import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Keeps one broken screen from taking the whole app down with it. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled UI error:', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children

    return (
      <main className="mx-auto max-w-lg px-6 py-20 text-center">
        <h1 className="font-serif text-2xl font-semibold">Something went wrong on this screen</h1>
        <p className="mt-2 text-ink/60">
          Your games, puzzles and progress are safe. Reloading usually clears it.
        </p>
        <p className="mt-4 rounded-lg bg-ink/5 px-3 py-2 text-left font-mono text-xs text-ink/60">
          {this.state.error.message}
        </p>
        <button
          onClick={() => window.location.reload()}
          className="mt-6 rounded-lg bg-accent px-4 py-2 font-medium text-white transition hover:bg-accent/90"
        >
          Reload
        </button>
      </main>
    )
  }
}
