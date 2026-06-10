import { cn } from "@/lib/utils";

const map: Record<string, string> = {
  Draft: "bg-muted text-muted-foreground border-border",
  Pending: "bg-[color-mix(in_oklab,var(--warning)_18%,transparent)] text-[var(--warning)] border-[color-mix(in_oklab,var(--warning)_30%,transparent)]",
  Analyzing: "bg-[color-mix(in_oklab,var(--info)_18%,transparent)] text-[var(--info)] border-[color-mix(in_oklab,var(--info)_30%,transparent)]",
  Approved: "bg-[color-mix(in_oklab,var(--success)_18%,transparent)] text-[var(--success)] border-[color-mix(in_oklab,var(--success)_30%,transparent)]",
  Rejected: "bg-[color-mix(in_oklab,var(--destructive)_18%,transparent)] text-[color-mix(in_oklab,var(--destructive)_85%,white)] border-[color-mix(in_oklab,var(--destructive)_30%,transparent)]",
  Executing: "bg-[color-mix(in_oklab,var(--primary)_18%,transparent)] text-primary border-[color-mix(in_oklab,var(--primary)_30%,transparent)]",
  Completed: "bg-[color-mix(in_oklab,var(--success)_14%,transparent)] text-[var(--success)] border-[color-mix(in_oklab,var(--success)_25%,transparent)]",
  RolledBack: "bg-[color-mix(in_oklab,var(--destructive)_14%,transparent)] text-[color-mix(in_oklab,var(--destructive)_85%,white)] border-[color-mix(in_oklab,var(--destructive)_25%,transparent)]",

  low: "bg-[color-mix(in_oklab,var(--success)_18%,transparent)] text-[var(--success)] border-[color-mix(in_oklab,var(--success)_30%,transparent)]",
  medium: "bg-[color-mix(in_oklab,var(--warning)_18%,transparent)] text-[var(--warning)] border-[color-mix(in_oklab,var(--warning)_30%,transparent)]",
  high: "bg-[color-mix(in_oklab,var(--destructive)_18%,transparent)] text-[color-mix(in_oklab,var(--destructive)_90%,white)] border-[color-mix(in_oklab,var(--destructive)_30%,transparent)]",
  critical: "bg-[color-mix(in_oklab,var(--destructive)_25%,transparent)] text-[color-mix(in_oklab,var(--destructive)_90%,white)] border-[color-mix(in_oklab,var(--destructive)_40%,transparent)]",

  active: "bg-[color-mix(in_oklab,var(--success)_18%,transparent)] text-[var(--success)] border-[color-mix(in_oklab,var(--success)_30%,transparent)]",
  inactive: "bg-muted text-muted-foreground border-border",
  error: "bg-[color-mix(in_oklab,var(--destructive)_18%,transparent)] text-[color-mix(in_oklab,var(--destructive)_90%,white)] border-[color-mix(in_oklab,var(--destructive)_30%,transparent)]",
};

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        map[value] ?? "bg-muted text-muted-foreground border-border",
        className,
      )}
    >
      <span className="size-1.5 rounded-full bg-current opacity-80" />
      {value}
    </span>
  );
}
