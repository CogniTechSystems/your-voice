import type {
  Agent,
  AgentWrite,
  ConversationDetail,
  Deployment,
  DeploymentLog,
  DeploymentWrite,
  Highlight,
  HubModel,
  JobDetail,
  JobSummary,
  JobWrite,
  LanguageModel,
  ModelDownloadRequest,
  OutputDocument,
  Proposal,
  RepositoryFile,
  Revision,
  RevisionSummary,
  Runtime,
  RuntimeWrite,
  Sample,
  SampleSummary,
  SampleWrite,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
}

function describeError(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return fallback;
  }
  const { detail } = body as { detail: unknown };
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => `${issue.loc.slice(1).join(".") || "request"}: ${issue.msg}`)
      .join("; ");
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, describeError(payload, response.statusText));
  }
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function query(parameters: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  hub: {
    search: (searchText: string, limit = 25) =>
      request<HubModel[]>("GET", `/hub/search${query({ query: searchText, limit })}`),
    files: (repoId: string, revision: string) =>
      request<RepositoryFile[]>("GET", `/hub/files${query({ repo_id: repoId, revision })}`),
  },
  models: {
    list: () => request<LanguageModel[]>("GET", "/models"),
    download: (payload: ModelDownloadRequest) => request<LanguageModel>("POST", "/models", payload),
    files: (id: number) => request<RepositoryFile[]>("GET", `/models/${id}/files`),
    remove: (id: number) => request<undefined>("DELETE", `/models/${id}`),
  },
  runtimes: {
    list: () => request<Runtime[]>("GET", "/runtimes"),
    create: (payload: RuntimeWrite) => request<Runtime>("POST", "/runtimes", payload),
    update: (id: number, payload: RuntimeWrite) =>
      request<Runtime>("PUT", `/runtimes/${id}`, payload),
    remove: (id: number) => request<undefined>("DELETE", `/runtimes/${id}`),
  },
  deployments: {
    list: () => request<Deployment[]>("GET", "/deployments"),
    create: (payload: DeploymentWrite) => request<Deployment>("POST", "/deployments", payload),
    update: (id: number, payload: DeploymentWrite) =>
      request<Deployment>("PUT", `/deployments/${id}`, payload),
    remove: (id: number) => request<undefined>("DELETE", `/deployments/${id}`),
    start: (id: number) => request<Deployment>("POST", `/deployments/${id}/start`),
    stop: (id: number) => request<Deployment>("POST", `/deployments/${id}/stop`),
    logs: (id: number, afterId = 0) =>
      request<DeploymentLog[]>("GET", `/deployments/${id}/logs${query({ after_id: afterId })}`),
  },
  samples: {
    list: () => request<SampleSummary[]>("GET", "/samples"),
    get: (id: number) => request<Sample>("GET", `/samples/${id}`),
    create: (payload: SampleWrite) => request<Sample>("POST", "/samples", payload),
    update: (id: number, payload: SampleWrite) => request<Sample>("PUT", `/samples/${id}`, payload),
    remove: (id: number) => request<undefined>("DELETE", `/samples/${id}`),
  },
  agents: {
    list: () => request<Agent[]>("GET", "/agents"),
    create: (payload: AgentWrite) => request<Agent>("POST", "/agents", payload),
    update: (id: number, payload: AgentWrite) => request<Agent>("PUT", `/agents/${id}`, payload),
    remove: (id: number) => request<undefined>("DELETE", `/agents/${id}`),
  },
  jobs: {
    list: (filters: { status?: string } = {}) =>
      request<JobSummary[]>("GET", `/jobs${query(filters)}`),
    get: (id: number) => request<JobDetail>("GET", `/jobs/${id}`),
    create: (payload: JobWrite) => request<JobDetail>("POST", "/jobs", payload),
    update: (id: number, payload: JobWrite) => request<JobDetail>("PUT", `/jobs/${id}`, payload),
    remove: (id: number) => request<undefined>("DELETE", `/jobs/${id}`),
    assign: (id: number, agentId: number | null) =>
      request<JobDetail>("PUT", `/jobs/${id}/agent`, { agent_id: agentId }),
    start: (id: number) => request<JobDetail>("POST", `/jobs/${id}/start`),
    complete: (id: number) => request<JobDetail>("POST", `/jobs/${id}/complete`),
    reopen: (id: number) => request<JobDetail>("POST", `/jobs/${id}/reopen`),
    cancel: (id: number) => request<JobDetail>("POST", `/jobs/${id}/cancel`),
    documents: (id: number) => request<OutputDocument[]>("GET", `/jobs/${id}/documents`),
    discuss: (id: number, highlight: Highlight, content: string) =>
      request<ConversationDetail>("POST", `/jobs/${id}/conversations`, {
        ...highlight,
        content,
      }),
  },
  documents: {
    update: (id: number, content: string) =>
      request<OutputDocument>("PUT", `/documents/${id}`, { content }),
    remove: (id: number) => request<undefined>("DELETE", `/documents/${id}`),
    revisions: (id: number) => request<RevisionSummary[]>("GET", `/documents/${id}/revisions`),
    revision: (id: number, revisionId: number) =>
      request<Revision>("GET", `/documents/${id}/revisions/${revisionId}`),
    restore: (id: number, revisionId: number) =>
      request<OutputDocument>("POST", `/documents/${id}/revisions/${revisionId}/restore`),
  },
  conversations: {
    get: (id: number) => request<ConversationDetail>("GET", `/conversations/${id}`),
    send: (id: number, content: string) =>
      request<ConversationDetail>("POST", `/conversations/${id}/messages`, { content }),
    cancel: (id: number) => request<undefined>("POST", `/conversations/${id}/cancel`),
    resolve: (id: number, resolved: boolean) =>
      request<ConversationDetail>("POST", `/conversations/${id}/resolve`, { resolved }),
    remove: (id: number) => request<undefined>("DELETE", `/conversations/${id}`),
  },
  proposals: {
    apply: (id: number) => request<Proposal>("POST", `/proposals/${id}/apply`),
    reject: (id: number) => request<Proposal>("POST", `/proposals/${id}/reject`),
  },
};
