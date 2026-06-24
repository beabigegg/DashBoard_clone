/**
 * Type declarations for navigationManifest.js
 * Contract: data-shape-contract.md §3.11b
 */

export interface ManifestDrawer {
  id: string;
  name: string;
  order: number;
  admin_only: boolean;
}

export interface ManifestRoute {
  drawerId: string | null;
  order: number;
  displayName: string;
  defaultStatus?: string;
}

export declare const drawers: ReadonlyArray<ManifestDrawer>;
export declare const routes: Readonly<Record<string, ManifestRoute>>;
