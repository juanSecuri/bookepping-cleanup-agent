# Auth (IN PROGRESS — 2026-08-27)

Empresa compró Render Starter y pidió Auth ahora. Scaffold: Supabase JWT + `workspace_members` + login/signup mínimo.

## Estado

| Pieza | Estado |
|-------|--------|
| `AUTH_ENABLED` + JWT verify (secret o JWKS) | Listo |
| Tabla `workspace_members` | **Aplicada** en Supabase `bookkeeping-agent` |
| Bootstrap primer owner (`AUTH_BOOTSTRAP_FIRST_OWNER`) | Listo |
| Checks en mutations (txs / movements / drive / file) | Listo |
| Frontend login + signup (`/app/*` gate si hay `VITE_*`) | Listo |
| Invite UX / RLS completa | Pendiente |

## Cómo activar Auth en producción (cuando estés en el PC)

1. Dashboard Supabase → Authentication → Providers → Email ON (y decide si confirmation email).
2. Crea cuenta en `/login` (Sign up) o Users → Add user.
3. Render → Environment:
   - `VITE_SUPABASE_URL` = `https://jhzhxxkvyicwkzrqrevm.supabase.co` (ya seteado)
   - `VITE_SUPABASE_ANON_KEY` = anon key (ya seteado)
   - `SUPABASE_JWT_SECRET` = Project Settings → API → JWT Secret
   - Luego `AUTH_ENABLED` = `true`
4. Redeploy (Docker build embebe `VITE_*`).
5. Primer login en workspace vacío de members → te hace **owner** automáticamente.

Hasta que `AUTH_ENABLED=true` + JWT secret + redeploy, la API sigue en bypass (demo abierta). **No dejes bypass en público** una vez Auth esté validado.

## Render Starter (disco)

| Item | Acción |
|------|--------|
| Plan | Ya `starter` |
| `LEDGERAI_UPLOAD_DIR` | `/var/data/ledgerai_uploads` (env seteado) |
| Disco | Dashboard → Disks → mount `/var/data` 1 GB (si no aparece, attach manual) |
| Health | `/health` |
| Worker aparte | **No** — el disco no se comparte entre servicios; la cola vive en el web process |

## Bug 2024 vacío (fix)

PostgREST devolvía ~1000 filas newest-first → 2024 nunca entraba al P&L. Ahora hay paginación + `list_by_tenant_date_range`.
