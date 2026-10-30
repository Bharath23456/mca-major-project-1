# Optional GCP deployment guide

## Status and cost warning

This repository has **not** created or deployed any GCP resources. A Compute
Engine VM, boot disk, static IP, network egress, and optional domain/TLS
services may incur charges. Prices depend on the billing account, region,
machine, disk, and usage; check the current Google Cloud Pricing Calculator
before proceeding. A small Ubuntu VM (for example `e2-small`, 2 vCPU/2 GB RAM)
is a low-cost starting point, but may be tight for the complete monitoring
stack. A disk of at least 30 GB is a practical starting assumption.

The steps below are examples only. Do not run cloud-creation commands until
you have reviewed the selected project, billing, region, machine, disk,
firewall scope, expected cost, and deletion procedure.

## Prerequisites

- GCP project with billing enabled and Compute Engine API enabled.
- Preferred region `asia-south1`; choose a zone such as `asia-south1-a` only
  after checking quota and availability.
- A named administrator account and a restricted SSH/IAP path.
- A repository clone on the VM. Do not store credentials in the repository.

## Resource creation (not executed)

Example creation command; it creates a VM and persistent boot disk and may
incur charges:

```bash
gcloud compute instances create cloudnetops-ai \
  --project=YOUR_PROJECT_ID \
  --zone=asia-south1-a \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --boot-disk-type=pd-balanced \
  --tags=cloudnetops-ai
```

Do not add a public SSH rule for `0.0.0.0/0`. Prefer IAP TCP forwarding or
restrict SSH ingress to your administrator IP. For an HTTPS deployment,
permit only TCP 80/443 after a reverse proxy and TLS configuration are ready.
Do not open ports 3000, 8000, 9090, 9093, 9100, or 9115 to the public internet.

To undo the example VM creation, first back up anything required, then delete
the named VM. This is destructive to the VM's local data and may delete its
auto-delete boot disk:

```bash
gcloud compute instances delete cloudnetops-ai \
  --project=YOUR_PROJECT_ID \
  --zone=asia-south1-a
```

Verify disk deletion in the Cloud Console or with `gcloud compute disks list`;
do not assume all separately created disks or IP addresses were deleted.

## VM setup and application startup

After you have created and secured the VM, install Docker Engine from its
official Ubuntu package repository:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and back in so the `docker` group membership is active. Membership in
that group is effectively root access on the VM; do not grant it to untrusted
users or broad identities.

Clone into the path expected by the optional GitHub deployment workflow and
ensure the OS Login identity used by that workflow owns the directory:

```bash
sudo mkdir -p /opt/cloudnetops-ai
sudo chown "$USER":"$USER" /opt/cloudnetops-ai
git clone https://github.com/Bharath23456/mca-major-project-1.git /opt/cloudnetops-ai
cd /opt/cloudnetops-ai
if [ ! -f .env ]; then cp .env.example .env; fi
nano .env
chmod 600 .env
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

Set a unique Grafana password in `.env` and do not copy any real credentials
into Git. The Compose ports stay bound to the VM's loopback interface.

## HTTPS and administration

Use a maintained reverse proxy such as Nginx or Caddy with a DNS name and
valid TLS certificate. This application has no built-in user accounts; protect
the dashboard and all API/docs paths with IAP, VPN, or reverse-proxy
authentication. A Basic Auth Nginx starting point is in
`scripts/nginx-cloudnetops.conf`; install `nginx` and `apache2-utils`, replace
`YOUR_DOMAIN`, obtain certificates, and generate a password file with
`sudo htpasswd -cB /etc/nginx/cloudnetops.htpasswd USERNAME` before enabling
the site. Review the proxy configuration and firewall before opening 80/443. Do not proxy
`/api/v1/alerts/webhook`; Alertmanager calls it over the private Compose
network. Keep Grafana, Prometheus, and Alertmanager on loopback and access
them through IAP, VPN, or an SSH tunnel. Restrict HTTP-to-HTTPS and firewall
rules to the services actually used.

## CI deployment and IAM

CI checks are separate from deployment. If a manual GCP deployment workflow
is configured, use GitHub Actions Workload Identity Federation rather than a
long-lived JSON service-account key. Limit the trust condition to this
repository and protected `main` branch, and require a protected GitHub
Environment approval.

For a workflow that connects to one VM over IAP and runs a deploy command, the
service account generally needs only:

- `compute.instances.get` on the selected instance (for example via a narrowly
  scoped custom role or an appropriate Compute Viewer binding).
- OS Login permission for the chosen login mode.
- IAP tunnel access on the selected VM.
- Workload Identity User on the deployment service account for the GitHub
  principal set.

Do not grant project Owner/Editor. Avoid adding permissions to create VMs or
change firewall rules to an application deploy identity. Confirm exact
permissions against the GCP OS Login/IAP setup chosen for the project.

## Verification, rollback, and cleanup

After any deployment, verify `docker compose ps`, the local health endpoint,
Prometheus **Status → Targets**, Grafana dashboards, and a real external
health check through HTTPS. A successful SSH command alone does not prove that
the app is healthy.

Before upgrading, back up persistent volumes. For a failed application
release, redeploy a previously reviewed Git revision using a fast-forward
update, rebuild, and repeat health checks. Keep deployment artifacts or
container image tags if exact binary rollback is required. Do not remove
volumes during rollback.

To stop the VM while retaining its boot disk:

```bash
gcloud compute instances stop cloudnetops-ai \
  --project=YOUR_PROJECT_ID \
  --zone=asia-south1-a
```

Starting it again may change its ephemeral public IP unless a reserved static
IP is configured. Stopping reduces compute charges but persistent disks and
reserved IPs can continue to incur charges. Deleting the VM and associated
disks is destructive; verify backups and list resources before deletion. No
stop, delete, or cloud resource operation has been run by this project setup.
