import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { DefaultChatTransport, type UIMessage } from "ai";
import { useChat } from "@ai-sdk/react";
import { ExternalLink, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChatCitation, ChatMessage } from "@/lib/api";
import { ApiError, getAuthHeaders } from "@/lib/http";
import { env } from "@/lib/env";
import { supabase } from "@/lib/supabase";

type ChatUIMessage = UIMessage<
  unknown,
  { citation: ChatCitation; progress: { message: string } }
>;
type ChatFailureKind =
  | "auth"
  | "retrieval"
  | "grounding"
  | "provider"
  | "storage"
  | "network"
  | "timeout"
  | "unknown";

interface ChatFailure {
  kind: ChatFailureKind;
  title: string;
  description: string;
}

class ChatRequestFailure extends Error {
  readonly kind: ChatFailureKind;

  constructor(kind: ChatFailureKind, message: string) {
    super(message);
    this.name = "ChatRequestFailure";
    this.kind = kind;
  }
}

function responseDetail(body: string): string {
  let payload: unknown;
  try {
    payload = JSON.parse(body);
  } catch (error: unknown) {
    if (error instanceof SyntaxError) return "";
    throw error;
  }
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return "";
}

function failureKind(status: number, detail: string): ChatFailureKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 503) return "retrieval";
  if (status === 504) return "timeout";
  if (
    status === 502 &&
    detail.toLowerCase().includes("could not be verified")
  ) {
    return "grounding";
  }
  if (status === 502) return "provider";
  return "unknown";
}

async function chatFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    if (error instanceof TypeError) {
      throw new ChatRequestFailure(
        "network",
        "Could not reach Rag with Supabase . Check your connection and try again.",
      );
    }
    throw error;
  }
  if (response.ok) return response;

  const detail = responseDetail(await response.text());
  const kind = failureKind(response.status, detail);
  throw new ChatRequestFailure(kind, failureMessage(kind));
}

function failureMessage(kind: ChatFailureKind): string {
  switch (kind) {
    case "auth":
      return "Your sign-in session has expired or cannot access this conversation.";
    case "retrieval":
      return "Filing search is temporarily unavailable. Please try again.";
    case "grounding":
      return "The generated answer could not be verified against its sources. Rephrase the question and try again.";
    case "provider":
      return "The answer service could not complete this request. Please try again.";
    case "storage":
      return "The answer was generated but could not be saved. Please try again.";
    case "network":
      return "Could not reach Rag with Supabase . Check your connection and try again.";
    case "timeout":
      return "Preparing a verified answer took too long. Please try again.";
    case "unknown":
      return "Something went wrong while sending your message. Please try again.";
  }
}

function describeFailure(error: Error): ChatFailure | null {
  if (error instanceof DOMException && error.name === "AbortError") return null;

  let kind: ChatFailureKind = "unknown";
  if (error instanceof ChatRequestFailure) {
    kind = error.kind;
  } else if (error instanceof ApiError) {
    if (error.isNetworkError) kind = "network";
    else if (
      error.status === null ||
      error.status === 401 ||
      error.status === 403
    )
      kind = "auth";
    else if (error.status === 503) kind = "retrieval";
    else if (
      error.status === 502 &&
      error.message.toLowerCase().includes("could not be verified")
    ) {
      kind = "grounding";
    } else if (error.status === 502) kind = "provider";
  } else if (error instanceof TypeError) {
    kind = "network";
  }
  if (kind === "unknown") {
    const message = error.message.toLowerCase();
    if (message.includes("timed out")) kind = "timeout";
    else if (message.includes("could not be verified")) kind = "grounding";
    else if (message.includes("database is unavailable")) kind = "retrieval";
    else if (message.includes("provider failed")) kind = "provider";
    else if (message.includes("could not be saved")) kind = "storage";
    else if (message.includes("sign-in session")) kind = "auth";
  }

  const messages: Record<ChatFailureKind, Omit<ChatFailure, "kind">> = {
    auth: {
      title: "Sign-in required",
      description: failureMessage("auth"),
    },
    retrieval: {
      title: "Filing search unavailable",
      description: failureMessage("retrieval"),
    },
    grounding: {
      title: "Answer could not be verified",
      description: failureMessage("grounding"),
    },
    provider: {
      title: "Answer service unavailable",
      description: failureMessage("provider"),
    },
    storage: {
      title: "Answer could not be saved",
      description: failureMessage("storage"),
    },
    network: {
      title: "Connection problem",
      description: failureMessage("network"),
    },
    timeout: {
      title: "Request timed out",
      description: failureMessage("timeout"),
    },
    unknown: {
      title: "Message not sent",
      description: failureMessage("unknown"),
    },
  };
  return { kind, ...messages[kind] };
}

