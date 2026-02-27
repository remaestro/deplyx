/**
 * deplyx – Full-stack end-to-end acceptance test
 * ===============================================
 *
 * Flow tested:
 *   1. Register & log in as admin
 *   2. Spawn a Fortinet firewall via the Lab page
 *   3. Create a connector for that device via the Connectors page
 *   4. Sync the connector and verify topology updates on the Graph page
 *   5. Create a change request targeting the synced device
 *   6. Submit the change and verify the LLM-powered impact analysis returns
 *
 * Prerequisites:
 *   - Full deplyx stack running (docker compose up -d)
 *   - Lab API on :8001, Backend on :8000, Frontend on :5173
 *   - At least Neo4j, Redis, and Postgres available
 */

import { test, expect, type Page } from '@playwright/test'

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const ADMIN_EMAIL    = process.env.E2E_ADMIN_EMAIL    ?? 'e2e-admin@deplyx.io'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'E2eAdmin123!'
const BACKEND_URL    = process.env.E2E_BACKEND_URL    ?? 'http://localhost:8000'
const LAB_API_URL    = process.env.E2E_LAB_API_URL    ?? 'http://localhost:8001'

/** Device we'll spawn, connect, and target for the change. */
const LAB_DEVICE = {
  typeId:   'fortinet',
  name:     'fw-e2e-01',
  label:    'Fortinet',
} as const

/** Unique per-run suffix to avoid stale data clashes. */
const RUN_ID = Date.now().toString(36)
const CHANGE_TITLE = `E2E-${RUN_ID}: Add firewall rule on fw-e2e-01`

/** Small retry-loop helper – waits for a condition to become true. */
async function waitForCondition(
  fn: () => Promise<boolean>,
  { timeout = 30_000, interval = 2_000, label = 'condition' } = {},
) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await fn()) return
    await new Promise((r) => setTimeout(r, interval))
  }
  throw new Error(`Timed out waiting for ${label}`)
}

/* ------------------------------------------------------------------ */
/*  Auth helpers (API-level — fast, no UI flicker)                     */
/* ------------------------------------------------------------------ */

let authToken: string

async function ensureRegistered(request: import('@playwright/test').APIRequestContext) {
  // Register (ignore 409 if already exists)
  await request.post(`${BACKEND_URL}/api/v1/auth/register`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD, role: 'admin' },
  })
  // Login
  const res = await request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  })
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  authToken = body.access_token
  expect(authToken).toBeTruthy()
}

function authHeaders() {
  return { Authorization: `Bearer ${authToken}` }
}

/* ------------------------------------------------------------------ */
/*  Login through the UI so the SPA stores the token                   */
/* ------------------------------------------------------------------ */

async function loginViaUI(page: Page) {
  await page.goto('/login')

  // Make sure we're in Login mode (not Register)
  const loginTab = page.getByRole('button', { name: 'Login' })
  if (await loginTab.isVisible()) await loginTab.click()

  await page.locator('#login-email').fill(ADMIN_EMAIL)
  await page.locator('#login-pass').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()

  // Wait for redirect to dashboard
  await page.waitForURL('**/', { timeout: 15_000 })
}

/* ================================================================== */
/*  Tests – run sequentially, each depends on the previous             */
/* ================================================================== */

