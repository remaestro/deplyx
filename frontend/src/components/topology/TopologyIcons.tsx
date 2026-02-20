/**
 * Network topology SVG icons — Cisco-inspired, designed for ReactFlow nodes.
 * Each icon is a pure SVG component accepting size, color, and className props.
 */

interface IconProps {
  size?: number
  color?: string
  className?: string
}

const defaults = { size: 32, color: 'currentColor' }

/* ── Router ────────────────────────────────────────────────────────── */
export function RouterIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Circle body */}
      <circle cx="32" cy="32" r="26" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Cross-hair arrows */}
      <line x1="32" y1="10" x2="32" y2="54" stroke={color} strokeWidth="2" />
      <line x1="10" y1="32" x2="54" y2="32" stroke={color} strokeWidth="2" />
      {/* Arrow tips */}
      <polyline points="28,14 32,6 36,14" stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
      <polyline points="28,50 32,58 36,50" stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
      <polyline points="14,28 6,32 14,36" stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
      <polyline points="50,28 58,32 50,36" stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
    </svg>
  )
}

/* ── Switch ─────────────────────────────────────────────────────────── */
export function SwitchIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Rectangular body */}
      <rect x="6" y="18" width="52" height="28" rx="4" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Arrow pairs — bidirectional data flow */}
      <polyline points="16,26 24,32 16,38" stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
      <polyline points="48,26 40,32 48,38" stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
      {/* Port indicators */}
      <rect x="18" y="42" width="4" height="4" rx="0.5" fill={color} opacity="0.4" />
      <rect x="26" y="42" width="4" height="4" rx="0.5" fill={color} opacity="0.4" />
      <rect x="34" y="42" width="4" height="4" rx="0.5" fill={color} opacity="0.4" />
      <rect x="42" y="42" width="4" height="4" rx="0.5" fill={color} opacity="0.4" />
    </svg>
  )
}

/* ── Firewall ──────────────────────────────────────────────────────── */
export function FirewallIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Shield shape */}
      <path
        d="M32 6 L54 18 L54 36 C54 48 44 56 32 60 C20 56 10 48 10 36 L10 18 Z"
        stroke={color}
        strokeWidth="2.5"
        fill="none"
        strokeLinejoin="round"
      />
      {/* Brick pattern — wall */}
      <line x1="18" y1="26" x2="46" y2="26" stroke={color} strokeWidth="1.5" opacity="0.5" />
      <line x1="16" y1="34" x2="48" y2="34" stroke={color} strokeWidth="1.5" opacity="0.5" />
      <line x1="18" y1="42" x2="46" y2="42" stroke={color} strokeWidth="1.5" opacity="0.5" />
      {/* Vertical bricks */}
      <line x1="28" y1="18" x2="28" y2="26" stroke={color} strokeWidth="1" opacity="0.4" />
      <line x1="38" y1="18" x2="38" y2="26" stroke={color} strokeWidth="1" opacity="0.4" />
      <line x1="22" y1="26" x2="22" y2="34" stroke={color} strokeWidth="1" opacity="0.4" />
      <line x1="32" y1="26" x2="32" y2="34" stroke={color} strokeWidth="1" opacity="0.4" />
      <line x1="42" y1="26" x2="42" y2="34" stroke={color} strokeWidth="1" opacity="0.4" />
      <line x1="28" y1="34" x2="28" y2="42" stroke={color} strokeWidth="1" opacity="0.4" />
      <line x1="38" y1="34" x2="38" y2="42" stroke={color} strokeWidth="1" opacity="0.4" />
    </svg>
  )
}

/* ── Load Balancer ─────────────────────────────────────────────────── */
export function LoadBalancerIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Balance scale */}
      <circle cx="32" cy="12" r="4" stroke={color} strokeWidth="2" fill="none" />
      {/* Pillar */}
      <line x1="32" y1="16" x2="32" y2="50" stroke={color} strokeWidth="2.5" />
      {/* Base */}
      <line x1="20" y1="50" x2="44" y2="50" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
      {/* Arms */}
      <line x1="14" y1="24" x2="50" y2="24" stroke={color} strokeWidth="2" />
      {/* Left pan */}
      <path d="M14,24 L10,34 L22,34 Z" stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" />
      {/* Right pan */}
      <path d="M50,24 L46,34 L58,34 Z" stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" />
      {/* Arrows showing distribution */}
      <polyline points="29,20 32,16 35,20" stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" />
    </svg>
  )
}

