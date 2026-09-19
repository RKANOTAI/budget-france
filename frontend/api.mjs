const DEFAULT_FISCAL_YEAR = 2026;
const DEFAULT_LEGAL_STAGE = "PLF";

export function normalizeApiBaseUrl(value) {
  const raw = String(value ?? "").trim().replace(/\/+$/, "");
  if (!raw) return "";
  const url = new URL(raw);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("The budget API URL must use HTTP or HTTPS");
  }
  return url.href.replace(/\/+$/, "");
}

export function treeResponseToAppData(payload) {
  const collection = payload?.data ?? payload;
  if (!collection?.release || !Array.isArray(collection.roots)) {
    throw new Error("The budget API returned an invalid tree collection");
  }

  const nodes = [];
  const metrics = {};
  const history = {};
  const provenance = {};
  const release = collection.release;

  const visit = (node, parentId = null) => {
    const id = String(node.id);
    const budget = node.budget ?? {};
    nodes.push({
      id,
      parent_id: parentId,
      node_type: node.node_type,
      code: node.code,
      name: node.name,
      description: "Crédits rattachés à ce niveau de la nomenclature budgétaire.",
    });
    metrics[id] = { ae: budget.ae ?? null, cp: budget.cp ?? null };
    history[id] = [{
      year: release.fiscal_year,
      ae: budget.ae ?? null,
      cp: budget.cp ?? null,
      version: release.version,
    }];
    provenance[id] = (node.source_refs ?? []).map((source) => ({
      title: source.document_type ?? "Document budgétaire officiel",
      document_type: source.document_type ?? "Source officielle",
      locator: source.locator ?? "—",
      published_at: source.publication_date ?? null,
      url: source.url,
    }));
    (node.children ?? []).forEach((child) => visit(child, id));
  };

  collection.roots.forEach((root) => visit(root));
  return {
    mode: "api",
    release: {
      ...release,
      status: "published",
      source: "API publique",
    },
    nodes,
    metrics,
    history,
    provenance,
  };
}

export async function fetchBudgetData({
  apiBaseUrl,
  fetchImpl = globalThis.fetch,
  fiscalYear = DEFAULT_FISCAL_YEAR,
  legalStage = DEFAULT_LEGAL_STAGE,
} = {}) {
  const baseUrl = normalizeApiBaseUrl(apiBaseUrl);
  if (!baseUrl) throw new Error("No public budget API URL is configured");
  if (typeof fetchImpl !== "function") throw new Error("Fetch is unavailable in this browser");

  const url = new URL("/api/v1/tree", `${baseUrl}/`);
  url.searchParams.set("fiscal_year", String(fiscalYear));
  url.searchParams.set("legal_stage", legalStage);
  const response = await fetchImpl(url.href, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Budget API request failed with HTTP ${response.status}`);
  }
  return treeResponseToAppData(await response.json());
}
