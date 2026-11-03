# Grafana setup and administrator access

Grafana is a separate monitoring UI. It does not use CloudNetOps-AI application
accounts, sessions, or roles.

## URL and first startup

The local Compose URL is <http://127.0.0.1:3000/>. The service binds to
loopback and should not be exposed directly to the public internet.

Before the first startup, set a unique `GRAFANA_ADMIN_PASSWORD` in the
untracked `.env` file. `GRAFANA_ADMIN_USER` defaults to `admin`; both values
are passed to the container as `GF_SECURITY_ADMIN_USER` and
`GF_SECURITY_ADMIN_PASSWORD`. Compose requires the password value to be set.
Keep `.env` private and never paste the password into source control, issue
reports, or logs.

On a new Grafana data volume, Grafana initializes its administrator using
these environment values. The named `grafana-data` volume preserves its
database, user settings, and other Grafana state between container restarts.
Changing the environment variable alone does not reset a password already
stored in that database.

## Password recovery for a local deployment owner

If you still know the password, change it in Grafana under the user
preferences. If it is lost, use Grafana's supported server CLI against the
existing database:

1. Stop other changes to the local stack and update `GRAFANA_ADMIN_PASSWORD`
   in `.env` to a new unique value. Protect `.env` as a secret.
2. Recreate only the Grafana container so its environment has the new value.
   This keeps named volumes:

   ```powershell
   docker compose up -d --force-recreate grafana
   ```

3. Reset the database administrator password with the configured environment
   value. The command does not place the literal password in shell history or
   print it in the command output:

   ```powershell
   docker compose exec grafana sh -c 'grafana cli admin reset-admin-password "$GF_SECURITY_ADMIN_PASSWORD"'
   ```

4. Sign in at <http://127.0.0.1:3000/> using the configured administrator
   username and the new password. Confirm the provisioned dashboard still
   appears.

This procedure changes the Grafana user record and does not remove the
`grafana-data` volume, dashboards, or application database. Do not use
`docker compose down -v` to recover access. If the CLI reports that it cannot
find the administrator, inspect Grafana's admin user ID and pass the
appropriate `--user-id` option as described in the official
[Grafana CLI documentation](https://grafana.com/docs/grafana/latest/administration/cli/#reset-admin-password).

## Prometheus datasource and dashboard

Compose provisions a read-only Prometheus datasource named `Prometheus` at
`http://prometheus:9090` over the private Compose network. It is defined in
`monitoring/grafana/provisioning/datasources/prometheus.yml`; it does not use
the host-published Prometheus URL.

The `CloudNetOps-AI` dashboard provider loads the JSON dashboard from
`monitoring/grafana/dashboards/`. After signing in, open **Dashboards** and
select **CloudNetOps-AI Infrastructure**. Its panels query Prometheus for
host resource usage, network traffic, endpoint probes, alert counts, and
application anomaly counters. Panels remain empty when their underlying
metrics are unavailable; they do not represent fabricated live values.

For troubleshooting, check `docker compose ps --all`,
`docker compose logs --tail 100 grafana prometheus`, and Prometheus
**Status → Targets**. Keep the Grafana, Prometheus, and Alertmanager ports
private; use a VPN, IAP, or SSH tunnel for remote administration.
