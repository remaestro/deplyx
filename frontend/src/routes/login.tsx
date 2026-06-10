import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Activity, ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "Sign in — Deplyx" }] }),
  component: LoginPage,
});

function LoginPage() {
  const { login, register, isAuthenticated } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("admin@deplyx.io");
  const [password, setPassword] = useState("Admin123!");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) nav({ to: "/" });
  }, [isAuthenticated, nav]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await (mode === "login" ? login(email, password) : register(email, password));
      toast.success("Signed in");
      nav({ to: "/" });
    } catch {
      toast.error("Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen grid-cols-1 md:grid-cols-[1.2fr_1fr]">
      {/* Left visual */}
      <section className="relative hidden overflow-hidden border-r border-border md:block">
        <div className="absolute inset-0 bg-grid opacity-40" />
        <div className="absolute -left-32 top-1/3 size-[420px] rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute right-10 bottom-10 size-[300px] rounded-full bg-[var(--info)]/15 blur-3xl" />
        <div className="relative flex h-full flex-col justify-between p-10">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-primary/15 text-primary">
              <Activity className="size-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight">Deplyx</span>
          </div>
          <div className="max-w-md">
            <h2 className="text-3xl font-semibold leading-tight tracking-tight">
              Ship network changes<br />without surprises.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Topology-aware impact analysis, risk scoring, and policy gates — all in one
              orchestration plane for your network &amp; security teams.
            </p>
            <div className="mt-8 grid grid-cols-3 gap-3 text-[11px] text-muted-foreground">
              {["22 connectors", "Graph-aware", "Policy engine"].map((t) => (
                <div key={t} className="rounded-md border border-border bg-card/40 px-3 py-2">{t}</div>
              ))}
            </div>
          </div>
          <div className="text-[11px] text-muted-foreground">© Deplyx — Demo build</div>
        </div>
      </section>

      {/* Right form */}
      <section className="flex items-center justify-center p-6 md:p-10">
        <div className="w-full max-w-sm">
          <div className="mb-6 md:hidden">
            <div className="flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-md bg-primary/15 text-primary">
                <Activity className="size-4" />
              </div>
              <span className="text-sm font-semibold">Deplyx</span>
            </div>
          </div>

          <h1 className="text-xl font-semibold tracking-tight">
            {mode === "login" ? "Sign in to your workspace" : "Create your account"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "login" ? "Use any email/password to enter the demo." : "Quick demo signup — no email sent."}
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-3">
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Email</span>
              <input
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none transition focus:border-ring focus:bg-input/70"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Password</span>
              <input
                type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none transition focus:border-ring focus:bg-input/70"
              />
            </label>

            <button
              type="submit" disabled={loading}
              className="group flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-60"
            >
              {loading ? "Signing in…" : mode === "login" ? "Sign in" : "Create account"}
              <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
            </button>
          </form>

          <p className="mt-5 text-center text-xs text-muted-foreground">
            {mode === "login" ? "New here? " : "Have an account? "}
            <button
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </div>
      </section>
    </main>
  );
}
