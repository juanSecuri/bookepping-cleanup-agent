import { NavLink, Outlet, useParams, Link, useNavigate } from 'react-router-dom'
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
  Sun,
  Moon,
  LogOut,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import BrandMark from '../../components/BrandMark'
import { useTheme } from '../../components/ThemeProvider'
import { useAuth } from '../../auth/AuthProvider'
import { useLocale } from '../../i18n'
import { api, type Workspace } from '../../lib/api'
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
  const navigate = useNavigate()
  const { t, locale, toggleLocale } = useLocale()
  const { theme, toggleTheme } = useTheme()
  const { configured: authOn, signOut } = useAuth()
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
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

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    setWorkspace(null)
    void api
      .getWorkspace(workspaceId)
      .then((ws) => {
        if (!cancelled) setWorkspace(ws)
      })
      .catch(() => {
        if (!cancelled) setWorkspace(null)
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  const controls = (compact: boolean) => (
    <div
      className={cn(
        'sidebar-controls flex gap-1.5',
        compact ? 'flex-col items-center' : 'flex-row',
      )}
    >
      <button
        type="button"
        onClick={toggleLocale}
        title={`${t('common.lang')}: ${locale.toUpperCase()}`}
        className={cn(
          'flex items-center rounded-md border border-sidebar-border bg-sidebar-accent/50 text-sm text-sidebar-foreground transition duration-200 hover:border-[var(--accent-cream)]/40 hover:bg-sidebar-accent',
          compact ? 'justify-center px-2 py-2' : 'gap-1.5 px-2.5 py-1.5',
        )}
      >
        <Languages className="h-3.5 w-3.5" />
        {!compact && <span className="font-semibold tracking-wide">{locale.toUpperCase()}</span>}
      </button>
      <button
        type="button"
        onClick={toggleTheme}
        title="Dark / Light"
        className={cn(
          'flex items-center rounded-md border border-sidebar-border bg-sidebar-accent/50 text-sm text-sidebar-foreground transition duration-200 hover:border-[var(--accent-cream)]/40 hover:bg-sidebar-accent',
          compact ? 'justify-center px-2 py-2' : 'gap-1.5 px-2.5 py-1.5',
        )}
      >
        {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        {!compact && <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>}
      </button>
      {authOn ? (
        <button
          type="button"
          title="Sign out"
          onClick={() => {
            void signOut().then(() => navigate('/login', { replace: true }))
          }}
          className={cn(
            'flex items-center rounded-md border border-sidebar-border bg-sidebar-accent/50 text-sm text-sidebar-foreground transition duration-200 hover:border-[var(--accent-cream)]/40 hover:bg-sidebar-accent',
            compact ? 'justify-center px-2 py-2' : 'gap-1.5 px-2.5 py-1.5',
          )}
        >
          <LogOut className="h-3.5 w-3.5" />
          {!compact && <span>Sign out</span>}
        </button>
      ) : null}
    </div>
  )

  const nav = (compact: boolean) => (
    <nav className="flex flex-col gap-1">
      {navItems.map(({ to, end, key, icon: Icon }, i) => (
        <NavLink
          key={key}
          to={to ? `${base}/${to}` : base}
          end={end}
          title={t(key)}
          onClick={() => setMobileOpen(false)}
          style={{ animationDelay: `${i * 40}ms` }}
          className={({ isActive }) =>
            cn(
              'animate-fade-up flex items-center rounded-md py-2.5 text-sm transition duration-200',
              compact ? 'justify-center px-2' : 'gap-3 px-3',
              isActive
                ? 'nav-item-active border border-[#faf6ee]/50 bg-[#1a4032] text-[#faf6ee]'
                : 'border border-transparent text-[#f3ead8] hover:border-[#faf6ee]/40 hover:bg-[#1a4032] hover:text-[#ffffff]',
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
        {/* Sticky top: brand + lang/theme always visible */}
        <div
          className={cn(
            'sticky top-0 z-10 border-b border-sidebar-border bg-sidebar/95 backdrop-blur-md',
            collapsed ? 'px-2 py-3' : 'px-4 py-4',
          )}
        >
          <div className="flex items-start justify-between gap-2">
            {collapsed ? (
              <Link to="/" title="The Profit Catalyst · LedgerAI" className="mx-auto block">
                <span className="font-display text-xl font-semibold text-[#faf6ee]">
                  L
                </span>
              </Link>
            ) : (
              <BrandMark size="sm" subtitle={t('brand.subtitle')} forceSidebarCream />
            )}
            <button
              type="button"
              onClick={() => setCollapsed((v) => !v)}
              className="rounded-md p-1.5 text-[#f3ead8]/80 transition duration-200 hover:bg-[#1a4032] hover:text-[#faf6ee]"
              title={collapsed ? t('nav.expand') : t('nav.collapse')}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </button>
          </div>
          {!collapsed && workspace?.name && (
            <p className="mt-2 truncate text-sm font-semibold text-[#faf6ee]">
              {workspace.name}
            </p>
          )}
          <div className={cn('mt-3', collapsed && 'mt-2')}>{controls(collapsed)}</div>
        </div>

        <div className={cn('flex-1 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')}>
          {nav(collapsed)}
          {!collapsed && (
            <div className="mt-6 animate-fade-up-delay-2">
              <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#f3ead8]/80">
                {t('nav.pipeline')}
              </p>
              <ol className="space-y-1.5">
                {pipeline.map((key, i) => (
                  <li
                    key={key}
                    className="flex items-center gap-2.5 text-xs font-medium text-[#f3ead8] transition duration-200 hover:text-white"
                  >
                    <span className="flex h-5 w-5 items-center justify-center rounded-md border border-[#faf6ee]/40 bg-[#1a4032] text-[10px] font-semibold text-[#faf6ee]">
                      {i + 1}
                    </span>
                    {t(key)}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        <div className={cn('border-t border-sidebar-border py-3', collapsed ? 'px-2' : 'px-4')}>
          <Link
            to="/workspaces"
            className={cn(
              'block text-center text-xs text-[#f3ead8]/75 transition duration-200 hover:text-[#faf6ee]',
              collapsed && 'truncate',
            )}
          >
            {collapsed ? '←' : `← ${t('nav.workspaces')}`}
          </Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card/95 px-4 py-3 backdrop-blur-md lg:hidden">
          <button type="button" onClick={() => setMobileOpen(true)} className="rounded-md p-2">
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-display text-lg font-semibold tracking-[0.04em] text-primary">
            LedgerAI
          </span>
          <div className="flex items-center gap-1">
            <button type="button" onClick={toggleLocale} className="rounded-md px-2 py-1 text-sm font-semibold">
              {locale.toUpperCase()}
            </button>
            <button type="button" onClick={toggleTheme} className="rounded-md px-2 py-1 text-sm">
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>

        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileOpen(false)}
              aria-label="Close"
            />
            <div className="relative flex h-full w-72 flex-col bg-sidebar text-sidebar-foreground animate-fade-up">
              <div className="flex items-center justify-between border-b border-sidebar-border px-4 py-4">
                <BrandMark size="sm" to="" subtitle={t('brand.subtitle')} />
                <button type="button" onClick={() => setMobileOpen(false)}>
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="border-b border-sidebar-border px-4 py-3">{controls(false)}</div>
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
                  'flex min-w-0 flex-1 flex-col items-center gap-0.5 px-0.5 py-2 text-[10px] leading-tight transition duration-200',
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
