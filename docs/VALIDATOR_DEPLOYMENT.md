# Validator Deployment

## Recommended topology

Keep the existing Vercel site as the frontend. Host the validator as a separate Linux container service because it must compile and execute a native C binary and may later launch .NET-based solvers.

```text
Vercel frontend
    -> HTTPS validator API
        -> omsim native binary
        -> later: OpusSolver worker
```

## Local build

From the repository root:

```bash
docker build \
  -f services/validator/Dockerfile \
  --build-arg OMSIM_COMMIT=<PINNED_COMMIT_SHA> \
  -t opus-validator .

docker run --rm -p 8080:8080 opus-validator
```

Health check:

```bash
curl http://localhost:8080/health
```

Validation request:

```bash
curl -X POST http://localhost:8080/validate \
  -F "puzzle=@example.puzzle" \
  -F "solution=@example.solution"
```

## Hosting options

### Preferred initial option: managed container

Use Render, Railway, Fly.io or Google Cloud Run. These platforms can build the Dockerfile directly from GitHub and expose the service over HTTPS.

Advantages:

- no server administration;
- automatic rebuilds from a selected branch;
- native binaries supported;
- easy logs and rollback;
- suitable for future .NET worker containers.

### Own web server

A Linux VPS is also suitable when Docker is available. Minimum practical starting point:

- Linux x86-64;
- Docker Engine and Compose;
- 1 vCPU;
- 1 GB RAM;
- HTTPS reverse proxy such as Caddy or nginx;
- a dedicated subdomain such as `validator.example.com`.

Do not expose the omsim executable directly. Expose only the restricted API container.

## Security requirements

Before public use:

- enforce upload-size limits;
- keep request timeouts;
- run as a non-root user;
- use temporary isolated directories;
- delete uploaded files after each request;
- restrict CORS to the production frontend;
- add rate limiting;
- avoid logging uploaded binary contents;
- pin omsim to an exact commit SHA;
- rebuild deliberately when updating upstream dependencies.

The initial service already implements size limits, timeouts, temporary directories and a non-root container user. CORS, authentication and rate limiting remain deployment tasks.

## Vercel integration

The frontend only needs an environment variable such as:

```text
OPUS_VALIDATOR_API_URL=https://validator.example.com
```

Vercel should not compile or execute omsim itself. Its role remains static/frontend hosting and lightweight proxying if required.

## Future OpusSolver deployment

OpusSolver should run in a separate worker container with .NET 8, `lp_solve` and omsim/libverify. Solver jobs may exceed normal HTTP request limits, so they should eventually use a job queue:

```text
POST /solver-jobs
GET /solver-jobs/{id}
```

This separation prevents expensive generation jobs from blocking validation requests.
