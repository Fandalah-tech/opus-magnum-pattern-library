# Adaptateur omsim

Première couche d'intégration entre omsim et le schéma canonique `validation-result.schema.json`.

## Utilisation

```bash
python tools/omsim_adapter/validate.py \
  path/to/puzzle.puzzle \
  path/to/solution.solution \
  --omsim path/to/omsim
```

Le résultat JSON est écrit sur la sortie standard. L'option `--output result.json` permet de l'enregistrer dans un fichier.

## Tests

```bash
python -m unittest tools.omsim_adapter.tests.test_validate -v
```

## Portée actuelle

- exécute la CLI omsim;
- extrait coût, instructions, cycles et aire;
- normalise les échecs;
- conserve le cycle et les coordonnées lorsqu'ils apparaissent dans l'erreur;
- retourne un code de sortie nul seulement pour une solution valide avec métriques complètes.

La prochaine version remplacera progressivement le parsing textuel par l'API FFI de `libverify`.
