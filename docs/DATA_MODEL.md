# Modèle de données — Pattern v0.1

Le MVP utilise un modèle volontairement simple, compatible avec une migration future vers des fichiers JSON individuels ou une base orientée graphe.

## Entité Pattern

| Champ | Type | Rôle |
|---|---|---|
| `id` | string | Identifiant stable, unique et lisible |
| `name` | string | Nom humain du pattern |
| `category` | string | Famille fonctionnelle principale |
| `summary` | string | Résumé court pour la carte |
| `description` | string | Explication détaillée |
| `metrics.cost` | number | Coût de l’implémentation documentée |
| `metrics.area` | number | Area de l’implémentation documentée |
| `metrics.cycles` | number | Cycles de l’implémentation documentée |
| `goals` | string[] | Métriques ou objectifs privilégiés |
| `tags` | string[] | Vocabulaire transversal de recherche |
| `requirements` | string[] | Composants ou conditions nécessaires |
| `relations` | string[] | IDs des patterns reliés |
| `visual` | string | Clé du visuel SVG associé |
| `status` | string | `concept`, `prototype`, `validated` ou `deprecated` |

## Principes

1. Un pattern décrit une mécanique réutilisable, pas nécessairement une solution complète.
2. Les métriques appartiennent à une implémentation précise et ne constituent pas une propriété absolue du concept.
3. Les relations sont stockées dès le MVP afin de préparer le graphe de connaissances.
4. Les identifiants ne doivent jamais dépendre du nom affiché.
5. Toute donnée incertaine doit être marquée comme telle plutôt que présentée comme validée.

## Évolution prévue

Le modèle sera ensuite séparé en trois niveaux :

- `concept` : principe abstrait ;
- `pattern` : architecture réutilisable ;
- `implementation` : réalisation concrète avec métriques, puzzle, auteur et preuve visuelle.

Cette séparation permettra de comparer plusieurs implémentations d’un même pattern sans confondre le mécanisme avec ses performances.