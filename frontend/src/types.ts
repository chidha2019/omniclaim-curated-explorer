import type { components } from "./api-schema";
export type Customer = components["schemas"]["Customer"];
export type Policy = components["schemas"]["PolicyMetric"];
export type Claim = components["schemas"]["Claim"];
export type Health = components["schemas"]["HealthStatus"];
export type Dataset = "customers" | "policies" | "claims";
export type Workspace = Dataset | "health";
export interface RuntimeConfig {
  demo: boolean;
  version: string;
  authority: string;
  client_id: string;
  scope: string;
  telemetry_sample_ratio: number;
  freshness_seconds: number;
}
export interface User {
  tenant: string;
  capabilities: Workspace[];
}
export type Page =
  | components["schemas"]["Page_Customer_"]
  | components["schemas"]["Page_PolicyMetric_"]
  | components["schemas"]["Page_Claim_"];
