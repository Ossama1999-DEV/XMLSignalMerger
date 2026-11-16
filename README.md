# Houston XML Signal Merger (Tkinter)

Outil destiné aux référentiels `layers.xml` et `signals_okrp_data.xml`.

## Démarrage

Python 3.9+ avec Tkinter (aucune dépendance `pip`).

Sur Debian : `sudo apt install python3-tk` puis `python3 app.py`.

Sur Windows : double-cliquer `app.py` ou lancer `py app.py`.

## Utilisation

1. Choisir un dossier contenant les nouveaux fichiers XML de `feature_type` (sous-dossiers inclus).
2. Sélectionner le `layers.xml` et le `signals_okrp_data.xml` à mettre à jour.
3. Cliquer **Analyser les XML** : prévisualisation par ligne, des ajouts nécessaires à chaque référentiel.
4. Sélectionner/désélectionner les types puis **Appliquer et sauvegarder**.
5. Deux sauvegardes `*.backup_YYYYMMDD_HHMMSS_*` sont générées dans les dossiers des fichiers cibles.

## Règles de fusion

- `CompositeSignal_*` → `layer id=320` + `composite_signal_types`.
- `Signal_US_WS_*` → `layer id=351` + `basic_signal_types`.
- Autres `Signal_*` → `layer id=352` + `basic_signal_types`.
- Si la référence existe déjà dans l'un des fichiers, elle n'est pas dupliquée.
- Les types inconnus sont ignorés. Les conflits de catégorie sont signalés.
- XML source invalide : fichier ignoré et erreur indiquée.
- Le contenu des XML *existants* est préservé textuellement (commentaires, ordre, attributs, formatage, entrées et doublons antérieurs). Seules de nouvelles entrées sont insérées.
- `feature_type` est une définition 3D. Pour la bibliothèque OKRP, un `basic_signal_type` minimal conforme à la structure existante est créé, sans importer arbitrairement tous les états/propriétés 3D. Les aspects fonctionnels spécifiques devront être validés avant utilisation en simulation.
- Le programme ne crée PAS les fichiers de définition 3D, `.node`, les icônes, ou les règles de comportement du simulateur. Il ne valide pas la disponibilité des ressources externes.
- La modification s'effectue directement après confirmation; la sauvegarde permet de revenir en arrière.

## Note importante

Dans les fichiers fournis, `CompositeSignal_WSSCA_mat_metal_2500cm` existe déjà dans `layers.xml`, mais pas encore dans `signals_okrp_data.xml`. Le programme sait compléter seulement ce dernier fichier. Le panneau `Signal_US_WS_SchoolCrossingAhead` n'est initialement présent dans aucun des deux référentiels.
