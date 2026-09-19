import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBreadcrumb,
  formatAmount,
  rankSearchResults,
} from "./app.mjs";

const nodes = [
  {
    id: "mission-defense",
    node_type: "mission",
    code: "146",
    name: "Défense",
    parent_id: null,
  },
  {
    id: "mission-justice",
    node_type: "mission",
    code: "166",
    name: "Justice",
    parent_id: null,
  },
  {
    id: "programme-defense",
    node_type: "programme",
    code: "178",
    name: "Défense opérationnelle",
    parent_id: "mission-defense",
  },
];

test("search ranks an exact name before lexical matches and stays stable", () => {
  const results = rankSearchResults(nodes, "défense");

  assert.deepEqual(
    results.map((node) => node.id),
    ["mission-defense", "programme-defense"],
  );
});

test("search is accent-insensitive and returns no result for blank input", () => {
  assert.deepEqual(
    rankSearchResults(nodes, "OPERATIONNELLE").map((node) => node.id),
    ["programme-defense"],
  );
  assert.deepEqual(rankSearchResults(nodes, "   "), []);
});

test("breadcrumb follows the Mission to Programme to Action ancestry", () => {
  assert.deepEqual(
    buildBreadcrumb(nodes, "programme-defense").map((node) => node.id),
    ["mission-defense", "programme-defense"],
  );
});

test("amount formatting keeps euro values readable and deterministic", () => {
  assert.equal(formatAmount("1234567.50"), "1,23 M€");
  assert.equal(formatAmount("0"), "0 €");
});
