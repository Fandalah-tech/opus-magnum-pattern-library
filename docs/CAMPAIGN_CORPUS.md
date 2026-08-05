# Campaign corpus

The corpus importer combines two public sources:

- campaign puzzle files from `gtw123/OpusSolver`;
- categorized record solutions from the community leaderboard at `zlbb.faendir.com`.

Binary puzzle and solution files are stored under `.datasets/` and are not committed. The generated `index.json` records source URLs, categories, sizes and SHA-256 hashes.

## Import puzzles only

```bash
python tools/import_campaign_corpus.py --puzzles-only
```

## Import puzzles and ZLBB records

ZLBB is a JavaScript application, so the importer uses a real headless browser and the site's Download controls.

```bash
python -m pip install playwright
playwright install chromium
python tools/import_campaign_corpus.py --limit-per-puzzle 3
```

Omit `--limit-per-puzzle` to download every record shown for every campaign puzzle.

## Output

```text
.datasets/campaign-corpus/
  index.json
  puzzles/<chapter>/*.puzzle
  solutions/zlbb/<puzzle-id>/*.solution
```

The next processing stage should parse each downloaded solution, validate it with OMSim, extract its metrics and part inventory, then select a coverage-oriented regression set rather than blindly retaining every near-duplicate record.
