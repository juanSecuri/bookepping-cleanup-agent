import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

/** Catches render errors so the tab does not stay blank blue. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('LedgerAI UI error', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-background px-6 text-center text-foreground">
          <h1 className="font-display text-2xl">Algo falló en la interfaz</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            Recarga la página. Si el servidor estaba procesando muchos PDFs, espera 1–2 min y vuelve a
            intentar.
          </p>
          <button
            type="button"
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
            onClick={() => window.location.reload()}
          >
            Recargar
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
