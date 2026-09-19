# ADR 0003 — PostgreSQL 17, pgvector et modèle de release

- **Statut :** accepté
- **Décision :** PostgreSQL 17 est la seule source de vérité du lot data. La
  migration Alembic `0001_postgresql_provenance` active `vector`, crée les
  tables de documents, fragments, releases, arbre budgétaire, montants,
  anomalies, validations, runs d'ingestion et pointeurs de publication.
- **Release :** une release suit `draft → validated → published` ou
  `rejected`. La fonction PostgreSQL `budget_publish_release` verrouille la
  release et le couple année/état juridique dans la même transaction avant de
  mettre à jour `published_releases`.
- **Provenance :** chaque ligne AE/CP est une ligne séparée et doit être liée à
  au moins un `source_fragment`. Le trigger vérifie que l'année et l'état
  juridique du document correspondent à la release et enregistre le document
  dans `release_source_documents`.
- **Immutabilité :** après publication, les facts, nœuds, liens de provenance,
  validations, anomalies et sources utilisés par la release sont refusés par
  des triggers. Une correction produit une nouvelle release.
- **Recherche :** les nœuds et fragments portent une colonne `tsvector`
  générée avec la configuration française et un index GIN. Les embeddings sont
  stockés dans `fragment_embeddings` avec `vector(1536)` et un index HNSW
  cosine. La dimension est un contrat de stockage ; tout modèle d'une autre
  dimension doit être projeté ou stocké dans une évolution de schéma dédiée.
- **Tests :** les tests démarrent un PostgreSQL 17 local en espace utilisateur
  via `scripts/postgres_test_server.py`. Une base externe n'est acceptée que par
  `TEST_DATABASE_URL` avec `BUDGET_FRANCE_ALLOW_EXTERNAL_TEST_DATABASE=1` et un
  nom `budget_france_test_<token>` isolé ; `DATABASE_URL` ambiante est refusée.
  Docker et SQLite ne font pas partie du chemin de test.

Les données budgétaires ne sont pas déduites d'une valeur par défaut :
absence d'une métrique AE ou CP signifie absence de ligne, et non zéro.
