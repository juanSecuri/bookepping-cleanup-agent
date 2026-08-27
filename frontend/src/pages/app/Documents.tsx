import { useCallback, useEffect, useMemo, useState, type DragEvent } from 'react'
import { useParams } from 'react-router-dom'
import {
  Upload,
  HardDrive,
  RefreshCw,
  Link2,
  FolderOpen,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  Folder,
  File,
  Download,
} from 'lucide-react'
import {
  api,
  DEFAULT_DRIVE_FOLDER_ID,
  DEFAULT_DRIVE_FOLDER_NAME,
  type Document,
  type DriveBrowseNode,
  type DriveStatus,
} from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

type SelectedFile = {
  id: string
  name: string
  path: string
  mime_type: string
}

function isSelectableFile(node: DriveBrowseNode) {
  const name = node.name.toLowerCase()
  return (
    !node.is_folder &&
    (name.endsWith('.pdf') ||
      name.endsWith('.xlsx') ||
      name.endsWith('.xls') ||
      name.endsWith('.csv') ||
      name.endsWith('.png') ||
      name.endsWith('.jpg') ||
      name.endsWith('.jpeg') ||
      (node.mime_type || '').includes('pdf') ||
      (node.mime_type || '').includes('sheet') ||
      (node.mime_type || '').includes('csv') ||
      (node.mime_type || '').startsWith('image/'))
  )
}

function docPreviewKind(doc: Document): 'pdf' | 'image' | 'other' {
  const name = String(doc.filename || doc.name || doc.file_name || '').toLowerCase()
  const ft = String(doc.file_type || '').toLowerCase()
  if (name.endsWith('.pdf') || ft === 'pdf' || ft.includes('pdf')) return 'pdf'
  if (
    /\.(png|jpe?g|webp|gif|tif|tiff)$/i.test(name) ||
    ft.startsWith('image') ||
    ft === 'png' ||
    ft === 'jpg' ||
    ft === 'jpeg'
  ) {
    return 'image'
  }
  return 'other'
}

