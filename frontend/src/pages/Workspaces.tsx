import { useEffect, useState, type FormEvent, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus,
  ArrowRight,
  Trash2,
  FolderKanban,
  Sparkles,
  CalendarRange,
  Scale,
} from 'lucide-react'
import BrandMark from '../components/BrandMark'
import { useTheme } from '../components/ThemeProvider'
import { api, type Workspace } from '../lib/api'
import { cn } from '../lib/utils'
import { useLocale } from '../i18n'

export default function Workspaces() {
  const { t, locale, toggleLocale } = useLocale()
  const { theme, toggleTheme } = useTheme()
  const [items, setItems] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listWorkspaces()
      setItems(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const created = await api.createWorkspace({
        name: name.trim(),
        description: description.trim() || undefined,
      })
      setItems((prev) => [created, ...prev])
      setOpen(false)
      setName('')
      setDescription('')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'))
    } finally {
      setSaving(false)
    }
  }

  async function onDelete(e: MouseEvent, ws: Workspace) {
    e.preventDefault()
    e.stopPropagation()
    const ok = window.confirm(
      t('workspaces.deleteConfirm').replace('{name}', ws.name),
    )
    if (!ok) return
    setDeletingId(ws.id)
    setError(null)
    try {
      await api.deleteWorkspace(ws.id)
      setItems((prev) => prev.filter((x) => x.id !== ws.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="workspaces-shell min-h-screen text-foreground">
      <header className="border-b border-border bg-card/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <BrandMark size="sm" />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleTheme}
              className="btn-secondary px-3 py-1.5 text-sm text-muted-foreground"
            >
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
            <button
              type="button"
              onClick={toggleLocale}
              className="btn-secondary px-3 py-1.5 text-sm text-muted-foreground"
            >
              {locale === 'es' ? 'EN' : 'ES'}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-12">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4 sm:gap-6">
          <div className="max-w-xl animate-fade-up">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80">
              LedgerAI · v1.0
            </p>
            <h1 className="font-display text-3xl tracking-tight sm:text-4xl md:text-5xl">
              {t('workspaces.title')}
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground sm:text-base">
              {t('workspaces.subtitle')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="btn-primary w-full px-5 py-3 sm:w-auto"
          >
            <Plus className="h-4 w-4" />
            {t('workspaces.create')}
          </button>
        </div>

        <div className="mb-10 grid gap-3 sm:grid-cols-3 animate-fade-up-delay-1">
          {[
            {
              icon: Sparkles,
              title: t('workspaces.pitch1Title'),
              body: t('workspaces.pitch1Body'),
            },
            {
              icon: CalendarRange,
              title: t('workspaces.pitch2Title'),
              body: t('workspaces.pitch2Body'),
            },
            {
              icon: Scale,
              title: t('workspaces.pitch3Title'),
              body: t('workspaces.pitch3Body'),
            },
          ].map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="rounded-lg border border-border bg-card/80 px-4 py-4 transition hover:border-champagne/30"
            >
              <Icon className="mb-2 h-4 w-4 text-primary" />
              <p className="text-sm font-semibold">{title}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>

        {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {error && (
          <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="soft-shadow rounded-2xl border border-dashed border-border bg-card/80 px-8 py-16 text-center animate-fade-up-delay-2">
            <FolderKanban className="mx-auto mb-4 h-10 w-10 text-primary/70" />
            <p className="font-display text-2xl">{t('workspaces.empty')}</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
              {t('workspaces.emptyHint')}
            </p>
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="btn-primary mt-6 px-4 py-2.5"
            >
              <Plus className="h-4 w-4" />
              {t('workspaces.create')}
            </button>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {items.map((ws, i) => (
            <div
              key={ws.id}
              className={cn(
                'group relative overflow-hidden rounded-lg border border-border bg-card p-6 soft-shadow transition duration-200 hover:-translate-y-0.5 hover:border-champagne/35',
                i === 0 ? 'animate-fade-up-delay-1' : 'animate-fade-up-delay-2',
              )}
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-md border border-champagne/20 bg-secondary text-primary">
                  <FolderKanban className="h-5 w-5" />
                </div>
                <button
                  type="button"
                  onClick={(e) => void onDelete(e, ws)}
                  disabled={deletingId === ws.id}
                  title={t('workspaces.delete')}
                  className="rounded-lg border border-transparent p-2 text-muted-foreground transition hover:border-destructive/30 hover:bg-destructive/5 hover:text-destructive disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              <h2 className="font-display text-2xl tracking-tight">{ws.name}</h2>
              {(ws.legal_name || ws.description) && (
                <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
                  {ws.legal_name || ws.description}
                </p>
              )}
              <div className="mt-6 flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground">{t('workspaces.spaceLabel')}</span>
                <Link
                  to={`/app/${ws.id}`}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary transition group-hover:gap-2"
                >
                  {t('workspaces.open')}
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      </main>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm">
          <form
            onSubmit={onCreate}
            className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl"
          >
            <h2 className="font-display text-2xl">{t('workspaces.create')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('workspaces.createHint')}</p>
            <label className="mt-5 block text-sm font-medium">
              {t('workspaces.name')}
              <input
                className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ej. Contabilidad 2024–2026"
                required
              />
            </label>
            <label className="mt-3 block text-sm font-medium">
              {t('workspaces.description')}
              <textarea
                className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('workspaces.descPlaceholder')}
              />
            </label>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm"
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                disabled={saving}
                className="btn-primary px-4 py-2 disabled:opacity-60"
              >
                {saving ? t('common.loading') : t('common.create')}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