function toUiMessages(messages: ChatMessage[]): ChatUIMessage[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    parts: [
      { type: "text", text: message.content },
      ...message.citations.map((citation) => ({
        type: "data-citation" as const,
        id: citation.chunk_id,
        data: citation,
      })),
    ],
  }));
}

function citationLocation(citation: ChatCitation): string {
  if (citation.page_references.length > 0) {
    return `Page ${citation.page_references.join(", ")}`;
  }
  return citation.section || "Location unavailable";
}

function citationLabel(citation: ChatCitation): string {
  return `${citation.ticker} · ${citation.filing_type} · ${citation.filing_date}`;
}

function formatFilingDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

interface CitationSourcePanelProps {
  citation: ChatCitation;
  onClose: () => void;
}

function CitationSourcePanel({ citation, onClose }: CitationSourcePanelProps) {
  const excerpt = citation.quote?.trim() || citation.passage;
  return (
    <aside
      id="citation-source-panel"
      aria-label="Citation source passage"
      className="fixed inset-x-0 bottom-0 z-20 max-h-[75svh] overflow-y-auto border-t bg-card p-5 shadow-xl md:static md:z-auto md:h-auto md:max-h-none md:w-[22rem] md:shrink-0 md:border-l md:border-t-0 md:shadow-none"
    >
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Source passage
          </p>
          <h2 className="mt-1 text-base font-semibold">{citation.ticker}</h2>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label="Close source passage"
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </Button>
      </header>

      <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Company</dt>
        <dd className="text-right">{citation.company_name}</dd>
        <dt className="text-muted-foreground">Filing</dt>
        <dd className="text-right">{citation.filing_type}</dd>
        <dt className="text-muted-foreground">Filed</dt>
        <dd className="text-right">{formatFilingDate(citation.filing_date)}</dd>
        <dt className="text-muted-foreground">Fiscal year</dt>
        <dd className="text-right">{citation.fiscal_year}</dd>
        <dt className="text-muted-foreground">Location</dt>
        <dd className="text-right">{citationLocation(citation)}</dd>
      </dl>

      <div className="mt-5 border-t pt-4">
        <h3 className="text-sm font-semibold">
          {citation.quote ? "Cited excerpt" : "Retrieved passage"}
        </h3>
        <blockquote className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/50 p-3 text-sm leading-6">
          {excerpt}
        </blockquote>
      </div>

      <a
        className="mt-4 inline-flex items-center gap-2 text-sm font-medium underline underline-offset-4"
        href={citation.source_url}
        target="_blank"
        rel="noopener noreferrer"
      >
        Open filing source
        <ExternalLink aria-hidden="true" className="size-4" />
      </a>
    </aside>
  );
}

interface ChatPanelProps {
  threadId: string;
  initialMessages: ChatMessage[];
}

