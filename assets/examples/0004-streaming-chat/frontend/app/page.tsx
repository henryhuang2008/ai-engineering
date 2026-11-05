"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useChat } from "@ai-sdk/react";
import {
  ArrowUpIcon,
  Loader2Icon,
  MessageSquareIcon,
  SquareIcon,
} from "lucide-react";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";

const SUGGESTIONS = [
  "Why was my ticket T-1001 charged twice?",
  "Summarize my last ticket in one line.",
  "What can you help me with?",
];

/**
 * useChat hands back whatever the failing request returned. When the route file
 * lives in the wrong folder that "body" is Next.js's 404 HTML page, so translate
 * the two mistakes people actually make into a sentence instead of dumping markup.
 */
function errorText(error: Error): string {
  const raw = error.message ?? "";
  if (raw.includes("<!DOCTYPE html") || raw.includes("__next")) {
    return (
      "The browser got a Next.js page instead of your route handler — " +
      "route.ts is not at app/api/chat/route.ts (or src/app/api/chat/route.ts). " +
      "Move it there and let the dev server reload."
    );
  }
  return raw.length > 400 ? `${raw.slice(0, 400)}…` : raw;
}

/** Three bouncing dots: the gap between "sent" and "first token". */
function TypingDots() {
  return (
    <span className="flex items-center gap-1 py-1" aria-label="Assistant is typing">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground/70"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

function Caret() {
  return (
    <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse rounded-full bg-foreground align-text-bottom" />
  );
}

export default function Page() {
  const { messages, sendMessage, status, stop, error } = useChat();
  const [text, setText] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const busy = status === "submitted" || status === "streaming";
  const empty = messages.length === 0 && !busy;

  // Follow the answer as it streams in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, status]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    sendMessage({ text: value });
    setText("");
  }

  function pickSuggestion(value: string) {
    setText(value);
    formRef.current?.querySelector("textarea")?.focus();
  }

  return (
    <main className="flex min-h-svh flex-col bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-2xl items-center gap-3 px-4 py-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <MessageSquareIcon className="size-4" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-medium leading-none">Support chat</h1>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              FastAPI + LangChain + DeepSeek
            </p>
          </div>
          <span
            data-status={status}
            className="ml-auto flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground"
          >
            {busy ? (
              <Loader2Icon
                aria-label="Loading"
                className="size-3 animate-spin text-emerald-500"
              />
            ) : (
              <span
                className={
                  status === "error"
                    ? "size-1.5 rounded-full bg-destructive"
                    : "size-1.5 rounded-full bg-muted-foreground/40"
                }
              />
            )}
            {status === "submitted"
              ? "connecting"
              : status === "streaming"
                ? "streaming"
                : status === "error"
                  ? "error"
                  : "ready"}
          </span>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4">
        <div
          role="log"
          aria-live="polite"
          className={
            empty
              ? "flex flex-1 flex-col justify-center py-6"
              : "flex-1 space-y-5 py-6"
          }
        >
          {messages.length === 0 && status !== "submitted" && (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <div className="flex size-11 items-center justify-center rounded-full bg-muted">
                <MessageSquareIcon className="size-5 text-muted-foreground" />
              </div>
              <h2 className="mt-4 text-base font-medium">How can I help?</h2>
              <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
                Ask about a ticket, a charge, or your account. The answer streams in as
                DeepSeek writes it.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => pickSuggestion(suggestion)}
                    className="rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message, index) => {
            const isUser = message.role === "user";
            const streamingThis =
              status === "streaming" &&
              index === messages.length - 1 &&
              message.role === "assistant";
            const hasText = message.parts.some(
              (part) => part.type === "text" && part.text.length > 0,
            );

            return (
              <div
                key={message.id}
                className={isUser ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={
                    isUser
                      ? "max-w-[85%] rounded-2xl bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground whitespace-pre-wrap"
                      : "max-w-[85%] rounded-2xl bg-muted px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap"
                  }
                >
                  {!isUser && !hasText && streamingThis ? (
                    <TypingDots />
                  ) : (
                    message.parts.map((part, partIndex) =>
                      part.type === "text" ? (
                        <span key={partIndex}>{part.text}</span>
                      ) : null,
                    )
                  )}
                  {streamingThis && hasText && <Caret />}
                </div>
              </div>
            );
          })}

          {status === "submitted" && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-muted px-4 py-2.5">
                <TypingDots />
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-sm">
              <p className="font-medium text-destructive">The stream failed</p>
              <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
                {errorText(error)}
              </p>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div className="sticky bottom-0 -mx-4 bg-gradient-to-t from-background via-background to-transparent px-4 pb-5 pt-8">
          <form ref={formRef} onSubmit={submit}>
            <InputGroup className="rounded-2xl border-transparent bg-input/50 shadow-none dark:bg-input/40">
              <InputGroupTextarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    formRef.current?.requestSubmit();
                  }
                }}
                placeholder="Ask about your ticket…"
                className="min-h-16 p-3 text-base md:text-sm"
              />
              <InputGroupAddon align="block-end" className="gap-2 px-2.5 pb-2.5">
                <span className="hidden text-[11px] text-muted-foreground sm:inline">
                  Enter to send · Shift+Enter for a new line
                </span>
                <div className="ml-auto flex items-center gap-2">
                  {busy ? (
                    <InputGroupButton
                      type="button"
                      size="icon-sm"
                      variant="default"
                      className="rounded-full"
                      onClick={() => stop()}
                      aria-label="Stop"
                    >
                      {status === "submitted" ? (
                        <Loader2Icon className="animate-spin" />
                      ) : (
                        <SquareIcon />
                      )}
                    </InputGroupButton>
                  ) : (
                    <InputGroupButton
                      type="submit"
                      size="icon-sm"
                      variant="default"
                      className="rounded-full"
                      disabled={!text.trim()}
                      aria-label="Send"
                    >
                      <ArrowUpIcon />
                    </InputGroupButton>
                  )}
                </div>
              </InputGroupAddon>
            </InputGroup>
          </form>
          <p className="pt-2 text-center text-[11px] text-muted-foreground">
            {status === "streaming"
              ? "streaming — press stop to cancel the Python request"
              : "Python owns the model call and the key; this page owns nothing but pixels."}
          </p>
        </div>
      </div>
    </main>
  );
}
