# OMSIM GitHub-to-PC bridge

This bridge lets a trusted GitHub commit ask a dedicated Windows self-hosted runner to execute one approved OMSIM operation and commit the result back to the repository.

## Security model

- The workflow runs only on pushes to `feature/disjoint-solver-readiness` or by manual dispatch.
- Push-triggered jobs are accepted only when `github.actor` is `Fandalah-tech`.
- The runner must have the custom label `omsim`.
- Task files cannot contain shell commands.
- `tools/om_worker.py` accepts only a fixed operation allow-list.
- Task paths, IDs, timeouts, and optional pytest targets are validated.
- Pull requests and forks never trigger the self-hosted runner.

The runner should still run under a normal Windows account without administrator rights and in a dedicated directory.

## Task format

Create one JSON file under `.om-bridge/tasks/pending/`:

```json
{
  "id": "rotor-structure-001",
  "operation": "search_rotor_structure",
  "timeout_seconds": 1800,
  "notes": "Continue the structure-only search from the A42 confined seed."
}
```

Approved operations:

- `run_tests`
- `run_reference_regression`
- `search_rotor_structure`
- `report_rotor_prefix`
- `report_rotor_macros`

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

The runner writes:

```text
.om-bridge/results/<task-id>/
  summary.json
  stdout.txt
  stderr.txt
```

It then commits those files to `feature/disjoint-solver-readiness`. Result commits do not retrigger the worker because the workflow watches only pending task JSON files.

## Register the Windows PC

1. Open the repository on GitHub.
2. Go to **Settings → Actions → Runners → New self-hosted runner**.
3. Select **Windows** and **x64**.
4. On the PC, open PowerShell in a new dedicated folder, for example `C:\GitHubRunners\OMSIM`.
5. Run the download and configuration commands displayed by GitHub. The registration token is temporary; do not post it in chat or commit it.
6. During configuration:
   - runner group: press Enter for Default;
   - runner name: `Bruno-OMSIM`;
   - additional labels: `omsim`;
   - work folder: `_work`.
7. First run interactively with `./run.cmd`.
8. Once the test job succeeds, stop it with Ctrl+C and install it as a Windows service from an Administrator PowerShell using the service command supplied with the runner package.

The runner makes outbound HTTPS connections to GitHub. No router port, remote desktop access, or inbound firewall rule is required.

## Emergency stop

Stop the runner service or remove the runner from **Settings → Actions → Runners**. Pending tasks will remain queued and cannot execute on another runner because of the `omsim` label.
