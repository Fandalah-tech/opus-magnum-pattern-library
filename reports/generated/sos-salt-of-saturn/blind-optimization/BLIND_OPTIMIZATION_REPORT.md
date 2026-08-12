# Sweet Vinegar of Saturn — blind metric search

No community record values or leaderboard solutions were consulted during this search. The starting architecture is the previously documented corpus-derived mechanism, rebuilt by the project generator.

## Event metrics

1. Cost > Area > Cycles
2. Rate
3. Instructions > Cost
4. Area > Cost
5. Cycles
6. Sum4 = Cost + Cycles + Area + Instructions

## Best candidates found

| Category | Cost | Cycles | Area | Instructions | Rate | Sum4 |
|---|---:|---:|---:|---:|---:|---:|
| Cost > Area > Cycles | 145 | 95 | 84 | 19 | 8 | 343 |
| Rate | 145 | 95 | 84 | 19 | 8 | 343 |
| Instructions > Cost | 145 | 295 | 218 | 18 | 48 | 676 |
| Area > Cost | 145 | 95 | 84 | 19 | 8 | 343 |
| Cycles | 145 | 95 | 84 | 19 | 8 | 343 |
| Sum4 | 145 | 95 | 84 | 19 | 8 | 343 |

`Rate` is the repeating output interval reported by OMSim (`output intervals: 55 [8]`).

## Search coverage

- independent phase shifts for all four arms;
- paired phase shifts between the delayed output arm and every manufacturing arm;
- greedy instruction deletion from the best phase candidates;
- translations of six logical subassemblies across a 17×17 axial window;
- simple part deletion and arm type/length substitutions;
- local piston replacements for the rail transport arm.

All retained candidates are independently accepted by OMSim. These are the best solutions found within the searched neighborhoods; they are not claimed as mathematical global optima.
