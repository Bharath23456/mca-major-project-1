# CloudNetOps-AI GitHub Actions CI/CD on Google Cloud

## What this pipeline does

The workflow in `.github/workflows/cloudnetops-ci-cd.yml` runs for pull
requests and pushes:

1. Installs the existing Python development dependencies, runs Ruff,
   `pip-audit`, and the repository's pytest suite.
2. Validates Docker Compose, Prometheus, Alertmanager, and the tracked JSON
   configuration.
3. Runs Trivy filesystem checks, builds the existing Dockerfile, and scans the
   resulting image for high and critical findings.
4. On pushes to `PRODUCTION_BRANCH` only, saves that already-scanned image,
   authenticates to Google Cloud with Workload Identity Federation, and pushes
   it to Artifact Registry with the full Git commit SHA as its tag.
5. Connects to the existing VM using IAP and OS Login, authenticates Docker on
   the VM through its attached service account, and runs
   [`deploy-gce.sh`](../scripts/deploy-gce.sh).
6. The script changes only the Compose `app` service, waits for its Docker
   health check and `GET /health/ready`, and retains a local tag for the
   previously deployed image. If deployment or readiness fails, it attempts
   to restore that image, verifies readiness again, prints Compose status and
   app logs, and returns a failing exit code.

Pull requests never authenticate to GCP, publish images, or deploy. Other
branch pushes run the checks and build/scan the image but do not publish or
deploy. No `docker compose down`, volume deletion, environment-file rewrite,
or monitoring-service restart is used.

```text
Pull request or push
        |
        v
pytest + Ruff + pip-audit + Compose/config validation
        |
        v
Trivy filesystem scan -> Docker build -> Trivy image scan
        |
        +---- PR / non-production push: finish without GCP access
        |
        +---- production push: WIF -> Artifact Registry (SHA tag)
                               -> IAP/OS Login -> update app only
                               -> Compose health + /health/ready
                                  | success: finish
                                  + failure: restore prior image, fail run
```

## Repository facts and items that could not be verified remotely

- The GitHub repository currently has `main` and `development` branches.
  `main` is therefore the workflow's documented production-branch choice.
- Existing Compose service names include `app`, `prometheus`,
  `node-exporter`, `blackbox-exporter`, `alertmanager`, and `grafana`. The
  workflow updates only `app`.
- The existing Compose file already has a readiness health check for
  `/health/ready`, binds application/monitoring ports to loopback, and uses
  named volumes. The deployment script leaves the Compose file, `.env`,
  secrets, and volumes untouched.
- The previous GCP workflow named project `cloudnetops-ai-513607`, VM
  `cloudnetops-ai`, and zone `asia-south1-a`; the existing deployment guide
  suggests `/opt/cloudnetops-ai`. Treat these as repository-recorded values,
  not verified live settings. Set the GitHub variables from the actual
  authorized GCP/VM configuration.
- Artifact Registry could not be queried: the project reported that
  `artifactregistry.googleapis.com` is not enabled. The VM description was
  also denied because the current GCP identity lacks `compute.instances.get`.
  No API was enabled and no cloud resource was created or changed. Ask a
  project administrator to inspect the live VM and registry before configuring
  deployment.

## Google Cloud setup

Use an authorized project administrator account for these steps. The commands
below inspect first. They do not run as part of GitHub Actions.

### 1. Confirm or create the Artifact Registry repository

Use the project ID from the actual deployment project. The following example
uses the ID recorded in the old workflow and `asia-south1` as an example
region; confirm both before running commands:

```bash
export PROJECT_ID="cloudnetops-ai-513607"
export REGION="asia-south1"
export REPOSITORY="YOUR_EXISTING_OR_APPROVED_REPOSITORY_NAME"

gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="config.name:artifactregistry.googleapis.com"
gcloud artifacts repositories list --project="$PROJECT_ID" --location=- --quiet
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$REGION" --quiet
```

If the API is disabled, enable it only after confirming the project and
approval:

```bash
gcloud services enable artifactregistry.googleapis.com --project="$PROJECT_ID"
```

