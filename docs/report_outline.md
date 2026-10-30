# Project report draft outline

The supplied `Contents.pptx` gives a 7-chapter content sequence, while the
student selected an 8-chapter sequence from the supplied VTU-formatting
notes. The working draft follows that selection; confirm the department's
required structure before submission. Neither item is a formatted report
document template. See [report_draft.md](./report_draft.md). The eight
literature titles and topic descriptions still lack full papers and complete
bibliographic records, so their review remains provisional.

## Draft abstract

CloudNetOps-AI is a local-first infrastructure and network monitoring
demonstration that combines a FastAPI application with Prometheus, Node
Exporter, Blackbox Exporter, Grafana, and Alertmanager. It collects available
Linux host and configured HTTP/HTTPS endpoint measurements, presents current
and historical values, and stores alert and anomaly events in SQLite.
Threshold-based rules provide a transparent baseline, while a reproducible
scikit-learn Isolation Forest scores validated metric samples. The system
labels missing or stale telemetry instead of substituting simulated live
values. In the current verification environment, 26 unit/API tests passed.
All six Compose services started, all six Prometheus targets reported `up`,
the approved `https://example.com` probe succeeded, and the provisioned
Grafana dashboard loaded. A live threshold finding also reached Alertmanager
and application alert history. A generated synthetic dataset produced
precision 0.8475, recall 1.0000, and F1 0.9174; these values describe only
that synthetic test split. Alert recovery was not tested, no GCP resources
were created, and the implementation is intended for student demonstration
and investigation support, not autonomous remediation or enterprise
availability.

## Selected 8-chapter sequence

1. **Front matter** — Title page, certificate, declaration, acknowledgement,
   abstract, table of contents, and lists of figures/tables.
2. **Chapter 1: Introduction** — Project context, problem, objectives,
   relevance, and scope.
3. **Chapter 2: Literature Review / Survey** — Related work, comparison, and
   identified gaps; full papers and bibliographic records are still needed.
4. **Chapter 3: System Requirement Analysis** — Feasibility, requirements,
   and hardware/software specifications.
5. **Chapter 4: System Design and Modeling** — Architecture, data flow,
   use-case/UML diagrams, and data model.
6. **Chapter 5: Implementation and Code Design** — Modules, algorithms,
   technology stack, and implementation details.
7. **Chapter 6: Testing Methodology** — Test strategy and documented test
   cases.
8. **Chapter 7: Results and Discussion** — Actual outputs, measured results,
   and verified limitations.
9. **Chapter 8: Conclusion and Future Enhancements** — Demonstrated
   achievements, limitations, and justified future work.
10. **References and appendices** — Complete verified citations and required
    supporting material.

For final report formatting, obtain the eight papers or verifiable
bibliographic records and confirm the department's precise VTU reference and
page-layout rules against the official circular. The supplied `Contents.pptx`
defines report content, not page layout.
