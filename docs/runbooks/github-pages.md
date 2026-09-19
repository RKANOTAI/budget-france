# Publier le frontend sur GitHub Pages

Le workflow `.github/workflows/pages.yml` publie le contenu statique de `frontend/` sur chaque push vers `main`.

## Configuration GitHub à faire une fois

1. Ouvrir **Settings → Actions → General** et laisser les GitHub Actions activées.
2. Ouvrir **Settings → Pages**.
3. Dans **Build and deployment → Source**, choisir **GitHub Actions**.
4. Vérifier que le dépôt est public, ou que le plan GitHub autorise Pages pour un dépôt privé.
5. Fusionner ce lot sur `main`. Le workflow affichera ensuite l'URL dans l'environnement `github-pages` et dans l'onglet **Actions**.

Aucun secret GitHub n'est nécessaire pour cette publication : le workflow utilise le jeton éphémère fourni par GitHub avec les permissions `pages: write` et `id-token: write`.

## URL attendue

Pour un dépôt `OWNER/budget-france`, l'URL de projet sera :

```text
https://OWNER.github.io/budget-france/
```

## Intégration API

La page actuelle est un frontend statique autonome avec des données de démonstration explicitement indiquées dans l'interface. GitHub Pages ne peut pas héberger FastAPI ni PostgreSQL. Pour passer en production, le frontend devra appeler l'API publique via HTTPS et l'API devra autoriser l'origine GitHub Pages par CORS.