If the repository does not exist in the chosen region, create only the
repository you approved (this may incur storage/egress costs):

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --repository-format=docker \
  --description="CloudNetOps-AI application images"
```

Do not create a second repository if an appropriate existing Docker repository
is found.

### 2. Configure Workload Identity Federation for GitHub

Reuse the provider/service account already named by the existing repository
variables if they exist. Inspect its attribute mappings and condition before
changing anything. Do **not** remove, broaden, or replace an existing
condition. The trusted GitHub identity should be limited to this repository
and the configured production branch; only push events should be allowed to
deploy.

If no suitable identity setup exists, an administrator can create a dedicated
deploy service account and pool/provider. Set the following values to your
chosen names:

```bash
export PROJECT_ID="cloudnetops-ai-513607"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" \
  --format='value(projectNumber)')"
export POOL_ID="github-cloudnetops"
export PROVIDER_ID="github-cloudnetops"
export DEPLOY_SA_ID="cloudnetops-github-deploy"
export DEPLOY_SA="${DEPLOY_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
export PRODUCTION_BRANCH="main"
```

Enable the IAM Credentials and Security Token Service APIs only if they are
not already enabled and after approval:

```bash
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com \
  --project="$PROJECT_ID"
```

Create the service account only if it does not already exist:

```bash
gcloud iam service-accounts describe "$DEPLOY_SA" --project="$PROJECT_ID" \
  || gcloud iam service-accounts create "$DEPLOY_SA_ID" \
       --project="$PROJECT_ID" \
       --display-name="CloudNetOps GitHub deployment"
```

Create a pool/provider only if inspection confirms there is no suitable
existing one. These attribute mappings and condition constrain OIDC trust to
the repository and production-branch push:

```bash
gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$PROJECT_ID" \
  --location=global \
  --display-name="GitHub Actions for CloudNetOps-AI"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location=global \
  --workload-identity-pool="$POOL_ID" \
  --display-name="CloudNetOps-AI GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name" \
  --attribute-condition="attribute.repository == 'Bharath23456/mca-major-project-1' && attribute.ref == 'refs/heads/${PRODUCTION_BRANCH}' && attribute.event_name == 'push'"
```

Grant that repository/branch principal permission to impersonate the deploy
service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/Bharath23456/mca-major-project-1"
```

If the production branch changes, update the provider's branch condition
deliberately and keep it branch-specific. The GitHub repository variable alone
cannot override a stricter Google provider condition.

### 3. Grant only the deployment permissions

Grant the GitHub deploy service account Artifact Registry Writer on the
specific repository, not project-wide:

```bash
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/artifactregistry.writer"
```

For IAP/OS Login deployment, grant the deploy identity IAP tunnel access and
OS Login on the existing VM/project. Use instance-level bindings where
available. A viewer/custom read-only role may also be needed for the VM
metadata lookups required by `gcloud compute ssh`; do not grant Owner, Editor,
VM creation, or firewall administration roles:

- `roles/iap.tunnelResourceAccessor`
- `roles/compute.osLogin`
- Read-only permission to inspect the selected VM (at minimum
  `compute.instances.get`; confirm the exact OS Login/IAP command permissions
  for your organization)

The current deployment identity could not be used to inspect the VM in this
environment, so an administrator must verify the VM name/zone, OS Login
configuration, IAP reachability, and the exact bindings before the first
deployment.

Example bindings (review scope with your administrator before applying):

```bash
export VM_NAME="cloudnetops-ai"
export VM_ZONE="asia-south1-a"
gcloud compute instances add-iam-policy-binding "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$VM_ZONE" \
  --member="serviceAccount:${DEPLOY_SA}" --role="roles/compute.osLogin"
gcloud compute instances add-iam-policy-binding "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$VM_ZONE" \
  --member="serviceAccount:${DEPLOY_SA}" --role="roles/iap.tunnelResourceAccessor"
```

`gcloud compute ssh` may also need read-only VM/project metadata permissions.
If an instance-level binding is insufficient, grant the narrowest approved
read-only role or custom role; do not use a broad write role to get around a
permission error.