function DocumentFilePreview({
  doc,
  workspaceId,
}: {
  doc: Document
  workspaceId: string
}) {
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const kind = docPreviewKind(doc)
  const url = api.documentFileUrl(String(doc.id), workspaceId)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    setFailed(false)
    setReady(false)
    setBlobUrl(null)
    if (kind === 'other') return
    ;(async () => {
      try {
        const res = await api.fetchDocumentFile(String(doc.id), workspaceId, {
          method: 'GET',
          cache: 'no-store',
        })
        if (cancelled) return
        if (!res.ok) {
          setFailed(true)
          return
        }
        const blob = await res.blob()
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
        setReady(true)
      } catch {
        if (!cancelled) setFailed(true)
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url, kind, doc.id, workspaceId])

  if (kind === 'other') {
    return (
      <div className="flex max-h-72 min-h-[12rem] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-4 text-center text-xs text-muted-foreground">
        <p>Vista previa en pantalla para PDF e imágenes. El texto extraído está a la izquierda.</p>
        <a
          className="rounded-md border border-border px-3 py-1.5 font-medium text-foreground hover:bg-muted"
          href={blobUrl || url}
          target="_blank"
          rel="noreferrer"
        >
          Intentar abrir / descargar
        </a>
      </div>
    )
  }

  if (failed) {
    return (
      <div className="flex max-h-72 min-h-[12rem] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-4 text-center text-xs text-muted-foreground">
        <p>
          Archivo no disponible en disco (montá disco Starter en /var/data o reimportá).
          El texto OCR a la izquierda sigue disponible.
        </p>
      </div>
    )
  }

  if (!ready || !blobUrl) {
    return (
      <div className="flex max-h-72 min-h-[12rem] items-center justify-center rounded-lg border border-dashed border-border bg-card p-4 text-xs text-muted-foreground">
        Cargando vista previa…
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {kind === 'pdf' ? (
        <iframe
          title={String(doc.filename || doc.name || 'PDF')}
          src={blobUrl}
          className="h-72 w-full bg-background"
        />
      ) : (
        <img
          src={blobUrl}
          alt={String(doc.filename || doc.name || 'Imagen')}
          className="max-h-72 w-full object-contain"
          onError={() => setFailed(true)}
        />
      )}
      <div className="border-t border-border px-3 py-2 text-center">
        <a
          className="text-xs font-medium text-primary hover:underline"
          href={blobUrl}
          target="_blank"
          rel="noreferrer"
        >
          Abrir en pestaña
        </a>
      </div>
    </div>
  )
}

function BrowseTree({
  node,
  depth = 0,
  parentPath = '',
  selected,
  onToggle,
  onImportFolder,
}: {
  node: DriveBrowseNode
  depth?: number
  parentPath?: string
  selected: Set<string>
  onToggle: (file: SelectedFile) => void
  onImportFolder: (folderId: string, folderName: string) => void
}) {
  const [open, setOpen] = useState(depth < 1)
  const [children, setChildren] = useState<DriveBrowseNode[]>(node.children || [])
  const [loadingKids, setLoadingKids] = useState(false)
  const [loaded, setLoaded] = useState(Boolean(node.children && node.children.length > 0))
  const path = node.path || (parentPath ? `${parentPath}/${node.name}` : node.name)
  const isFile = !node.is_folder
  const canSelect = isFile && isSelectableFile(node)

  async function ensureChildren() {
    if (!node.is_folder || loaded || loadingKids) return
    setLoadingKids(true)
    try {
      const kids = await api.driveChildren(node.id, path)
      setChildren(
        kids.map((k) => ({
          ...k,
          path: k.path || `${path}/${k.name}`,
          is_folder: Boolean(k.is_folder),
          children: k.is_folder ? [] : undefined,
        })),
      )
      setLoaded(true)
    } catch {
      setChildren([])
      setLoaded(true)
    } finally {
      setLoadingKids(false)
    }
  }

  async function toggleOpen() {
    if (!node.is_folder) return
    const next = !open
    setOpen(next)
    if (next) await ensureChildren()
  }

  return (
    <div className={cn(depth > 0 && 'ml-3 border-l border-border pl-2')}>
      <div
        className={cn(
          'flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-sm transition hover:bg-secondary/70',
          canSelect && selected.has(node.id) && 'bg-primary/10',
        )}
      >
        {node.is_folder ? (
          <button
            type="button"
            onClick={() => void toggleOpen()}
            className="shrink-0 rounded p-0.5 hover:bg-secondary"
            aria-label="expand"
          >
            <ChevronRight
              className={cn('h-3.5 w-3.5 text-muted-foreground transition', open && 'rotate-90')}
            />
          </button>
        ) : (
          <span className="w-4" />
        )}

        {canSelect ? (
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-[var(--primary)]"
            checked={selected.has(node.id)}
            onChange={() =>
              onToggle({
                id: node.id,
                name: node.name,
                path,
                mime_type: node.mime_type || 'application/octet-stream',
              })
            }
          />
        ) : (
          <span className="w-3.5" />
        )}

        {node.is_folder ? (
          <Folder className="h-3.5 w-3.5 shrink-0 text-primary" />
        ) : (
          <File className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <button
          type="button"
          className="min-w-0 flex-1 truncate text-left font-medium"
          onClick={() => {
            if (node.is_folder) void toggleOpen()
            else if (canSelect) {
              onToggle({
                id: node.id,
                name: node.name,
                path,
                mime_type: node.mime_type || 'application/octet-stream',
              })
            }
          }}
        >
          {node.name}
          {loadingKids && <span className="ml-2 text-xs font-normal text-muted-foreground">…</span>}
        </button>
        {node.is_folder && depth >= 0 && (
          <button
            type="button"
            title="Importar todos los PDF/Excel de esta carpeta (recursivo)"
            onClick={() => onImportFolder(node.id, node.name)}
            className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground hover:border-primary hover:text-primary"
          >
            Importar
          </button>
        )}
      </div>
      {open &&
        children.map((child) => (
          <BrowseTree
            key={child.id}
            node={child}
            depth={depth + 1}
            parentPath={path}
            selected={selected}
            onToggle={onToggle}
            onImportFolder={onImportFolder}
          />
        ))}
    </div>
  )
}

export default function Documents() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null)
  const [linkedFolderId, setLinkedFolderId] = useState(DEFAULT_DRIVE_FOLDER_ID)
  const [linkedFolderName, setLinkedFolderName] = useState(DEFAULT_DRIVE_FOLDER_NAME)
  const [driveLinked, setDriveLinked] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [linking, setLinking] = useState(false)
  const [importing, setImporting] = useState(false)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)
  const [browseTree, setBrowseTree] = useState<DriveBrowseNode | null>(null)
  const [browsing, setBrowsing] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Map<string, SelectedFile>>(new Map())
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null)

  const groupedDocs = useMemo(() => {
    const map = new Map<string, Document[]>()
    for (const d of docs) {
      // Prefer classify folder_group: "Wells Fargo / 8398 / 2025"
      const group = String(d.folder_group || d.drive_path || 'Sin carpeta')
      if (!map.has(group)) map.set(group, [])
      map.get(group)!.push(d)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [docs])

  const load = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!opts?.quiet) setLoading(true)
    setError(null)
    try {
      const data = await api.listDocuments({
        workspace_id: workspaceId,
        tenant_id: workspaceId,
      })
      setDocs(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setDocs([])
    } finally {
      if (!opts?.quiet) setLoading(false)
    }
  }, [workspaceId, t])

  const loadDrive = useCallback(async () => {
    try {
      const status = await api.driveStatus()
      setDriveStatus(status)
      if (status.default_folder_id) setLinkedFolderId(String(status.default_folder_id))
      if (status.default_folder_name) setLinkedFolderName(String(status.default_folder_name))
    } catch {
      setDriveStatus({ configured: false })
    }
  }, [])

  useEffect(() => {
    void load()
    void loadDrive()
  }, [load, loadDrive])

  // Poll while docs are pending/processing (sequential queue)
  useEffect(() => {
    const busy = docs.some((d) => {
      const s = String(d.status || '')
      return s === 'pending' || s === 'processing' || s === 'uploading'
    })
    if (!busy) return
    const id = window.setInterval(() => {
      void load({ quiet: true })
    }, 4000)
    return () => window.clearInterval(id)
  }, [docs, load])

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files)
    if (!list.length) return
    setUploading(true)
    setError(null)
    try {
      for (const file of list) {
        const form = new FormData()
        form.append('file', file)
        form.append('workspace_id', workspaceId)
        form.append('tenant_id', workspaceId)
        await api.uploadDocument(form)
      }
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setUploading(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files?.length) void uploadFiles(e.dataTransfer.files)
  }

  function toggleFile(file: SelectedFile) {
    setSelected((prev) => {
      const next = new Map(prev)
      if (next.has(file.id)) next.delete(file.id)
      else next.set(file.id, file)
      return next
    })
  }

  async function handleLink() {
    setLinking(true)
    setSyncMessage(null)
    setError(null)
    try {
      const res = await api.driveLink({
        workspace_id: workspaceId,
        folder_id: linkedFolderId || DEFAULT_DRIVE_FOLDER_ID,
        folder_name: linkedFolderName || DEFAULT_DRIVE_FOLDER_NAME,
      })
      setDriveLinked(true)
      if (res.drive_folder_id) setLinkedFolderId(res.drive_folder_id)
      if (res.drive_folder_name) setLinkedFolderName(String(res.drive_folder_name))
      setSyncMessage(t('drive.linkedSuccess'))
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setLinking(false)
    }
  }

  async function handleSync() {
    setSyncing(true)
    setSyncMessage(null)
    setError(null)
    try {
      const res = await api.driveSync({
        workspace_id: workspaceId,
        folder_id: linkedFolderId || DEFAULT_DRIVE_FOLDER_ID,
        max_files: 40,
        ingest: true,
      })
      const imported = Number(res.imported ?? 0)
      const skipped = Number(res.skipped ?? 0)
      setSyncMessage(
        t('drive.imported')
          .replace('{imported}', String(imported))
          .replace('{skipped}', String(skipped)),
      )
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setSyncing(false)
    }
  }

  async function handleBrowse() {
    setBrowsing(true)
    setBrowseError(null)
    try {
      const tree = await api.driveBrowse(linkedFolderId || DEFAULT_DRIVE_FOLDER_ID)
      setBrowseTree(tree)
      if (tree.name) setLinkedFolderName(tree.name)
    } catch (e) {
      setBrowseTree(null)
      setBrowseError(e instanceof Error ? e.message : t('drive.browseFailed'))
    } finally {
      setBrowsing(false)
    }
  }

  async function handleImportSelected() {
    if (!selected.size) return
    setImporting(true)
    setSyncMessage(null)
    setError(null)
    try {
      const res = await api.driveImportFiles({
        workspace_id: workspaceId,
        files: [...selected.values()],
        ingest: true,
      })
      setSyncMessage(typeof res.message === 'string' ? res.message : t('drive.imported'))
      setSelected(new Map())
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setImporting(false)
    }
  }

  async function handleImportFolder(folderId: string, folderName: string) {
    setImporting(true)
    setSyncMessage(null)
    setError(null)
    try {
      const res = await api.driveImportFolder({
        workspace_id: workspaceId,
        folder_id: folderId,
        max_files: 40,
        ingest: true,
      })
      setSyncMessage(
        typeof res.message === 'string'
          ? `${folderName}: ${res.message}`
          : `Carpeta ${folderName} encolada`,
      )
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setImporting(false)
    }
  }

  const configured = Boolean(driveStatus?.configured)
  const selectedIds = new Set(selected.keys())

  return (
    <div>
      <div className="mb-8 animate-fade-up">
        <h1 className="page-title">{t('documents.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('documents.subtitle')}</p>
        <p className="mt-2 text-xs text-muted-foreground">{t('documents.queueHint')}</p>
      </div>

      <section className="animate-fade-up-delay-1 soft-shadow mb-6 rounded-xl border border-border bg-card p-5 sm:p-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-primary">
              <HardDrive className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">{t('drive.title')}</h2>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Entra a Wells Fargo → 8398 → 2026, marca PDFs/Excel o pulsa Importar en la carpeta.
              </p>
            </div>
          </div>
          <div
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
              configured ? 'bg-success text-success-foreground' : 'bg-warning text-warning-foreground',
            )}
          >
            {configured ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
            {configured ? t('drive.connected') : t('drive.notConfigured')}
          </div>
        </div>

        <div className="mb-4 rounded-lg border border-border/80 bg-secondary/40 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('drive.linkedFolder')}
          </p>
          <p className="mt-1 flex items-center gap-2 font-medium">
            <FolderOpen className="h-4 w-4 text-primary" />
            {linkedFolderName || DEFAULT_DRIVE_FOLDER_NAME}
            {(driveLinked || linkedFolderName) && (
              <span className="text-xs font-normal text-muted-foreground">({t('drive.linked')})</span>
            )}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleSync()}
            disabled={syncing || !configured}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          >
            <RefreshCw className={cn('h-4 w-4', syncing && 'animate-spin')} />
            {syncing ? t('drive.syncing') : t('drive.sync')}
          </button>
          <button
            type="button"
            onClick={() => void handleLink()}
            disabled={linking}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <Link2 className="h-4 w-4" />
            {linking ? t('drive.linking') : t('drive.link')}
          </button>
          <button
            type="button"
            onClick={() => void handleBrowse()}
            disabled={browsing || !configured}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <FolderOpen className="h-4 w-4" />
            {browsing ? t('drive.browsing') : t('drive.browse')}
          </button>
        </div>

        {syncMessage && <p className="mt-3 text-sm text-emerald-700">{syncMessage}</p>}
        {browseError && <p className="mt-3 text-sm text-muted-foreground">{browseError}</p>}

        {browseTree && (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-muted-foreground">
              Haz clic en la flecha para entrar a subcarpetas (8398 → 2026). Estados de cuenta van a
              Conciliación; facturas a Transacciones.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void handleImportSelected()}
                disabled={!selected.size || importing}
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
              >
                <Download className="h-4 w-4" />
                {importing ? t('drive.importing') : `${t('drive.importSelected')} (${selected.size})`}
              </button>
              {selected.size > 0 && (
                <button
                  type="button"
                  onClick={() => setSelected(new Map())}
                  className="rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground"
                >
                  {t('drive.clearSelection')}
                </button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto rounded-lg border border-border bg-background p-3">
              <BrowseTree
                node={browseTree}
                selected={selectedIds}
                onToggle={toggleFile}
                onImportFolder={(id, name) => void handleImportFolder(id, name)}
              />
            </div>
          </div>
        )}
      </section>

      <label
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          'animate-fade-up-delay-2 soft-shadow mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-card px-6 py-12 transition hover:border-primary/40',
          dragOver && 'border-primary bg-primary/5',
        )}
      >
        <Upload className="mb-3 h-8 w-8 text-primary" />
        <p className="text-sm font-medium">
          {uploading ? t('documents.uploading') : t('documents.drop')}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">Solo archivos locales</p>
        <input
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.csv,.xlsx,.xls,.png,.jpg,.jpeg,.webp,.tif,.tiff,.mp3,.wav,.m4a,.ogg,.webm"
          onChange={(e) => e.target.files && void uploadFiles(e.target.files)}
        />
      </label>

      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {!loading && docs.length === 0 && (
        <p className="text-muted-foreground">{t('documents.empty')}</p>
      )}

      {docs.length > 0 && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Agrupados por banco / cuenta / año (como en Drive: Wells → 8398 → 2025,
            Truist Checking 4461 → 2026, etc.). Abre cada archivo para ver APIs y texto
            extraído.
          </p>
          {groupedDocs.map(([folder, items]) => (
            <section
              key={folder}
              className="soft-shadow overflow-hidden rounded-xl border border-border bg-card"
            >
              <header className="flex items-center gap-2 border-b border-border bg-secondary/40 px-4 py-3">
                <FolderOpen className="h-4 w-4 text-primary" />
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-sm font-semibold">{folder}</h3>
                  <p className="text-xs text-muted-foreground">{items.length} archivo(s)</p>
                </div>
              </header>
              <ul className="divide-y divide-border">
                {items.map((doc) => {
                  const open = expandedDoc === doc.id
                  const kind = String(doc.pipeline_kind || 'pending')
                  const status = String(doc.status ?? '—')
                  const statusLabel =
                    status === 'pending'
                      ? t('documents.statusPending')
                      : status === 'processing'
                        ? t('documents.statusProcessing')
                        : status
                  const kindLabel =
                    kind === 'statement'
                      ? 'Estado de cuenta'
                      : kind === 'invoice'
                        ? 'Factura / recibo'
                        : kind === 'spreadsheet'
                          ? 'Excel / CSV'
                          : kind
                  return (
                    <li key={doc.id}>
                      <button
                        type="button"
                        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-secondary/40"
                        onClick={() => setExpandedDoc(open ? null : doc.id)}
                      >
                        <File className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">
                              {doc.filename || doc.name || doc.id}
                            </span>
                            <span
                              className={cn(
                                'rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide',
                                status === 'pending' || status === 'processing'
                                  ? 'bg-warning text-warning-foreground'
                                  : status === 'failed'
                                    ? 'bg-destructive/15 text-destructive'
                                    : 'bg-secondary',
                              )}
                            >
                              {statusLabel}
                            </span>
                            <span className="rounded-full bg-warning px-2 py-0.5 text-[10px] text-warning-foreground">
                              {kindLabel}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs font-medium text-foreground/80">
                            {doc.vendor ? `Detectado: ${String(doc.vendor)} · ` : ''}
                            {doc.apis_used
                              ? `APIs: ${String(doc.apis_used)}`
                              : 'APIs: en cola / pendientes'}
                          </p>
                        </div>
                        <ChevronRight
                          className={cn(
                            'mt-1 h-4 w-4 shrink-0 text-muted-foreground transition',
                            open && 'rotate-90',
                          )}
                        />
                      </button>
                      {open && (
                        <div className="space-y-2 border-t border-border bg-background/80 px-4 py-3 text-sm">
                          <p>
                            <span className="text-muted-foreground">Ruta Drive: </span>
                            {String(doc.drive_path || '—')}
                          </p>
                          <p>
                            <span className="text-muted-foreground">Fecha doc: </span>
                            {String(doc.document_date || '—')}
                            {' · '}
                            <span className="text-muted-foreground">Confianza: </span>
                            {doc.extraction_confidence != null
                              ? `${Math.round(Number(doc.extraction_confidence) * 100)}%`
                              : '—'}
                          </p>
                          {doc.error_message != null && (
                            <p className="text-destructive">{String(doc.error_message)}</p>
                          )}
                          <div className="grid gap-3 lg:grid-cols-2">
                            <div>
                              <p className="mb-1 text-xs font-medium text-muted-foreground">
                                Texto extraído / OCR
                              </p>
                              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-card p-3 text-xs leading-relaxed text-muted-foreground">
                                {String(
                                  doc.extract_preview ||
                                    doc.raw_extracted_text ||
                                    'Aún no hay texto extraído (si está en processing, espera 1–3 min y recarga).',
                                )}
                              </pre>
                            </div>
                            <div>
                              <p className="mb-1 text-xs font-medium text-muted-foreground">
                                Vista documento
                              </p>
                              <DocumentFilePreview doc={doc} workspaceId={workspaceId} />
                            </div>
                          </div>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
