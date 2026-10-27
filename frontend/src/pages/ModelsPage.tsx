import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { HubModel, LanguageModel } from "../api/types";
import {
  Alert,
  Card,
  EmptyState,
  Field,
  PageHeader,
  ProgressBar,
  StatusBadge,
} from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";
import { formatBytes, formatNumber } from "../lib/format";

const IN_PROGRESS = new Set(["queued", "downloading"]);

export function ModelsPage() {
  const [polling, setPolling] = useState(false);
  const models = useResource(api.models.list, "models", polling ? 2000 : undefined);
  const downloading = models.data?.some((model) => IN_PROGRESS.has(model.status)) ?? false;

  useEffect(() => setPolling(downloading), [downloading]);

  return (
    <>
      <PageHeader title="Models" description="Downloaded models and Hugging Face Hub" />
      <HubSearch
        onQueued={() => {
          setPolling(true);
          void models.refresh();
        }}
      />
      <Card title="Downloaded models">
        <Alert message={models.error} />
        {models.data?.length === 0 ? (
          <EmptyState>No models have been downloaded.</EmptyState>
        ) : (
          <ModelTable models={models.data ?? []} onChange={models.refresh} />
        )}
      </Card>
    </>
  );
}

function HubSearch({ onQueued }: { onQueued: () => void }) {
  const [searchText, setSearchText] = useState("");
  const [results, setResults] = useState<HubModel[]>();
  const [selected, setSelected] = useState<string>();
  const search = useAction();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void search.run(async () => setResults(await api.hub.search(searchText.trim())));
  };

  return (
    <Card title="Hugging Face Hub">
      <form className="inline-form" onSubmit={submit}>
        <input
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          placeholder="Search models, for example qwen2.5-coder gguf"
        />
        <button type="submit" disabled={search.pending}>
          Search
        </button>
        <button
          type="button"
          className="secondary"
          disabled={!searchText.includes("/")}
          onClick={() => setSelected(searchText.trim())}
        >
          Open repository
        </button>
      </form>
      <Alert message={search.error} />
      {results && results.length === 0 && <EmptyState>No models matched the search.</EmptyState>}
      {results && results.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Task</th>
              <th className="numeric">Downloads</th>
              <th className="numeric">Likes</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {results.map((result) => (
              <tr
                key={result.repo_id}
                className={result.repo_id === selected ? "selected" : undefined}
              >
                <td>
                  <code>{result.repo_id}</code>
                </td>
                <td>{result.pipeline_tag ?? "-"}</td>
                <td className="numeric">{formatNumber(result.downloads)}</td>
                <td className="numeric">{formatNumber(result.likes)}</td>
                <td className="numeric">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setSelected(result.repo_id)}
                  >
                    Choose files
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected && (
        <DownloadPanel
          key={selected}
          repoId={selected}
          onClose={() => setSelected(undefined)}
          onQueued={() => {
            setSelected(undefined);
            onQueued();
          }}
        />
      )}
    </Card>
  );
}

function splitPatterns(text: string): string[] {
  return text
    .split(",")
    .map((pattern) => pattern.trim())
    .filter(Boolean);
}

function DownloadPanel({
  repoId,
  onClose,
  onQueued,
}: {
  repoId: string;
  onClose: () => void;
  onQueued: () => void;
}) {
  const [revisionInput, setRevisionInput] = useState("main");
  const [revision, setRevision] = useState("main");
  const files = useResource(() => api.hub.files(repoId, revision), `${repoId}@${revision}`);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [patterns, setPatterns] = useState("");
  const download = useAction();

  const allowPatterns = [...chosen, ...splitPatterns(patterns)];
  const selectedBytes = (files.data ?? [])
    .filter((file) => allowPatterns.length === 0 || chosen.has(file.path))
    .reduce((total, file) => total + (file.size_bytes ?? 0), 0);

  const toggle = (path: string) => {
    const next = new Set(chosen);
    if (next.has(path)) {
      next.delete(path);
    } else {
      next.add(path);
    }
    setChosen(next);
  };

  const submit = (registerOnly: boolean) =>
    void download.run(async () => {
      await api.models.download({
        repo_id: repoId,
        revision,
        allow_patterns: allowPatterns.length ? allowPatterns : null,
        register_only: registerOnly,
      });
      onQueued();
    });

  return (
    <div className="panel">
      <div className="card-header">
        <h3>
          <code>{repoId}</code>
        </h3>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="form-grid">
        <Field label="Revision">
          <input
            value={revisionInput}
            onChange={(event) => setRevisionInput(event.target.value)}
            onBlur={() => setRevision(revisionInput.trim() || "main")}
          />
        </Field>
        <Field label="Additional patterns" hint="Comma separated, for example *Q4_K_M.gguf">
          <input value={patterns} onChange={(event) => setPatterns(event.target.value)} />
        </Field>
      </div>
      <Alert message={files.error} />
      <p className="muted small">
        Select individual files to download, or leave everything unselected to download the whole
        repository. Quantised GGUF repositories usually need only one weights file.
      </p>
      <div className="file-list">
        {(files.data ?? []).map((file) => (
          <label key={file.path} className="file-row">
            <input
              type="checkbox"
              checked={chosen.has(file.path)}
              onChange={() => toggle(file.path)}
            />
            <code>{file.path}</code>
            <span className="muted">{formatBytes(file.size_bytes)}</span>
          </label>
        ))}
      </div>
      <Alert message={download.error} />
      <div className="actions">
        <span className="muted small">
          {allowPatterns.length ? `${allowPatterns.length} selections` : "Entire repository"} ·{" "}
          {formatBytes(selectedBytes)}
          {patterns && " plus pattern matches"}
        </span>
        <button
          type="button"
          className="secondary"
          onClick={() => submit(true)}
          disabled={download.pending}
          title="Record the model for runtimes such as Ollama or LM Studio that manage their own files"
        >
          Register only
        </button>
        <button
          type="button"
          onClick={() => submit(false)}
          disabled={download.pending || !files.data}
        >
          Download
        </button>
      </div>
    </div>
  );
}

function ModelTable({
  models,
  onChange,
}: {
  models: LanguageModel[];
  onChange: () => Promise<void>;
}) {
  const action = useAction();

  const retry = (model: LanguageModel) =>
    void action.run(async () => {
      await api.models.download({
        repo_id: model.repo_id,
        revision: model.revision,
        allow_patterns: model.allow_patterns,
      });
      await onChange();
    });

  const remove = (model: LanguageModel) => {
    if (window.confirm(`Delete ${model.repo_id} and its files?`)) {
      void action.run(async () => {
        await api.models.remove(model.id);
        await onChange();
      });
    }
  };

  return (
    <>
      <Alert message={action.error} />
      <table>
        <thead>
          <tr>
            <th>Repository</th>
            <th>Files</th>
            <th>Status</th>
            <th>Size</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.id}>
              <td>
                <code>{model.repo_id}</code>
                <div className="muted small">
                  {model.revision} · {model.local_path}
                </div>
              </td>
              <td className="small">{model.allow_patterns?.join(", ") ?? "Entire repository"}</td>
              <td>
                <StatusBadge status={model.status} />
                {model.error && <div className="error-text small">{model.error}</div>}
              </td>
              <td className="progress-cell">
                {IN_PROGRESS.has(model.status) && model.total_bytes ? (
                  <ProgressBar value={model.downloaded_bytes / model.total_bytes} />
                ) : null}
                <span className="small">
                  {formatBytes(model.downloaded_bytes)}
                  {model.total_bytes ? ` of ${formatBytes(model.total_bytes)}` : ""}
                </span>
              </td>
              <td className="numeric actions">
                {model.status === "failed" && (
                  <button type="button" className="secondary" onClick={() => retry(model)}>
                    Retry
                  </button>
                )}
                <button
                  type="button"
                  className="danger"
                  disabled={IN_PROGRESS.has(model.status)}
                  onClick={() => remove(model)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