/* ── Server / Rack ─────────────────────────────────────────────────── */
export function ServerIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Server unit 1 */}
      <rect x="12" y="8" width="40" height="14" rx="2" stroke={color} strokeWidth="2" fill="none" />
      <circle cx="44" cy="15" r="2.5" fill={color} opacity="0.5" />
      <line x1="18" y1="15" x2="30" y2="15" stroke={color} strokeWidth="1.5" opacity="0.4" />
      {/* Server unit 2 */}
      <rect x="12" y="25" width="40" height="14" rx="2" stroke={color} strokeWidth="2" fill="none" />
      <circle cx="44" cy="32" r="2.5" fill={color} opacity="0.5" />
      <line x1="18" y1="32" x2="30" y2="32" stroke={color} strokeWidth="1.5" opacity="0.4" />
      {/* Server unit 3 */}
      <rect x="12" y="42" width="40" height="14" rx="2" stroke={color} strokeWidth="2" fill="none" />
      <circle cx="44" cy="49" r="2.5" fill={color} opacity="0.5" />
      <line x1="18" y1="49" x2="30" y2="49" stroke={color} strokeWidth="1.5" opacity="0.4" />
    </svg>
  )
}

/* ── Cloud ─────────────────────────────────────────────────────────── */
export function CloudIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      <path
        d="M16 44 C8 44 4 38 4 32 C4 26 8 22 14 20 C14 12 22 6 32 6 C40 6 46 10 48 16 C56 16 60 22 60 28 C60 36 54 44 46 44 Z"
        stroke={color}
        strokeWidth="2.5"
        fill="none"
        strokeLinejoin="round"
      />
      {/* Up/down arrows — cloud connectivity */}
      <polyline points="26,28 32,22 38,28" stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" />
      <line x1="32" y1="22" x2="32" y2="38" stroke={color} strokeWidth="1.5" />
      <polyline points="26,36 32,42 38,36" stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" opacity="0.5" />
    </svg>
  )
}

/* ── Wireless AP ───────────────────────────────────────────────────── */
export function WirelessAPIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* AP body (small rectangle) */}
      <rect x="24" y="36" width="16" height="8" rx="2" stroke={color} strokeWidth="2" fill="none" />
      {/* Mount post */}
      <line x1="32" y1="44" x2="32" y2="54" stroke={color} strokeWidth="2" />
      <line x1="24" y1="54" x2="40" y2="54" stroke={color} strokeWidth="2" strokeLinecap="round" />
      {/* Radio waves */}
      <path d="M20 28 C24 20 40 20 44 28" stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M14 22 C20 10 44 10 50 22" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.6" />
      <path d="M8 16 C16 0 48 0 56 16" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.3" />
      {/* Signal dot */}
      <circle cx="32" cy="32" r="2" fill={color} />
    </svg>
  )
}

/* ── Wireless Controller ───────────────────────────────────────────── */
export function WirelessControllerIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Controller body */}
      <rect x="10" y="22" width="44" height="24" rx="3" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Antenna */}
      <line x1="22" y1="22" x2="22" y2="12" stroke={color} strokeWidth="2" />
      <line x1="42" y1="22" x2="42" y2="12" stroke={color} strokeWidth="2" />
      {/* Small waves */}
      <path d="M18 12 C20 8 24 8 26 12" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <path d="M38 12 C40 8 44 8 46 12" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" />
      {/* Status LEDs */}
      <circle cx="20" cy="34" r="2" fill={color} opacity="0.5" />
      <circle cx="28" cy="34" r="2" fill={color} opacity="0.5" />
      <circle cx="36" cy="34" r="2" fill={color} opacity="0.5" />
      {/* Port indicators */}
      <rect x="18" y="40" width="6" height="3" rx="0.5" fill={color} opacity="0.3" />
      <rect x="29" y="40" width="6" height="3" rx="0.5" fill={color} opacity="0.3" />
      <rect x="40" y="40" width="6" height="3" rx="0.5" fill={color} opacity="0.3" />
    </svg>
  )
}

