# Viva questions and short answers

1. **What problem does CloudNetOps-AI address?**  
   It combines host and endpoint monitoring, dashboards, alerts, and anomaly
   scoring in a small reproducible DevOps demonstration.

2. **What is Prometheus used for?**  
   Prometheus scrapes time-series metrics, stores them for a limited
   retention period, evaluates alert rules, and exposes a query API.

3. **What does Node Exporter collect?**  
   It exports operating-system and hardware metrics for Linux hosts. On
   Docker Desktop, its view is the Docker Linux environment, not native
   Windows host data.

4. **How is an endpoint checked?**  
   Prometheus asks Blackbox Exporter to make an ordinary HTTP GET request to a
   configured endpoint and records success, latency, and status information.

5. **How do rule alerts differ from Isolation Forest?**  
   Rules compare a value to an explicit threshold. Isolation Forest compares a
   metric row with a learned baseline and reports unusual patterns.

6. **Does an anomaly confirm an incident?**  
   No. It is a signal for investigation. It does not prove an outage, attack,
   or root cause.

7. **How is the model evaluated?**  
   A deterministic synthetic training set and separate labelled synthetic
   test set are passed through scikit-learn metrics. The resulting scores only
   describe those generated samples.

8. **Why use Docker Compose?**  
   Compose describes the API and monitoring services, networking, health
   checks, and persistent volumes in one reproducible local deployment.

9. **How are alerts persisted?**  
   Alertmanager sends firing/resolved updates to a private API receiver, which
   stores the latest state per alert fingerprint in SQLite.

10. **Why is SQLite used?**  
    It keeps local event history simple and dependency-light for a student
    demonstration. It is not intended for high-volume concurrent production
    use.

11. **How does the system avoid fake metrics?**  
    The dashboard queries Prometheus and labels absent or old values as
    missing/stale. Synthetic values are only used by the documented model
    training and evaluation path.

12. **Does it repair infrastructure automatically?**  
    No. It reports metrics and recommends investigation; it has no
    self-healing or infrastructure write permissions.

13. **How does CI/CD work?**  
    CI runs tests and configuration/build checks on pushes and pull requests.
    Any cloud deployment is separate and must be explicitly configured and
    protected.

14. **What are key limitations?**  
    Linux host telemetry requirements, synthetic model data, limited
    single-VM availability, and local SQLite persistence.

15. **How is the cloud environment secured?**  
    Keep internal monitoring ports private, use HTTPS and restricted
    administration, avoid long-lived keys, and grant least-privilege IAM.
