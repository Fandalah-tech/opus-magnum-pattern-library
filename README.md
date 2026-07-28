# Opus Magnus Pattern Library

Une base de connaissances ouverte consacrée aux mécanismes réutilisables, aux architectures et aux heuristiques d’optimisation dans **Opus Magnum**.

## MVP actuel

La branche `feature/mvp-pattern-explorer` contient un premier explorateur web statique :

- catalogue responsive ;
- recherche plein texte ;
- filtres par catégorie et objectif ;
- fiches détaillées ;
- relations entre patterns ;
- visuels SVG originaux ;
- modèle de données documenté.

## Lancer localement

Aucune compilation ni dépendance n’est requise.

```bash
python -m http.server 8000
```

Puis ouvrir `http://localhost:8000`.

Le site peut également être publié directement avec GitHub Pages.

## Structure

```text
assets/
  css/style.css
  js/app.js
data/
  patterns.js
docs/
  DATA_MODEL.md
  VISION.md
index.html
```

## Direction à long terme

1. Formaliser les concepts et primitives d’Opus Magnum.
2. Documenter des patterns et leurs implémentations concrètes.
3. Construire un graphe de connaissances navigable.
4. Importer et analyser des fichiers `.solution`.
5. Développer des heuristiques, des bornes théoriques et un futur solveur assisté.

Les données d’exemple du MVP sont des prototypes de structure et ne doivent pas encore être considérées comme des références de performance validées.