/* ── Datacenter / Building ─────────────────────────────────────────── */
export function DatacenterIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Building outline */}
      <rect x="12" y="12" width="40" height="44" rx="2" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Roof accent */}
      <line x1="12" y1="12" x2="52" y2="12" stroke={color} strokeWidth="3" strokeLinecap="round" />
      {/* Windows row 1 */}
      <rect x="18" y="18" width="8" height="6" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      <rect x="30" y="18" width="8" height="6" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      <rect x="42" y="18" width="5" height="6" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      {/* Windows row 2 */}
      <rect x="18" y="28" width="8" height="6" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      <rect x="30" y="28" width="8" height="6" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      <rect x="42" y="28" width="5" height="6" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      {/* Server rack indicators */}
      <rect x="18" y="38" width="8" height="3" rx="0.5" fill={color} opacity="0.3" />
      <rect x="30" y="38" width="8" height="3" rx="0.5" fill={color} opacity="0.3" />
      {/* Door */}
      <rect x="26" y="46" width="12" height="10" rx="1" stroke={color} strokeWidth="1.5" fill="none" opacity="0.6" />
    </svg>
  )
}

/* ── Application ───────────────────────────────────────────────────── */
export function ApplicationIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Window frame */}
      <rect x="8" y="8" width="48" height="48" rx="6" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Title bar */}
      <line x1="8" y1="18" x2="56" y2="18" stroke={color} strokeWidth="1.5" opacity="0.4" />
      <circle cx="16" cy="13" r="2" fill={color} opacity="0.4" />
      <circle cx="24" cy="13" r="2" fill={color} opacity="0.4" />
      {/* Code brackets */}
      <path d="M22 30 L16 38 L22 46" stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M42 30 L48 38 L42 46" stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {/* Slash */}
      <line x1="36" y1="28" x2="28" y2="48" stroke={color} strokeWidth="2" opacity="0.6" />
    </svg>
  )
}

/* ── Service ───────────────────────────────────────────────────────── */
export function ServiceIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Gear shape (simplified) */}
      <circle cx="32" cy="32" r="12" stroke={color} strokeWidth="2.5" fill="none" />
      <circle cx="32" cy="32" r="6" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      {/* Gear teeth */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => {
        const rad = (angle * Math.PI) / 180
        const x1 = 32 + 12 * Math.cos(rad)
        const y1 = 32 + 12 * Math.sin(rad)
        const x2 = 32 + 17 * Math.cos(rad)
        const y2 = 32 + 17 * Math.sin(rad)
        return (
          <line
            key={angle}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={color}
            strokeWidth="3"
            strokeLinecap="round"
          />
        )
      })}
    </svg>
  )
}

/* ── VLAN ──────────────────────────────────────────────────────────── */
export function VLANIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Overlapping network segments */}
      <ellipse cx="26" cy="30" rx="18" ry="14" stroke={color} strokeWidth="2" fill="none" opacity="0.5" />
      <ellipse cx="38" cy="34" rx="18" ry="14" stroke={color} strokeWidth="2" fill="none" opacity="0.5" />
      {/* Center highlight */}
      <circle cx="32" cy="32" r="5" stroke={color} strokeWidth="2" fill="none" />
      <circle cx="32" cy="32" r="2" fill={color} opacity="0.5" />
    </svg>
  )
}

/* ── IP Address ────────────────────────────────────────────────────── */
export function IPIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Globe */}
      <circle cx="32" cy="32" r="22" stroke={color} strokeWidth="2" fill="none" />
      <ellipse cx="32" cy="32" rx="10" ry="22" stroke={color} strokeWidth="1.5" fill="none" opacity="0.4" />
      <line x1="10" y1="24" x2="54" y2="24" stroke={color} strokeWidth="1" opacity="0.3" />
      <line x1="10" y1="40" x2="54" y2="40" stroke={color} strokeWidth="1" opacity="0.3" />
      <line x1="10" y1="32" x2="54" y2="32" stroke={color} strokeWidth="1.5" opacity="0.4" />
    </svg>
  )
}

