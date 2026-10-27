"""System prompts and conversion of stored messages into chat completion requests."""

from collections.abc import Sequence
from typing import Any

from app.models import ChatMessage, Conversation, ConversationKind, Job, JobStatus, MessageRole

VOICE_GUIDANCE = """\
Your job is to write in the voice of the person you work for. Their writing samples show that \
voice. Before writing anything, read every sample with read_sample and study it: tone and \
attitude, sentence length and rhythm, vocabulary, how paragraphs open and close, use of \
headings, lists and examples, spelling conventions, and what the author leaves out. Write as \
the author would write, not as an assistant would. Do not copy passages from the samples."""

NO_SAMPLES = "No writing samples were provided, so write in a clear, natural, direct voice."

FORMAT_GUIDANCE = """\
The file extension sets the format: .md for Markdown, .html for HTML and .txt for plain text. \
HTML outputs must be complete, standalone documents with any styling inline or in a <style> \
element and no scripts."""

ACTIVE_INSTRUCTIONS = """\
Work through the job:
1. Read every writing sample, then every context document.
2. Write each output with write_document, passing the complete content.
3. Refine with edit_document if needed.
4. Call finish_job with a short summary for the user.
If something essential is missing or unclear, ask the user instead of guessing."""

REVIEW_INSTRUCTIONS = """\
The user is reviewing your outputs with you. When they ask for a change, make it straight away \
with edit_document, or write_document for larger rewrites, then say briefly what you changed. \
Answer questions about the outputs directly. Stay in the author's voice."""

HIGHLIGHT_INSTRUCTIONS = """\
The user highlighted a passage and wants to discuss it with you. Do not change the document \
until you have agreed what to do:
- Discuss first. Work out what the user wants, offer alternatives or ask a question if their \
request is unclear.
- When there is a concrete change to make, call propose_revision with the exact passage from \
the document source (including any Markdown or HTML markup) and its replacement. The user \
reviews the proposal and can apply it themselves.
- Call apply_revision only after the user has clearly agreed to a specific proposal.
- Keep changes to the highlighted passage unless the user asks for more."""

QUOTE_CONTEXT_LENGTH = 300


def build_system_prompt(conversation: Conversation, document_limit: int) -> str:
    job = conversation.job
    agent = job.agent
    sections = [
        f"You are {agent.name if agent else 'a writer'}, a writing agent.",
        VOICE_GUIDANCE if job.samples else NO_SAMPLES,
    ]
    if agent and agent.instructions.strip():
        sections.append(f"Role instructions from the user:\n{agent.instructions.strip()}")
    sections.append(_job_brief(job))
    sections.append(FORMAT_GUIDANCE)

    if conversation.kind is ConversationKind.HIGHLIGHT:
        sections.append(HIGHLIGHT_INSTRUCTIONS)
        sections.append(_highlight_brief(conversation, document_limit))
    elif job.status is JobStatus.ACTIVE:
        sections.append(ACTIVE_INSTRUCTIONS)
    else:
        sections.append(REVIEW_INSTRUCTIONS)
    return "\n\n".join(sections)


def _job_brief(job: Job) -> str:
    lines = [f"Job: {job.title}", "", "Instructions from the user:", job.instructions.strip()]
    if job.samples:
        lines += ["", "Writing samples (read with read_sample):"]
        lines += [
            f"- {sample.id}: {sample.title} ({sample.word_count} words)"
            + (f". {sample.notes.strip()}" if sample.notes.strip() else "")
            for sample in job.samples
        ]
    if job.contexts:
        lines += ["", "Context documents (read with read_context):"]
        lines += [f"- {context.id}: {context.title}" for context in job.contexts]
    if job.requested_outputs:
        lines += ["", "Requested outputs:"]
        lines += [
            f"- {output['path']}"
            + (f": {output['description']}" if output.get("description") else "")
            for output in job.requested_outputs
        ]
    else:
        lines += ["", "No file names were requested. Choose short, descriptive ones."]
    if job.documents:
        lines += ["", "Current outputs (read with read_document):"]
        lines += [
            f"- {document.path} ({len(document.content.split())} words)"
            for document in job.documents
        ]
    return "\n".join(lines)


def _highlight_brief(conversation: Conversation, document_limit: int) -> str:
    document = conversation.document
    if document is None:
        return "The highlighted document has been deleted."
    prefix = (conversation.prefix or "")[-QUOTE_CONTEXT_LENGTH:]
    suffix = (conversation.suffix or "")[:QUOTE_CONTEXT_LENGTH]
    content = document.content
    if len(content) > document_limit:
        content = content[:document_limit] + "\n... (truncated, use read_document for the rest)"
    return (
        f"Highlighted document: {document.path}\n\n"
        "The highlighted passage, as displayed to the user with formatting removed:\n"
        f"<<<{conversation.quote or ''}>>>\n\n"
        f"Text just before it: <<<{prefix}>>>\n"
        f"Text just after it: <<<{suffix}>>>\n\n"
        f"Current source of {document.path}:\n<document>\n{content}\n</document>"
    )


def build_conversation(system_prompt: str, messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    """Convert stored messages into the OpenAI chat format.

    Tool calls without a recorded result, which can occur if a turn was interrupted, are
    omitted so the conversation remains valid.
    """
    answered = {message.tool_call_id for message in messages if message.role is MessageRole.TOOL}
    conversation: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for message in messages:
        if message.role is MessageRole.USER:
            conversation.append({"role": "user", "content": message.content or ""})
        elif message.role is MessageRole.ASSISTANT:
            entry: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            calls = [call for call in message.tool_calls or [] if call["id"] in answered]
            if calls:
                entry["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"]},
                    }
                    for call in calls
                ]
            conversation.append(entry)
        elif message.role is MessageRole.TOOL:
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content or "",
                }
            )
    return conversation
