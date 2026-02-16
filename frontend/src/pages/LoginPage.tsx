import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Network, LogIn, Shield } from 'lucide-react'
import { apiClient } from '../api/client'
import { useAppStore } from '../store/useAppStore'
import { motion } from 'framer-motion'
import { Button, Input, Select, Label, useToast } from '../components/ui'

/* ── Animated topology background ────────────────────── */

function TopologyBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationId: number
    let width = 0
    let height = 0

    type Node = { x: number; y: number; vx: number; vy: number; r: number }
    const nodes: Node[] = []
    const NODE_COUNT = 30

    function resize() {
      width = canvas!.parentElement?.clientWidth ?? window.innerWidth * 0.6
      height = window.innerHeight
      canvas!.width = width
      canvas!.height = height
    }

    function init() {
      resize()
      nodes.length = 0
      for (let i = 0; i < NODE_COUNT; i++) {
        nodes.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.4,
          vy: (Math.random() - 0.5) * 0.4,
          r: Math.random() * 2 + 1.5,
        })
      }
    }

    function draw() {
      ctx!.clearRect(0, 0, width, height)

      // Edges
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 180) {
            ctx!.strokeStyle = `rgba(99, 102, 241, ${0.12 * (1 - dist / 180)})`
            ctx!.lineWidth = 0.8
            ctx!.beginPath()
            ctx!.moveTo(nodes[i].x, nodes[i].y)
            ctx!.lineTo(nodes[j].x, nodes[j].y)
            ctx!.stroke()
          }
        }
      }

      // Nodes
      for (const n of nodes) {
        ctx!.fillStyle = 'rgba(99, 102, 241, 0.25)'
        ctx!.beginPath()
        ctx!.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx!.fill()

        // Glow
        ctx!.fillStyle = 'rgba(99, 102, 241, 0.06)'
        ctx!.beginPath()
        ctx!.arc(n.x, n.y, n.r * 4, 0, Math.PI * 2)
        ctx!.fill()

        n.x += n.vx
        n.y += n.vy
        if (n.x < 0 || n.x > width) n.vx *= -1
        if (n.y < 0 || n.y > height) n.vy *= -1
      }

      animationId = requestAnimationFrame(draw)
    }

    init()
    draw()
    window.addEventListener('resize', () => { resize(); })

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
}

/* ── Main Login Page ─────────────────────────────────── */

