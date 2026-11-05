import { useCallback, useEffect, useState } from "react";
import {
  Link,
  Outlet,
  useNavigate,
  useOutletContext,
  useParams,
} from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ChatPanel } from "@/components/chat/chat-panel";
import {
  api,
  ApiError,
  type ChatThread,
  type ChatThreadHistory,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

type RequestFailureKind = "auth" | "network" | "retrieval" | "unknown";

interface RequestFailure {
  kind: RequestFailureKind;
  message: string;
}

function describeRequestFailure(
  error: unknown,
  fallback: string,
): RequestFailure {
  if (error instanceof ApiError) {
    if (error.isNetworkError) {
      return {
        kind: "network",
        message: "Could not reach Rag with Supabase . Check your connection.",
      };
    }
    if (error.status === 401 || error.status === 403 || error.status === null) {
      return {
        kind: "auth",
        message:
          "Your sign-in session has expired or cannot access this conversation.",
      };
    }
    if (error.status === 503) {
      return {
        kind: "retrieval",
        message: "A backend service is temporarily unavailable.",
      };
    }
  }
  return {
    kind: "unknown",
    message: error instanceof Error ? error.message : fallback,
  };
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function ConversationsLayout() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [retryAction, setRetryAction] = useState<"load" | "create" | null>(
    null,
  );

  const loadThreads = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setRetryAction(null);
    try {
      setThreads(await api.listThreads());
    } catch (loadError: unknown) {
      setError(
        describeRequestFailure(loadError, "Could not load conversations."),
      );
      setRetryAction("load");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadThreads();
  }, [loadThreads, session?.access_token]);

  async function createThread() {
    setIsCreating(true);
    setError(null);
    setRetryAction(null);
    try {
      const thread = await api.createThread();
      setThreads((current) => [thread, ...current]);
      navigate(`/chat/${thread.id}`);
    } catch (createError: unknown) {
      setError(
        describeRequestFailure(createError, "Could not create a conversation."),
      );
      setRetryAction("create");
    } finally {
      setIsCreating(false);
    }
  }

  async function signOut() {
    const { error: signOutError } = await supabase.auth.signOut();
    if (signOutError) {
      setError({ kind: "unknown", message: signOutError.message });
      setRetryAction(null);
    } else {
      navigate("/login", { replace: true });
    }
  }

  const { threadId } = useParams();

  return (
    <main className="flex min-h-svh bg-background">
      <aside className="flex w-64 shrink-0 flex-col border-r bg-muted/30">
        <div className="border-b p-4">
          <Link to="/chat" className="text-sm font-semibold tracking-wide">
            Rag with Supabase
          </Link>
          <Button
            className="mt-4 w-full"
            type="button"
            onClick={() => void createThread()}
            disabled={isCreating || isLoading}
          >
            {isCreating ? "Creating..." : "New conversation"}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <p className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Conversations
          </p>
          {isLoading ? (
            <p
              role="status"
              aria-live="polite"
              className="px-2 py-3 text-sm text-muted-foreground"
            >
              Loading conversations...
            </p>
          ) : threads.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              No conversations yet.
            </p>
          ) : (
            <nav aria-label="Conversations" className="space-y-1">
              {threads.map((thread) => (
                <Link
                  key={thread.id}
                  to={`/chat/${thread.id}`}
                  className={`block rounded-md px-2 py-2 text-sm hover:bg-muted ${thread.id === threadId ? "bg-muted font-medium" : ""}`}
                >
                  <span className="block truncate">{thread.title}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {formatDate(thread.updated_at)}
                  </span>
                </Link>
              ))}
            </nav>
          )}
        </div>
        <div className="border-t p-3">
          {error && (
            <div
              role="alert"
              className="mb-3 space-y-2 text-xs text-destructive"
            >
              <p>{error.message}</p>
              <div className="flex flex-wrap gap-2">
                {error.kind === "auth" ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void signOut()}
                  >
                    Sign in again
                  </Button>
                ) : null}
                {retryAction === "load" && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void loadThreads()}
                  >
                    Retry
                  </Button>
                )}
                {retryAction === "create" && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void createThread()}
                  >
                    Retry
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setError(null);
                    setRetryAction(null);
                  }}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          )}
          <p className="truncate px-1 text-xs text-muted-foreground">
            {session?.user.email}
          </p>
          <Button
            className="mt-2 w-full"
            type="button"
            variant="outline"
            onClick={() => void signOut()}
          >
            Sign out
          </Button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet context={{ createThread }} />
      </div>
    </main>
  );
}

export function ConversationWelcome() {
  const { createThread } = useOutletContext<{
    createThread: () => Promise<void>;
  }>();
  return (
    <section className="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">
        What would you like to research?
      </h1>
      <p className="mt-3 max-w-xl text-sm text-muted-foreground">
        Ask a question about the available company filings. Answers include
        citations to the source passages.
      </p>
      <Button
        className="mt-6"
        type="button"
        onClick={() => void createThread()}
      >
        Start a conversation
      </Button>
    </section>
  );
}

export function ConversationPage() {
  const { threadId } = useParams();
  const navigate = useNavigate();
  const [thread, setThread] = useState<ChatThreadHistory | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setThread(null);
    setError(null);
    if (!threadId || threadId === "new") {
      setError({
        kind: "unknown",
        message: "Create a conversation from the sidebar to get started.",
      });
      setIsLoading(false);
      return;
    }
    void api
      .getThread(threadId)
      .then((result) => {
        if (active) setThread(result);
      })
      .catch((loadError: unknown) => {
        if (!active) return;
        setError(
          describeRequestFailure(
            loadError,
            "Could not load this conversation.",
          ),
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [threadId, loadAttempt]);

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        aria-busy="true"
        className="m-auto text-sm text-muted-foreground"
      >
        Loading conversation...
      </p>
    );
  }
  if (error || !thread) {
    return (
      <section className="m-auto max-w-lg px-6 text-center">
        <p role="alert" className="text-sm text-destructive">
          {error?.message ?? "Conversation not found."}
        </p>
        <div className="mt-4 flex justify-center gap-2">
          {error?.kind === "auth" ? (
            <Button
              variant="outline"
              onClick={() => {
                void supabase.auth.signOut().then(({ error: signOutError }) => {
                  if (signOutError) {
                    setError({
                      kind: "unknown",
                      message: signOutError.message,
                    });
                    return;
                  }
                  navigate("/login", { replace: true });
                });
              }}
            >
              Sign in again
            </Button>
          ) : error ? (
            <Button
              variant="outline"
              onClick={() => setLoadAttempt((attempt) => attempt + 1)}
            >
              Retry
            </Button>
          ) : null}
          <Button variant="outline" onClick={() => navigate("/chat")}>
            Back to conversations
          </Button>
        </div>
      </section>
    );
  }

  return (
    <>
      <header className="border-b px-6 py-4">
        <h1 className="truncate font-medium">{thread.title}</h1>
      </header>
      <ChatPanel
        key={thread.id}
        threadId={thread.id}
        initialMessages={thread.messages}
      />
    </>
  );
}
