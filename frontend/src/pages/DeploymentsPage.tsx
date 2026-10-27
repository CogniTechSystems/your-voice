import { useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Deployment, DeploymentLog, DeploymentWrite } from "../api/types";
import { Alert, Card, EmptyState, Field, PageHeader, StatusBadge } from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";
import { errorMessage, formatBytes, formatDateTime } from "../lib/format";

const ACTIVE = new Set(["starting", "running"]);

function toWrite(deployment: Deployment): DeploymentWrite {
  return {
    name: deployment.name,
    model_id: deployment.model_id,
    runtime_id: deployment.runtime_id,
    model_file: deployment.model_file,
    served_model_name: deployment.served_model_name,
    launch_args: deployment.launch_args,
    temperature: deployment.temperature,
    top_p: deployment.top_p,
    max_tokens: deployment.max_tokens,
    request_timeout_seconds: deployment.request_timeout_seconds,
  };
}

export function DeploymentsPage() {
  const [polling, setPolling] = useState(false);
  const deployments = useResource(api.deployments.list, "deployments", polling ? 2000 : undefined);
  const [editing, setEditing] = useState<Deployment | "new" | null>(null);
  const [logsFor, setLogsFor] = useState<number>();
  const action = useAction();
  const starting =
    deployments.data?.some((deployment) => deployment.status === "starting") ?? false;

  useEffect(() => setPolling(starting), [starting]);

  const perform = (operation: () => Promise<unknown>) =>
    void action.run(async () => {
      await operation();
      setPolling(true);
      await deployments.refresh();
    });

  const remove = (deployment: Deployment) => {
    if (window.confirm(`Delete deployment ${deployment.name}?`)) {
      perform(() => api.deployments.remove(deployment.id));
    }
  };

  return (
    <>
      <PageHeader
        title="Deployments"
        description="Model and runtime configurations"
        actions={
          <button type="button" onClick={() => setEditing("new")}>
            Add deployment
          </button>
        }
      />
      {editing && (
        <DeploymentForm
          key={editing === "new" ? "new" : editing.id}
          deployment={editing === "new" ? undefined : editing}
          onDone={() => {
            setEditing(null);
            void deployments.refresh();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <Card title="Configured deployments">
        <Alert message={deployments.error ?? action.error} />
        {deployments.data?.length === 0 ? (
          <EmptyState>No deployments yet.</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Model</th>
                <th>Runtime</th>
                <th>Generation</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(deployments.data ?? []).map((deployment) => (
                <tr
                  key={deployment.id}
                  className={deployment.id === logsFor ? "selected" : undefined}
                >
                  <td>
                    <strong>{deployment.name}</strong>
                    {deployment.port && <div className="muted small">port {deployment.port}</div>}
                  </td>
                  <td>
                    <code>{deployment.model_repo_id}</code>
                    {deployment.model_file && (
                      <div className="muted small">{deployment.model_file}</div>
                    )}
                  </td>
                  <td>{deployment.runtime_name}</td>
                  <td className="small">
                    temperature {deployment.temperature} · top p {deployment.top_p} · max{" "}
                    {deployment.max_tokens}
                  </td>
                  <td>
                    <StatusBadge status={deployment.status} />
                    {deployment.error && <div className="error-text small">{deployment.error}</div>}
                  </td>
                  <td className="numeric actions">
                    {ACTIVE.has(deployment.status) ? (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => perform(() => api.deployments.stop(deployment.id))}
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => perform(() => api.deployments.start(deployment.id))}
                      >
                        Start
                      </button>
                    )}
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setLogsFor(deployment.id)}
                    >
                      Logs
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={ACTIVE.has(deployment.status)}
                      onClick={() => setEditing(deployment)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="danger"
                      disabled={ACTIVE.has(deployment.status)}
                      onClick={() => remove(deployment)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {logsFor !== undefined && (
        <LogViewer key={logsFor} deploymentId={logsFor} onClose={() => setLogsFor(undefined)} />
      )}
    </>
  );
}

const DEFAULTS: Omit<DeploymentWrite, "model_id" | "runtime_id"> = {
  name: "",
  model_file: null,
  served_model_name: null,
  launch_args: "",
  temperature: 0.2,
  top_p: 0.95,
  max_tokens: 4096,
  request_timeout_seconds: 600,
};

function DeploymentForm({
  deployment,
  onDone,
  onCancel,
}: {
  deployment?: Deployment;
  onDone: () => void;
  onCancel: () => void;
}) {
  const models = useResource(api.models.list, "models");
  const runtimes = useResource(api.runtimes.list, "runtimes");
  const [values, setValues] = useState<Partial<DeploymentWrite>>(
    deployment ? toWrite(deployment) : DEFAULTS,
  );
  const readyModels = (models.data ?? []).filter((model) => model.status === "ready");
  const modelId = values.model_id ?? readyModels[0]?.id;
  const runtimeId = values.runtime_id ?? runtimes.data?.[0]?.id;
  const files = useResource(
    () => (modelId ? api.models.files(modelId) : Promise.resolve([])),
    `files-${modelId ?? "none"}`,
  );
  const action = useAction();
  const update = (changes: Partial<DeploymentWrite>) => setValues({ ...values, ...changes });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (modelId === undefined || runtimeId === undefined) {
      return;
    }
    const payload = { ...DEFAULTS, ...values, model_id: modelId, runtime_id: runtimeId };
    void action.run(async () => {
      if (deployment) {
        await api.deployments.update(deployment.id, payload);
      } else {
        await api.deployments.create(payload);
      }
      onDone();
    });
  };

  const numberInput = (
    field: "temperature" | "top_p" | "max_tokens" | "request_timeout_seconds",
    step: string,
  ) => (
    <input
      type="number"
      step={step}
      value={values[field] ?? ""}
      onChange={(event) => update({ [field]: Number(event.target.value) })}
    />
  );

  return (
    <Card title={deployment ? `Edit ${deployment.name}` : "New deployment"}>
      <Alert message={models.error ?? runtimes.error} />
      {readyModels.length === 0 && (
        <Alert message="Download a model before creating a deployment." />
      )}
      <form className="form-grid" onSubmit={submit}>
        <Field label="Name">
          <input
            value={values.name ?? ""}
            onChange={(event) => update({ name: event.target.value })}
            required
          />
        </Field>
        <Field label="Model">
          <select
            value={modelId ?? ""}
            onChange={(event) => update({ model_id: Number(event.target.value), model_file: null })}
          >
            {readyModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.repo_id}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Model file"
          hint="Required by runtimes that load a single file, such as llama.cpp."
        >
          <select
            value={values.model_file ?? ""}
            onChange={(event) => update({ model_file: event.target.value || null })}
          >
            <option value="">Entire model directory</option>
            {(files.data ?? []).map((file) => (
              <option key={file.path} value={file.path}>
                {file.path} ({formatBytes(file.size_bytes)})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Runtime">
          <select
            value={runtimeId ?? ""}
            onChange={(event) => update({ runtime_id: Number(event.target.value) })}
          >
            {(runtimes.data ?? []).map((runtime) => (
              <option key={runtime.id} value={runtime.id}>
                {runtime.name} ({runtime.kind})
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Served model name"
          hint="Sent as the model field in requests. Defaults to the repository ID."
        >
          <input
            value={values.served_model_name ?? ""}
            onChange={(event) => update({ served_model_name: event.target.value || null })}
          />
        </Field>
        <Field
          label="Extra launch arguments"
          hint="Appended to the runtime command, for example -ngl 99."
        >
          <input
            value={values.launch_args ?? ""}
            onChange={(event) => update({ launch_args: event.target.value })}
          />
        </Field>
        <Field label="Temperature">{numberInput("temperature", "0.05")}</Field>
        <Field label="Top p">{numberInput("top_p", "0.05")}</Field>
        <Field label="Max tokens per response">{numberInput("max_tokens", "1")}</Field>
        <Field label="Request timeout (seconds)">
          {numberInput("request_timeout_seconds", "1")}
        </Field>
        <Alert message={action.error} />
        <div className="actions form-actions">
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={action.pending || modelId === undefined || runtimeId === undefined}
          >
            {deployment ? "Save changes" : "Create deployment"}
          </button>
        </div>
      </form>
    </Card>
  );
}

function LogViewer({ deploymentId, onClose }: { deploymentId: number; onClose: () => void }) {
  const [lines, setLines] = useState<DeploymentLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastId = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await api.deployments.logs(deploymentId, lastId.current);
        if (!cancelled && next.length > 0) {
          lastId.current = next[next.length - 1]?.id ?? lastId.current;
          setLines((current) => [...current, ...next]);
        }
        setError(null);
      } catch (caught) {
        setError(errorMessage(caught));
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [deploymentId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [lines.length]);

  return (
    <Card
      title="Runtime output"
      actions={
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      }
    >
      <Alert message={error} />
      <pre className="log">
        {lines.length === 0 && "No output captured yet."}
        {lines.map((line) => (
          <div key={line.id} title={formatDateTime(line.created_at)}>
            {line.line}
          </div>
        ))}
        <div ref={endRef} />
      </pre>
    </Card>
  );
}
