# Architecture L0

## Topologie du monorepo

La topologie cible est imposée par le cahier des charges :

```text
budget-france/
├── apps/
│   ├── web/                 # site public Next.js
│   └── admin/               # opérations internes
├── api/                     # frontière HTTP FastAPI et contrats exposés
├── agents/                  # orchestration Hermes et agents spécialisés
├── pipelines/               # découverte, téléchargement, parsing, normalisation
├── database/                # schéma PostgreSQL, migrations et contrôles
├── prompts/                 # prompts versionnés et non secrets
├── storage/                 # fichiers bruts/traités, jamais la source canonique
├── tests/                   # tests unitaires, contrats et intégration
└── docs/                    # spécifications, décisions et sources
```

Le lot L0 crée uniquement les contrats Python, leur export JSON Schema, la
frontière `api/` et la documentation. Il ne crée aucune application, connexion
DB, pipeline, agent, stockage ou migration.

## Frontières

- **`apps/web` et `apps/admin`** consomment l'API et les contrats générés ; ils
  n'accèdent jamais directement à PostgreSQL, aux fichiers bruts ou au LLM.
- **`api`** valide les entrées/sorties avec Pydantic et lit des releases
  publiées. Il ne calcule pas de faits budgétaires à partir d'une explication.
- **`pipelines` et `agents`** découvrent, téléchargent, parsèrent et valident
  les sources. Leurs écritures de données passent par une ingestion contrôlée
  et produisent une nouvelle release.
- **`database`** possède le schéma, les contraintes d'intégrité et les
  migrations. PostgreSQL est la source de vérité des faits budgétaires.
- **`storage`** conserve les artefacts bruts et leurs métadonnées de collecte ;
  un fichier n'est pas une valeur publiée sans enregistrement PostgreSQL et
  provenance exploitable.
- **`prompts`** contient des instructions versionnées. Un LLM peut classer,
  rechercher ou expliquer des passages, mais ne peut ni créer ni modifier un
  montant canonique.
- **`docs` et `tests`** décrivent et contrôlent les invariants sans devenir une
  source de chiffres.

## Invariants de publication

1. Les années supportées par le MVP sont 2025 et 2026 ; l'année publiée est
   portée uniquement par `release.fiscal_year`. L'arbre est
   Mission → Programme → Action. Un `TreeResponse` peut être un sous-arbre de
   drill-down ; ses enfants restent des Programmes sous une Mission, des
   Actions sous un Programme, et une Action n'a aucun enfant. `NodeDetail`
   exige une release et applique les mêmes contrôles à son parent et ses
   enfants. Le runtime contrôle aussi l'unicité des UUID de nœud dans chaque
   `TreeResponse` ; ce contrôle global n'est pas exprimable en JSON Schema.
2. AE et CP sont deux faits distincts ; au moins l'un des deux est requis.
   Les montants utilisent `Decimal` en Python et des chaînes JSON décimales
   canoniques sans exposant. Les tableaux JSON des contrats sont reconstruits
   en tuples immuables sans désactiver `strict=True`.
3. Les identifiants de release, de nœud, de fragment source et de requête sont
   des UUID. Chaque montant publié possède une `SourceRef` complète :
   `source_fragment_id`, `url` HTTP(S), `sha256`, `locator`, `legal_stage`
   (PLF/LFI), `document_type`, `retrieved_at` UTC et `source_version` ; la date
   de publication reste optionnelle. Une release porte obligatoirement
   `source_snapshot_hash` et `released_at` UTC.
4. Une explication est du texte sourcé. Elle n'expose aucun champ numérique
   canonique et exige `summary`, `what_it_funds`, `main_changes`,
   `limitations` et au moins un `source_fragment_id`. Une absence de contexte
   est décrite dans `limitations`, jamais par omission du champ.
5. Chaque publication est identifiée par une release immuable. Une correction
   produit une nouvelle release ; elle n'écrase pas silencieusement
   l'historique.
6. Les anomalies `error` et `critical` doivent être bloquantes ; elles ne
   peuvent pas être publiées automatiquement.
7. Les enveloppes API exportées sont concrètes et typées (`TreeApiResponse`,
   `NodeApiResponse`, `SearchApiResponse`). Le générique Python reste
   disponible pour l'implémentation, mais aucun schéma générique nu n'est
   exporté.
8. Une comparaison PLF/LFI n'est jamais implicite : l'état juridique et la
   version de chaque document restent visibles dans les contrats et la
   provenance.
9. Chaque `SearchHit` porte `match_kind` (`exact`, `lexical` ou `semantic`).
   Un résultat `semantic` est une reconstruction et ne doit pas être présenté
   comme un résultat exact.

## Contrats L0

Les modèles Pydantic de `packages/contracts/models.py` sont stricts, immuables
et interdisent les champs supplémentaires. `api/contracts.py` est le point
d'import côté API. `scripts/export_contracts.py` produit les JSON Schema
versionnés dans `packages/contracts/schemas/`; `--check` échoue si un fichier
est manquant, modifié ou inattendu.
