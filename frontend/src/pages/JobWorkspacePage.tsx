import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type {
  ConversationSummary,
  JobDetail,
  LiveWrite,
  OutputDocument,
  Revision,
} from "../api/types";
import {
  ConversationPanel,
  type ConversationSelection,
  type PendingHighlight,
} from "../components/ConversationPanel";
import { DocumentViewer, type ViewMode } from "../components/DocumentViewer";
import { Markdown } from "../components/Markdown";
import { Alert, Badge, EmptyState, StatusBadge } from "../components/ui";
import { useAction, useResource } from "../hooks/useResource";
import { downloadText, formatForName, formatLabel } from "../lib/files";
import { formatDateTime, formatDuration, formatNumber } from "../lib/format";
import type { Passage, TextSelection } from "../lib/highlights";

export function JobWorkspacePage() {
  const jobId = Number(useParams().jobId);
  const [busy, setBusy] = useState(false);
  const job = useResource(() => api.jobs.get(jobId), `job-${jobId}`, busy ? 1500 : 10000);
  const documents = useResource(
    () => api.jobs.documents(jobId),
    `documents-${jobId}`,
    busy ? 1500 : undefined,
  );
  const refreshJob = job.refresh;
  const refreshDocuments = documents.refresh;

  useEffect(() => {
    if (job.data) {
      setBusy(job.data.busy);
    }
  }, [job.data]);

  // Pick up the final state of the documents once the agent stops working.
  useEffect(() => {
    if (!busy) {
      void refreshDocuments();
    }
  }, [busy, refreshDocuments]);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshJob(), refreshDocuments()]);
  }, [refreshJob, refreshDocuments]);

  if (!job.data || !documents.data) {
    return job.error ? <Alert message={job.error} /> : <EmptyState>Loading…</EmptyState>;
  }
  return <Workspace key={jobId} job={job.data} documents={documents.data} onChanged={refreshAll} />;
}

function Workspace({
  job,
  documents,
  onChanged,
}: {
  job: JobDetail;
  documents: OutputDocument[];
  onChanged: () => Promise<void>;
}) {
  const main = job.conversations.find((conversation) => conversation.kind === "main");
  const running = job.conversations.find((conversation) => conversation.status === "running");
  const [conversation, setConversation] = useState<ConversationSelection>(main?.id ?? null);
  const [selectedPath, setSelectedPath] = useState<string | null>(documents[0]?.path ?? null);
  const [follow, setFollow] = useState(true);
  const [pendingHighlight, setPendingHighlight] = useState<PendingHighlight | null>(null);
  const live = useLiveWrite(running?.id);

  useEffect(() => {
    if (conversation === null && main) {
      setConversation(main.id);
    }
  }, [conversation, main]);

  useEffect(() => {
    if (follow && live?.path) {
      setSelectedPath(live.path);
    }
  }, [follow, live?.path]);

  useEffect(() => {
    if (selectedPath === null && documents[0]) {
      setSelectedPath(documents[0].path);
    }
  }, [selectedPath, documents]);

  const threads = job.conversations.filter((item) => item.kind === "highlight");
  const selectConversation = (selection: ConversationSelection) => {
    setConversation(selection);
    const thread = threads.find((item) => item.id === selection);
    const document = documents.find((item) => item.id === thread?.document_id);
    if (document) {
      setFollow(false);
      setSelectedPath(document.path);
    }
  };

  const discuss = (document: OutputDocument, selection: TextSelection) => {
    setPendingHighlight({
      document_id: document.id,
      document_path: document.path,
      quote: selection.quote,
      prefix: selection.prefix,
      suffix: selection.suffix,
    });
    setConversation("highlight");
  };

  const activeThread = threads.find((item) => item.id === conversation);

  return (
    <div className="workspace">
      <WorkspaceHeader job={job} onChanged={onChanged} />
      <div className="workspace-grid">
        <section className="documents-pane">
          <DocumentsPane
            job={job}
            documents={documents}
            selectedPath={selectedPath}
            onSelectPath={(path) => {
              setFollow(false);
              setSelectedPath(path);
            }}
            live={live}
            follow={follow}
            onFollowChange={setFollow}
            threads={threads}
            activeThread={activeThread}
            pendingHighlight={conversation === "highlight" ? pendingHighlight : null}
            onDiscuss={discuss}
            onChanged={onChanged}
          />
        </section>
        <ConversationPanel
          job={job}
          selected={conversation}
          onSelect={selectConversation}
          pendingHighlight={pendingHighlight}
          onCancelHighlight={() => {
            setPendingHighlight(null);
            setConversation(main?.id ?? null);
          }}
          onChanged={onChanged}
        />
      </div>
      <BriefPanel job={job} />
    </div>
  );
}

