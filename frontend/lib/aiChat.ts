/**
 * WebSocket client for the OpenFOAM AI assistant service.
 *
 * Protocol:
 *   → { type: "init", pageContext, inputFields?, viewerState? }
 *   ← { type: "ready" }
 *   → { type: "user_message", message }
 *   ← { type: "assistant_message", message }
 *   ← { type: "error", message }
 *   → { type: "update_context", pageContext, inputFields?, viewerState? }
 *   ← { type: "context_updated" }
 */

export type AIChatHandlers = {
  onAssistantMessage: (raw: string) => void;
  onReady?: () => void;
  onStatusChange?: (status: string) => void;
  onError?: (msg: string) => void;
  onDisconnect?: () => void;
};

export type AIChatInitPayload = {
  pageContext: "run" | "job";
  inputFields?: unknown[];
  viewerState?: Record<string, unknown>;
};

export function connectAIChat(
  init: AIChatInitPayload,
  handlers: AIChatHandlers,
): WebSocket {
  const url =
    process.env.NEXT_PUBLIC_AI_WS_URL ||
    (typeof window !== "undefined"
      ? `ws://${window.location.hostname}:8081/ws`
      : "ws://localhost:8081/ws");

  const socket = new WebSocket(url);
  let hasOpened = false;
  let intentionallyClosed = false;

  socket.onopen = () => {
    hasOpened = true;
    handlers.onStatusChange?.("Connected");
    socket.send(JSON.stringify({ type: "init", ...init }));
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload?.type === "assistant_message" && typeof payload.message === "string") {
        handlers.onAssistantMessage(payload.message);
      } else if (payload?.type === "ready") {
        handlers.onStatusChange?.("Assistant ready");
        handlers.onReady?.();
      } else if (payload?.type === "context_updated") {
        handlers.onStatusChange?.("Context updated");
      } else if (payload?.type === "error") {
        const msg = typeof payload.message === "string" ? payload.message : "AI error";
        handlers.onError?.(msg);
      }
    } catch {
      handlers.onError?.("Failed to parse AI response");
    }
  };

  socket.onerror = () => {};

  const originalClose = socket.close.bind(socket);
  socket.close = (code?: number, reason?: string) => {
    intentionallyClosed = true;
    originalClose(code, reason);
  };

  socket.onclose = (event) => {
    if (intentionallyClosed) {
      handlers.onDisconnect?.();
      return;
    }
    if (!hasOpened && event.code === 1006) {
      handlers.onError?.("Cannot reach AI service. Is it running?");
    } else if (hasOpened) {
      handlers.onStatusChange?.("Disconnected");
      handlers.onDisconnect?.();
    }
  };

  return socket;
}

// ── XML tag parser ──

/** Simulation-level actions (run page only). */
export type SimActionName = "start_simulation" | "reset_inputs";

export type ParsedTag =
  | { tag: "UpdateInputs"; data: Record<string, string> }
  | { tag: "ViewerCmd"; data: Record<string, unknown> }
  | { tag: "SimAction"; action: SimActionName }
  | { tag: "NeedMoreInfo"; text: string }
  | { tag: "CasualMessage"; text: string };

const TAG_RE =
  /<(UpdateInputs|ViewerCmd|SimAction|NeedMoreInfo|CasualMessage)>([\s\S]*?)<\/\1>/g;

const VALID_SIM_ACTIONS = new Set<SimActionName>(["start_simulation", "reset_inputs"]);

export function parseAssistantXml(raw: string): {
  tags: ParsedTag[];
  plainText: string;
} {
  const tags: ParsedTag[] = [];
  let plainText = raw;

  for (const m of raw.matchAll(TAG_RE)) {
    const tagName = m[1] as string;
    const inner = m[2].trim();
    plainText = plainText.replace(m[0], "");

    if (tagName === "UpdateInputs") {
      try {
        tags.push({ tag: "UpdateInputs", data: JSON.parse(inner) });
      } catch { /* malformed JSON – skip */ }
    } else if (tagName === "ViewerCmd") {
      try {
        tags.push({ tag: "ViewerCmd", data: JSON.parse(inner) });
      } catch { /* skip */ }
    } else if (tagName === "SimAction") {
      const action = inner as SimActionName;
      if (VALID_SIM_ACTIONS.has(action)) {
        tags.push({ tag: "SimAction", action });
      }
    } else if (tagName === "NeedMoreInfo") {
      tags.push({ tag: "NeedMoreInfo", text: inner });
    } else if (tagName === "CasualMessage") {
      tags.push({ tag: "CasualMessage", text: inner });
    }
  }

  plainText = plainText.replace(/\n{3,}/g, "\n\n").trim();
  return { tags, plainText };
}
