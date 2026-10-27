export type DownloadStatus = "queued" | "downloading" | "ready" | "failed";
export type RuntimeKind = "managed" | "external";
export type DeploymentStatus = "stopped" | "starting" | "running" | "failed";
export type DocumentFormat = "markdown" | "html" | "text";
export type JobStatus = "draft" | "active" | "completed" | "cancelled";
export type ConversationKind = "main" | "highlight";
export type ConversationStatus = "idle" | "queued" | "running" | "error";
export type MessageRole = "user" | "assistant" | "tool";
export type ProposalStatus = "pending" | "applied" | "rejected" | "superseded";
export type RevisionSource = "agent" | "proposal" | "user" | "restore";

export interface HubModel {
  repo_id: string;
  downloads: number;
  likes: number;
  pipeline_tag: string | null;
  tags: string[];
}

export interface RepositoryFile {
  path: string;
  size_bytes: number | null;
}

export interface LanguageModel {
  id: number;
  repo_id: string;
  revision: string;
  allow_patterns: string[] | null;
  local_path: string;
  status: DownloadStatus;
  error: string | null;
  total_bytes: number | null;
  downloaded_bytes: number;
  completed_at: string | null;
  created_at: string;
}

export interface ModelDownloadRequest {
  repo_id: string;
  revision: string;
  allow_patterns: string[] | null;
  register_only?: boolean;
}

export interface RuntimeWrite {
  name: string;
  description: string;
  kind: RuntimeKind;
  command_template: string | null;
  base_url: string | null;
  health_path: string;
  startup_timeout_seconds: number;
}

export interface Runtime extends RuntimeWrite {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface DeploymentWrite {
  name: string;
  model_id: number;
  runtime_id: number;
  model_file: string | null;
  served_model_name: string | null;
  launch_args: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  request_timeout_seconds: number;
}

export interface Deployment extends DeploymentWrite {
  id: number;
  model_repo_id: string;
  runtime_name: string;
  status: DeploymentStatus;
  port: number | null;
  pid: number | null;
  error: string | null;
  started_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeploymentLog {
  id: number;
  line: string;
  created_at: string;
}

export interface SampleWrite {
  title: string;
  format: DocumentFormat;
  content: string;
  notes: string;
}

export interface SampleSummary {
  id: number;
  title: string;
  format: DocumentFormat;
  notes: string;
  word_count: number;
  excerpt: string;
  created_at: string;
  updated_at: string;
}

export interface Sample extends SampleSummary {
  content: string;
}

export interface AgentWrite {
  name: string;
  deployment_id: number;
  instructions: string;
}

export interface Agent extends AgentWrite {
  id: number;
  deployment_name: string;
  deployment_status: DeploymentStatus;
  model_repo_id: string;
  created_at: string;
  updated_at: string;
}

export interface ContextWrite {
  title: string;
  format: DocumentFormat;
  content: string;
}

export interface ContextDocument extends ContextWrite {
  id: number;
}

export interface RequestedOutput {
  path: string;
  description: string;
}

export interface JobWrite {
  title: string;
  instructions: string;
  agent_id: number | null;
  sample_ids: number[];
  contexts: ContextWrite[];
  requested_outputs: RequestedOutput[];
}

export interface JobSummary {
  id: number;
  title: string;
  status: JobStatus;
  agent_id: number | null;
  agent_name: string | null;
  busy: boolean;
  sample_count: number;
  document_count: number;
  started_at: string | null;
  finished_at: string | null;
  working_seconds: number;
  llm_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentSummary {
  id: number;
  job_id: number;
  path: string;
  format: DocumentFormat;
  word_count: number;
  revision_count: number;
  created_at: string;
  updated_at: string;
}

export interface OutputDocument extends DocumentSummary {
  content: string;
}

export interface RevisionSummary {
  id: number;
  number: number;
  source: RevisionSource;
  summary: string | null;
  conversation_id: number | null;
  word_count: number;
  created_at: string;
}

export interface Revision extends RevisionSummary {
  content: string;
}

export interface ConversationSummary {
  id: number;
  job_id: number;
  kind: ConversationKind;
  status: ConversationStatus;
  error: string | null;
  document_id: number | null;
  document_path: string | null;
  quote: string | null;
  prefix: string | null;
  suffix: string | null;
  resolved: boolean;
  message_count: number;
  pending_proposals: number;
  created_at: string;
  updated_at: string;
}

export interface JobDetail extends JobSummary {
  instructions: string;
  requested_outputs: RequestedOutput[];
  sample_ids: number[];
  samples_read: number[];
  contexts: ContextDocument[];
  documents: DocumentSummary[];
  conversations: ConversationSummary[];
  settings_snapshot: Record<string, unknown> | null;
  agent_summary: string | null;
}

export interface StoredToolCall {
  id: string;
  name: string;
  arguments: string;
}

export interface ChatMessage {
  id: number;
  role: MessageRole;
  content: string | null;
  reasoning: string | null;
  tool_calls: StoredToolCall[] | null;
  tool_call_id: string | null;
  tool_name: string | null;
  agent_name: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  created_at: string;
}

export interface Proposal {
  id: number;
  document_id: number;
  original: string;
  replacement: string;
  explanation: string;
  status: ProposalStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface LiveWrite {
  path: string;
  content: string;
}

export interface Draft {
  reasoning: string;
  content: string;
  writing: LiveWrite | null;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
  proposals: Proposal[];
  draft: Draft | null;
}

/** A passage selected in a document, with surrounding text to tell repeated passages apart. */
export interface Highlight {
  document_id: number;
  quote: string;
  prefix: string;
  suffix: string;
}
