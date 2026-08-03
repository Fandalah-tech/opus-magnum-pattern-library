# Private reference fixtures

Campaign puzzle and solution binaries are not committed to the public repository. They are stored in a private Google Cloud Storage bucket and accessed by GitHub Actions through Workload Identity Federation.

## Bucket

- Project: `opus-magnum-codex`
- Bucket: `gs://opus-magnum-codex-private-fixtures`
- Object: `campaign/p007-p015.zip`
- Region: `northamerica-northeast1`
- Public access prevention: enforced
- Uniform bucket-level access: enabled

## Create the bucket

```bash
gcloud storage buckets create gs://opus-magnum-codex-private-fixtures \
  --project=opus-magnum-codex \
  --location=northamerica-northeast1 \
  --uniform-bucket-level-access

gcloud storage buckets update gs://opus-magnum-codex-private-fixtures \
  --public-access-prevention=enforced
```

## Grant the GitHub deployer read-only access

```bash
gcloud storage buckets add-iam-policy-binding \
  gs://opus-magnum-codex-private-fixtures \
  --member=serviceAccount:opus-github-deployer@opus-magnum-codex.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer
```

## Upload the private archive

```bash
gcloud storage cp opus-campaign-p007-p015-private-fixtures.zip \
  gs://opus-magnum-codex-private-fixtures/campaign/p007-p015.zip
```

## Verify

```bash
gcloud storage ls -L \
  gs://opus-magnum-codex-private-fixtures/campaign/p007-p015.zip
```

The workflow `.github/workflows/reference-regression.yml` downloads this object, verifies every SHA-256 and file size against the metadata-only manifest, runs the parsers, calls the deployed omsim service, checks metrics when returned, and uploads a JSON report as a GitHub Actions artifact.
