import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Agent, AgentWrite, Deployment } from "../api/types";
import { Alert, Card, EmptyState, Field, PageHeader, StatusBadge } from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";

const INSTRUCTIONS_HINT =
  "Optional. The role the agent plays, on top of matching your voice. For example: " +
  "“You write technical blog posts for developers. Prefer concrete examples to adjectives.”";

export function AgentsPage() {
  const agents = useResource(api.agents.list, "agents", 10000);
  const deployments = useResource(api.deployments.list, "deployments");
  const [editing, setEditing] = useState<Agent | "new" | null>(null);
  const action = useAction();

  const remove = (agent: Agent) => {
    if (window.confirm(`Delete agent ${agent.name}?`)) {
      void action.run(async () => {
        await api.agents.remove(agent.id);
        await agents.refresh();
      });
    }
  };

  return (
    <>
      <PageHeader
        title="Agents"
        description="Writers you can assign to jobs. Each agent pairs a deployed model with role instructions."
        actions={
          <button
            type="button"
            onClick={() => setEditing("new")}
            disabled={deployments.data?.length === 0}
          >
            Add agent
          </button>
        }
      />
      {deployments.data?.length === 0 && (
        <p className="muted">
          Create a deployment under <Link to="/admin/deployments">Deployments</Link> first.
        </p>
      )}
      {editing && (
        <AgentForm
          key={editing === "new" ? "new" : editing.id}
          agent={editing === "new" ? undefined : editing}
          deployments={deployments.data ?? []}
          onDone={() => {
            setEditing(null);
            void agents.refresh();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <Card title="Agents">
        <Alert message={agents.error ?? action.error} />
        {agents.data?.length === 0 ? (
          <EmptyState>No agents yet.</EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Deployment</th>
                <th>Model</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(agents.data ?? []).map((agent) => (
                <tr key={agent.id}>
                  <td>
                    <strong>{agent.name}</strong>
                    {agent.instructions && (
                      <div className="muted small excerpt">{agent.instructions}</div>
                    )}
                  </td>
                  <td>{agent.deployment_name}</td>
                  <td>{agent.model_repo_id}</td>
                  <td>
                    <StatusBadge status={agent.deployment_status} />
                  </td>
                  <td className="numeric actions">
                    <button type="button" className="secondary" onClick={() => setEditing(agent)}>
                      Edit
                    </button>
                    <button type="button" className="danger" onClick={() => remove(agent)}>
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

function AgentForm({
  agent,
  deployments,
  onDone,
  onCancel,
}: {
  agent?: Agent;
  deployments: Deployment[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<AgentWrite>(
    agent
      ? { name: agent.name, deployment_id: agent.deployment_id, instructions: agent.instructions }
      : { name: "", deployment_id: deployments[0]?.id ?? 0, instructions: "" },
  );
  const action = useAction();
  const update = (changes: Partial<AgentWrite>) => setValues({ ...values, ...changes });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      if (agent) {
        await api.agents.update(agent.id, values);
      } else {
        await api.agents.create(values);
      }
      onDone();
    });
  };

  return (
    <Card title={agent ? `Edit ${agent.name}` : "New agent"}>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Name">
          <input
            value={values.name}
            onChange={(event) => update({ name: event.target.value })}
            placeholder="Blog writer"
            required
          />
        </Field>
        <Field label="Deployment" hint="The model that does the writing.">
          <select
            value={values.deployment_id}
            onChange={(event) => update({ deployment_id: Number(event.target.value) })}
          >
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deployment.name} ({deployment.model_repo_id})
              </option>
            ))}
          </select>
        </Field>
        <div className="field-wide">
          <Field label="Role instructions" hint={INSTRUCTIONS_HINT}>
            <textarea
              rows={5}
              value={values.instructions}
              onChange={(event) => update({ instructions: event.target.value })}
            />
          </Field>
        </div>
        <Alert message={action.error} />
        <div className="actions form-actions">
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" disabled={action.pending}>
            {agent ? "Save changes" : "Create agent"}
          </button>
        </div>
      </form>
    </Card>
  );
}
