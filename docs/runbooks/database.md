# Runbook base de données

## Pré-requis

Le lot utilise PostgreSQL 17 et pgvector. SQLite n'est pas supporté. Une
installation PostgreSQL en espace utilisateur suffit ; Docker n'est pas
nécessaire.

```bash
export PGROOT=/opt/data/cache/spikes/pg17-local/replay/root
export PATH="$PGROOT/usr/lib/postgresql/17/bin:$PATH"
export LD_LIBRARY_PATH="$PGROOT/usr/lib/x86_64-linux-gnu"
uv sync
```

Pour une base externe de test, fournir `TEST_DATABASE_URL` avec
`BUDGET_FRANCE_ALLOW_EXTERNAL_TEST_DATABASE=1`. Le nom de base doit être
`budget_france_test_<token>` afin de signaler une base jetable isolée. Le helper
refuse `DATABASE_URL` ambiante pour éviter de détruire une base applicative. Pour
les migrations applicatives, Alembic consomme et valide `DATABASE_URL` lui-même.
Le helper convertit `postgresql://` en URL SQLAlchemy `postgresql+psycopg://`.

## Migrations

Depuis la racine du dépôt :

```bash
uv run alembic -c database/alembic.ini upgrade head
uv run alembic -c database/alembic.ini downgrade base
```

Le runner de test applique les mêmes migrations Alembic. L'upgrade active les
extensions `pgcrypto` et `vector`, considérées comme infrastructure partagée.
Le downgrade supprime uniquement les fonctions, triggers, tables et index du lot;
il laisse ces extensions en place et refuse de supprimer une table référencée
par un objet externe.

Les contraintes de base valident la forme des URL, des SHA-256, des années et
états juridiques, ainsi que les propriétaires locaux. Elles ne peuvent pas
prouver que l'URL distante est joignable ni comparer le hash aux octets distants;
la collecte et l'ingestion doivent effectuer ces vérifications avant insertion.

## Vérifications de publication

Les écritures d'ingestion restent dans une release `draft`. Les montants AE et
CP sont des lignes distinctes dans `budget_amounts`; une ligne doit être liée à
un fragment via `amount_source_fragments`. Les anomalies `error` et `critical`
doivent être `blocked=true`.

Le chemin recommandé est :

```sql
SELECT budget_validate_release(:release_id, :validator);
SELECT budget_publish_release(:release_id);
```

Ces fonctions sont appelées par `database.repository.ReleaseRepository` et
n'acceptent pas une release sans montant, provenance, arbre valide,
validation passée ou sans absence d'anomalie bloquante. La seconde fonction
met à jour le pointeur `(fiscal_year, legal_stage)` atomiquement.

## Tests d'intégration

```bash
uv run pytest -q tests/database
uv run python scripts/postgres_test_server.py --pgroot "$PGROOT"
```

Sans URL externe, `temporary_postgres()` crée un cluster temporaire, choisit un
port libre, utilise des sockets Unix dans le répertoire temporaire et détruit
le cluster à la fin du contexte. Avec une URL de test explicitement marquée, le
helper valide l'isolement du nom de base, affiche uniquement une URL sans
identifiants et ne démarre ni n'arrête la base fournie.

## Diagnostic rapide

- `vector` manquant : vérifier que la base cible expose pgvector 0.8 ou plus
  récent, puis relancer l'upgrade.
- échec d'une publication : lire l'anomalie PostgreSQL et corriger les données
  dans une nouvelle release ; ne pas modifier une release publiée.
- échec du serveur local : vérifier `PGROOT`, les binaires `initdb`, `pg_ctl`,
  `psql` et la variable `LD_LIBRARY_PATH`.
