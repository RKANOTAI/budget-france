# Déploiement de l’API publique sur Railway

Le backend est déployable depuis ce dépôt avec `Dockerfile` et `railway.json`.
Le conteneur applique les migrations Alembic avant de démarrer Uvicorn.

## 1. Créer les services

1. Créer un projet Railway depuis le dépôt GitHub `RKANOTAI/budget-france`.
2. Ajouter un service PostgreSQL Railway.
3. Vérifier que le service API utilise le `Dockerfile` du dépôt.
4. Définir la référence Railway de `DATABASE_URL` vers le service PostgreSQL.
5. Définir `CORS_ORIGINS` à :

   ```text
   https://rkanotai.github.io,http://localhost:4173
   ```

`DATABASE_URL` est une configuration privée du service. Elle ne doit jamais être copiée
à la place de `frontend/config.js` ni commitée.

## 2. Vérifier le service

Après le premier déploiement, vérifier les URLs suivantes sur le domaine public Railway :

- `/healthz` doit retourner `{"status":"ok"}` ;
- `/readyz` doit retourner `{"status":"ready"}` quand PostgreSQL est accessible ;
- `/docs` doit afficher la documentation OpenAPI ;
- `/api/v1/tree?fiscal_year=2026&legal_stage=PLF` doit retourner une release publiée.

Une base vide peut répondre à `/healthz` mais ne contient aucune release. Dans ce cas,
le endpoint `/api/v1/tree` retourne une erreur de release indisponible jusqu’au chargement
des données officielles.

## 3. Charger les données officielles

Depuis un shell du service API, lancer une ingestion à la fois :

```bash
python -m scripts.ingest_budget --fiscal-year 2026
python -m scripts.ingest_budget --fiscal-year 2025
```

Le chargeur :

- télécharge le classeur officiel `budget.gouv.fr` ;
- conserve le hash SHA-256 du snapshot ;
- filtre le Budget général (`Type Mission = BG`) ;
- agrège AE et CP de l’Action vers le Programme puis la Mission ;
- crée les fragments et liens de provenance ;
- valide la release avant sa publication atomique.

Si `budget.gouv.fr` présente une page de blocage au service Railway, ne pas publier une
release partielle : récupérer le classeur depuis la source officielle, vérifier son hash,
puis relancer avec `--url` et `--version` explicites.

## 4. Brancher GitHub Pages

Une fois le domaine Railway connu, modifier uniquement la valeur publique de :

```js
// frontend/config.js
globalThis.__BUDGET_API_BASE_URL__ = "https://<domaine-railway>";
```

Cette valeur ne doit contenir aucun token ou secret. Le frontend appelle alors :

- `GET /api/v1/tree` pour l’arbre Mission → Programme → Action ;
- `GET /api/v1/search` pour la recherche déterministe ;
- `GET /api/v1/nodes/{id}` pour le détail, l’historique et la provenance.

Sans URL configurée, le site reste explicitement en mode démonstration locale. Avec une
URL configurée mais une API indisponible, il affiche une erreur live au lieu de masquer
l’échec avec des données de démonstration.