/** The document the agent is writing right now, streamed from the running conversation. */
function useLiveWrite(conversationId: number | undefined): LiveWrite | null {
  const conversation = useResource(
    () => (conversationId ? api.conversations.get(conversationId) : Promise.resolve(null)),
    `live-${conversationId ?? "none"}`,
    conversationId ? 1000 : undefined,
  );
  return conversation.data?.status === "running"
    ? (conversation.data.draft?.writing ?? null)
    : null;
}

function WorkspaceHeader({ job, onChanged }: { job: JobDetail; onChanged: () => Promise<void> }) {
  const navigate = useNavigate();
  const agents = useResource(api.agents.list, "agents", 15000);
  const action = useAction();
  const run = (operation: () => Promise<unknown>) =>
    void action.run(async () => {
      await operation();
      await onChanged();
    });
  const agent = agents.data?.find((item) => item.id === job.agent_id);

  return (
    <header className="workspace-header">
      <div>
        <div className="actions">
          <h1>{job.title}</h1>
          <StatusBadge status={job.status} />
          {job.busy && <Badge tone="info">writing</Badge>}
        </div>
        <p className="muted small">
          {job.started_at ? `Started ${formatDateTime(job.started_at)}` : "Not started"}
          {job.finished_at && ` · completed ${formatDateTime(job.finished_at)}`}
          {job.started_at && ` · ${formatDuration(job.working_seconds)} working time`}
        </p>
      </div>
      <div className="actions">
        <label className="inline-field">
          <span className="muted small">Agent</span>
          <select
            value={job.agent_id ?? ""}
            disabled={action.pending}
            onChange={(event) =>
              run(() =>
                api.jobs.assign(job.id, event.target.value ? Number(event.target.value) : null),
              )
            }
          >
            <option value="">Unassigned</option>
            {(agents.data ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {agent && agent.deployment_status !== "running" && (
          <Badge tone="warning">
            {agent.deployment_name} is {agent.deployment_status}
          </Badge>
        )}
        <Link className="button-link inline" to={`/jobs/${job.id}/edit`}>
          Edit job
        </Link>
        {job.status === "draft" && (
          <button
            type="button"
            disabled={action.pending || job.agent_id === null}
            onClick={() => run(() => api.jobs.start(job.id))}
          >
            Start job
          </button>
        )}
        {job.status === "active" && (
          <>
            <button
              type="button"
              className="secondary"
              disabled={action.pending}
              onClick={() => run(() => api.jobs.complete(job.id))}
            >
              Mark complete
            </button>
            <button
              type="button"
              className="danger"
              disabled={action.pending}
              onClick={() => run(() => api.jobs.cancel(job.id))}
            >
              Cancel job
            </button>
          </>
        )}
        {(job.status === "completed" || job.status === "cancelled") && (
          <button
            type="button"
            className="secondary"
            disabled={action.pending}
            onClick={() => run(() => api.jobs.reopen(job.id))}
          >
            Reopen
          </button>
        )}
        <button
          type="button"
          className="danger"
          disabled={action.pending || job.busy}
          onClick={() => {
            if (window.confirm(`Delete job "${job.title}" and all of its outputs?`)) {
              void action.run(async () => {
                await api.jobs.remove(job.id);
                navigate("/jobs");
              });
            }
          }}
        >
          Delete
        </button>
      </div>
      <Alert message={action.error ?? agents.error} />
    </header>
  );
}

type PaneView = "document" | "edit" | "history";

function DocumentsPane({
  job,
  documents,
  selectedPath,
  onSelectPath,
  live,
  follow,
  onFollowChange,
  threads,
  activeThread,
  pendingHighlight,
  onDiscuss,
  onChanged,
}: {
  job: JobDetail;
  documents: OutputDocument[];
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
  live: LiveWrite | null;
  follow: boolean;
  onFollowChange: (follow: boolean) => void;
  threads: ConversationSummary[];
  activeThread: ConversationSummary | undefined;
  pendingHighlight: PendingHighlight | null;
  onDiscuss: (document: OutputDocument, selection: TextSelection) => void;
  onChanged: () => Promise<void>;
}) {
  const [mode, setMode] = useState<ViewMode>("preview");
  const [view, setView] = useState<PaneView>("document");
  const written = new Set(documents.map((document) => document.path));
  const tabs = [
    ...documents.map((document) => document.path),
    ...job.requested_outputs.map((output) => output.path).filter((path) => !written.has(path)),
  ];
  if (live?.path && !tabs.includes(live.path)) {
    tabs.push(live.path);
  }
  const document = documents.find((item) => item.path === selectedPath);
  const isLive = live !== null && live.path === selectedPath;

  useEffect(() => {
    setView("document");
  }, [selectedPath]);

  const passages = useMemo(
    () =>
      threads
        .filter((thread) => !thread.resolved && thread.document_id === document?.id && thread.quote)
        .map((thread) => ({ quote: thread.quote ?? "", prefix: thread.prefix })),
    [threads, document?.id],
  );
  const activePassage: Passage | null =
    pendingHighlight && pendingHighlight.document_id === document?.id
      ? { quote: pendingHighlight.quote, prefix: pendingHighlight.prefix }
      : activeThread && activeThread.document_id === document?.id && activeThread.quote
        ? { quote: activeThread.quote, prefix: activeThread.prefix }
        : null;

  return (
    <>
      <div className="document-tabs" role="tablist">
        {tabs.map((path) => (
          <button
            key={path}
            type="button"
            role="tab"
            aria-selected={path === selectedPath}
            className={`document-tab${path === selectedPath ? " active" : ""}${written.has(path) ? "" : " pending"}`}
            onClick={() => onSelectPath(path)}
          >
            {path}
            {live?.path === path && <span className="live-dot" aria-label="being written" />}
          </button>
        ))}
        {tabs.length === 0 && (
          <span className="muted small">
            {job.status === "draft" ? "No outputs yet." : "The agent has not written anything yet."}
          </span>
        )}
      </div>
      {selectedPath && (
        <div className="document-toolbar">
          <div className="segmented" role="group" aria-label="View">
            <button
              type="button"
              className={mode === "preview" && view === "document" ? "active" : ""}
              onClick={() => {
                setMode("preview");
                setView("document");
              }}
            >
              Preview
            </button>
            <button
              type="button"
              className={mode === "source" && view === "document" ? "active" : ""}
              onClick={() => {
                setMode("source");
                setView("document");
              }}
            >
              Source
            </button>
            {document && (
              <>
                <button
                  type="button"
                  className={view === "edit" ? "active" : ""}
                  onClick={() => setView("edit")}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className={view === "history" ? "active" : ""}
                  onClick={() => setView("history")}
                >
                  History ({document.revision_count})
                </button>
              </>
            )}
          </div>
          <div className="actions">
            {job.busy && (
              <label className="inline-field small">
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(event) => onFollowChange(event.target.checked)}
                />
                Follow the agent
              </label>
            )}
            {document && (
              <>
                <span className="muted small">
                  {formatLabel(document.format)} · {formatNumber(document.word_count)} words
                </span>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => downloadText(document.path, document.content, document.format)}
                >
                  Download
                </button>
              </>
            )}
          </div>
        </div>
      )}
      {!selectedPath ? (
        <EmptyState>
          {job.status === "draft"
            ? "Start the job to have the agent write the outputs."
            : "Outputs appear here as the agent writes them."}
        </EmptyState>
      ) : isLive ? (
        <DocumentViewer
          content={live.content}
          format={document?.format ?? formatForName(live.path)}
          mode={mode}
          live
        />
      ) : !document ? (
        <EmptyState>{selectedPath} has not been written yet.</EmptyState>
      ) : view === "edit" ? (
        <DocumentEditor
          key={document.id}
          document={document}
          onDone={async () => {
            setView("document");
            await onChanged();
          }}
          onCancel={() => setView("document")}
        />
      ) : view === "history" ? (
        <RevisionHistory
          key={document.id}
          document={document}
          mode={mode}
          onRestored={async () => {
            setView("document");
            await onChanged();
          }}
        />
      ) : (
        <>
          {job.status !== "draft" && job.status !== "cancelled" && (
            <p className="muted small hint">
              Select any passage to discuss it with the agent, or use the chat to change the whole
              document.
            </p>
          )}
          <DocumentViewer
            content={document.content}
            format={document.format}
            mode={mode}
            passages={passages}
            activePassage={activePassage}
            onDiscuss={
              job.status === "active" || job.status === "completed"
                ? (selection) => onDiscuss(document, selection)
                : undefined
            }
          />
        </>
      )}
    </>
  );
}