### 4. Configure the VM's attached service account

Find the service account already attached to the existing VM using an
authorized administrator account:

```bash
gcloud compute instances describe cloudnetops-ai \
  --project="$PROJECT_ID" \
  --zone="asia-south1-a" \
  --format="value(serviceAccounts.email)"
```

Grant the attached account Artifact Registry Reader on the single image
repository:

```bash
export VM_SERVICE_ACCOUNT="ATTACHED_VM_SERVICE_ACCOUNT_EMAIL"
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
  --role="roles/artifactregistry.reader"
```

Verify that the VM's attached service account has an access scope compatible
with Artifact Registry (normally `cloud-platform`). Do not replace the VM's
service account or change its scopes blindly; scope changes may require a
planned VM maintenance operation. Docker uses the VM's attached identity via
`gcloud auth configure-docker`, so no registry password or service-account key
is stored on the VM.

## GitHub repository configuration

Add these **repository variables** under **Settings → Secrets and variables →
Actions → Variables**:

| Variable | Required value |
|---|---|
| `PRODUCTION_BRANCH` | `main` (the current branch choice; change only if intentionally selecting another production branch) |
| `GCP_PROJECT_ID` | GCP project that contains the registry and existing VM; old workflow recorded `cloudnetops-ai-513607` |
| `GCP_REGION` | Artifact Registry location, e.g. `asia-south1` |
| `ARTIFACT_REGISTRY_REPOSITORY` | Existing or explicitly created Docker repository name |
| `GCP_WIF_PROVIDER` | Full provider resource name: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID` |
| `GCP_SERVICE_ACCOUNT` | Email of the GitHub deploy service account |
| `VM_NAME` | Existing VM name; old workflow recorded `cloudnetops-ai` |
| `VM_ZONE` | Existing VM zone; old workflow recorded `asia-south1-a` |
| `APP_DIRECTORY` | Absolute directory containing the existing `docker-compose.yml`; existing guide suggests `/opt/cloudnetops-ai`, verify it on the VM |

Optional variables:

- `IMAGE_NAME` defaults to `cloudnetops-ai`.
- `DOCKER_PLATFORM` defaults to `linux/amd64`; set `linux/arm64` if the VM
  architecture is ARM.

No GitHub secret is required by this implementation. The provider resource
name and service-account email are identifiers, not credentials. The workflow
uses GitHub's short-lived OIDC token; it does not need
`GCP_WORKLOAD_IDENTITY_PROVIDER`, a service-account JSON key, `VM_USER`, or
`VM_SSH_PRIVATE_KEY`. OS Login determines the remote username.

Create/protect the GitHub `production` environment and configure required
reviewers if deployments need manual approval. Verify branch protection and
required checks on the production branch. These GitHub settings must be
configured by a repository administrator.

## Prepare the existing VM

Before enabling production pushes, an administrator should verify the real
Compose directory and make sure the selected OS Login account:

- Can use Docker and the Docker Compose plugin (`docker compose version`).
- Has Google Cloud CLI installed; the deployment script uses
  `gcloud auth configure-docker` to get short-lived credentials from the
  attached VM service account. If it is not installed, add the official
  Google Cloud apt repository and install it:

  ```bash
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/cloud.google.gpg
  sudo chmod a+r /etc/apt/keyrings/cloud.google.gpg
  echo "deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
  sudo apt-get update
  sudo apt-get install -y google-cloud-cli
  ```

- Can read the existing Compose file, `.env`, and `secrets/` files, and can
  access the running Docker daemon. Docker-group membership is effectively
  root access; grant it only to this trusted deployment identity.
- Can run `gcloud auth configure-docker` using the VM's attached service
  account.
- Can connect through IAP/OS Login and can access only the intended VM.
- Has the app already running so the deploy script can capture and retain its
  current image before replacing it.

The script requires an existing `app` Compose container; it intentionally
refuses an unbacked first deployment. It does not modify `.env`,
`secrets/alertmanager-webhook-token`, volumes, the VM, or the Compose file.

## First deployment and verification

After the GCP and GitHub settings are ready:

1. Open a pull request and confirm the test and security jobs pass. The PR
   workflow does not contact GCP.
2. Merge/push to `PRODUCTION_BRANCH` (`main` unless deliberately changed).
3. In **Actions**, confirm the workflow passes the tests and both Trivy scans,
   publishes an image tagged with the full commit SHA, then reports deployment
   success only after the Compose health check and `/health/ready` succeed.
4. On the VM, verify without restarting monitoring services:

   ```bash
   cd /opt/cloudnetops-ai
   docker compose ps
   curl --fail http://127.0.0.1:8000/health/ready
   ```

   Use the verified `APP_DIRECTORY` and configured `APP_PORT` if they differ.
   The workflow never reports a successful deployment merely because SSH or
   `docker push` succeeded.

The build is tagged as
`REGION-docker.pkg.dev/PROJECT/REPOSITORY/IMAGE:FULL_GIT_SHA`; it does not
depend on a mutable `latest` tag. The exact scanned image is transferred
between workflow jobs and then pushed.

## Failure handling, rollback, and troubleshooting

If the deployment command fails, the workflow reports failure. The VM script
prints `docker compose ps` and the app's last 100 log lines. If the app update
had started, it retags the prior local image, restores only the `app` service,
checks container health and `/health/ready` again, and still exits with an
error so the failed release is visible. Previous Artifact Registry images are
not deleted; the VM's rollback image tags are also retained.

If automatic rollback cannot restore readiness, inspect:

```bash
cd /opt/cloudnetops-ai
docker compose ps -a app
docker compose logs --tail=100 app
docker image ls cloudnetops-rollback
```

To manually restart the prior app image, use the rollback tag printed by the
failed deployment (replace `ROLLBACK_TAG`):

```bash
cat > /tmp/cloudnetops-rollback.yml <<'EOF'
services:
  app:
    image: ROLLBACK_TAG
