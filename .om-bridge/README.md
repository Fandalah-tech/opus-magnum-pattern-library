# OMSIM GitHub-to-PC bridge

This bridge now uses the **OM User Agent** running inside the signed-in Windows session as the canonical queue consumer. The previous GitHub Actions self-hosted runner is retained only as historical infrastructure and is no longer triggered automatically by pending tasks.

## Runtime architecture

1. Trusted changes are committed to `feature/disjoint-solver-readiness`.
2. Approved task JSON files are placed under `.om-bridge/tasks/pending/`.
3. The OM User Agent periodically fetches/pulls the research branch.
4. It selects the highest-priority pending task, then the oldest task when priorities tie.
5. `tools/om_worker.py` executes one allow-listed operation with the repository as `PYTHONPATH`.
6. The agent constrains the worker to the configured CPU share and below-normal process priority.
7. Results are written under `.om-bridge/results/<task-id>/` and reports under `reports/`.
8. The task is moved to `completed/` when the worker exits successfully or `failed/` otherwise.
9. The agent commits and pushes the result back to the research branch.

The OM Agent also watches the signed-in user's `Documents\My Games\Opus Magnum` tree so local puzzle/solution changes can be incorporated by future operations.

## Resilience

The installer on `main` deploys two scripts into `%LOCALAPPDATA%\OpusMagnumAgent`:

- `om_local_agent.ps1`: queue consumer, Start/Pause/Stop/Status control, repository synchronization, CPU affinity and Opus filesystem watcher.
- `om_agent_watchdog.ps1`: keeps the agent alive in the interactive user session, refreshes the agent script after a crash/restart, and requests Windows to stay awake while the desired state is `running`.

The scheduled task `Opus Magnum User Agent` starts the watchdog at user logon and is configured for automatic restart after watchdog failure. Locking the Windows session does not stop the agent. Manual sleep, shutdown, loss of power or loss of network connectivity can pause processing until Windows resumes.

## Security model

- Task files cannot contain arbitrary shell commands.
- `tools/om_worker.py` accepts only a fixed operation allow-list.
- Task paths, IDs, priorities, timeouts and optional pytest targets are validated.
- The agent executes under the signed-in standard user account, not `SYSTEM` or `NetworkService`.
- Git remains the source of truth; no inbound port, router rule or remote-desktop access is required.
- The legacy `.github/workflows/om-local-worker.yml` is manual-only and does not consume the queue automatically.

## Task format

Create one JSON file under `.om-bridge/tasks/pending/`:

```json
{
  "id": "rotor-structure-001",
  "operation": "search_rotor_structure",
  "priority": 100,
  "timeout_seconds": 1800,
  "notes": "Continue the structure-only search from the A42 confined seed."
}
```

Higher `priority` values execute first. The supported range is `-10000` through `10000`.

`run_tests` may optionally include repository-local test files:

```json
{
  "id": "solver-tests-001",
  "operation": "run_tests",
  "timeout_seconds": 900,
  "pytest_targets": [
    "tests/test_structure_goal.py",
    "tests/test_macro_explorer.py"
  ]
}
```

## Result format

The worker writes:

```text
.om-bridge/results/<task-id>/
  summary.json
  stdout.txt
  stderr.txt
```

The agent then moves the task JSON from `pending/` to `completed/` or `failed/` and commits the queue transition together with generated reports.

## Controls

The installed convenience commands are:

```text
%LOCALAPPDATA%\OpusMagnumAgent\OM Agent - Start.cmd
%LOCALAPPDATA%\OpusMagnumAgent\OM Agent - Pause.cmd
%LOCALAPPDATA%\OpusMagnumAgent\OM Agent - Stop.cmd
%LOCALAPPDATA%\OpusMagnumAgent\OM Agent - Status.cmd
```

`Pause` and `Stop` are persistent desired states, so the watchdog will respect them rather than immediately restarting work.

## Emergency stop

Use `OM Agent - Stop.cmd`. The current worker process tree is terminated by the agent, pending task files remain in Git, and work can later resume with `OM Agent - Start.cmd`.
