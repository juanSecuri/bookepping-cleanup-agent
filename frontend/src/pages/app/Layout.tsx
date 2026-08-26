import { NavLink, Outlet, useParams, Link } from 'react-router-dom'
import {
  LayoutDashboard,
  FileText,
  ArrowLeftRight,
  Landmark,
  LineChart,
  BookOpen,
  Languages,
  Menu,
  X,
  PanelLeftClose,
  PanelLeft,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import BrandMark from '../../components/BrandMark'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

const navItems = [
  { to: '', end: true as boolean, key: 'nav.dashboard', icon: LayoutDashboard },
  { to: 'documents', end: false as boolean, key: 'nav.documents', icon: FileText },
  { to: 'transactions', end: false as boolean, key: 'nav.transactions', icon: ArrowLeftRight },
  { to: 'reconciliation', end: false as boolean, key: 'nav.reconciliation', icon: Landmark },
  { to: 'reports', end: false as boolean, key: 'nav.reports', icon: LineChart },
  { to: 'chart-of-accounts', end: false as boolean, key: 'nav.coa', icon: BookOpen },
]

const pipeline = [
  'dashboard.stage.ingest',
  'dashboard.stage.classify',
  'dashboard.stage.review',
  'dashboard.stage.reconcile',
  'dashboard.stage.close',
] as const

const SIDEBAR_KEY = 'ledgerai.sidebarCollapsed'

export default function Layout() {
  const { workspaceId } = useParams()
  const { t, locale, toggleLocale } = useLocale()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === '1'
    } catch {
      return false
    }
  })
  const base = `/app/${workspaceId}`

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [collapsed])

  const nav = (compact: boolean) => (
    <nav className="flex flex-col gap-1">
      {navItems.map(({ to, end, key, icon: Icon }) => (
        <NavLink
          key={key}
          to={to ? `${base}/${to}` : base}
          end={end}
          title={t(key)}
          onClick={() => setMobileOpen(false)}
          className={({ isActive }) =>
            cn(
              'flex items-center rounded-md py-2.5 text-sm transition duration-200',
              compact ? 'justify-center px-2' : 'gap-3 px-3',
              isActive
                ? 'border border-champagne/30 bg-sidebar-accent text-sidebar-primary'
                : 'border border-transparent text-sidebar-foreground/75 hover:border-champagne/20 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground',
            )
          }
        >
          <Icon className="h-4 w-4 shrink-0" />
          {!compact && <span className="truncate">{t(key)}</span>}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside
        className={cn(
          'hidden shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 lg:flex',
          collapsed ? 'w-[72px]' : 'w-64',
        )}
      >
        <div className={cn('border-b border-sidebar-border py-5', collapsed ? 'px-3' : 'px-5')}>
          <div className="flex items-start justify-between gap-2">
            {collapsed ? (
              <Link to="/" title="YASNAY · LedgerAI" className="mx-auto block">
                <img
                  src="/yasnay-logo.png"
                  alt="YASNAY"
                  className="mx-auto h-8 w-8 rounded-sm object-cover object-center"
                />
              </Link>
            ) : (
              <div className="min-w-0">
                <BrandMark size="sm" />
                <p className="mt-2 font-display text-lg tracking-[0.06em] text-sidebar-primary">
                  LedgerAI
                </p>
              </div>
            )}
            <button
              type="button"
              onClick={() => setCollapsed((v) => !v)}
              className="rounded-md p-1.5 text-sidebar-foreground/60 transition hover:bg-sidebar-accent hover:text-sidebar-foreground"
              title={collapsed ? 'Abrir menú' : 'Cerrar menú'}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </button>
          </div>
          {!collapsed && (
            <p className="mt-1.5 truncate text-xs text-sidebar-foreground/45">{workspaceId}</p>
          )}
        </div>
        <div className={cn('flex-1 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')}>
          {nav(collapsed)}
        </div>
        <div className={cn('border-t border-sidebar-border py-4', collapsed ? 'px-2' : 'px-4')}>
          {!collapsed && (
            <>
              <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-sidebar-foreground/45">
                {t('nav.pipeline')}
              </p>
              <ol className="mb-3 space-y-1.5">
                {pipeline.map((key, i) => (
                  <li key={key} className="flex items-center gap-2.5 text-xs text-sidebar-foreground/70">
                    <span className="flex h-5 w-5 items-center justify-center rounded-md border border-champagne/20 bg-sidebar-accent text-[10px] font-medium text-sidebar-primary">
                      {i + 1}
                    </span>
                    {t(key)}
                  </li>
                ))}
              </ol>
            </>
          )}
          <button
            type="button"
            onClick={toggleLocale}
            title={`${t('common.lang')}: ${locale.toUpperCase()}`}
            className={cn(
              'flex w-full items-center rounded-md border border-sidebar-border text-sm text-sidebar-foreground/80 transition hover:border-champagne/35 hover:bg-sidebar-accent',
              collapsed ? 'justify-center px-2 py-2' : 'gap-2 px-3 py-2',
            )}
          >
            <Languages className="h-4 w-4" />
            {!collapsed && (
              <span>
                {t('common.lang')}: {locale.toUpperCase()}
              </span>
            )}
          </button>
          {!collapsed && (
            <Link
              to="/workspaces"
              className="mt-2 block text-center text-xs text-sidebar-foreground/45 transition hover:text-sidebar-foreground"
            >
              ← {t('nav.workspaces')}
            </Link>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-card px-4 py-3 lg:hidden">
          <button type="button" onClick={() => setMobileOpen(true)} className="rounded-md p-2">
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-display text-lg tracking-[0.04em] text-primary">LedgerAI</span>
          <button type="button" onClick={toggleLocale} className="rounded-md px-2 py-1 text-sm">
            {locale.toUpperCase()}
          </button>
        </header>

        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileOpen(false)}
              aria-label="Close"
            />
            <div className="relative flex h-full w-72 flex-col bg-sidebar text-sidebar-foreground">
              <div className="flex items-center justify-between border-b border-sidebar-border px-4 py-4">
                <BrandMark size="sm" to="" />
                <button type="button" onClick={() => setMobileOpen(false)}>
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto px-3 py-4">{nav(false)}</div>
            </div>
          </div>
        )}

        <main className="flex-1 overflow-x-hidden overflow-y-auto p-4 pb-[calc(5.5rem+env(safe-area-inset-bottom))] sm:p-6 lg:p-8 lg:pb-8">
          <Outlet />
        </main>

        <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-card pb-[env(safe-area-inset-bottom)] lg:hidden">
          {navItems.slice(0, 5).map(({ to, end, key, icon: Icon }) => (
            <NavLink
              key={key}
              to={to ? `${base}/${to}` : base}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex min-w-0 flex-1 flex-col items-center gap-0.5 px-0.5 py-2 text-[10px] leading-tight transition',
                  isActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground/80',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="w-full truncate text-center">{t(key)}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}
