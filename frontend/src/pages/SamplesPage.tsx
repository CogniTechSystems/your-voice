import { useState, type ChangeEvent, type FormEvent } from "react";

import { api } from "../api/client";
import type { DocumentFormat, Sample, SampleSummary, SampleWrite } from "../api/types";
import { Alert, Badge, Card, EmptyState, Field, PageHeader } from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";
import { ACCEPTED_FILES, formatLabel, readTextFiles } from "../lib/files";
import { formatDateTime, formatNumber } from "../lib/format";

const EMPTY_SAMPLE: SampleWrite = { title: "", format: "markdown", content: "", notes: "" };

export function SamplesPage() {
  const samples = useResource(api.samples.list, "samples");
  const [editing, setEditing] = useState<Sample | "new" | null>(null);
  const action = useAction();

  const upload = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    void action.run(async () => {
      for (const file of await readTextFiles(files)) {
        await api.samples.create({ ...file, notes: "" });
      }
      await samples.refresh();
    });
    event.target.value = "";
  };

  const edit = (sample: SampleSummary) =>
    void action.run(async () => setEditing(await api.samples.get(sample.id)));

  const remove = (sample: SampleSummary) => {
    if (window.confirm(`Delete writing sample "${sample.title}"?`)) {
      void action.run(async () => {
        await api.samples.remove(sample.id);
        await samples.refresh();
      });
    }
  };

  const totalWords = (samples.data ?? []).reduce((total, sample) => total + sample.word_count, 0);

  return (
    <>
      <PageHeader
        title="Writing samples"
        description="Articles and documents you have written. Agents read the samples chosen for a job before they start writing, and use them to match your voice."
        actions={
          <>
            <label className="button-like secondary">
              Upload files
              <input type="file" accept={ACCEPTED_FILES} multiple hidden onChange={upload} />
            </label>
            <button type="button" onClick={() => setEditing("new")}>
              Add sample
            </button>
          </>
        }
      />
      {editing && (
        <SampleForm
          key={editing === "new" ? "new" : editing.id}
          sample={editing === "new" ? undefined : editing}
          onDone={() => {
            setEditing(null);
            void samples.refresh();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <Card
        title="Your samples"
        actions={
          samples.data &&
          samples.data.length > 0 && (
            <span className="muted small">
              {samples.data.length} samples · {formatNumber(totalWords)} words
            </span>
          )
        }
      >
        <Alert message={samples.error ?? action.error} />
        {samples.data?.length === 0 ? (
          <EmptyState>
            No samples yet. Add a few pieces you are happy with, ideally of the kind you want
            written.
          </EmptyState>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Sample</th>
                <th>Format</th>
                <th className="numeric">Words</th>
                <th>Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(samples.data ?? []).map((sample) => (
                <tr key={sample.id}>
                  <td>
                    <strong>{sample.title}</strong>
                    {sample.notes && <div className="small">{sample.notes}</div>}
                    <div className="muted small excerpt">{sample.excerpt}</div>
                  </td>
                  <td>
                    <Badge>{formatLabel(sample.format)}</Badge>
                  </td>
                  <td className="numeric">{formatNumber(sample.word_count)}</td>
                  <td>{formatDateTime(sample.updated_at)}</td>
                  <td className="numeric actions">
                    <button type="button" className="secondary" onClick={() => edit(sample)}>
                      Edit
                    </button>
                    <button type="button" className="danger" onClick={() => remove(sample)}>
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

function SampleForm({
  sample,
  onDone,
  onCancel,
}: {
  sample?: Sample;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<SampleWrite>(
    sample
      ? { title: sample.title, format: sample.format, content: sample.content, notes: sample.notes }
      : EMPTY_SAMPLE,
  );
  const action = useAction();
  const update = (changes: Partial<SampleWrite>) => setValues({ ...values, ...changes });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      if (sample) {
        await api.samples.update(sample.id, values);
      } else {
        await api.samples.create(values);
      }
      onDone();
    });
  };

  return (
    <Card title={sample ? `Edit ${sample.title}` : "New writing sample"}>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Title">
          <input
            value={values.title}
            onChange={(event) => update({ title: event.target.value })}
            required
          />
        </Field>
        <Field label="Format">
          <select
            value={values.format}
            onChange={(event) => update({ format: event.target.value as DocumentFormat })}
          >
            <option value="markdown">Markdown</option>
            <option value="html">HTML</option>
            <option value="text">Plain text</option>
          </select>
        </Field>
        <Field
          label="Notes for the agent"
          hint="Optional. For example: where it was published, or what makes it typical of you."
        >
          <input value={values.notes} onChange={(event) => update({ notes: event.target.value })} />
        </Field>
        <div className="field-wide">
          <Field label="Content">
            <textarea
              rows={16}
              value={values.content}
              onChange={(event) => update({ content: event.target.value })}
              required
            />
          </Field>
        </div>
        <Alert message={action.error} />
        <div className="actions form-actions">
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" disabled={action.pending}>
            {sample ? "Save changes" : "Add sample"}
          </button>
        </div>
      </form>
    </Card>
  );
}
