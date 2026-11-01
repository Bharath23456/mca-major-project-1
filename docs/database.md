# Database schema and migrations

The application uses SQLite through SQLAlchemy. The database lives at
`DATABASE_URL` (the Compose default is the persistent `/data/cloudnetops.db`
file in the `app-data` volume). Schema changes are managed with Alembic; app
startup upgrades the database to the latest revision before serving requests.
Do not delete the database file to apply a schema change.

## Tables

| Table | Purpose |
|---|---|
| `alert_events` | Latest Alertmanager state per fingerprint; original monitoring history is retained. |
| `anomaly_events` | Persisted threshold and Isolation Forest findings, including metric evidence, target, and model status. |
| `users` | Username/email, Argon2id password hash, role, activation state, and timestamps. |
| `user_sessions` | SHA-256 token digest, CSRF-token digest, expiration, and last-use timestamps; raw session tokens are not stored. |
| `login_attempts` | Hashed account/address key and timestamp for login throttling. |
| `incidents` | Incident title, severity, state, target, operator assignment, and timestamps. |
| `incident_events` | Unique relationship between an incident and one alert or anomaly, plus the correlation reason. |
| `incident_notes` | Operator-authored notes associated with an incident. |
| `audit_logs` | Actor, action, resource, result, timestamp, and non-secret structured details. |

Foreign keys, check constraints, unique event links, and indexes protect the
relationships. Existing `alert_events` and `anomaly_events` are not recreated
or dropped by the forward migrations.

## Upgrade and verification

Normal startup runs `alembic upgrade head`. To inspect or explicitly upgrade a
local development database:

```powershell
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini upgrade head
```

In Compose, app startup applies upgrades automatically. Back up the SQLite
file or volume before an upgrade and verify `/health/ready` and application
history afterward. The migration tests construct a legacy schema with alert
and anomaly rows, upgrade it, verify row preservation and new relationships,
and exercise downgrade behavior on a disposable test database:

```powershell
python -m pytest -q tests\test_migrations.py
```

Downgrades are intended for disposable development/test databases only.
Downgrading removes the newly introduced access/incident tables and therefore
deletes data stored in those tables; it does not remove legacy alert/anomaly
tables. Never downgrade a database containing data you need to preserve
without first taking and validating a backup.

SQLite is suitable for this local student demonstration, not high-concurrency
production workloads. No migration automatically creates an administrator.
Bootstrap the first admin separately with `python -m app.auth_setup`.
