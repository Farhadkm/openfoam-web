/**
 * WebSocket client for the Forge AI assistant service.
 *
 * Protocol:
 *   → { type: "init", pageContext, inputFields?, viewerState? }
 *   ← { type: "ready", conversationId }
 *   → { type: "user_message", message }
 *   ← { type: "assistant_message", message, agent?, agent_label? }
 *   ← { type: "intent_classification", intents, primary_intent, ... }  (optional, from ICS)
 *   ← { type: "error", message }
 *   → { type: "update_context", pageContext, inputFields?, viewerState? }
 *   ← { type: "context_updated" }
 */

export type AssistantMessageMeta = {
  agent?: string;
  agentLabel?: string;
};

export type AIChatHandlers = {
  onAssistantMessage: (raw: string, meta?: AssistantMessageMeta) => void;
  onIntentClassification?: (payload: Record<string, unknown>) => void;
  onReady?: (conversationId: string) => void;
  onStatusChange?: (status: string) => void;
  onError?: (msg: string) => void;
  onDisconnect?: () => void;
};

export type AIChatInitPayload = {
  pageContext: "run" | "job";
  inputFields?: unknown[];
  viewerState?: Record<string, unknown>;
  /** When set, CCS appends messages to this conversation (in-memory on server). */
  conversationId?: string;
};

function aiWsUrl(): string {
  const api = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";
  const u = new URL("/api/ai/ws", api);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

export function connectAIChat(
  init: AIChatInitPayload,
  handlers: AIChatHandlers,
): WebSocket {
  const url = aiWsUrl();

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
        const meta: AssistantMessageMeta | undefined =
          typeof payload.agent === "string" || typeof payload.agent_label === "string"
            ? {
                agent: typeof payload.agent === "string" ? payload.agent : undefined,
                agentLabel:
                  typeof payload.agent_label === "string" ? payload.agent_label : undefined,
              }
            : undefined;
        handlers.onAssistantMessage(payload.message, meta);
      } else if (payload?.type === "intent_classification") {
        handlers.onIntentClassification?.(payload as Record<string, unknown>);
      } else if (payload?.type === "ready") {
        handlers.onStatusChange?.("Assistant ready");
        const conversationId =
          typeof payload.conversationId === "string" ? payload.conversationId : "";
        if (conversationId) {
          handlers.onReady?.(conversationId);
        } else {
          handlers.onError?.("Assistant ready but no conversation ID.");
        }
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

/** Collapse doubled braces when the model echoes format-escaped prompt examples. */
function normalizeJsonTagInner(inner: string): string {
  return inner.replace(/\{\{/g, "{").replace(/\}\}/g, "}");
}

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
        tags.push({ tag: "UpdateInputs", data: JSON.parse(normalizeJsonTagInner(inner)) });
      } catch { /* malformed JSON – skip */ }
    } else if (tagName === "ViewerCmd") {
      try {
        tags.push({ tag: "ViewerCmd", data: JSON.parse(normalizeJsonTagInner(inner)) });
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