export function ChatPanel({ threadId, initialMessages }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [selectedCitation, setSelectedCitation] = useState<ChatCitation | null>(
    null,
  );
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [signInError, setSignInError] = useState<string | null>(null);
  const navigate = useNavigate();
  const transport = useMemo(
    () =>
      new DefaultChatTransport<ChatUIMessage>({
        api: `${env.apiBaseUrl}/chat/stream`,
        headers: getAuthHeaders,
        body: { threadId },
        fetch: chatFetch,
      }),
    [threadId],
  );
  const { messages, sendMessage, status, error, stop, clearError } =
    useChat<ChatUIMessage>({
      id: threadId,
      messages: toUiMessages(initialMessages),
      transport,
      onData: (dataPart) => {
        if (dataPart.type === "data-progress") {
          setProgressMessage(dataPart.data.message);
        }
      },
    });
  const isStreaming = status === "submitted" || status === "streaming";
  const chatFailure = error ? describeFailure(error) : null;

  useEffect(() => {
    if (status === "ready" || status === "error") setProgressMessage(null);
  }, [status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isStreaming) return;
    clearError();
    setProgressMessage(null);
    setSignInError(null);
    setInput("");
    await sendMessage({ text });
  }

  async function signInAgain() {
    const { error: authError } = await supabase.auth.signOut();
    if (authError) {
      setSignInError(authError.message);
      return;
    }
    navigate("/login", { replace: true });
  }

  function dismissError() {
    clearError();
    setSignInError(null);
  }

  return (
    <section className="flex min-h-0 flex-1" aria-busy={isStreaming}>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-8">
          {messages.length === 0 && (
            <div className="mx-auto mt-16 max-w-lg text-center">
              <h1 className="text-2xl font-semibold tracking-tight">
                Start a conversation
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Ask a question about the available filings. Answers include
                references to their source passages.
              </p>
            </div>
          )}
          {messages.map((message) => (
            <article
              key={message.id}
              className={`mx-auto max-w-3xl rounded-xl border p-4 ${message.role === "user" ? "bg-muted/50" : "bg-card"}`}
            >
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {message.role === "user" ? "You" : "Rag with Supabase "}
              </h2>
              <div className="mt-2 space-y-2 whitespace-pre-wrap text-sm leading-6">
                {message.parts.map((part, index) => {
                  if (part.type === "text") {
                    return <p key={`${message.id}-${index}`}>{part.text}</p>;
                  }
                  if (part.type === "data-citation") {
                    const isSelected =
                      selectedCitation?.chunk_id === part.data.chunk_id;
                    return (
                      <button
                        key={`${message.id}-${index}`}
                        type="button"
                        aria-controls={
                          selectedCitation ? "citation-source-panel" : undefined
                        }
                        aria-expanded={isSelected}
                        title={`${part.data.company_name} · ${part.data.filing_type} · ${formatFilingDate(part.data.filing_date)} · ${citationLocation(part.data)}`}
                        onClick={() => setSelectedCitation(part.data)}
                        className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 text-left text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${isSelected ? "border-primary bg-primary text-primary-foreground" : "bg-muted/50 text-foreground hover:bg-muted"}`}
                      >
                        <span className="shrink-0">
                          [{part.data.citation_index}]
                        </span>
                        <span className="truncate">
                          {citationLabel(part.data)}
                        </span>
                        <span className="hidden shrink-0 text-muted-foreground sm:inline">
                          {citationLocation(part.data)}
                        </span>
                      </button>
                    );
                  }
                  return null;
                })}
              </div>
            </article>
          ))}
          {isStreaming && (
            <p
              aria-live="polite"
              role="status"
              className="mx-auto max-w-3xl text-sm text-muted-foreground"
            >
              {progressMessage || "Assistant is responding..."}
            </p>
          )}
          {chatFailure && (
            <div
              role="alert"
              className="mx-auto flex max-w-3xl items-start justify-between gap-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <div>
                <p className="font-semibold">{chatFailure.title}</p>
                <p className="mt-1">{chatFailure.description}</p>
                {signInError && <p className="mt-2">{signInError}</p>}
                {chatFailure.kind !== "auth" && (
                  <p className="mt-1 text-xs">
                    You can edit the question and send it again when ready.
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-col gap-2">
                {chatFailure.kind === "auth" ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void signInAgain()}
                  >
                    Sign in again
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={dismissError}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          )}
        </div>
        <form
          onSubmit={(event) => void submit(event)}
          className="mx-auto w-full max-w-3xl border-t px-4 py-4 sm:px-8"
        >
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <div className="flex items-end gap-2 rounded-xl border bg-card p-2 shadow-sm">
            <textarea
              id="chat-input"
              rows={2}
              maxLength={2_000}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Ask a question..."
              className="max-h-40 min-h-10 flex-1 resize-y bg-transparent px-2 py-2 text-sm outline-none"
            />
            {isStreaming ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => void stop()}
              >
                Stop
              </Button>
            ) : (
              <Button type="submit" disabled={!input.trim()}>
                Send
              </Button>
            )}
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Answers are limited to evidence available in the filing corpus.
          </p>
        </form>
      </div>
      {selectedCitation && (
        <CitationSourcePanel
          citation={selectedCitation}
          onClose={() => setSelectedCitation(null)}
        />
      )}
    </section>
  );
}
