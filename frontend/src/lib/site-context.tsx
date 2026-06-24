import {
  createContext, useContext, useEffect, useMemo, useState, useCallback, type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, SITE_KEY } from "./api";
import type { Site } from "./types";

interface SiteContextValue {
  sites: Site[];
  selectedSite: Site | null;
  selectedSiteId: number | null;
  setSite: (id: number) => void;
  isLoading: boolean;
}

const SiteContext = createContext<SiteContextValue | null>(null);

function readStoredSiteId(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SITE_KEY);
  return raw ? Number(raw) : null;
}

export function SiteProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [selectedSiteId, setSelectedSiteId] = useState<number | null>(readStoredSiteId);

  const { data: sites = [], isLoading } = useQuery({
    queryKey: ["sites"],
    queryFn: () => api.listSites(),
  });

  // Pick a default site once the list is available and persist it.
  useEffect(() => {
    if (sites.length === 0) return;
    const exists = selectedSiteId != null && sites.some((s) => s.id === selectedSiteId);
    if (!exists) {
      const fallback = sites[0].id;
      setSelectedSiteId(fallback);
      window.localStorage.setItem(SITE_KEY, String(fallback));
    }
  }, [sites, selectedSiteId]);

  const setSite = useCallback(
    (id: number) => {
      setSelectedSiteId(id);
      window.localStorage.setItem(SITE_KEY, String(id));
      // Refetch every site-scoped query (connectors, changes, topology, dashboard…).
      qc.invalidateQueries();
    },
    [qc],
  );

  const selectedSite = useMemo(
    () => sites.find((s) => s.id === selectedSiteId) ?? null,
    [sites, selectedSiteId],
  );

  return (
    <SiteContext.Provider value={{ sites, selectedSite, selectedSiteId, setSite, isLoading }}>
      {children}
    </SiteContext.Provider>
  );
}

export function useSite() {
  const ctx = useContext(SiteContext);
  if (!ctx) throw new Error("useSite must be used within SiteProvider");
  return ctx;
}
