# Évaluation technique d'omsim

Statut : audit source complété; exécution native à confirmer dans un environnement avec accès réseau et compilateur C.

## Résultat

omsim est retenu comme oracle de validation initial du projet.

## Capacités confirmées

- lecture de fichiers `.puzzle` et `.solution`;
- simulation et validation;
- calcul natif de `cost`, `instructions`, `cycles` et `area`;
- erreurs de simulation avec cycle et coordonnées hexagonales;
- API FFI dans `verifier.h`;
- création depuis des chemins ou directement depuis des tableaux d'octets;
- limites de cycles configurables;
- métriques exactes et approximatives;
- intervalles de sortie et détection de répétition;
- compilation en exécutable, bibliothèque partagée et WebAssembly.

## Compilation documentée

```bash
make omsim
make run-tests && ./run-tests
make libverify.so
make libverify.wasm
```

Le Makefile utilise un compilateur C11, `libm` et Emscripten uniquement pour la cible WebAssembly.

## Interface CLI retenue

```bash
omsim --puzzle-file puzzle.puzzle solution.solution
```

Sortie nominale :

```text
120g/18i@0 42c/37a@V
```

Cette ligne fournit respectivement coût, instructions, cycles et aire.

## Interface d'intégration recommandée

### Phase 1

Appel de l'exécutable avec `subprocess`, isolation forte et parsing de la sortie standard.

### Phase 2

Utilisation de `libverify` par FFI pour :

- éviter les fichiers temporaires;
- transmettre les fichiers sous forme d'octets;
- récupérer les erreurs structurées;
- demander des métriques additionnelles;
- améliorer les performances des traitements en lot.

### Phase navigateur éventuelle

La cible `libverify.wasm` est officiellement prévue par le Makefile. Elle pourra être évaluée après stabilisation du backend, sans remplacer l'oracle natif au départ.

## Limites connues documentées

- clonage à distance par conduits non implémenté;
- comportement de reset de tracks différent du jeu dans certains cas;
- validation finale dans le jeu à conserver pour les records ou cas limites.

## Licence

Le fichier `COPYING` autorise explicitement l'utilisation libre du logiciel. La formulation n'est pas une licence SPDX standard; la provenance et le texte doivent être conservés lors d'une éventuelle redistribution du code source.

## État du projet

- dépôt public;
- plus de 400 commits;
- suite de tests et tests contre des données de leaderboard;
- activité récente observée en juillet 2026;
- non archivé.

## Vérifications réalisées dans ce bloc

- structure et commandes de compilation inspectées;
- API FFI inspectée;
- format de sortie CLI confirmé dans `main.c`;
- adaptateur CLI créé;
- analyseur de sortie testé localement par trois tests unitaires.

## Vérification encore requise

Le clonage et la compilation réels n'ont pas pu être exécutés dans l'environnement de travail actuel, dont la résolution DNS externe est désactivée. Cette limite est environnementale et non un échec observé d'omsim.
