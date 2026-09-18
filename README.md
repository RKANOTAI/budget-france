# Où va l'argent ?

Monorepo du MVP d'exploration traçable du budget général de l'État français pour 2025 et 2026.

Le cahier des charges de référence est conservé dans [`docs/product-spec.md`](docs/product-spec.md).

## Invariants produit

- PostgreSQL est la source de vérité.
- Aucun montant n'est publiable sans provenance officielle exploitable.
- Les anomalies critiques passent en `FLAG_REVIEW` et bloquent la publication.
- Le LLM explique des données récupérées ; il ne génère et ne modifie jamais les montants.

Les commandes de développement seront documentées après la mise en place du socle technique.
