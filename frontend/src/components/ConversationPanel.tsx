import { useEffect, useState, type KeyboardEvent } from "react";

import { api } from "../api/client";
import type { ConversationSummary, Highlight, JobDetail, Proposal } from "../api/types";
import { useAction, useResource } from "../hooks/useResource";
import { MessageList, type ProposalActions } from "./ChatMessages";
import { Alert, Badge, EmptyState, StatusBadge } from "./ui";

const MAIN_SUGGESTIONS = [
  "Does this sound like me? Point out anything that doesn't.",
  "Tighten the whole piece by about 20%.",
  "Give me three alternative titles.",
];

const HIGHLIGHT_SUGGESTIONS = [
  "This doesn't sound like me. Rephrase it in my voice.",
  "Make this punchier.",
  "Expand on this with a concrete example.",
  "Cut this down.",
];

export interface PendingHighlight extends Highlight {
  document_path: string;
}

export type ConversationSelection = number | "highlight" | null;

/**
 * Chat about a job's outputs: the main conversation, which may edit any document directly, and
 * one conversation per highlighted passage, where changes are proposed before they are applied.
 */
export function ConversationPanel({
  job,
  selected,
  onSelect,
  pendingHighlight,
  onCancelHighlight,
  onChanged,
}: {
  job: JobDetail;
  selected: ConversationSelection;
  onSelect: (selection: ConversationSelection) => void;
  pendingHighlight: PendingHighlight | null;
  onCancelHighlight: () => void;
  onChanged: () => Promise<void>;
}) {
  const [showResolved, setShowResolved] = useState(false);
  const main = job.conversations.find((conversation) => conversation.kind === "main");
  const threads = job.conversations.filter((conversation) => conversation.kind === "highlight");
  const open = threads.filter((thread) => !thread.resolved).reverse();
  const resolved = threads.filter((thread) => thread.resolved).reverse();

  return (
    <aside className="conversation-panel" aria-label="Conversations">
      <div className="thread-list">
        {main ? (
          <ThreadButton
            active={selected === main.id}
            onClick={() => onSelect(main.id)}
            conversation={main}
            label="Whole job"
            detail={`${job.agent_name ?? "Agent"} · edits outputs directly`}
          />
        ) : (
          <p className="muted small">The conversation starts when the job is started.</p>
        )}
        {open.map((thread) => (
          <ThreadButton
            key={thread.id}
            active={selected === thread.id}
            onClick={() => onSelect(thread.id)}
            conversation={thread}
            label={`“${thread.quote ?? ""}”`}
            detail={thread.document_path ?? "Deleted document"}
          />
        ))}
        {resolved.length > 0 && (
          <button
            type="button"
            className="link-button small"
            onClick={() => setShowResolved(!showResolved)}
          >
            {showResolved ? "Hide" : "Show"} {resolved.length} resolved
          </button>
        )}
        {showResolved &&
          resolved.map((thread) => (
            <ThreadButton
              key={thread.id}
              active={selected === thread.id}
              onClick={() => onSelect(thread.id)}
              conversation={thread}
              label={`“${thread.quote ?? ""}”`}
              detail={thread.document_path ?? "Deleted document"}
            />
          ))}
      </div>
      {selected === "highlight" && pendingHighlight ? (
        <NewHighlight
          job={job}
          highlight={pendingHighlight}
          onCancel={onCancelHighlight}
          onCreated={async (id) => {
            onSelect(id);
            await onChanged();
          }}
        />
      ) : typeof selected === "number" ? (
        <ConversationView
          key={selected}
          conversationId={selected}
          job={job}
          onChanged={onChanged}
          onDeleted={() => onSelect(main?.id ?? null)}
        />
      ) : (
        <EmptyState>
          {job.status === "draft"
            ? "Start the job to have the agent write the outputs."
            : "Choose a conversation."}
        </EmptyState>
      )}
    </aside>
  );
}

function ThreadButton({
  conversation,
  label,
  detail,
  active,
  onClick,
}: {
  conversation: ConversationSummary;
  label: string;
  detail: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`thread${active ? " active" : ""}${conversation.resolved ? " resolved" : ""}`}
      onClick={onClick}
    >
      <span className="thread-label">{label}</span>
      <span className="thread-meta">
        {detail}
        {conversation.status !== "idle" && <StatusBadge status={conversation.status} />}
        {conversation.pending_proposals > 0 && (
          <Badge tone="warning">{conversation.pending_proposals} to review</Badge>
        )}
      </span>
    </button>
  );
}

function NewHighlight({
  job,
  highlight,
  onCancel,
  onCreated,
}: {
  job: JobDetail;
  highlight: PendingHighlight;
  onCancel: () => void;
  onCreated: (conversationId: number) => Promise<void>;
}) {
  const action = useAction();
  const send = (content: string) =>
    void action.run(async () => {
      const passage: Highlight = {
        document_id: highlight.document_id,
        quote: highlight.quote,
        prefix: highlight.prefix,
        suffix: highlight.suffix,
      };
      const conversation = await api.jobs.discuss(job.id, passage, content);
      await onCreated(conversation.id);
    });

  return (
    <div className="conversation">
      <div className="conversation-header">
        <div>
          <span className="eyebrow">New discussion · {highlight.document_path}</span>
          <blockquote className="quote">{highlight.quote}</blockquote>
        </div>
      </div>
      <p className="muted small">
        The agent discusses changes to this passage with you first, and proposes a revision you can
        apply or reject.
      </p>
      <div className="spacer" />
      <Composer
        placeholder="What would you like to change?"
        suggestions={HIGHLIGHT_SUGGESTIONS}
        disabled={false}
        note={
          job.busy
            ? "The agent is working on another message. Yours will be answered as soon as it finishes."
            : undefined
        }
        pending={action.pending}
        error={action.error}
        onSend={send}
        onCancel={onCancel}
      />
    </div>
  );
}

