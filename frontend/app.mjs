const TYPE_ORDER = {
  mission: 0,
  programme: 1,
  action: 2,
};

const TYPE_LABELS = {
  mission: "Mission",
  programme: "Programme",
  action: "Action",
};

const METRIC_LABELS = {
  ae: "AE",
  cp: "CP",
};

export function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr-FR")
    .trim();
}

function compareNodes(left, right) {
  return (
    (TYPE_ORDER[left.node_type] ?? 99) - (TYPE_ORDER[right.node_type] ?? 99) ||
    String(left.code ?? "").localeCompare(String(right.code ?? ""), "fr", {
      numeric: true,
      sensitivity: "base",
    }) ||
    String(left.name ?? "").localeCompare(String(right.name ?? ""), "fr", {
      sensitivity: "base",
    }) ||
    String(left.id).localeCompare(String(right.id))
  );
}

function scoreNode(node, needle) {
  const name = normalizeText(node.name);
  const code = normalizeText(node.code);
  const words = name.split(/\s+/).filter(Boolean);
  const queryWords = needle.split(/\s+/).filter(Boolean);

  if (name === needle) return 100;
  if (code === needle) return 98;
  if (name.startsWith(needle)) return 90;
  if (queryWords.every((word) => words.some((nameWord) => nameWord.startsWith(word)))) {
    return 82;
  }
  if (name.includes(needle) || code.includes(needle)) return 70;
  if (queryWords.every((word) => normalizeText(`${node.name} ${node.code}`).includes(word))) {
    return 60;
  }
  return 0;
}

export function rankSearchResults(nodes, query) {
  const needle = normalizeText(query);
  if (!needle) return [];

  return nodes
    .map((node) => ({ node, score: scoreNode(node, needle) }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => right.score - left.score || compareNodes(left.node, right.node))
    .map(({ node }) => node);
}

export function buildBreadcrumb(nodes, nodeId) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const breadcrumb = [];
  const visited = new Set();
  let current = byId.get(nodeId);

  while (current && !visited.has(current.id)) {
    visited.add(current.id);
    breadcrumb.unshift(current);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }

  return breadcrumb;
}

export function formatAmount(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";

  const absolute = Math.abs(amount);
  let scaled = amount;
  let suffix = "€";
  if (absolute >= 1_000_000_000) {
    scaled = amount / 1_000_000_000;
    suffix = "Md€";
  } else if (absolute >= 1_000_000) {
    scaled = amount / 1_000_000;
    suffix = "M€";
  } else if (absolute >= 1_000) {
    scaled = amount / 1_000;
    suffix = "k€";
  }

  const digits = suffix === "€" ? 0 : 2;
  const formatted = new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
    useGrouping: false,
  }).format(scaled);
  return `${formatted} ${suffix}`;
}