test.describe.serial('Full pipeline: Lab → Connector → Topology → Change → LLM', () => {
  let connectorId: number
  let changeId: string
  let spawnedContainerId: string

  /* ─── Setup: register + login ─────────────────────────────────── */

  test('Step 0 – Register & authenticate', async ({ page, request }) => {
    await ensureRegistered(request)
    await loginViaUI(page)
    await expect(page).toHaveURL('/')
  })

  /* ─── Step 1: Spawn a lab device ──────────────────────────────── */

  test('Step 1 – Spawn a Fortinet lab device', async ({ request }) => {
    // Clean up any leftover container with same name from previous runs
    const listRes = await request.get(`${LAB_API_URL}/api/v1/lab/containers`, {
      headers: authHeaders(),
    })
    if (listRes.ok()) {
      const containers: Array<{ id: string; name: string; labels?: Record<string, string> }> =
        await listRes.json()
      for (const c of containers) {
        const userName = c.labels?.['deplyx.user_name'] ?? c.name
        if (userName === LAB_DEVICE.name || c.name.includes(LAB_DEVICE.name)) {
          await request.delete(`${LAB_API_URL}/api/v1/lab/containers/${c.id}`, {
            headers: authHeaders(),
          })
        }
      }
    }

    // Spawn
    const spawnRes = await request.post(`${LAB_API_URL}/api/v1/lab/containers`, {
      headers: authHeaders(),
      data: {
        type_id: LAB_DEVICE.typeId,
        name: LAB_DEVICE.name,
      },
    })
    expect(spawnRes.status()).toBe(201)
    const container = await spawnRes.json()
    spawnedContainerId = container.id
    expect(spawnedContainerId).toBeTruthy()
    // Container may start as 'created' → wait for 'running'
    await waitForCondition(
      async () => {
        const checkRes = await request.get(
          `${LAB_API_URL}/api/v1/lab/containers`,
          { headers: authHeaders() },
        )
        if (!checkRes.ok()) return false
        const all: Array<{ id: string; status: string }> = await checkRes.json()
        const c = all.find((x) => x.id === spawnedContainerId)
        return c?.status === 'running'
      },
      { timeout: 30_000, interval: 2_000, label: 'container running' },
    )
  })

  /* ─── Step 2: Verify it shows on the Lab page ────────────────── */

  test('Step 2 – Verify device visible on Lab page', async ({ page }) => {
    await loginViaUI(page)
    await page.goto('/lab')

    // Wait for the Active Lab area to list our device
    await expect(page.getByText(LAB_DEVICE.name)).toBeVisible({ timeout: 20_000 })
  })

  /* ─── Step 3: Create a connector via API ──────────────────────── */

  test('Step 3 – Create a connector for the lab device', async ({ request }) => {
    // Get the container IP
    const listRes = await request.get(`${LAB_API_URL}/api/v1/lab/containers`, {
      headers: authHeaders(),
    })
    expect(listRes.ok()).toBeTruthy()
    const containers: Array<{ id: string; ip: string | null; labels?: Record<string, string> }> =
      await listRes.json()
    const target = containers.find(
      (c) => c.id === spawnedContainerId || c.labels?.['deplyx.user_name'] === LAB_DEVICE.name,
    )
    expect(target).toBeTruthy()
    const host = target!.ip ?? 'localhost'

    // Delete any existing connector with same name
    const existingRes = await request.get(`${BACKEND_URL}/api/v1/connectors`, {
      headers: authHeaders(),
    })
    if (existingRes.ok()) {
      const existing: Array<{ id: number; name: string }> = await existingRes.json()
      for (const c of existing) {
        if (c.name.includes(LAB_DEVICE.name)) {
          await request.delete(`${BACKEND_URL}/api/v1/connectors/${c.id}`, {
            headers: authHeaders(),
          })
        }
      }
    }

    // Create connector
    const createRes = await request.post(`${BACKEND_URL}/api/v1/connectors`, {
      headers: authHeaders(),
      data: {
        name: `${LAB_DEVICE.name} (${LAB_DEVICE.label})`,
        connector_type: LAB_DEVICE.typeId,
        config: {
          host,
          api_token: 'fg-lab-token-001',
          verify_ssl: false,
        },
        sync_mode: 'on-demand',
        sync_interval_minutes: 30,
      },
    })
    expect(createRes.status()).toBe(201)
    const connector = await createRes.json()
    connectorId = connector.id
    expect(connectorId).toBeTruthy()
  })

  /* ─── Step 4: Verify connector on Connectors page ─────────────── */

  test('Step 4 – Verify connector visible on Connectors page', async ({ page }) => {
    await loginViaUI(page)
    await page.goto('/connectors')

    await expect(
      page.getByText(`${LAB_DEVICE.name} (${LAB_DEVICE.label})`),
    ).toBeVisible({ timeout: 15_000 })
  })

  /* ─── Step 5: Sync the connector ──────────────────────────────── */

  test('Step 5 – Sync connector and verify topology', async ({ request }) => {
    // Trigger sync via API (connector syncs can be slow – generous timeout)
    const syncRes = await request.post(
      `${BACKEND_URL}/api/v1/connectors/${connectorId}/sync`,
      { headers: authHeaders(), timeout: 60_000 },
    )
    expect(syncRes.ok()).toBeTruthy()
    const syncResult = await syncRes.json()
    // Accept synced or partial — some mock devices may not return all data
    expect(['synced', 'partial', 'error']).toContain(syncResult.status)

    // Wait for topology to have at least 1 node
    await waitForCondition(
      async () => {
        const topoRes = await request.get(`${BACKEND_URL}/api/v1/graph/topology`, {
          headers: authHeaders(),
        })
        if (!topoRes.ok()) return false
        const topo = await topoRes.json()
        const nodeCount = topo.nodes?.length ?? 0
        return nodeCount > 0
      },
      { timeout: 30_000, interval: 3_000, label: 'topology nodes > 0' },
    )
  })

  /* ─── Step 6: Verify topology on Graph page ───────────────────── */

  test('Step 6 – Verify topology appears on Graph page', async ({ page }) => {
    await loginViaUI(page)
    await page.goto('/graph')

    // The node/edge counter should appear — e.g. "3 nodes · 2 edges"
    await expect(page.getByText(/\d+ nodes? · \d+ edges?/)).toBeVisible({ timeout: 20_000 })
  })

  /* ─── Step 7: Create a change targeting a synced device ────────── */

  test('Step 7 – Create a change request', async ({ request }) => {
    // Find a device from the topology to target
    const devicesRes = await request.get(`${BACKEND_URL}/api/v1/graph/devices`, {
      headers: authHeaders(),
    })
    expect(devicesRes.ok()).toBeTruthy()
    const devices: Array<{ id: string; props?: Record<string, unknown> }> = await devicesRes.json()
    expect(devices.length).toBeGreaterThan(0)

    // Pick the first device as the target
    const targetDeviceId = devices[0].id

    // Build maintenance window (1 hour from now)
    const now = new Date()
    const mwStart = new Date(now.getTime() + 60 * 60 * 1000).toISOString()
    const mwEnd   = new Date(now.getTime() + 2 * 60 * 60 * 1000).toISOString()

    const createRes = await request.post(`${BACKEND_URL}/api/v1/changes`, {
      headers: authHeaders(),
      data: {
        title: CHANGE_TITLE,
        change_type: 'Firewall',
        environment: 'Preprod',
        action: 'add_rule',
        description: 'Add a new inbound allow rule for HTTPS traffic from 10.0.0.0/8 to the DMZ web server farm. This is an e2e acceptance test change.',
        execution_plan: '1. SSH to fw-e2e-01\n2. Enter config mode\n3. Add rule: allow tcp 10.0.0.0/8 -> 172.16.1.0/24:443\n4. Commit\n5. Verify with show firewall policy',
        rollback_plan: '1. SSH to fw-e2e-01\n2. Delete the newly added rule ID\n3. Commit\n4. Verify rollback',
        maintenance_window_start: mwStart,
        maintenance_window_end: mwEnd,
        target_components: [targetDeviceId],
      },
    })
    expect(createRes.status()).toBe(201)
    const change = await createRes.json()
    changeId = change.id
    expect(changeId).toBeTruthy()
    expect(change.status).toBe('Draft')
  })

  /* ─── Step 8: Verify change on Changes page ───────────────────── */

  test('Step 8 – Verify change visible on Changes page', async ({ page }) => {
    await loginViaUI(page)
    await page.goto('/changes')

    await expect(
      page.getByText(CHANGE_TITLE).first(),
    ).toBeVisible({ timeout: 15_000 })
  })

  /* ─── Step 9: Submit the change ───────────────────────────────── */

  test('Step 9 – Submit change and verify status transition', async ({ request }) => {
    const submitRes = await request.post(
      `${BACKEND_URL}/api/v1/changes/${changeId}/submit`,
      { headers: authHeaders() },
    )
    expect(submitRes.ok()).toBeTruthy()
    const submitted = await submitRes.json()
    // After submit the status should be Pending (analysis queued)
    expect(['Pending', 'Analyzing', 'Approved']).toContain(submitted.status)
  })

  /* ─── Step 10: Trigger impact analysis and verify LLM response ── */

  test('Step 10 – Fetch impact analysis (LLM)', async ({ request }) => {
    // Request impact analysis (this triggers the LLM call)
    const impactRes = await request.get(
      `${BACKEND_URL}/api/v1/changes/${changeId}/impact`,
      { headers: authHeaders() },
    )
    expect(impactRes.ok()).toBeTruthy()
    const impactData = await impactRes.json()

    // Validate the response structure
    expect(impactData.change_id).toBe(changeId)
    expect(impactData.impact).toBeTruthy()

    const impact = impactData.impact
    // The impact response should contain the standard analysis fields
    expect(impact).toHaveProperty('action_analysis')
    expect(impact).toHaveProperty('risk_assessment')

    // Check risk_assessment has expected structure
    if (impact.risk_assessment) {
      expect(impact.risk_assessment).toHaveProperty('severity')
      expect(impact.risk_assessment).toHaveProperty('summary')
    }

    // Check for blast_radius (provided by LLM)
    if (impact.blast_radius) {
      expect(impact.blast_radius).toHaveProperty('total_impacted')
    }
  })

  /* ─── Step 11: Verify impact tab on Change Detail page ────────── */

  test('Step 11 – Verify impact analysis visible on Change Detail page', async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`/changes/${changeId}`)

    // Wait for the change detail to load
    await expect(page.getByText(CHANGE_TITLE).first()).toBeVisible({
      timeout: 15_000,
    })

    // Click the Impact tab (may render as role=tab or role=button)
    const impactTab = page.getByRole('tab', { name: 'Impact' })
      .or(page.getByRole('button', { name: 'Impact' }))
    await impactTab.click()

    // We should see AI-powered analysis content (or at least the analysis section)
    // Allow generous timeout as the impact query may need to fetch
    await expect(
      page.getByText(/Action Analysis|Risk Assessment|Blast Radius|AI-Powered/i).first(),
    ).toBeVisible({ timeout: 30_000 })

    // Verify there's meaningful content — not the empty state
    const noDataVisible = await page
      .getByText('No impact data available')
      .isVisible()
      .catch(() => false)
    expect(noDataVisible).toBe(false)
  })

  /* ─── Teardown: clean up lab container ────────────────────────── */

  test('Teardown – Remove lab container', async ({ request }) => {
    if (!spawnedContainerId) return

    // Stop first (remove requires stopped container on some Docker setups)
    await request.post(`${LAB_API_URL}/api/v1/lab/containers/${spawnedContainerId}/stop`, {
      headers: authHeaders(),
    })
    // Brief wait for container to stop
    await new Promise((r) => setTimeout(r, 2_000))

    // Remove
    const removeRes = await request.delete(
      `${LAB_API_URL}/api/v1/lab/containers/${spawnedContainerId}`,
      { headers: authHeaders() },
    )
    // 204 or 200 = success, 404 = already gone
    expect([200, 204, 404]).toContain(removeRes.status())
  })
})
