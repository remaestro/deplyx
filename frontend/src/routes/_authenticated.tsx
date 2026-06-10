import { createFileRoute, Outlet, redirect, isRedirect } from "@tanstack/react-router";
import { AppSidebar } from "@/components/app-sidebar";
import { SyncProvider } from "@/lib/sync-context";

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: () => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("deplyx.auth");
      if (!raw) throw redirect({ to: "/login" });
    } catch (e) {
      if (isRedirect(e)) throw e;
      throw redirect({ to: "/login" });
    }
  },
  component: AuthLayout,
});

function AuthLayout() {
  return (
    <SyncProvider>
      <div className="flex min-h-screen w-full bg-background">
        <AppSidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </SyncProvider>
  );
}
