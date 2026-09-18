# ADR 0002 — Sérialisation JSON des décimaux

- **Statut :** accepté
- **Décision :** les montants sont des `Decimal` en Python et sont sérialisés
  en chaînes décimales JSON. AE et CP restent des champs séparés.
- **Motif :** JSON ne possède pas de type décimal exact et les flottants
  risquent de modifier la valeur affichée ou comparée. La représentation en
  chaîne préserve la précision et rend le contrat explicite ; les JSON Schema
  publiés décrivent donc ces champs comme des chaînes.
