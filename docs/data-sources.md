# Sources budgétaires vérifiées

## Périmètre et état juridique

Les documents doivent être distingués par leur état juridique avant toute
comparaison :

- **PLF** (*projet de loi de finances*) : prévision/proposition avant le vote ;
- **LFI** (*loi de finances initiale*) : texte adopté et promulgué.

Une valeur PLF n'est donc pas silencieusement comparée à une valeur LFI. La
release, la version du document, son état juridique, sa date de collecte et son
hash restent attachés aux faits.

## Sources 2025

- **PLF 2025 — API CSV** :
  <https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/plf25-depenses-2025-selon-destination/exports/csv?use_labels=false>
  - filtrer `typebudget=BG` pour le budget général ;
  - conserver `Mission`, `Programme`, `Action`, `AE` et `CP` ;
  - lire l'unité directement dans la source et la conserver dans les
    métadonnées de collecte.
- **LFI 2025** :
  <https://www.budget.gouv.fr/documentation/file-download/28970>
- **Nomenclature LFI 2025** :
  <https://www.budget.gouv.fr/documentation/file-download/28964>

## Sources 2026

- **PLF 2026** :
  <https://www.budget.gouv.fr/documentation/file-download/31621>
- **LFI 2026** :
  <https://www.budget.gouv.fr/documentation/file-download/32270>
- **Nomenclature LFI 2026** :
  <https://www.budget.gouv.fr/documentation/file-download/32276>

## Mapping CSV et téléchargements

Pour les exports CSV réels, le mapping des colonnes est explicite :

- `autorisation_engagement` → `AE` ;
- `credit_de_paiement` → `CP`.

Les URLs `file-download` peuvent parfois renvoyer un interstitiel Incapsula au
lieu du document demandé. Le downloader doit donc vérifier le MIME attendu, la
signature du fichier et le hash annoncé avant parsing ou publication, puis
échouer fermé (aucune donnée n'est ingérée si l'une de ces vérifications échoue).

## Définitions et règles de lecture

- Niveaux budgétaires et définitions officielles :
  <https://www.budget.gouv.fr/reperes/lolf/articles/missions-programmes-actions>
- Définitions LOLF des autorisations d'engagement (AE) et crédits de paiement
  (CP) :
  <https://www.legifrance.gouv.fr/loda/article_lc/LEGIARTI000006321027>

Règles d'ingestion et de publication :

1. appliquer le filtre `typebudget=BG` pour l'API CSV ; ne pas mélanger budget
   général et autres périmètres ;
2. conserver les codes de mission, programme et action comme **texte** afin de
   préserver zéros initiaux et conventions de nomenclature ;
3. stocker AE et CP séparément, sans les additionner ni les confondre ;
4. enregistrer explicitement l'état juridique (`PLF` ou `LFI`), l'année, la
   version, la date de collecte et le hash du fichier ou de la réponse ;
5. relever l'unité dans chaque source (et non dans une hypothèse de pipeline) ;
6. conserver une page, section, onglet, ligne ou cellule comme localisateur ;
7. interdire toute comparaison PLF ↔ LFI silencieuse : une comparaison doit
   afficher les deux états, les releases et une éventuelle rupture de
   nomenclature.

## Mission pilote recommandée

La première ingestion verticale recommandée est la mission **« Action
extérieure de l'État »**. Elle permet de valider la chaîne
Mission → Programme → Action, le traitement des codes, la séparation AE/CP,
la provenance par fragment et la distinction PLF/LFI avant extension au reste
du budget général.
