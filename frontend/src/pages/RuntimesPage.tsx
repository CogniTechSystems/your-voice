import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Runtime, RuntimeKind, RuntimeWrite } from "../api/types";
import { Alert, Badge, Card, EmptyState, Field, PageHeader } from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";
import { EMPTY_RUNTIME, RUNTIME_PRESETS } from "../lib/runtimePresets";

const PLACEHOLDER_HELP =
  "Placeholders: {model_path} (selected file or model directory), {model_dir}, {host}, {port}, " +
  "{served_model_name}.";

function toWrite(runtime: Runtime): RuntimeWrite {
  return {
    name: runtime.name,
    description: runtime.description,
    kind: runtime.kind,
    command_template: runtime.command_template,
    base_url: runtime.base_url,
    health_path: runtime.health_path,
    startup_timeout_seconds: runtime.startup_timeout_seconds,
  };
}

export function RuntimesPage() {
  const runtimes = useResource(api.runtimes.list, "runtimes");
  const [editing, setEditing] = useState<Runtime | "new" | null>(null);
  const action = useAction();

  const remove = (runtime: Runtime) => {
    if (window.confirm(`Delete runtime ${runtime.name}?`)) {
      void action.run(async () => {
        await api.runtimes.remove(runtime.id);
        await runtimes.refresh();
      });
    }
  };

  return (
    <>
      <PageHeader
        title="Runtimes"
        description="Configured inference servers"
        actions={
          <button type="button" onClick={() => setEditing("new")}>
            Add runtime
          </button>
        }
      />
      {editing && (
        <RuntimeForm
          key={editing === "new" ? "new" : editing.id}
          runtime={editing === "new" ? undefined : editing}
          onDone={() => {
            setEditing(null);
            void runtimes.refresh();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <Card title="Configured runtimes">
        <Alert message={runtimes.error ?? action.error} />
        {runtimes.data?.length === 0 ? (
          <EmptyState>No runtimes configured. Add one to create deployments.</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Command or URL</th>
                <th>Health check</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(runtimes.data ?? []).map((runtime) => (
                <tr key={runtime.id}>
                  <td>
                    <strong>{runtime.name}</strong>
                    <div className="muted small">{runtime.description}</div>
                  </td>
                  <td>
                    <Badge tone={runtime.kind === "managed" ? "info" : "neutral"}>
                      {runtime.kind}
                    </Badge>
                  </td>
                  <td>
                    <code className="wrap">
                      {runtime.kind === "managed" ? runtime.command_template : runtime.base_url}
                    </code>
                  </td>
                  <td>
                    <code>{runtime.health_path}</code>
                  </td>
                  <td className="numeric actions">
                    <button type="button" className="secondary" onClick={() => setEditing(runtime)}>
                      Edit
                    </button>
                    <button type="button" className="danger" onClick={() => remove(runtime)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

function RuntimeForm({
  runtime,
  onDone,
  onCancel,
}: {
  runtime?: Runtime;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<RuntimeWrite>(runtime ? toWrite(runtime) : EMPTY_RUNTIME);
  const action = useAction();
  const update = (changes: Partial<RuntimeWrite>) => setValues({ ...values, ...changes });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      if (runtime) {
        await api.runtimes.update(runtime.id, values);
      } else {
        await api.runtimes.create(values);
      }
      onDone();
    });
  };

  return (
    <Card
      title={runtime ? `Edit ${runtime.name}` : "New runtime"}
      actions={
        !runtime && (
          <Field label="Start from a preset">
            <select
              defaultValue=""
              onChange={(event) => {
                const preset = RUNTIME_PRESETS[Number(event.target.value)];
                if (preset) {
                  setValues(preset.runtime);
                }
              }}
            >
              <option value="" disabled>
                Choose a preset
              </option>
              {RUNTIME_PRESETS.map((preset, index) => (
                <option key={preset.label} value={index}>
                  {preset.label}
                </option>
              ))}
            </select>
          </Field>
        )
      }
    >
      <form className="form-grid" onSubmit={submit}>
        <Field label="Name">
          <input
            value={values.name}
            onChange={(event) => update({ name: event.target.value })}
            required
          />
        </Field>
        <Field label="Type">
          <select
            value={values.kind}
            onChange={(event) => update({ kind: event.target.value as RuntimeKind })}
          >
            <option value="managed">Managed: launched by this application</option>
            <option value="external">External: already running</option>
          </select>
        </Field>
        <Field label="Description" hint="Optional notes shown in the runtime list.">
          <input
            value={values.description}
            onChange={(event) => update({ description: event.target.value })}
          />
        </Field>
        {values.kind === "managed" ? (
          <Field label="Command template" hint={PLACEHOLDER_HELP}>
            <textarea
              rows={3}
              value={values.command_template ?? ""}
              onChange={(event) => update({ command_template: event.target.value })}
              required
            />
          </Field>
        ) : (
          <Field label="Base URL" hint="The server root, without the /v1 suffix.">
            <input
              value={values.base_url ?? ""}
              onChange={(event) => update({ base_url: event.target.value })}
              placeholder="http://127.0.0.1:11434"
              required
            />
          </Field>
        )}
        <Field label="Health check path">
          <input
            value={values.health_path}
            onChange={(event) => update({ health_path: event.target.value })}
            required
          />
        </Field>
        <Field label="Startup timeout (seconds)">
          <input
            type="number"
            min={5}
            max={7200}
            value={values.startup_timeout_seconds}
            onChange={(event) => update({ startup_timeout_seconds: Number(event.target.value) })}
          />
        </Field>
        <Alert message={action.error} />
        <div className="actions form-actions">
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" disabled={action.pending}>
            {runtime ? "Save changes" : "Create runtime"}
          </button>
        </div>
      </form>
    </Card>
  );
}
