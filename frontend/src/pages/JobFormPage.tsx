import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { DocumentFormat, JobDetail, JobWrite, SampleSummary } from "../api/types";
import { Alert, Card, EmptyState, Field, PageHeader, StatusBadge } from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";
import { ACCEPTED_FILES, readTextFiles } from "../lib/files";
import { formatNumber } from "../lib/format";

const EMPTY_JOB: JobWrite = {
  title: "",
  instructions: "",
  agent_id: null,
  sample_ids: [],
  contexts: [],
  requested_outputs: [],
};

const INSTRUCTIONS_PLACEHOLDER =
  "What should the agent write? For example: “Write a launch announcement for the project in " +
  "the README. Aim at developers who have never heard of it, keep it under 700 words, and end " +
  "with how to try it.”";

function toWrite(job: JobDetail): JobWrite {
  return {
    title: job.title,
    instructions: job.instructions,
    agent_id: job.agent_id,
    sample_ids: job.sample_ids,
    contexts: job.contexts.map(({ title, format, content }) => ({ title, format, content })),
    requested_outputs: job.requested_outputs,
  };
}

export function JobFormPage() {
  const { jobId } = useParams();
  const existingId = jobId ? Number(jobId) : undefined;
  const job = useResource(
    () => (existingId ? api.jobs.get(existingId) : Promise.resolve(null)),
    `job-form-${existingId ?? "new"}`,
  );
  const samples = useResource(api.samples.list, "samples");

  if (job.error) {
    return <Alert message={job.error} />;
  }
  if (job.data === undefined || samples.data === undefined) {
    return <EmptyState>Loading…</EmptyState>;
  }
  return <JobForm key={existingId ?? "new"} job={job.data} samples={samples.data} />;
}

function JobForm({ job, samples }: { job: JobDetail | null; samples: SampleSummary[] }) {
  const navigate = useNavigate();
  const agents = useResource(api.agents.list, "agents");
  const [values, setValues] = useState<JobWrite>(() =>
    job ? toWrite(job) : { ...EMPTY_JOB, sample_ids: samples.map((sample) => sample.id) },
  );
  const action = useAction();
  const update = (changes: Partial<JobWrite>) =>
    setValues((current) => ({ ...current, ...changes }));

  useEffect(() => {
    const first = agents.data?.[0];
    if (!job && first && values.agent_id === null) {
      update({ agent_id: first.id });
    }
    // Only preselect once, when the agent list first arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents.data]);

  const save = (start: boolean) =>
    void action.run(async () => {
      const saved = job ? await api.jobs.update(job.id, values) : await api.jobs.create(values);
      if (start) {
        await api.jobs.start(saved.id);
      }
      navigate(`/jobs/${saved.id}`);
    });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save(false);
  };

  const canStart = (!job || job.status === "draft") && values.agent_id !== null;

  return (
    <form className="job-form" onSubmit={submit}>
      <PageHeader
        title={job ? `Edit ${job.title}` : "New job"}
        description={
          job ? (
            <>
              <StatusBadge status={job.status} /> Changes apply to the agent’s next reply.
            </>
          ) : (
            "Describe what you need, add the background material and choose who writes it."
          )
        }
      />

      <Card title="Brief">
        <div className="form-grid">
          <Field label="Title">
            <input
              value={values.title}
              onChange={(event) => update({ title: event.target.value })}
              placeholder="Launch announcement"
              required
            />
          </Field>
          <Field
            label="Agent"
            hint={
              agents.data?.length === 0 ? (
                <>
                  No agents yet. <Link to="/agents">Create one</Link>.
                </>
              ) : (
                "You can also assign one later."
              )
            }
          >
            <select
              value={values.agent_id ?? ""}
              onChange={(event) =>
                update({ agent_id: event.target.value ? Number(event.target.value) : null })
              }
            >
              <option value="">Assign later</option>
              {(agents.data ?? []).map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name} ({agent.deployment_name}, {agent.deployment_status})
                </option>
              ))}
            </select>
          </Field>
          <div className="field-wide">
            <Field label="Instructions">
              <textarea
                rows={6}
                value={values.instructions}
                onChange={(event) => update({ instructions: event.target.value })}
                placeholder={INSTRUCTIONS_PLACEHOLDER}
                required
              />
            </Field>
          </div>
        </div>
      </Card>

      <SampleChooser
        samples={samples}
        selected={values.sample_ids}
        onChange={(sample_ids) => update({ sample_ids })}
      />
      <ContextEditor contexts={values.contexts} onChange={(contexts) => update({ contexts })} />
      <OutputEditor
        outputs={values.requested_outputs}
        onChange={(requested_outputs) => update({ requested_outputs })}
      />

      <Alert message={action.error} />
      <div className="actions form-actions">
        <button
          type="button"
          className="secondary"
          onClick={() => navigate(job ? `/jobs/${job.id}` : "/jobs")}
        >
          Cancel
        </button>
        <button
          type="submit"
          className={canStart ? "secondary" : undefined}
          disabled={action.pending}
        >
          {job ? "Save changes" : "Save as draft"}
        </button>
        {canStart && (
          <button type="button" disabled={action.pending} onClick={() => save(true)}>
            {job ? "Save and start" : "Create and start"}
          </button>
        )}
      </div>
    </form>
  );
}

