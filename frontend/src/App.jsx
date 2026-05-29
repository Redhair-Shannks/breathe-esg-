import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  Factory,
  FileSpreadsheet,
  Filter,
  History,
  Lock,
  Plane,
  RefreshCw,
  ShieldCheck,
  Upload,
  XCircle,
  Zap
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  approveActivity,
  getActivities,
  getAuditEvents,
  getBootstrap,
  getDashboard,
  reopenActivity,
  rejectActivity,
  updateActivity,
  uploadBatch
} from "./api";

const SOURCE_OPTIONS = [
  { value: "", label: "All sources", icon: Database },
  { value: "SAP", label: "SAP", icon: Factory },
  { value: "UTILITY", label: "Electricity", icon: Zap },
  { value: "TRAVEL", label: "Travel", icon: Plane }
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "NEEDS_REVIEW", label: "Needs review" },
  { value: "BLOCKED", label: "Blocked" },
  { value: "LOCKED", label: "Locked" },
  { value: "REJECTED", label: "Rejected" }
];

const SOURCE_COPY = {
  SAP: "SAP fuel/procurement CSV or XLSX",
  UTILITY: "Green Button electricity CSV or XLSX",
  TRAVEL: "Concur-like travel CSV or XLSX"
};

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function statusClass(status) {
  return `pill ${status.toLowerCase().replaceAll("_", "-")}`;
}

