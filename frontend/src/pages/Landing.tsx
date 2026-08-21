import { Link } from 'react-router-dom'
import { ArrowRight, FileText, GitBranch, Landmark, LineChart } from 'lucide-react'
import { useLocale } from '../i18n'
import { cn } from '../lib/utils'

export default function Landing() {
  const { t, locale, toggleLocale } = useLocale()

  const features = [
    { icon: FileText, label: t('landing.feature1') },
    { icon: GitBranch, label: t('landing.feature2') },
    { icon: Landmark, label: t('landing.feature3') },
    { icon: LineChart, label: t('landing.feature4') },
  ]

  return (
    <div className="landing-mesh relative min-h-screen overflow-hidden text-white">
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="font-display text-2xl tracking-tight text-amber-400 sm:text-3xl">
          LedgerAI
        </div>
        <button
          type="button"
          onClick={toggleLocale}
          className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-white/80 transition hover:border-amber-400/50 hover:text-amber-400"
        >
          {locale === 'es' ? 'EN' : 'ES'}
        </button>
      </header>

      <main className="relative z-10 mx-auto flex min-h-[calc(100vh-5.5rem)] max-w-6xl flex-col justify-center px-6 pb-16 pt-8">
        <section className="max-w-2xl animate-fade-up">
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight text-white sm:text-7xl lg:text-8xl">
            LedgerAI
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-white/65 sm:text-xl">
            {t('landing.subtitle')}
          </p>
          <Link
            to="/workspaces"
            className="mt-10 inline-flex items-center gap-2 rounded-lg bg-amber-500 px-6 py-3.5 text-sm font-semibold text-[#080c14] shadow-[0_8px_30px_rgb(217_145_40_/_0.35)] transition hover:bg-amber-400 hover:shadow-[0_10px_36px_rgb(217_145_40_/_0.45)]"
          >
            {t('landing.cta')}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </section>

        <section className="mt-24 animate-fade-up-delay-2 border-t border-white/10 pt-12">
          <p className="mb-6 text-xs font-medium uppercase tracking-[0.22em] text-amber-500/80">
            {t('landing.featuresHeading')}
          </p>
          <ul className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {features.map(({ icon: Icon, label }, i) => {
              const delay =
                i === 0
                  ? 'animate-fade-up-delay-1'
                  : i === 1
                    ? 'animate-fade-up-delay-2'
                    : i === 2
                      ? 'animate-fade-up-delay-3'
                      : 'animate-fade-up-delay-4'
              return (
                <li key={label} className={cn(delay, 'group')}>
                  <Icon className="mb-3 h-5 w-5 text-amber-400 transition group-hover:text-amber-300" />
                  <p className="text-sm leading-snug text-white/75 transition group-hover:text-white/90">
                    {label}
                  </p>
                </li>
              )
            })}
          </ul>
        </section>
      </main>
    </div>
  )
}