export function formatFullAmount(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return `${new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(amount)} €`;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function getNode(nodes, id) {
  return nodes.find((node) => node.id === id) ?? null;
}

function getChildren(nodes, parentId) {
  return nodes.filter((node) => node.parent_id === parentId).sort(compareNodes);
}

function getMetric(data, nodeId, metric) {
  return data.metrics?.[nodeId]?.[metric] ?? null;
}

function getHistory(data, nodeId) {
  return (data.history?.[nodeId] ?? []).slice().sort((left, right) => left.year - right.year);
}

function getProvenance(data, nodeId) {
  return data.provenance?.[nodeId] ?? [];
}

function metricCard(metric, value) {
  const label = METRIC_LABELS[metric];
  const definition = metric === "ae" ? "Autorisations d'engagement" : "Crédits de paiement";
  return `
    <div class="metric-card">
      <div class="metric-card__topline">
        <span class="metric-card__label">${label}</span>
        <span class="metric-card__definition">${definition}</span>
      </div>
      <strong>${formatAmount(value)}</strong>
      <span class="metric-card__exact">${formatFullAmount(value)}</span>
    </div>`;
}

function renderTree(nodes, selectedId) {
  const roots = getChildren(nodes, null);
  const rows = [];
  const visit = (node, depth) => {
    const selected = node.id === selectedId;
    rows.push(`
      <li>
        <button class="tree-row ${selected ? "is-selected" : ""}" data-node-id="${escapeHtml(node.id)}" style="--depth: ${depth}" aria-current="${selected ? "page" : "false"}">
          <span class="tree-row__rail" aria-hidden="true"></span>
          <span class="tree-row__type">${escapeHtml(TYPE_LABELS[node.node_type] ?? node.node_type)}</span>
          <span class="tree-row__name">${escapeHtml(node.name)}</span>
          <span class="tree-row__code">${escapeHtml(node.code)}</span>
        </button>
      </li>`);
    getChildren(nodes, node.id).forEach((child) => visit(child, depth + 1));
  };
  roots.forEach((root) => visit(root, 0));
  return rows.join("");
}

function renderSearchResults(nodes, query, selectedId) {
  const results = rankSearchResults(nodes, query).slice(0, 8);
  if (!normalizeText(query)) return "";
  if (!results.length) {
    return `<div class="search-results search-results--empty"><span>Aucun nœud trouvé.</span><small>Essayez un nom, un code ou un mot-clé.</small></div>`;
  }
  return `
    <div class="search-results" aria-label="Résultats de recherche">
      <div class="search-results__header"><span>${results.length} résultat${results.length > 1 ? "s" : ""}</span><small>Classement lexical déterministe</small></div>
      <ul>${results.map((node) => `
        <li>
          <button class="search-result ${node.id === selectedId ? "is-selected" : ""}" data-node-id="${escapeHtml(node.id)}">
            <span class="search-result__type">${escapeHtml(TYPE_LABELS[node.node_type] ?? node.node_type)}</span>
            <span><strong>${escapeHtml(node.name)}</strong><small>${escapeHtml(node.code)}</small></span>
            <span class="search-result__arrow" aria-hidden="true">↗</span>
          </button>
        </li>`).join("")}</ul>
    </div>`;
}

function renderHistory(data, nodeId) {
  const history = getHistory(data, nodeId);
  if (!history.length) {
    return `<div class="empty-state">Pas encore d'historique publié pour ce nœud.</div>`;
  }
  const max = Math.max(...history.map((point) => Math.max(Number(point.ae ?? 0), Number(point.cp ?? 0))), 1);
  return `
    <div class="history-list">
      ${history.map((point) => {
        const aeWidth = Math.max(2, (Number(point.ae ?? 0) / max) * 100);
        const cpWidth = Math.max(2, (Number(point.cp ?? 0) / max) * 100);
        return `
          <div class="history-row">
            <div class="history-row__year">${escapeHtml(point.year)}</div>
            <div class="history-row__bars">
              <div class="history-bar history-bar--ae"><span style="width: ${aeWidth}%"></span></div>
              <div class="history-bar history-bar--cp"><span style="width: ${cpWidth}%"></span></div>
            </div>
            <div class="history-row__values"><span>AE ${formatAmount(point.ae)}</span><span>CP ${formatAmount(point.cp)}</span></div>
          </div>`;
      }).join("")}
    </div>
    <div class="history-legend"><span><i class="legend-dot legend-dot--ae"></i>AE</span><span><i class="legend-dot legend-dot--cp"></i>CP</span></div>`;
}

function renderProvenance(data, nodeId) {
  const sources = getProvenance(data, nodeId);
  if (!sources.length) {
    return `<div class="empty-state">La provenance n'est pas encore disponible.</div>`;
  }
  return `
    <div class="source-list">
      ${sources.map((source) => `
        <a class="source-row" href="${escapeHtml(safeUrl(source.url))}" target="_blank" rel="noreferrer noopener">
          <span class="source-row__mark" aria-hidden="true">↗</span>
          <span class="source-row__body"><strong>${escapeHtml(source.title)}</strong><small>${escapeHtml(source.document_type)} · ${escapeHtml(source.locator)}</small></span>
          <span class="source-row__date">${escapeHtml(formatDate(source.published_at))}</span>
        </a>`).join("")}
    </div>`;
}

function renderDetail(data, selectedId) {
  const nodes = data.nodes ?? [];
  const selected = getNode(nodes, selectedId) ?? nodes[0];
  if (!selected) return `<div class="empty-state">Aucune donnée à afficher.</div>`;

  const breadcrumb = buildBreadcrumb(nodes, selected.id);
  const children = getChildren(nodes, selected.id);
  const parent = selected.parent_id ? getNode(nodes, selected.parent_id) : null;
  const ae = getMetric(data, selected.id, "ae");
  const cp = getMetric(data, selected.id, "cp");
  const detail = selected.description ?? "Crédits rattachés à ce niveau de la nomenclature budgétaire.";
  const childLabel = selected.node_type === "mission" ? "Programmes" : selected.node_type === "programme" ? "Actions" : "Niveau terminal";

  return `
    <article class="detail-panel">
      <div class="detail-panel__topline">
        <div class="breadcrumbs" aria-label="Fil d'Ariane">
          ${breadcrumb.map((item, index) => `
            <button data-node-id="${escapeHtml(item.id)}" class="breadcrumb ${index === breadcrumb.length - 1 ? "is-current" : ""}">${escapeHtml(item.name)}</button>
            ${index < breadcrumb.length - 1 ? `<span aria-hidden="true">/</span>` : ""}`).join("")}
        </div>
        <span class="node-badge">${escapeHtml(TYPE_LABELS[selected.node_type] ?? selected.node_type)} · ${escapeHtml(selected.code)}</span>
      </div>
      <div class="detail-heading">
        <div>
          <p class="eyebrow">Nœud sélectionné</p>
          <h2>${escapeHtml(selected.name)}</h2>
          <p>${escapeHtml(detail)}</p>
        </div>
        ${parent ? `<div class="parent-note"><span>Rattaché à</span><button data-node-id="${escapeHtml(parent.id)}">${escapeHtml(parent.name)} <span aria-hidden="true">↗</span></button></div>` : ""}
      </div>
      <div class="metric-grid">
        ${metricCard("ae", ae)}
        ${metricCard("cp", cp)}
      </div>
      <section class="detail-section detail-section--children">
        <div class="section-title"><div><p class="eyebrow">Drill-down</p><h3>${escapeHtml(childLabel)}</h3></div><span class="section-count">${children.length} élément${children.length > 1 ? "s" : ""}</span></div>
        ${children.length ? `<div class="child-grid">${children.map((child) => `
          <button class="child-card" data-node-id="${escapeHtml(child.id)}">
            <span class="child-card__meta">${escapeHtml(TYPE_LABELS[child.node_type] ?? child.node_type)} · ${escapeHtml(child.code)}</span>
            <strong>${escapeHtml(child.name)}</strong>
            <span class="child-card__amount">CP ${formatAmount(getMetric(data, child.id, "cp"))}</span>
            <span class="child-card__arrow" aria-hidden="true">↗</span>
          </button>`).join("")}</div>` : `<div class="terminal-note"><span class="terminal-note__dot"></span>Ce nœud est au niveau Action. Les montants sont consultables dans les cartes ci-dessus.</div>`}
      </section>
      <div class="detail-columns">
        <section class="detail-section">
          <div class="section-title"><div><p class="eyebrow">Lecture temporelle</p><h3>Historique publié</h3></div><span class="section-count">${getHistory(data, selected.id).length} années</span></div>
          ${renderHistory(data, selected.id)}
        </section>
        <section class="detail-section">
          <div class="section-title"><div><p class="eyebrow">Traçabilité</p><h3>Sources officielles</h3></div><span class="section-count">${getProvenance(data, selected.id).length} source${getProvenance(data, selected.id).length > 1 ? "s" : ""}</span></div>
          ${renderProvenance(data, selected.id)}
        </section>
      </div>
    </article>`;
}

function renderApp(data, state) {
  const release = data.release ?? {};
  const nodes = data.nodes ?? [];
  const selected = getNode(nodes, state.selectedId) ?? nodes[0];
  const selectedId = selected?.id ?? "";
  const sourceLabel = data.mode === "api" ? "API connectée" : "Démonstration locale";

  return `
    <div class="site-shell">
      <header class="site-header">
        <a class="brand" href="./" aria-label="Où va l'argent ? accueil"><span class="brand__mark">O</span><span>Où va l'argent<span class="brand__period">?</span></span></a>
        <div class="header-note"><span class="status-dot"></span>Un explorateur public, sourcé et reproductible</div>
        <a class="header-link" href="https://www.budget.gouv.fr/" target="_blank" rel="noreferrer noopener">Sources publiques <span aria-hidden="true">↗</span></a>
      </header>
      <main>
        <section class="intro-band">
          <div class="intro-copy">
            <p class="eyebrow">Budget général de l'État · ${escapeHtml(release.legal_stage ?? "PLF")} ${escapeHtml(release.fiscal_year ?? "2026")}</p>
            <h1>Suivre un euro,<br /><em>du programme à la source.</em></h1>
            <p class="intro-copy__lede">Explorez les missions, programmes et actions du budget. Chaque montant conserve son contexte et sa provenance.</p>
          </div>
          <div class="release-card">
            <div class="release-card__label"><span class="status-dot status-dot--warm"></span>Release publiée</div>
            <strong>${escapeHtml(release.version ?? "—")}</strong>
            <span>Snapshot ${escapeHtml(String(release.source_snapshot_hash ?? "").slice(0, 12))}…</span>
            <small>Mode : ${escapeHtml(sourceLabel)}</small>
          </div>
        </section>
        <section class="explorer" aria-label="Explorateur budgétaire">
          <div class="explorer-toolbar">
            <div><p class="eyebrow">Explorer</p><h2>La nomenclature budgétaire</h2></div>
            <div class="toolbar-meta"><span>${nodes.length} nœuds indexés</span><span class="toolbar-divider"></span><span>AE / CP séparés</span></div>
          </div>
          <div class="search-wrap">
            <form id="search-form" class="search-form" role="search">
              <span class="search-icon" aria-hidden="true">⌕</span>
              <input id="search-input" name="q" type="search" autocomplete="off" placeholder="Rechercher une mission, un programme, un code…" value="${escapeHtml(state.query)}" aria-label="Rechercher dans la nomenclature" />
              <kbd>⌘ K</kbd>
              <button type="submit">Rechercher</button>
            </form>
            ${renderSearchResults(nodes, state.query, selectedId)}
          </div>
          <div class="explorer-grid">
            <aside class="tree-panel">
              <div class="tree-panel__header"><span>Arbre budgétaire</span><span>2026</span></div>
              <ol class="tree-list">${renderTree(nodes, selectedId)}</ol>
              <div class="tree-panel__footer"><span class="legend-line"></span><span>Cliquez pour inspecter un niveau</span></div>
            </aside>
            ${renderDetail(data, selectedId)}
          </div>
        </section>
        <section class="trust-strip">
          <div><span class="trust-strip__number">01</span><strong>Les chiffres restent déterministes</strong><p>Les montants affichés viennent d'une release publiée, pas d'une génération narrative.</p></div>
          <div><span class="trust-strip__number">02</span><strong>La hiérarchie reste lisible</strong><p>Mission → Programme → Action : trois niveaux, une navigation directe.</p></div>
          <div><span class="trust-strip__number">03</span><strong>La source reste accessible</strong><p>Chaque fact consultable renvoie à son document et à son fragment d'origine.</p></div>
        </section>
      </main>
      <footer class="site-footer"><span>Où va l'argent ?</span><span>Interface de démonstration · données à connecter à l'API de production</span></footer>
    </div>`;
}

export function mountApp(root, data) {
  if (!root) throw new Error("A frontend root element is required");
  const state = {
    query: "",
    selectedId: data.nodes?.find((node) => node.node_type === "mission")?.id ?? data.nodes?.[0]?.id ?? null,
  };

  const render = (focusSearch = false) => {
    root.innerHTML = renderApp(data, state);
    if (focusSearch) {
      const input = root.querySelector("#search-input");
      input?.focus();
      input?.setSelectionRange(input.value.length, input.value.length);
    }
  };

  root.addEventListener("click", (event) => {
    const target = event.target.closest("[data-node-id]");
    if (!target) return;
    event.preventDefault();
    state.selectedId = target.dataset.nodeId;
    state.query = "";
    render();
  });

  root.addEventListener("input", (event) => {
    if (event.target.id !== "search-input") return;
    state.query = event.target.value;
    render(true);
  });

  root.addEventListener("submit", (event) => {
    if (event.target.id !== "search-form") return;
    event.preventDefault();
    const first = rankSearchResults(data.nodes ?? [], state.query)[0];
    if (first) {
      state.selectedId = first.id;
      state.query = "";
      render();
    }
  });

  render();
  return {
    getState: () => ({ ...state }),
    selectNode: (id) => {
      if (!getNode(data.nodes ?? [], id)) return;
      state.selectedId = id;
      state.query = "";
      render();
    },
  };
}

export function nodeTypeLabel(nodeType) {
  return TYPE_LABELS[nodeType] ?? nodeType;
}