function DocumentEditor({
  document,
  onDone,
  onCancel,
}: {
  document: OutputDocument;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [content, setContent] = useState(document.content);
  const action = useAction();
  return (
    <div className="document-editor">
      <textarea
        value={content}
        onChange={(event) => setContent(event.target.value)}
        aria-label={`Edit ${document.path}`}
        spellCheck
      />
      <Alert message={action.error} />
      <div className="actions form-actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          disabled={action.pending || content === document.content}
          onClick={() =>
            void action.run(async () => {
              await api.documents.update(document.id, content);
              await onDone();
            })
          }
        >
          Save as new revision
        </button>
      </div>
    </div>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  agent: "Agent",
  proposal: "Applied proposal",
  user: "Your edit",
  restore: "Restored",
};

function RevisionHistory({
  document,
  mode,
  onRestored,
}: {
  document: OutputDocument;
  mode: ViewMode;
  onRestored: () => Promise<void>;
}) {
  const revisions = useResource(
    () => api.documents.revisions(document.id),
    `revisions-${document.id}-${document.revision_count}`,
  );
  const [shown, setShown] = useState<Revision | null>(null);
  const action = useAction();

  return (
    <div className="history">
      <div className="history-list">
        <Alert message={revisions.error ?? action.error} />
        {(revisions.data ?? []).map((revision) => (
          <button
            key={revision.id}
            type="button"
            className={`history-item${shown?.id === revision.id ? " active" : ""}`}
            onClick={() =>
              void action.run(async () =>
                setShown(await api.documents.revision(document.id, revision.id)),
              )
            }
          >
            <span>
              <strong>Revision {revision.number}</strong>{" "}
              <span className="muted small">{SOURCE_LABELS[revision.source]}</span>
            </span>
            <span className="muted small">
              {formatDateTime(revision.created_at)} · {formatNumber(revision.word_count)} words
            </span>
            {revision.summary && <span className="small">{revision.summary}</span>}
          </button>
        ))}
      </div>
      <div className="history-preview">
        {shown ? (
          <>
            <div className="actions">
              <span className="muted small">Revision {shown.number}</span>
              <button
                type="button"
                disabled={action.pending || shown.content === document.content}
                onClick={() =>
                  void action.run(async () => {
                    await api.documents.restore(document.id, shown.id);
                    await onRestored();
                  })
                }
              >
                Restore this revision
              </button>
            </div>
            <DocumentViewer content={shown.content} format={document.format} mode={mode} />
          </>
        ) : (
          <EmptyState>Choose a revision to view it.</EmptyState>
        )}
      </div>
    </div>
  );
}

function BriefPanel({ job }: { job: JobDetail }) {
  const samples = useResource(api.samples.list, "samples");
  const read = new Set(job.samples_read);
  const written = new Set(job.documents.map((document) => document.path));
  const chosen = (samples.data ?? []).filter((sample) => job.sample_ids.includes(sample.id));

  return (
    <details className="brief card">
      <summary>
        <h2>Brief and run details</h2>
        <span className="muted small">
          {job.sample_ids.length} samples ({job.samples_read.length} read) · {job.contexts.length}{" "}
          context documents · {job.llm_calls} model calls ·{" "}
          {formatNumber(job.prompt_tokens + job.completion_tokens)} tokens
        </span>
      </summary>
      <div className="brief-grid">
        <div>
          <h3>Instructions</h3>
          <Markdown>{job.instructions}</Markdown>
          {job.agent_summary && (
            <>
              <h3>Agent summary</h3>
              <p>{job.agent_summary}</p>
            </>
          )}
        </div>
        <div>
          <h3>Writing samples</h3>
          {chosen.length === 0 && <p className="muted small">None chosen.</p>}
          <ul className="plain-list">
            {chosen.map((sample) => (
              <li key={sample.id}>
                {sample.title}{" "}
                {job.status !== "draft" &&
                  (read.has(sample.id) ? (
                    <Badge tone="success">read</Badge>
                  ) : (
                    <Badge tone="warning">not read</Badge>
                  ))}
              </li>
            ))}
          </ul>
          <h3>Context</h3>
          {job.contexts.length === 0 && <p className="muted small">None.</p>}
          {job.contexts.map((context) => (
            <details key={context.id} className="context-item">
              <summary>{context.title}</summary>
              <pre className="code">{context.content}</pre>
            </details>
          ))}
          <h3>Requested outputs</h3>
          {job.requested_outputs.length === 0 && <p className="muted small">Left to the agent.</p>}
          <ul className="plain-list">
            {job.requested_outputs.map((output) => (
              <li key={output.path}>
                <code>{output.path}</code> {output.description}{" "}
                {written.has(output.path) && <Badge tone="success">written</Badge>}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3>Run</h3>
          <dl className="details">
            <dt>Model calls</dt>
            <dd>{job.llm_calls}</dd>
            <dt>Tool calls</dt>
            <dd>{job.tool_calls}</dd>
            <dt>Prompt tokens</dt>
            <dd>{formatNumber(job.prompt_tokens)}</dd>
            <dt>Completion tokens</dt>
            <dd>{formatNumber(job.completion_tokens)}</dd>
            <dt>Working time</dt>
            <dd>{formatDuration(job.working_seconds)}</dd>
            {Object.entries(job.settings_snapshot ?? {}).map(([key, value]) => (
              <Fragment key={key}>
                <dt>{key.replace(/_/g, " ")}</dt>
                <dd>{String(value ?? "-")}</dd>
              </Fragment>
            ))}
          </dl>
        </div>
      </div>
    </details>
  );
}
