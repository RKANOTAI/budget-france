# ADR 0001 — PostgreSQL et releases immuables

- **Statut :** accepté
- **Décision :** PostgreSQL est la source de vérité des faits budgétaires et
  des relations publiées. Une release publiée est immuable ; toute correction,
  nouvelle collecte ou nouvelle nomenclature produit une nouvelle release.
- **Conséquences :** l'API et les applications lisent une release identifiée.
  Les fichiers de `storage/`, les sorties d'agent et les explications LLM ne
  peuvent pas remplacer un fait PostgreSQL. Les historiques restent
  auditables et une publication peut être reconstruite depuis ses sources.
