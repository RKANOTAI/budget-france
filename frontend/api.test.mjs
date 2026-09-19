import test from "node:test";
import assert from "node:assert/strict";

import { fetchBudgetData, normalizeApiBaseUrl, treeResponseToAppData } from "./api.mjs";

const treePayload = {
  data: {
    release: {
      fiscal_year: 2026,
      legal_stage: "PLF",
      version: "plf-2026-20251024",
      released_at: "2026-01-01T00:00:00Z",
      source_snapshot_hash: "abc123",
    },
    roots: [{
      id: "mission-1",
      node_type: "mission",
      code: "DEF",
      name: "Défense",
      budget: { ae: "100", cp: "90", currency: "EUR" },
      source_refs: [{
        url: "https://example.test/source.xls",
        document_type: "XLS",
        locator: "mission=DEF",
        publication_date: "2025-10-24",
      }],
      children: [{
        id: "programme-1",
        node_type: "programme",
        code: "178",
        name: "Préparation et emploi des forces",
        budget: { ae: "100", cp: "90", currency: "EUR" },
        source_refs: [],
        children: [],
      }],
    }],
  },
};

test("normalizes a public API base URL without changing its origin", () => {
  assert.equal(normalizeApiBaseUrl(" https://api.example.test/// "), "https://api.example.test");
  assert.equal(normalizeApiBaseUrl(""), "");
  assert.throws(() => normalizeApiBaseUrl("ftp://api.example.test"), /HTTP or HTTPS/);
});

test("maps the public tree collection to the deterministic app model", () => {
  const data = treeResponseToAppData(treePayload);
  assert.equal(data.mode, "api");
  assert.equal(data.nodes.length, 2);
  assert.equal(data.nodes[1].parent_id, "mission-1");
  assert.deepEqual(data.metrics["mission-1"], { ae: "100", cp: "90" });
  assert.equal(data.provenance["mission-1"][0].published_at, "2025-10-24");
});

test("fetches the tree with explicit release query parameters", async () => {
  let requestUrl = "";
  const data = await fetchBudgetData({
    apiBaseUrl: "https://api.example.test/",
    fetchImpl: async (url) => {
      requestUrl = url;
      return { ok: true, status: 200, json: async () => treePayload };
    },
  });
  assert.equal(requestUrl, "https://api.example.test/api/v1/tree?fiscal_year=2026&legal_stage=PLF");
  assert.equal(data.release.version, "plf-2026-20251024");
});
