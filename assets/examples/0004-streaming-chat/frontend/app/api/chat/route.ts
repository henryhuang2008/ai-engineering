import { createUIMessageStream, createUIMessageStreamResponse } from "ai";
import type { UIMessage } from "ai";

export const maxDuration = 60;

const PY_BACKEND = process.env.PY_BACKEND ?? "http://127.0.0.1:8000";

type Frame = { delta?: string; error?: string; done?: boolean };

/** Keep only the text parts; the UI message carries tool/attachment parts too. */
function textOf(message: UIMessage): string {
  return message.parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}

/**
 * Plain text, never an HTML page: useChat shows `error.message` verbatim, and a
 * 500 from this file would hand the user a wall of markup instead of a sentence.
 */
function plain(body: string, status: number): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

export async function POST(req: Request) {
  let messages: UIMessage[];
  try {
    ({ messages } = (await req.json()) as { messages: UIMessage[] });
  } catch {
    return plain("request body is not JSON with a messages array", 400);
  }

  const history = messages
    .map((message) => ({ role: message.role, content: textOf(message) }))
    .filter((message) => message.content.length > 0);

  let upstream: Response;
  try {
    upstream = await fetch(`${PY_BACKEND}/chat-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
      // Client hits Stop -> the browser aborts this request -> Python stops too.
      signal: req.signal,
    });
  } catch (error) {
    if (req.signal.aborted) throw error; // the user pressed Stop, not a failure
    const detail = error instanceof Error ? error.message : String(error);
    return plain(
      `python backend unreachable at ${PY_BACKEND}\n` +
        `  start it:  uv run uvicorn main:app --reload\n` +
        `  detail:    ${detail}`,
      502,
    );
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return plain(
      `python backend answered ${upstream.status} at ${PY_BACKEND}\n` +
        `  check the uvicorn terminal for the traceback\n` +
        `  detail: ${detail.slice(0, 600)}`,
      502,
    );
  }

  const textId = crypto.randomUUID();

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      const reader = upstream.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let failure: unknown = null;

      writer.write({ type: "text-start", id: textId });

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE events end with a blank line; a chunk boundary can split one.
          let split: number;
          while ((split = buffer.indexOf("\n\n")) !== -1) {
            const raw = buffer.slice(0, split);
            buffer = buffer.slice(split + 2);
            if (!raw.startsWith("data: ")) continue;

            const frame = JSON.parse(raw.slice(6)) as Frame;
            if (frame.error) throw new Error(frame.error);
            if (frame.delta) {
              writer.write({ type: "text-delta", id: textId, delta: frame.delta });
            }
          }
        }
      } catch (error) {
        failure = error;
      } finally {
        writer.write({ type: "text-end", id: textId });
      }

      if (failure) throw failure;
    },
    onError: (error) => (error instanceof Error ? error.message : String(error)),
  });

  return createUIMessageStreamResponse({ stream });
}
