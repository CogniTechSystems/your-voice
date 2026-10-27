import { useEffect, useMemo, useRef } from "react";

import type { ChatMessage, Draft, Proposal, StoredToolCall } from "../api/types";
import { useAction } from "../hooks/useResource";
import { Markdown } from "./Markdown";
import { Reasoning } from "./Reasoning";
import { Alert, EmptyState, StatusBadge } from "./ui";

const PROPOSAL_RESULT = /^Proposal (\d+) /;

export interface ProposalActions {
  apply: (proposal: Proposal) => Promise<unknown>;
  reject: (proposal: Proposal) => Promise<unknown>;
  disabled: boolean;
}

export function MessageList({
  messages,
  proposals,
  proposalActions,
  running,
  draft,
  empty,
}: {
  messages: ChatMessage[];
  proposals: Proposal[];
  proposalActions: ProposalActions;
  running: boolean;
  draft: Draft | null;
  empty: string;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const results = useMemo(() => {
    const byCallId = new Map<string, ChatMessage>();
    for (const message of messages) {
      if (message.role === "tool" && message.tool_call_id) {
        byCallId.set(message.tool_call_id, message);
      }
    }
    return byCallId;
  }, [messages]);
  const proposalsById = useMemo(
    () => new Map(proposals.map((proposal) => [proposal.id, proposal])),
    [proposals],
  );

  const proposalStates = proposals.map((proposal) => proposal.status).join();
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages.length, running, draft?.content.length, proposalStates]);

  return (
    <div className="messages">
      {messages.length === 0 && <EmptyState>{empty}</EmptyState>}
      {messages
        .filter((message) => message.role !== "tool")
        .map((message) =>
          message.role === "user" ? (
            <div key={message.id} className="message message-user">
              {message.content}
            </div>
          ) : (
            <AssistantMessage
              key={message.id}
              message={message}
              results={results}
              proposals={proposalsById}
              proposalActions={proposalActions}
            />
          ),
        )}
      {running && <DraftMessage draft={draft} />}
      <div ref={endRef} />
    </div>
  );
}

function DraftMessage({ draft }: { draft: Draft | null }) {
  if (!draft || (!draft.reasoning && !draft.content && !draft.writing)) {
    return (
      <div className="message message-pending">
        Reading the conversation… Long prompts can take a while on local hardware.
      </div>
    );
  }
  return (
    <div className="message message-assistant message-draft">
      {draft.reasoning && <Reasoning text={draft.reasoning} live />}
      {draft.content && <Markdown>{draft.content}</Markdown>}
      {draft.writing && (
        <div className="tool-call">
          <code>
            write_document {draft.writing.path || "…"} · {draft.writing.content.split(/\s+/).length}{" "}
            words so far
          </code>
        </div>
      )}
      <div className="message-meta">Generating…</div>
    </div>
  );
}

function AssistantMessage({
  message,
  results,
  proposals,
  proposalActions,
}: {
  message: ChatMessage;
  results: Map<string, ChatMessage>;
  proposals: Map<number, Proposal>;
  proposalActions: ProposalActions;
}) {
  const details = [
    message.agent_name,
    message.latency_ms !== null ? `${(message.latency_ms / 1000).toFixed(1)}s` : null,
    message.completion_tokens !== null ? `${message.completion_tokens} tokens` : null,
  ].filter(Boolean);

  return (
    <div className="message message-assistant">
      {message.reasoning && <Reasoning text={message.reasoning} />}
      {message.content && <Markdown>{message.content}</Markdown>}
      {message.tool_calls?.map((call) => {
        const result = results.get(call.id);
        const proposalId = Number(result?.content?.match(PROPOSAL_RESULT)?.[1]);
        const proposal = call.name === "propose_revision" ? proposals.get(proposalId) : undefined;
        return proposal ? (
          <ProposalCard key={call.id} proposal={proposal} actions={proposalActions} />
        ) : (
          <ToolCallView key={call.id} call={call} result={result} />
        );
      })}
      {details.length > 0 && <div className="message-meta">{details.join(" · ")}</div>}
    </div>
  );
}

function ProposalCard({ proposal, actions }: { proposal: Proposal; actions: ProposalActions }) {
  const action = useAction();
  const pending = proposal.status === "pending";
  return (
    <div className={`proposal proposal-${proposal.status}`}>
      <div className="proposal-header">
        <strong>Proposed revision #{proposal.id}</strong>
        <StatusBadge status={proposal.status} />
      </div>
      {proposal.explanation && <p className="proposal-explanation">{proposal.explanation}</p>}
      <pre className="code code-removed">{proposal.original}</pre>
      <pre className="code code-added">{proposal.replacement}</pre>
      <Alert message={action.error} />
      {pending && (
        <div className="actions">
          <button
            type="button"
            disabled={actions.disabled || action.pending}
            onClick={() => void action.run(() => actions.apply(proposal))}
          >
            Apply
          </button>
          <button
            type="button"
            className="secondary"
            disabled={actions.disabled || action.pending}
            onClick={() => void action.run(() => actions.reject(proposal))}
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function parseArguments(call: StoredToolCall): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(call.arguments || "{}");
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function summariseCall(call: StoredToolCall, args: Record<string, unknown>): string {
  const target = args.path ?? args.sample_id ?? args.context_id ?? args.proposal_id;
  const label = call.name.replace(/_/g, " ");
  return target !== undefined ? `${label} ${String(target)}` : label;
}

function ToolCallView({ call, result }: { call: StoredToolCall; result?: ChatMessage }) {
  const args = parseArguments(call);
  const failed = result?.content?.startsWith("Error:") ?? false;
  const { content, original, replacement, ...rest } = args;

  return (
    <details className={`tool-call${failed ? " tool-call-failed" : ""}`}>
      <summary>
        <code>{summariseCall(call, args)}</code>
        {!result && <span className="muted small">running…</span>}
        {failed && <StatusBadge status="error" />}
      </summary>
      {original !== undefined && <pre className="code code-removed">{String(original)}</pre>}
      {replacement !== undefined && <pre className="code code-added">{String(replacement)}</pre>}
      {content !== undefined && <pre className="code tool-result">{String(content)}</pre>}
      {Object.keys(rest).length > 0 && <pre className="code">{JSON.stringify(rest, null, 2)}</pre>}
      {result?.content && <pre className="code tool-result">{result.content}</pre>}
    </details>
  );
}
