import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import BrandMark from '../components/BrandMark'
import HeroParticles from '../components/HeroParticles'
import { useTheme } from '../components/ThemeProvider'
import { useLocale } from '../i18n'
import { cn } from '../lib/utils'

const features = [
  {
    title: 'Ingesta Drive / web / foto / audio',
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M12 18v-6M9 15l3 3 3-3" />
      </svg>
    ),
  },
  {
    title: 'Clasificación por plan de cuentas (reglas, $0)',
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M16 3h5v5M8 3H3v5M21 16v5h-5M3 16v5h5M21 3l-7 7M3 21l7-7" />
      </svg>
    ),
  },
  {
    title: 'Conciliación bancaria por periodo',
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <path d="M2 10h20M6 15h4" />
      </svg>
    ),
  },
  {
    title: 'Balance · P&L · Cash flow por año/mes',
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M4 19V5M4 19h16M8 17V9M12 17v-5M16 17V7" />
      </svg>
    ),
  },
]

export default function Landing() {
  const { t, locale, toggleLocale } = useLocale()
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="landing-mesh relative min-h-screen overflow-hidden text-[var(--text-primary)]">
      <HeroParticles />

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6 sm:py-6">
        <BrandMark size="md" showProduct={false} />
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={toggleLocale}
            className="btn-secondary px-3 py-1.5 text-sm"
          >
            {locale === 'es' ? 'EN' : 'ES'}
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            className="btn-secondary px-3 py-1.5 text-sm"
            title="Dark / Light"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
      </header>

      <main className="relative z-10 mx-auto flex min-h-[calc(100dvh-5.5rem)] max-w-6xl flex-col justify-center px-4 pb-12 pt-6 sm:px-6 sm:pb-16 sm:pt-8">
        <section className="max-w-3xl animate-fade-up">
          <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.28em] text-[var(--text-muted)]">
            THE PROFIT CATALYST
          </p>
          <h1
            className="font-display text-[clamp(3rem,12vw,6rem)] font-medium leading-[0.92] tracking-[0.02em] text-[var(--accent-cream)]"
            style={{ textShadow: '0 4px 40px rgba(0,0,0,0.35)' }}
          >
            LedgerAI
          </h1>
          <h2 className="mt-3 font-display text-2xl text-[var(--text-primary)] sm:text-3xl">
            Bookkeeping Cleanup
          </h2>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-[var(--text-muted)] sm:mt-6 sm:text-lg">
            Organiza años de contabilidad atrasada. Clasifica, concilia y emite estados financieros
            por mes y año — sin pagar agentes IA.
          </p>
          <Link to="/workspaces" className="btn-primary mt-8 w-full px-6 py-3.5 sm:mt-10 sm:w-auto">
            {t('landing.cta') || 'Entrar al workspace'}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </section>

        <section className="mt-16 animate-fade-up-delay-2 border-t border-[var(--border)] pt-10 sm:mt-24 sm:pt-12">
          <p className="mb-6 text-xs font-medium uppercase tracking-[0.22em] text-[var(--text-muted)]">
            Capacidades
          </p>
          <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f, i) => {
              const delay =
                i === 0
                  ? 'animate-fade-up-delay-1'
                  : i === 1
                    ? 'animate-fade-up-delay-2'
                    : i === 2
                      ? 'animate-fade-up-delay-3'
                      : 'animate-fade-up-delay-4'
              return (
                <li
                  key={f.title}
                  className={cn(
                    delay,
                    'soft-shadow-lift rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 transition duration-200 hover:border-[var(--accent-cream)]/30',
                  )}
                >
                  <div className="mb-3 text-[var(--accent-cream)]">{f.icon}</div>
                  <p className="text-sm leading-snug text-[var(--text-primary)]">{f.title}</p>
                </li>
              )
            })}
          </ul>
        </section>
      </main>
    </div>
  )
}