export default function LoginPage() {
  const navigate = useNavigate()
  const login = useAppStore((s) => s.login)
  const { toast } = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [role, setRole] = useState('viewer')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        await apiClient.post('/auth/register', { email, password, role })
      }
      const { data } = await apiClient.post('/auth/login', { email, password })
      const token: string = data.access_token

      // fetch user info
      const me = await apiClient.get('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })

      login(token, { id: me.data.id, email: me.data.email, role: me.data.role })
      navigate('/')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Authentication failed'
      setError(String(msg))
    } finally {
      setLoading(false)
    }
  }

  const handleSSO = () => {
    toast('info', 'SSO integration is not configured yet. Contact your administrator.')
  }

  return (
    <div className="flex min-h-screen">
      {/* Left panel: animated topology (60%) */}
      <div className="relative hidden lg:flex lg:w-[60%] items-center justify-center bg-slate-900 overflow-hidden">
        <TopologyBackground />
        {/* Overlay text */}
        <div className="relative z-10 text-center px-12">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
          >
            <div className="flex items-center justify-center gap-3 mb-6">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 shadow-lg shadow-brand-600/30">
                <Network className="h-7 w-7 text-white" />
              </div>
            </div>
            <h1 className="text-4xl font-bold text-white mb-3">Deplyx</h1>
            <p className="text-lg text-slate-400 max-w-md mx-auto">
              Change Intelligence Engine for network infrastructure. Plan, validate, and deploy with confidence.
            </p>
          </motion.div>

          {/* Stats */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.6 }}
            className="mt-10 flex justify-center gap-8 text-center"
          >
            {[
              { label: 'Devices Managed', value: '2,400+' },
              { label: 'Changes/Month', value: '340' },
              { label: 'Uptime', value: '99.98%' },
            ].map((s) => (
              <div key={s.label}>
                <p className="text-2xl font-bold text-white">{s.value}</p>
                <p className="text-xs text-slate-500">{s.label}</p>
              </div>
            ))}
          </motion.div>
        </div>
      </div>

      {/* Right panel: login form (40%) */}
      <div className="flex flex-1 items-center justify-center bg-slate-50 dark:bg-slate-950 px-6">
        {/* Subtle grid background */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03] dark:opacity-[0.04] lg:hidden"
          style={{
            backgroundImage: 'radial-gradient(circle, currentColor 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />

        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.4 }}
          className="relative w-full max-w-sm"
        >
          {/* Glass-morphism card */}
          <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/50 bg-white/80 dark:bg-slate-900/70 backdrop-blur-xl p-8 shadow-xl dark:shadow-2xl">
            {/* Mobile logo */}
            <div className="mb-6 flex flex-col items-center gap-2 lg:hidden">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/25">
                <Network className="h-6 w-6" />
              </div>
              <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Deplyx</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">Change Intelligence Engine</p>
            </div>

            {/* Desktop header */}
            <div className="hidden lg:block mb-6">
              <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100">
                {mode === 'login' ? 'Welcome back' : 'Create account'}
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                {mode === 'login' ? 'Sign in to your account' : 'Get started with Deplyx'}
              </p>
            </div>

            {/* Mode toggle */}
            <div className="mb-4 flex rounded-btn border border-slate-200 dark:border-slate-700 overflow-hidden">
              <button
                onClick={() => setMode('login')}
                className={`flex-1 py-2 text-sm font-medium transition ${
                  mode === 'login'
                    ? 'bg-brand-600 text-white'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
              >
                Login
              </button>
              <button
                onClick={() => setMode('register')}
                className={`flex-1 py-2 text-sm font-medium transition ${
                  mode === 'register'
                    ? 'bg-brand-600 text-white'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
              >
                Register
              </button>
            </div>

            {error && (
              <div className="mb-4 rounded-btn bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-600 dark:text-red-400">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="login-email">Email</Label>
                <Input
                  id="login-email"
                  type="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition-shadow"
                />
              </div>
              <div>
                <Label htmlFor="login-pass">Password</Label>
                <Input
                  id="login-pass"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition-shadow"
                />
              </div>

              {mode === 'register' && (
                <div>
                  <Label htmlFor="login-role">Role</Label>
                  <Select id="login-role" value={role} onChange={(e) => setRole(e.target.value)}>
                    <option value="viewer">Viewer</option>
                    <option value="network">Network Engineer</option>
                    <option value="security">Security Engineer</option>
                    <option value="approver">Approver</option>
                    <option value="admin">Admin</option>
                  </Select>
                </div>
              )}

              <Button type="submit" disabled={loading} className="w-full justify-center">
                <LogIn className="h-4 w-4" />
                {loading ? 'Loading...' : mode === 'login' ? 'Sign In' : 'Create Account'}
              </Button>
            </form>

            {/* Divider */}
            <div className="my-5 flex items-center gap-3">
              <div className="flex-1 border-t border-slate-200 dark:border-slate-700" />
              <span className="text-xs text-slate-400 dark:text-slate-500">or</span>
              <div className="flex-1 border-t border-slate-200 dark:border-slate-700" />
            </div>

            {/* Mock SSO */}
            <Button variant="secondary" className="w-full justify-center" onClick={handleSSO}>
              <Shield className="h-4 w-4" />
              Sign in with SSO
            </Button>
          </div>

          {/* Footer */}
          <p className="mt-4 text-center text-xs text-slate-400 dark:text-slate-500">
            By signing in you agree to the Terms of Service and Privacy Policy.
          </p>
        </motion.div>
      </div>
    </div>
  )
}
