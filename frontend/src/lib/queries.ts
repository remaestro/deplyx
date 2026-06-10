import { queryOptions } from "@tanstack/react-query";
import { api } from "./api";

export const kpisQuery = () =>
  queryOptions({ queryKey: ["kpis"], queryFn: () => api.kpis() });

export const changesQuery = () =>
  queryOptions({ queryKey: ["changes"], queryFn: () => api.listChanges() });

export const changeQuery = (id: string) =>
  queryOptions({ queryKey: ["changes", id], queryFn: () => api.getChange(id) });

export const connectorsQuery = () =>
  queryOptions({ queryKey: ["connectors"], queryFn: () => api.listConnectors() });

export const policiesQuery = () =>
  queryOptions({ queryKey: ["policies"], queryFn: () => api.listPolicies() });

export const auditQuery = (params?: { range?: string; action?: string }) =>
  queryOptions({
    queryKey: ["audit", params ?? {}],
    queryFn: () => api.listAudit(params),
  });

export const topologyQuery = () =>
  queryOptions({ queryKey: ["topology"], queryFn: () => api.topology() });

export const impactQuery = (id: string) =>
  queryOptions({ queryKey: ["impact", id], queryFn: () => api.getChangeImpact(id) });