function SampleChooser({
  samples,
  selected,
  onChange,
}: {
  samples: SampleSummary[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const chosen = new Set(selected);
  const words = samples
    .filter((sample) => chosen.has(sample.id))
    .reduce((total, sample) => total + sample.word_count, 0);
  const toggle = (id: number) =>
    onChange(chosen.has(id) ? selected.filter((item) => item !== id) : [...selected, id]);

  return (
    <Card
      title="Your voice"
      actions={
        samples.length > 0 && (
          <>
            <span className="muted small">
              {chosen.size} of {samples.length} chosen · {formatNumber(words)} words
            </span>
            <button
              type="button"
              className="secondary"
              onClick={() => onChange(samples.map((sample) => sample.id))}
            >
              All
            </button>
            <button type="button" className="secondary" onClick={() => onChange([])}>
              None
            </button>
          </>
        )
      }
    >
      <p className="muted small">
        The agent must read every chosen sample before it writes anything. Choose pieces close to
        what you want; local models have limited context, so fewer good samples beat many.
      </p>
      {samples.length === 0 ? (
        <EmptyState>
          No writing samples yet. <Link to="/samples">Add some</Link> so the agent can match your
          voice.
        </EmptyState>
      ) : (
        <div className="choice-list">
          {samples.map((sample) => (
            <label key={sample.id} className="choice">
              <input
                type="checkbox"
                checked={chosen.has(sample.id)}
                onChange={() => toggle(sample.id)}
              />
              <span>
                <strong>{sample.title}</strong>
                <span className="muted small"> · {formatNumber(sample.word_count)} words</span>
                <span className="muted small excerpt">{sample.excerpt}</span>
              </span>
            </label>
          ))}
        </div>
      )}
    </Card>
  );
}

function ContextEditor({
  contexts,
  onChange,
}: {
  contexts: JobWrite["contexts"];
  onChange: (contexts: JobWrite["contexts"]) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const change = (index: number, changes: Partial<JobWrite["contexts"][number]>) =>
    onChange(
      contexts.map((item, position) => (position === index ? { ...item, ...changes } : item)),
    );

  const upload = (event: ChangeEvent<HTMLInputElement>) => {
    readTextFiles(event.target.files)
      .then((files) => onChange([...contexts, ...files]))
      .catch((caught: unknown) => setError(String(caught)));
    event.target.value = "";
  };

  return (
    <Card
      title="Context"
      actions={
        <>
          <label className="button-like secondary">
            Upload files
            <input type="file" accept={ACCEPTED_FILES} multiple hidden onChange={upload} />
          </label>
          <button
            type="button"
            className="secondary"
            onClick={() => onChange([...contexts, { title: "", format: "markdown", content: "" }])}
          >
            Add context
          </button>
        </>
      }
    >
      <p className="muted small">
        Background the agent should work from: a project README, the goal of the piece, notes, facts
        that must be included.
      </p>
      <Alert message={error} />
      {contexts.length === 0 && <EmptyState>No context added.</EmptyState>}
      {contexts.map((item, index) => (
        <div className="repeater-item" key={index}>
          <div className="repeater-row">
            <Field label="Title">
              <input
                value={item.title}
                onChange={(event) => change(index, { title: event.target.value })}
                placeholder="Project README"
                required
              />
            </Field>
            <Field label="Format">
              <select
                value={item.format}
                onChange={(event) =>
                  change(index, { format: event.target.value as DocumentFormat })
                }
              >
                <option value="markdown">Markdown</option>
                <option value="html">HTML</option>
                <option value="text">Plain text</option>
              </select>
            </Field>
            <button
              type="button"
              className="danger"
              onClick={() => onChange(contexts.filter((_, position) => position !== index))}
            >
              Remove
            </button>
          </div>
          <textarea
            rows={8}
            value={item.content}
            onChange={(event) => change(index, { content: event.target.value })}
            aria-label={`Content of ${item.title || "context"}`}
            required
          />
        </div>
      ))}
    </Card>
  );
}

function OutputEditor({
  outputs,
  onChange,
}: {
  outputs: JobWrite["requested_outputs"];
  onChange: (outputs: JobWrite["requested_outputs"]) => void;
}) {
  const change = (index: number, changes: Partial<JobWrite["requested_outputs"][number]>) =>
    onChange(
      outputs.map((item, position) => (position === index ? { ...item, ...changes } : item)),
    );
  const add = (path: string) => onChange([...outputs, { path, description: "" }]);

  return (
    <Card
      title="Outputs"
      actions={
        <>
          <button type="button" className="secondary" onClick={() => add("article.md")}>
            Add Markdown
          </button>
          <button type="button" className="secondary" onClick={() => add("page.html")}>
            Add HTML
          </button>
          <button type="button" className="secondary" onClick={() => add("notes.txt")}>
            Add text
          </button>
        </>
      }
    >
      <p className="muted small">
        Name each file the agent should produce. The extension sets the format: <code>.md</code>,{" "}
        <code>.html</code> or <code>.txt</code>. Leave this empty to let the agent decide.
      </p>
      {outputs.map((item, index) => (
        <div className="repeater-row" key={index}>
          <Field label="File name">
            <input
              value={item.path}
              onChange={(event) => change(index, { path: event.target.value })}
              required
            />
          </Field>
          <Field label="Description">
            <input
              value={item.description}
              onChange={(event) => change(index, { description: event.target.value })}
              placeholder="What this file is for"
            />
          </Field>
          <button
            type="button"
            className="danger"
            onClick={() => onChange(outputs.filter((_, position) => position !== index))}
          >
            Remove
          </button>
        </div>
      ))}
    </Card>
  );
}