EOF
docker compose -f docker-compose.yml -f /tmp/cloudnetops-rollback.yml \
  up --no-build --pull never -d --no-deps app
curl --fail http://127.0.0.1:8000/health/ready
```

Common causes:

- Missing GitHub variables or a provider condition that does not match the
  repository/branch/event: inspect workflow configuration and the WIF provider
  condition; do not broaden trust as a workaround.
- `403` while pushing: grant the GitHub deploy service account
  `roles/artifactregistry.writer` on the correct repository and confirm the
  repository location in the image URI.
- `403` while pulling on the VM: grant the attached VM service account
  `roles/artifactregistry.reader` on that repository and verify its access
  scope.
- IAP/SSH failure: check IAP ingress, OS Login, the correct VM name/zone, and
  the deploy identity's narrowly scoped IAM permissions.
- Missing Compose file/container or Docker permission denied: verify
  `APP_DIRECTORY`, the pre-existing `app` service, file permissions, and
  trusted OS Login Docker access.
- Readiness failure: use the deployment log output and `docker compose logs`;
  confirm the database volume and application secrets remain accessible. Do
  not remove volumes or use `docker compose down -v`.
- Failed Trivy scan: review the finding and update/fix the affected dependency
  or configuration; do not suppress a finding without an explicit, reviewed
  exception.

To test a later code change, open a pull request first. After its checks pass,
merge or push to the configured production branch. Do not push directly to
production as a test if your branch-protection policy requires reviewed
changes.

## Remaining limitations

- GCP settings, APIs, IAM bindings, the live VM, and Artifact Registry could
  not be verified from this workspace; administrators must do that setup.
- The workflow uses `linux/amd64` by default. Configure the platform to match
  the VM CPU architecture.
- Trivy fails on unfixed-excluded high/critical findings. This is a
  vulnerability gate, not a guarantee of zero risk.
- IAP/OS Login and Docker access are assumed to be configured on the existing
  VM. The GitHub workflow does not create, replace, stop, or reconfigure that
  VM.
- Automatic rollback requires a currently running `app` container and a
  compatible Compose project. The script deliberately fails rather than
  attempting a first deployment without a known prior image.