/* ── Rule (Firewall Rule) ──────────────────────────────────────────── */
export function RuleIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Clipboard */}
      <rect x="14" y="12" width="36" height="44" rx="3" stroke={color} strokeWidth="2" fill="none" />
      {/* Clip top */}
      <rect x="24" y="8" width="16" height="8" rx="2" stroke={color} strokeWidth="2" fill="none" />
      {/* Lines (rules) */}
      <line x1="22" y1="26" x2="42" y2="26" stroke={color} strokeWidth="2" opacity="0.5" />
      <line x1="22" y1="34" x2="42" y2="34" stroke={color} strokeWidth="2" opacity="0.5" />
      <line x1="22" y1="42" x2="36" y2="42" stroke={color} strokeWidth="2" opacity="0.5" />
      {/* Check mark */}
      <polyline points="38,40 42,44 48,36" stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.7" />
    </svg>
  )
}

/* ── VPN Gateway ───────────────────────────────────────────────────── */
export function VPNIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Lock body */}
      <rect x="14" y="30" width="36" height="26" rx="4" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Shackle */}
      <path d="M20 30 L20 22 A12 12 0 0 1 44 22 L44 30" stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" />
      {/* Keyhole */}
      <circle cx="32" cy="42" r="4" stroke={color} strokeWidth="2" fill="none" />
      <line x1="32" y1="46" x2="32" y2="52" stroke={color} strokeWidth="2" strokeLinecap="round" />
      {/* Tunnel arrows */}
      <polyline points="4,32 10,28 10,36 4,32" stroke={color} strokeWidth="1.5" fill={color} opacity="0.5" />
      <polyline points="60,32 54,28 54,36 60,32" stroke={color} strokeWidth="1.5" fill={color} opacity="0.5" />
    </svg>
  )
}

/* ── IDS / Snort ───────────────────────────────────────────────────── */
export function IDSIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Eye outline */}
      <path d="M6 32 C14 14 50 14 58 32 C50 50 14 50 6 32 Z" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Iris */}
      <circle cx="32" cy="32" r="8" stroke={color} strokeWidth="2" fill="none" />
      {/* Pupil */}
      <circle cx="32" cy="32" r="3" fill={color} opacity="0.6" />
      {/* Alert mark */}
      <path d="M44 10 L48 20 L40 20 Z" stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" />
      <circle cx="44" cy="22" r="1" fill={color} opacity="0.7" />
    </svg>
  )
}

/* ── LDAP / Directory ──────────────────────────────────────────────── */
export function LDAPIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Root node */}
      <circle cx="32" cy="10" r="6" stroke={color} strokeWidth="2" fill="none" />
      {/* Branch lines */}
      <line x1="32" y1="16" x2="32" y2="30" stroke={color} strokeWidth="1.5" />
      <line x1="32" y1="30" x2="14" y2="38" stroke={color} strokeWidth="1.5" />
      <line x1="32" y1="30" x2="50" y2="38" stroke={color} strokeWidth="1.5" />
      {/* Child nodes left */}
      <circle cx="14" cy="44" r="5" stroke={color} strokeWidth="2" fill="none" />
      <line x1="14" y1="49" x2="8" y2="57" stroke={color} strokeWidth="1.5" />
      <line x1="14" y1="49" x2="20" y2="57" stroke={color} strokeWidth="1.5" />
      {/* Child nodes right */}
      <circle cx="50" cy="44" r="5" stroke={color} strokeWidth="2" fill="none" />
      <line x1="50" y1="49" x2="44" y2="57" stroke={color} strokeWidth="1.5" />
      <line x1="50" y1="49" x2="56" y2="57" stroke={color} strokeWidth="1.5" />
    </svg>
  )
}

/* ── Web Server / Nginx ────────────────────────────────────────────── */
export function WebServerIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Globe outline */}
      <circle cx="32" cy="32" r="24" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Horizontal lines */}
      <line x1="8" y1="24" x2="56" y2="24" stroke={color} strokeWidth="1.5" opacity="0.5" />
      <line x1="8" y1="40" x2="56" y2="40" stroke={color} strokeWidth="1.5" opacity="0.5" />
      {/* Vertical meridian */}
      <line x1="32" y1="8" x2="32" y2="56" stroke={color} strokeWidth="1.5" opacity="0.5" />
      {/* Oval paths (curved) */}
      <path d="M32 8 C20 20 20 44 32 56" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
      <path d="M32 8 C44 20 44 44 32 56" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
    </svg>
  )
}

