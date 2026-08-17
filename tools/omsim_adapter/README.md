# Adaptateur omsim

Couche d'intégration entre omsim/libverify et le schéma canonique `validation-result.schema.json`.

## Utilisation standard

```bash
python tools/omsim_adapter/validate.py \
  path/to/puzzle.puzzle \
  path/to/solution.solution \
  --omsim path/to/omsim
```

Le résultat JSON est écrit sur la sortie standard. L'option `--output result.json` permet de l'enregistrer dans un fichier.

## Métriques libverify arbitraires

L'adaptateur peut aussi évaluer directement les métriques exposées par `omsim --metric` :

```bash
python tools/omsim_adapter/validate.py \
  path/to/puzzle.puzzle \
  path/to/solution.solution \
  --omsim path/to/omsim \
  --metric cost \
  --metric cycles \
  --metric area \
  --metric "minimum hexagon"
```

Les quatre métriques standards restent dans `metrics`; les métriques supplémentaires sont conservées dans `extraMetrics`. Cette voie est notamment utilisée par l'objectif Critelli BCA, qui classe `minimum hexagon > cycles > area` et reconstruit l'expression publique `default restrictions` à partir de ses métriques primitives.

Le solveur autonome soumet au même oracle les générateurs directs, les architectures complètes apprises et les machines recomposées par fragments. Un générateur direct n'a donc aucune priorité implicite dès qu'une autre famille de candidats est disponible : le gagnant est choisi uniquement par l'objectif demandé.

## Tests

```bash
python -m unittest tools.omsim_adapter.tests.test_validate -v
python -m unittest tests.test_bca -v
```

## Portée actuelle

- exécute la CLI omsim;
- extrait coût, instructions, cycles, aire et taux de sortie;
- accepte une liste arbitraire de métriques libverify;
- normalise les échecs;
- conserve le cycle et les coordonnées lorsqu'ils apparaissent dans l'erreur;
- permet le classement autoritaire du portfolio unifié du solver, y compris Bounding Hexagon;
- retourne un code de sortie nul seulement pour une solution valide avec toutes les métriques demandées.

La prochaine version pourra remplacer progressivement le parsing textuel par l'API FFI de `libverify` sans changer ce contrat.
