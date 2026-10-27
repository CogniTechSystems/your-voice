import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { Alert, Badge, Card, EmptyState, Field, PageHeader, StatusBadge } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDateTime, formatDuration } from "../lib/format";

const STATUSES = ["draft", "active", "completed", "cancelled"];

export function JobsPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const jobs = useResource(
    () => api.jobs.list({ status: status || undefined }),
    `jobs-${status}`,
    5000,
  );

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Give an agent context and instructions, let it write, then refine the outputs together."
        actions={
          <button type="button" onClick={() => navigate("/jobs/new")}>
            New job
          </button>
        }
      />
      <Card
        title="All jobs"
        actions={
          <Field label="Status">
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">Any status</option>
              {STATUSES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
        }
      >
        <Alert message={jobs.error} />
        {jobs.data?.length === 0 ? (
          <EmptyState>
            No jobs yet. <Link to="/jobs/new">Create one</Link> to get started.
          </EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Agent</th>
                <th>Status</th>
                <th className="numeric">Samples</th>
                <th className="numeric">Outputs</th>
                <th className="numeric">Working time</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {(jobs.data ?? []).map((job) => (
                <tr key={job.id}>
                  <td>
                    <Link to={`/jobs/${job.id}`}>
                      <strong>{job.title}</strong>
                    </Link>
                  </td>
                  <td>{job.agent_name ?? <span className="muted">Unassigned</span>}</td>
                  <td>
                    <span className="actions">
                      <StatusBadge status={job.status} />
                      {job.busy && <Badge tone="info">writing</Badge>}
                    </span>
                  </td>
                  <td className="numeric">{job.sample_count}</td>
                  <td className="numeric">{job.document_count}</td>
                  <td className="numeric">
                    {job.started_at ? formatDuration(job.working_seconds) : "-"}
                  </td>
                  <td>{formatDateTime(job.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
