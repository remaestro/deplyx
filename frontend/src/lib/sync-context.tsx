import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface SyncContextValue {
  syncingIds: Set<number>;
  syncCount: number;
  startSync: (id: number) => void;
  finishSync: (id: number) => void;
  startBatch: (ids: number[]) => void;
}

const SyncContext = createContext<SyncContextValue | null>(null);

export function SyncProvider({ children }: { children: ReactNode }) {
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set());

  const startSync = useCallback((id: number) => {
    setSyncingIds((prev) => new Set(prev).add(id));
  }, []);

  const finishSync = useCallback((id: number) => {
    setSyncingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const startBatch = useCallback((ids: number[]) => {
    setSyncingIds(new Set(ids));
  }, []);

  return (
    <SyncContext.Provider value={{ syncingIds, syncCount: syncingIds.size, startSync, finishSync, startBatch }}>
      {children}
    </SyncContext.Provider>
  );
}

export function useSyncContext() {
  const ctx = useContext(SyncContext);
  if (!ctx) throw new Error("useSyncContext must be used within SyncProvider");
  return ctx;
}