function ConversationView({
  conversationId,
  job,
  onChanged,
  onDeleted,
}: {
  conversationId: number;
  job: JobDetail;
  onChanged: () => Promise<void>;
  onDeleted: () => void;
}) {
  const [polling, setPolling] = useState(false);
  const conversation = useResource(
    () => api.conversations.get(conversationId),
    `conversation-${conversationId}`,
    polling ? 1000 : undefined,
  );
  const action = useAction();
  const status = conversation.data?.status;
  const refreshConversation = conversation.refresh;

  useEffect(() => {
    setPolling(status === "running" || status === "queued");
    if (status !== undefined) {
      void onChanged();
    }
  }, [status, onChanged]);

  // Another conversation, or the job itself, may finish a turn while this one is shown.
  useEffect(() => {
    void refreshConversation();
  }, [job.updated_at, refreshConversation]);

  if (!conversation.data) {
    return conversation.error ? (
      <Alert message={conversation.error} />
    ) : (
      <EmptyState>Loading…</EmptyState>
    );
  }
  const data = conversation.data;
  const running = data.status === "running";
  const waiting = running || data.status === "queued";
  const afterChange = async () => {
    await refreshConversation();
    await onChanged();
  };
  const proposalActions: ProposalActions = {
    apply: async (proposal: Proposal) => {
      await api.proposals.apply(proposal.id);
      await afterChange();
    },
    reject: async (proposal: Proposal) => {
      await api.proposals.reject(proposal.id);
      await afterChange();
    },
    disabled: false,
  };
  const closed = job.status === "cancelled" || job.status === "draft";

  const send = (content: string) =>
    void action.run(async () => {
      await api.conversations.send(data.id, content);
      setPolling(true);
      await afterChange();
    });

  return (
    <div className="conversation">
      {data.kind === "highlight" && (
        <div className="conversation-header">
          <div>
            <span className="eyebrow">{data.document_path ?? "Deleted document"}</span>
            <blockquote className="quote">{data.quote}</blockquote>
          </div>
          <div className="actions">
            <button
              type="button"
              className="secondary"
              disabled={action.pending}
              onClick={() =>
                void action.run(async () => {
                  await api.conversations.resolve(data.id, !data.resolved);
                  await afterChange();
                })
              }
            >
              {data.resolved ? "Reopen" : "Resolve"}
            </button>
            <button
              type="button"
              className="danger"
              disabled={action.pending || waiting}
              onClick={() => {
                if (window.confirm("Delete this discussion?")) {
                  void action.run(async () => {
                    await api.conversations.remove(data.id);
                    onDeleted();
                    await onChanged();
                  });
                }
              }}
            >
              Delete
            </button>
          </div>
        </div>
      )}
      <MessageList
        messages={data.messages}
        proposals={data.proposals}
        proposalActions={proposalActions}
        running={running}
        draft={data.draft}
        empty="No messages yet."
      />
      <Alert message={data.error} />
      <Composer
        placeholder={
          data.kind === "main"
            ? "Discuss the outputs. The agent updates them as you talk."
            : "Reply about this passage"
        }
        suggestions={data.kind === "main" && job.status === "completed" ? MAIN_SUGGESTIONS : []}
        disabled={closed}
        note={
          job.status === "cancelled"
            ? "The job was cancelled. Reopen it to continue."
            : data.status === "queued"
              ? "The agent is working on another message. Yours will be answered as soon as it finishes."
              : undefined
        }
        running={waiting}
        pending={action.pending}
        error={action.error}
        onSend={send}
        onStop={() => void api.conversations.cancel(data.id)}
      />
    </div>
  );
}

function Composer({
  placeholder,
  suggestions,
  disabled,
  note,
  running = false,
  pending,
  error,
  onSend,
  onStop,
  onCancel,
}: {
  placeholder: string;
  suggestions: string[];
  disabled: boolean;
  note?: string;
  running?: boolean;
  pending: boolean;
  error: string | null;
  onSend: (content: string) => void;
  onStop?: () => void;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState("");
  const blocked = disabled || running || pending;

  const send = (content: string) => {
    const text = content.trim();
    if (text && !blocked) {
      onSend(text);
      setDraft("");
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send(draft);
    }
  };

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        send(draft);
      }}
    >
      {suggestions.length > 0 && !blocked && (
        <div className="suggestions">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className="secondary small-button"
              onClick={() => send(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
      {note && <p className="muted small">{note}</p>}
      <Alert message={error} />
      <div className="composer-row">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={`${placeholder} · Enter to send, Shift+Enter for a new line`}
          rows={3}
          disabled={disabled || running}
        />
        <div className="composer-buttons">
          {running && onStop ? (
            <button type="button" className="secondary" onClick={onStop}>
              Stop
            </button>
          ) : (
            <button type="submit" disabled={!draft.trim() || blocked}>
              Send
            </button>
          )}
          {onCancel && (
            <button type="button" className="secondary" onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
