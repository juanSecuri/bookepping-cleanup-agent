import { Link } from 'react-router-dom'
import { ArrowRight, FileText, GitBranch, Landmark, LineChart } from 'lucide-react'
import BrandMark from '../components/BrandMark'
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
    <div className="landing-mesh relative min-h-screen overflow-hidden text-champagne-bright">
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6 sm:py-6">
        <BrandMark size="md" />
        <button
          type="button"
          onClick={toggleLocale}
          className="btn-secondary px-3 py-1.5 text-sm text-champagne-bright/80"
        >
          {locale === 'es' ? 'EN' : 'ES'}
        </button>
      </header>

      <main className="relative z-10 mx-auto flex min-h-[calc(100dvh-5.5rem)] max-w-6xl flex-col justify-center px-4 pb-12 pt-6 sm:px-6 sm:pb-16 sm:pt-8">
        <section className="max-w-2xl animate-fade-up">
          <div className="mb-6 sm:mb-8">
            <BrandMark to="" size="hero" />
          </div>
          <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.28em] text-champagne/70">
            YASNAY · The Profit Catalyst
          </p>
          <h1 className="font-display text-[2.75rem] font-medium leading-[0.95] tracking-[0.02em] text-champagne-bright sm:text-6xl md:text-7xl">
            LedgerAI
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-champagne-muted sm:mt-6 sm:text-lg md:text-xl">
            {t('landing.subtitle')}
          </p>
          <Link
            to="/workspaces"
            className="btn-primary mt-8 w-full px-6 py-3.5 sm:mt-10 sm:w-auto"
          >
            {t('landing.cta')}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </section>

        <section className="mt-16 animate-fade-up-delay-2 border-t border-champagne/15 pt-10 sm:mt-24 sm:pt-12">
          <p className="mb-6 text-xs font-medium uppercase tracking-[0.22em] text-champagne/65">
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
                  <Icon className="mb-3 h-5 w-5 text-champagne transition group-hover:text-champagne-bright" />
                  <p className="text-sm leading-snug text-champagne-muted transition group-hover:text-champagne-bright/90">
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