function formatEventType(value) {
  return String(value || "")
    .replaceAll(".", " ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function App() {
  const [tenant, setTenant] = useState("acme-manufacturing");
  const [bootstrap, setBootstrap] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [activities, setActivities] = useState([]);
  const [filters, setFilters] = useState({ source_kind: "", review_status: "", severity: "" });
  const [selectedId, setSelectedId] = useState(null);
  const [sourceKind, setSourceKind] = useState("SAP");
  const [uploadFile, setUploadFile] = useState(null);
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditEvents, setAuditEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const selected = useMemo(() => activities.find((activity) => activity.id === selectedId), [activities, selectedId]);

  async function refresh() {
    setBusy(true);
    try {
      const [boot, dash, rows] = await Promise.all([
        getBootstrap(tenant),
        getDashboard(tenant),
        getActivities(tenant, filters)
      ]);
      setBootstrap(boot);
      setDashboard(dash);
      setActivities(rows);
      if (selectedId && !rows.some((row) => row.id === selectedId)) setSelectedId(null);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [tenant, filters.source_kind, filters.review_status, filters.severity]);

  async function handleUpload(event) {
    event.preventDefault();
    if (!uploadFile) return;
    setBusy(true);
    setMessage("");
    try {
      const batch = await uploadBatch(tenant, sourceKind, uploadFile);
      setMessage(`Imported ${batch.imported_count} rows from ${batch.file_name}.`);
      setUploadFile(null);
      event.target.reset();
      await refresh();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDecision(action) {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      if (action === "approve") {
        await approveActivity(tenant, selected.id, "Analyst sign-off from review dashboard.");
      } else if (action === "reject") {
        await rejectActivity(tenant, selected.id, "Rejected during analyst review.");
      } else {
        const note = window.prompt("Why are you reopening this row?");
        if (!note?.trim()) return;
        await reopenActivity(tenant, selected.id, note.trim());
      }
      await refresh();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleEdit(event) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    setBusy(true);
    try {
      await updateActivity(tenant, selected.id, payload);
      setMessage("Saved normalized row changes.");
      await refresh();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function openAuditTrail() {
    setBusy(true);
    setMessage("");
    try {
      const events = await getAuditEvents(tenant);
      setAuditEvents(events);
      setAuditOpen(true);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  const summary = dashboard?.summary;
  const sourceRows = summary?.by_source || [];
  const issueRows = dashboard?.top_issues || [];
  const hasFilters = Boolean(filters.source_kind || filters.review_status || filters.severity);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Breathe ESG prototype</p>
          <h1>Ingestion Review Workbench</h1>
        </div>
        <div className="topbar-actions">
          <button type="button" className="secondary" onClick={openAuditTrail} disabled={busy}>
            <History size={16} />
            Audit trail
          </button>
          <select value={tenant} onChange={(event) => setTenant(event.target.value)} aria-label="Tenant">
            {bootstrap?.tenants?.map((item) => (
              <option value={item.slug} key={item.slug}>
                {item.name}
              </option>
            ))}
          </select>
          <button type="button" className="icon-button" onClick={refresh} disabled={busy} title="Refresh data">
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="metrics-grid">
        <Metric label="Rows ingested" value={summary?.activity_count} icon={Database} />
        <Metric label="Needs review" value={summary?.needs_review} icon={FileSpreadsheet} tone="blue" />
        <Metric label="Blocked" value={summary?.blocked} icon={AlertTriangle} tone="amber" />
        <Metric label="Locked for audit" value={summary?.locked} icon={Lock} tone="green" />
        <Metric label="Open errors" value={summary?.open_errors} icon={XCircle} tone="red" />
        <Metric label="Estimated tCO2e" value={summary?.estimated_kg_co2e ? Number(summary.estimated_kg_co2e) / 1000 : 0} icon={CheckCircle2} tone="teal" digits={2} />
      </section>

      <section className="insight-grid">
        <div className="insight-panel">
          <div className="panel-title">
            <Activity size={18} />
            <h2>Source coverage</h2>
          </div>
          <div className="source-stack">
            {SOURCE_OPTIONS.filter((option) => option.value).map((option) => {
              const Icon = option.icon;
              const row = sourceRows.find((item) => item.source_system__kind === option.value);
              return (
                <button
                  type="button"
                  className={`source-card ${filters.source_kind === option.value ? "active" : ""}`}
                  key={option.value}
                  onClick={() => setFilters({ ...filters, source_kind: filters.source_kind === option.value ? "" : option.value })}
                >
                  <Icon size={18} />
                  <span>{option.label}</span>
                  <strong>{row?.rows || 0}</strong>
                </button>
              );
            })}
          </div>
        </div>

        <div className="insight-panel">
          <div className="panel-title">
            <AlertTriangle size={18} />
            <h2>Issue queue</h2>
          </div>
          <div className="issue-summary">
            {issueRows.length === 0 ? (
              <p className="empty">No open issues.</p>
            ) : (
              issueRows.slice(0, 5).map((issue) => (
                <div className={`issue-chip ${issue.severity.toLowerCase()}`} key={`${issue.severity}-${issue.code}`}>
                  <span className="issue-dot" />
                  <span className="issue-copy">
                    <strong>{issue.code.replaceAll("_", " ")}</strong>
                    <small>{issue.severity.toLowerCase()}</small>
                  </span>
                  <em>{issue.rows}</em>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="insight-panel lock-panel">
          <div className="panel-title">
            <ShieldCheck size={18} />
            <h2>Audit readiness</h2>
          </div>
          <div className="readiness-list">
            <ReadinessRow label="Rows locked" value={summary?.locked || 0} />
            <ReadinessRow label="Rows blocked" value={summary?.blocked || 0} />
            <ReadinessRow label="Open warnings" value={summary?.open_warnings || 0} />
          </div>
        </div>
      </section>

      <section className="workspace-grid">
        <aside className="side-panel">
          <form className="upload-panel" onSubmit={handleUpload}>
            <div className="panel-title">
              <Upload size={18} />
              <h2>Import source data</h2>
            </div>
            <label>
              File source category
              <select value={sourceKind} onChange={(event) => setSourceKind(event.target.value)}>
                <option value="SAP">SAP fuel/procurement</option>
                <option value="UTILITY">Utility electricity</option>
                <option value="TRAVEL">Corporate travel</option>
              </select>
            </label>
            <label>
              File
              <input type="file" accept=".csv,.xlsx" onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
            </label>
            <p className="hint">{SOURCE_COPY[sourceKind]}</p>
            <button type="submit" disabled={busy || !uploadFile}>
              <Upload size={16} />
              Import
            </button>
          </form>

          <div className="batch-list">
            <div className="panel-title">
              <FileSpreadsheet size={18} />
              <h2>Recent batches</h2>
            </div>
            {dashboard?.recent_batches?.map((batch) => (
              <div className="batch-row" key={batch.id}>
                <strong>{batch.source_kind}</strong>
                <span>{batch.file_name}</span>
                <small>
                  {batch.imported_count} rows - {batch.failed_count} blocked - {batch.warning_count} warnings
                </small>
              </div>
            ))}
          </div>
        </aside>

        <section className="review-panel">
          <div className="review-toolbar">
            <div className="panel-title">
              <Filter size={18} />
              <h2>Review queue</h2>
            </div>
            <div className="filters">
              <select value={filters.source_kind} onChange={(event) => setFilters({ ...filters, source_kind: event.target.value })}>
                {SOURCE_OPTIONS.map((option) => (
                  <option value={option.value} key={option.label}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select value={filters.review_status} onChange={(event) => setFilters({ ...filters, review_status: event.target.value })}>
                {STATUS_OPTIONS.map((option) => (
                  <option value={option.value} key={option.label}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select value={filters.severity} onChange={(event) => setFilters({ ...filters, severity: event.target.value })}>
                <option value="">Any issue</option>
                <option value="ERROR">Errors</option>
                <option value="WARNING">Warnings</option>
              </select>
              {hasFilters && (
                <button type="button" className="clear-filters" onClick={() => setFilters({ source_kind: "", review_status: "", severity: "" })}>
                  Clear filters
                </button>
              )}
            </div>
          </div>

          <div className="activity-table" role="table">
            <div className="table-head" role="row">
              <span>Source</span>
              <span>Activity</span>
              <span>Facility</span>
              <span>Quantity</span>
              <span>Emissions</span>
              <span>Status</span>
            </div>
            {activities.map((activity) => (
              <button
                className={`table-row ${selectedId === activity.id ? "selected" : ""}`}
                role="row"
                key={activity.id}
                onClick={() => setSelectedId(activity.id)}
              >
                <span>{activity.source_kind}</span>
                <span>
                  <strong>{activity.category || activity.activity_kind}</strong>
                  <small>{activity.description}</small>
                </span>
                <span>{activity.facility_code || "-"}</span>
                <span>
                  {formatNumber(activity.normalized_quantity, 2)} {activity.normalized_unit}
                </span>
                <span>{activity.emission_estimate?.co2e_kg ? `${formatNumber(activity.emission_estimate.co2e_kg, 1)} kg` : "-"}</span>
                <span>
                  <em className={statusClass(activity.review_status)}>{activity.review_status.replaceAll("_", " ")}</em>
                </span>
              </button>
            ))}
          </div>
        </section>
      </section>

      {selected && (
        <ActivityDrawer
          activity={selected}
          facilities={bootstrap?.facilities || []}
          onClose={() => setSelectedId(null)}
          onApprove={() => handleDecision("approve")}
          onReject={() => handleDecision("reject")}
          onReopen={() => handleDecision("reopen")}
          onEdit={handleEdit}
          busy={busy}
        />
      )}

      {auditOpen && (
        <AuditTrailModal
          events={auditEvents}
          onClose={() => setAuditOpen(false)}
        />
      )}
    </main>
  );
}

function Metric({ label, value, icon: Icon, tone = "neutral", digits = 0 }) {
  return (
    <div className={`metric ${tone}`}>
      <Icon size={20} />
      <span>{label}</span>
      <strong>{formatNumber(value || 0, digits)}</strong>
    </div>
  );
}

function ReadinessRow({ label, value }) {
  return (
    <div className="readiness-row">
      <span>{label}</span>
      <strong>{formatNumber(value || 0)}</strong>
    </div>
  );
}

function ActivityDrawer({ activity, facilities, onClose, onApprove, onReject, onReopen, onEdit, busy }) {
  const hasBlockingIssue = activity.validation_issues.some((issue) => issue.severity === "ERROR" && issue.status === "OPEN");
  const locked = activity.review_status === "LOCKED";
  const rejected = activity.review_status === "REJECTED";
  const terminal = locked || rejected;

  return (
    <aside className="drawer" aria-label="Activity details">
      <div className="drawer-head">
        <div>
          <p className="eyebrow">{activity.source_kind} row #{activity.raw_record?.row_number}</p>
          <h2>{activity.category || activity.activity_kind}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} title="Close details">
          <XCircle size={20} />
        </button>
      </div>

      <div className="drawer-actions">
        <button type="button" onClick={onApprove} disabled={busy || terminal || hasBlockingIssue}>
          <CheckCircle2 size={16} />
          Approve and lock
        </button>
        <button type="button" className="secondary danger" onClick={onReject} disabled={busy || terminal}>
          <XCircle size={16} />
          Reject
        </button>
        {terminal && (
          <button type="button" className="secondary" onClick={onReopen} disabled={busy}>
            <RefreshCw size={16} />
            Reopen
          </button>
        )}
      </div>

      <section className="detail-section">
        <h3>Lineage</h3>
        <dl className="lineage-grid">
          <div>
            <dt>Source</dt>
            <dd>{activity.source_kind}</dd>
          </div>
          <div>
            <dt>Batch</dt>
            <dd>{activity.batch_file}</dd>
          </div>
          <div>
            <dt>Row</dt>
            <dd>#{activity.raw_record?.row_number || "-"}</dd>
          </div>
          <div>
            <dt>External ID</dt>
            <dd>{activity.external_id || "-"}</dd>
          </div>
          <div className="wide">
            <dt>Row hash</dt>
            <dd className="hash">{activity.raw_record?.row_hash || "-"}</dd>
          </div>
        </dl>
      </section>

      <section className="detail-section">
        <h3>Validation</h3>
        {activity.validation_issues.length === 0 ? (
          <p className="empty">No open issues.</p>
        ) : (
          activity.validation_issues.map((issue) => (
            <div className={`issue ${issue.severity.toLowerCase()}`} key={issue.id}>
              <strong>{issue.code}</strong>
              <span>{issue.message}</span>
            </div>
          ))
        )}
      </section>

      <form className="detail-section edit-grid" onSubmit={onEdit}>
        <h3>Normalized row</h3>
        <label>
          Facility
          <select name="facility" defaultValue={activity.facility || ""} disabled={terminal}>
            <option value="">No facility</option>
            {facilities.map((facility) => (
              <option value={facility.id} key={facility.id}>
                {facility.code} - {facility.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <input name="category" defaultValue={activity.category || ""} disabled={terminal} />
        </label>
        <label>
          Quantity
          <input name="normalized_quantity" defaultValue={activity.normalized_quantity || ""} disabled={terminal} />
        </label>
        <label>
          Unit
          <input name="normalized_unit" defaultValue={activity.normalized_unit || ""} disabled={terminal} />
        </label>
        <label className="wide">
          Description
          <textarea name="description" defaultValue={activity.description || ""} disabled={terminal} />
        </label>
        <input type="hidden" name="note" value="Analyst edited normalized row from dashboard." />
        <button type="submit" className="secondary" disabled={busy || terminal}>
          Save changes
        </button>
      </form>

      <section className="detail-section estimate">
        <h3>Emission estimate</h3>
        <dl>
          <div>
            <dt>kgCO2e</dt>
            <dd>{activity.emission_estimate?.co2e_kg || "-"}</dd>
          </div>
          <div>
            <dt>Factor</dt>
            <dd>{activity.emission_estimate?.factor_label || "-"}</dd>
          </div>
          <div>
            <dt>Calculation</dt>
            <dd>{activity.emission_estimate?.calculation_note || "-"}</dd>
          </div>
        </dl>
      </section>

      <section className="detail-section">
        <h3>Raw source row</h3>
        <pre>{JSON.stringify(activity.raw_record?.payload, null, 2)}</pre>
      </section>

      <section className="detail-section">
        <h3>Audit trail</h3>
        <AuditEventList events={activity.audit_events} compact />
      </section>
    </aside>
  );
}

function AuditTrailModal({ events, onClose }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Audit trail">
      <section className="audit-modal">
        <div className="drawer-head">
          <div>
            <p className="eyebrow">Tenant audit log</p>
            <h2>Audit Trail</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} title="Close audit trail">
            <XCircle size={20} />
          </button>
        </div>
        <div className="audit-summary-bar">
          <ReadinessRow label="Events shown" value={events.length} />
          <ReadinessRow label="Locked rows" value={events.filter((event) => event.event_type === "activity.approved_locked").length} />
          <ReadinessRow label="Edits" value={events.filter((event) => event.event_type === "activity.edited").length} />
        </div>
        <AuditEventList events={events} />
      </section>
    </div>
  );
}

function AuditEventList({ events, compact = false }) {
  if (!events.length) {
    return <p className="empty">No audit events yet.</p>;
  }
  return (
    <div className={compact ? "audit-list compact" : "audit-list"}>
      {events.map((event) => (
        <article className="audit-event" key={event.id}>
          <div className="audit-marker">
            <Clock3 size={15} />
          </div>
          <div className="audit-body">
            <div className="audit-title-row">
              <strong>{formatEventType(event.event_type)}</strong>
              <span>{new Date(event.created_at).toLocaleString()}</span>
            </div>
            <div className="audit-meta">
              <span>{event.actor_name}</span>
              {event.source_kind && <span>{event.source_kind}</span>}
              {event.row_number && <span>Row #{event.row_number}</span>}
              {event.activity_label && <span>{event.activity_label}</span>}
            </div>
            {event.note && <p>{event.note}</p>}
            {!compact && (
              <details>
                <summary>Event data</summary>
                <pre>{JSON.stringify({ before: event.before, after: event.after }, null, 2)}</pre>
              </details>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export default App;