/* ── Database / PostgreSQL ─────────────────────────────────────────── */
export function DatabaseIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Top cap */}
      <ellipse cx="32" cy="14" rx="20" ry="7" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Bottom cap */}
      <ellipse cx="32" cy="50" rx="20" ry="7" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Sides */}
      <line x1="12" y1="14" x2="12" y2="50" stroke={color} strokeWidth="2.5" />
      <line x1="52" y1="14" x2="52" y2="50" stroke={color} strokeWidth="2.5" />
      {/* Middle shelf */}
      <path d="M12 32 C12 36 52 36 52 32" stroke={color} strokeWidth="1.5" fill="none" opacity="0.5" />
    </svg>
  )
}

/* ── Cache / Redis ─────────────────────────────────────────────────── */
export function CacheIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Box */}
      <rect x="10" y="10" width="44" height="44" rx="6" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Lightning bolt */}
      <path d="M36 12 L26 34 L34 34 L28 52 L42 28 L34 28 Z"
        stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" />
    </svg>
  )
}

/* ── Monitoring / Prometheus+Grafana ───────────────────────────────── */
export function MonitoringIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      {/* Screen */}
      <rect x="6" y="10" width="52" height="36" rx="4" stroke={color} strokeWidth="2.5" fill="none" />
      {/* Chart bars */}
      <rect x="14" y="28" width="6" height="12" rx="1" fill={color} opacity="0.4" />
      <rect x="24" y="20" width="6" height="20" rx="1" fill={color} opacity="0.6" />
      <rect x="34" y="24" width="6" height="16" rx="1" fill={color} opacity="0.5" />
      <rect x="44" y="18" width="6" height="22" rx="1" fill={color} opacity="0.7" />
      {/* Stand */}
      <line x1="32" y1="46" x2="32" y2="56" stroke={color} strokeWidth="2.5" />
      <line x1="18" y1="56" x2="46" y2="56" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

/* ── Generic fallback ──────────────────────────────────────────────── */
export function GenericNodeIcon({ size = defaults.size, color = defaults.color, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
      <circle cx="32" cy="32" r="22" stroke={color} strokeWidth="2.5" fill="none" />
      <circle cx="32" cy="32" r="8" fill={color} opacity="0.3" />
    </svg>
  )
}

/* ── Icon resolver ─────────────────────────────────────────────────── */

/**
 * Maps a graph node type + device sub-type to the appropriate icon component.
 * Uses the Neo4j label (e.g. "Device") and the `type` property
 * (e.g. "firewall", "router") to pick the right icon.
 */
export function getTopologyIcon(
  nodeType: string,
  deviceSubType?: string,
): React.ComponentType<IconProps> {
  // Device sub-types
  if (nodeType === 'Device' && deviceSubType) {
    const t = deviceSubType.toLowerCase()
    if (t === 'router') return RouterIcon
    if (t === 'switch') return SwitchIcon
    if (t === 'firewall') return FirewallIcon
    if (t === 'load_balancer') return LoadBalancerIcon
    if (t === 'server') return ServerIcon
    if (t === 'cloud_gateway') return CloudIcon
    if (t === 'wireless_ap') return WirelessAPIcon
    if (t === 'wireless_controller') return WirelessControllerIcon
    if (t === 'rack') return ServerIcon
    if (t === 'patch_panel') return SwitchIcon
    return GenericNodeIcon
  }

  // Lab catalog icon_type values
  switch (nodeType) {
    case 'firewall': return FirewallIcon
    case 'switch': return SwitchIcon
    case 'router': return RouterIcon
    case 'wireless_controller': return WirelessControllerIcon
    case 'wireless_ap': return WirelessAPIcon
    case 'vpn': return VPNIcon
    case 'ids': return IDSIcon
    case 'ldap': return LDAPIcon
    case 'webserver': return WebServerIcon
    case 'database': return DatabaseIcon
    case 'cache': return CacheIcon
    case 'monitoring': return MonitoringIcon
    case 'application': return ApplicationIcon
    case 'server': return ServerIcon
  }

  switch (nodeType) {
    case 'Datacenter':
      return DatacenterIcon
    case 'Application':
      return ApplicationIcon
    case 'Service':
      return ServiceIcon
    case 'VLAN':
      return VLANIcon
    case 'IP':
      return IPIcon
    case 'Interface':
      return SwitchIcon
    case 'Rule':
      return RuleIcon
    case 'Port':
      return SwitchIcon
    case 'Cable':
      return GenericNodeIcon
    default:
      return GenericNodeIcon
  }
}
