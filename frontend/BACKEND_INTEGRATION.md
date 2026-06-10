# Backend integration

The frontend is wired to a typed HTTP client in `src/lib/api.ts`. All UI data is
fetched through TanStack Query (`src/lib/queries.ts`). No mock data remains in
the codebase.

## Configuration

Set the backend base URL in `.env.local`:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

If unset, the client defaults to `/api/v1` (same-origin).

## Auth

`src/lib/api.ts` attaches an `Authorization: Bearer <token>` header when a
token is present in `localStorage["deplyx_token"]`. Wire your login flow to
write that key (and clear it on logout). Swap the implementation for cookies
or a different auth layer as needed.

## Expected endpoints

The backend must implement these routes (see `src/lib/api.ts` for shapes):

### Dashboard
- `GET  /dashboard/kpis` → `Kpis`

### Changes
- `GET    /changes` → `Change[]`
- `GET    /changes/{id}` → `Change`
- `POST   /changes` → `Change`
- `PATCH  /changes/{id}` → `Change`
- `POST   /changes/{id}/approve` → `Change`
- `POST   /changes/{id}/reject`  body `{ reason }` → `Change`
- `POST   /changes/{id}/execute` → `Change`
- `POST   /changes/{id}/rollback` → `Change`
- `POST   /changes/{id}/reanalyze` → `Change`

### Connectors
- `GET    /connectors` → `Connector[]`
- `POST   /connectors` → `Connector`
- `POST   /connectors/{id}/sync` → `Connector`
- `DELETE /connectors/{id}` → 204

### Policies
- `GET    /policies` → `Policy[]`
- `PATCH  /policies/{id}` body `{ enabled }` → `Policy`
- `DELETE /policies/{id}` → 204

### Audit
- `GET /audit?range=&action=` → `AuditEntry[]`

### Graph
- `GET /graph/topology` → `{ nodes: GraphNode[], edges: GraphEdge[] }`

All DTO shapes are defined in `src/lib/types.ts`. Keep frontend types in sync
with backend pydantic models.

## Loading & error states

Every route shows a "Loading…" placeholder while queries are pending and a
"Failed to load" message on error. Empty arrays render an empty-state message
inviting the user to create their first resource.
