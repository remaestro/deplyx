import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard, GitPullRequest, Layers, Plug, ShieldCheck, FileText, LogOut, Activity, Loader2,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { useSyncContext } from "@/lib/sync-context";

const sections = [
  {
    label: "Operations",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard },
      { to: "/changes", label: "Changes", icon: GitPullRequest },
      { to: "/graph-v3", label: "Topology", icon: Layers },
    ],
  },
  {
    label: "Configuration",
    items: [
      { to: "/connectors", label: "Connectors", icon: Plug },
      { to: "/policies", label: "Policies", icon: ShieldCheck },
      { to: "/audit-log", label: "Audit Log", icon: FileText },
    ],
  },
];

export function AppSidebar() {
  const { user, logout } = useAuth();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { syncCount } = useSyncContext();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-4">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary/15 text-primary">
          <Activity className="size-4" />
        </div>
        <span className="text-sm font-semibold tracking-tight">Deplyx</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4">
        {sections.map((s) => (
          <div key={s.label} className="mb-5">
            <div className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {s.label}
            </div>
            <ul className="space-y-0.5">
              {s.items.map((it) => {
                const active =
                  it.to === "/" ? pathname === "/" : pathname.startsWith(it.to);
                return (
                  <li key={it.to}>
                    <Link
                      to={it.to}
                      className={cn(
                        "group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] transition-colors",
                        active
                          ? "bg-sidebar-accent text-sidebar-accent-foreground"
                          : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                      )}
                    >
                      <it.icon className={cn("size-4", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                      {it.label}
                      {it.to === "/connectors" && syncCount > 0 && (
                        <span className="ml-auto flex items-center gap-1 text-[10px] font-medium text-primary">
                          <Loader2 className="size-2.5 animate-spin" />
                          {syncCount}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-2.5 rounded-md px-2 py-1.5">
          <div className="flex size-7 items-center justify-center rounded-full bg-primary/20 text-[11px] font-semibold text-primary">
            {user?.email?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium">{user?.email}</div>
            <div className="text-[10px] text-muted-foreground">{user?.role}</div>
          </div>
          <button
            onClick={logout}
            className="rounded p-1 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
            aria-label="Sign out"
          >
            <LogOut className="size-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
