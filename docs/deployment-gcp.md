# Optional Google Cloud deployment

Local Docker Compose is the primary reproducible project deployment. This
guide is an entry point to the detailed, cost-aware instructions in
[deployment.md](./deployment.md) and the implemented GitHub Actions pipeline
in [ci-cd-gcp.md](./ci-cd-gcp.md).

The optional example targets `asia-south1` and an existing secured VM. Before
using it:

- Review current VM, disk, IP, egress, and TLS costs in the Google Cloud
  Pricing Calculator.
- Keep all monitoring interfaces private; do not open ports 3000, 8000, 9090,
  9093, 9100, or 9115 to the public internet.
- Use HTTPS and an authenticated access layer for dashboard/API routes.
- Restrict SSH using IAP or an administrator allowlist; use least-privilege
  IAM and GitHub OIDC Workload Identity Federation rather than key files.
- Back up persistent data and document a rollback path before upgrading.

No cloud project, VM, service account, firewall rule, or other resource has
been created by this project work. Do not execute resource-changing commands
without confirming the project, region, expected cost, access controls, and
authorization.
