"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  connectAIChat,
  parseAssistantXml,
  type AIChatInitPayload,
  type ParsedTag,
  type SimActionName,
} from "@/lib/aiChat";

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  text: string;
  tags?: ParsedTag[];
};

type Props = {
  pageContext: "run" | "job";
  inputFields?: unknown[];
  viewerState?: Record<string, unknown> | null;
  onUpdateInputs?: (patch: Record<string, string>) => void;
  onViewerCmd?: (cmd: Record<string, unknown>) => void;
  onSimAction?: (action: SimActionName) => void;
};

export function ChatBot({
  pageContext,
  inputFields,
  viewerState,
  onUpdateInputs,
  onViewerCmd,
  onSimAction,
}: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("Disconnected");
  const [ready, setReady] = useState(false);
  const [sending, setSending] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const onUpdateInputsRef = useRef(onUpdateInputs);
  onUpdateInputsRef.current = onUpdateInputs;
  const onViewerCmdRef = useRef(onViewerCmd);
  onViewerCmdRef.current = onViewerCmd;
  const onSimActionRef = useRef(onSimAction);
  onSimActionRef.current = onSimAction;

  const pushMsg = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  useEffect(() => {
    if (!open) return;

    const init: AIChatInitPayload = {
      pageContext,
      inputFields: inputFields ?? undefined,
      viewerState: (viewerState as Record<string, unknown>) ?? undefined,
    };

    const ws = connectAIChat(init, {
      onAssistantMessage(raw) {
        const { tags, plainText } = parseAssistantXml(raw);

        for (const t of tags) {
          if (t.tag === "UpdateInputs" && onUpdateInputsRef.current) {
            onUpdateInputsRef.current(t.data);
          }
          if (t.tag === "ViewerCmd" && onViewerCmdRef.current) {
            console.debug("[AI→Viewer]", JSON.stringify(t.data));
            onViewerCmdRef.current(t.data);
          }
          if (t.tag === "SimAction" && onSimActionRef.current) {
            onSimActionRef.current(t.action);
          }
        }

        const display =
          plainText ||
          tags
            .filter((t) => t.tag === "NeedMoreInfo" || t.tag === "CasualMessage")
            .map((t) => (t as { text: string }).text)
            .join("\n") ||
          "(action applied)";

        pushMsg({ role: "assistant", text: display, tags });
        setSending(false);
      },
      onReady() {
        setReady(true);
        setStatus("Ready");
      },
      onStatusChange: setStatus,
      onError(msg) {
        pushMsg({ role: "system", text: msg });
        setStatus(`Error: ${msg}`);
        setSending(false);
      },
      onDisconnect() {
        setReady(false);
        setStatus("Disconnected");
      },
    });

    socketRef.current = ws;

    return () => {
      ws.close();
      socketRef.current = null;
      setReady(false);
    };
    // Only reconnect when `open` or pageContext changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pageContext]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    if (open && ready) inputRef.current?.focus();
  }, [open, ready]);

  const handleSend = (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    pushMsg({ role: "user", text });
    socketRef.current.send(JSON.stringify({ type: "user_message", message: text }));
    setDraft("");
    setSending(true);
  };

  return (
    <>
      {/* Floating toggle button */}
      <button
        type="button"
        className="chat-fab"
        onClick={() => setOpen((p) => !p)}
        aria-label={open ? "Close assistant" : "Open assistant"}
        title="AI Assistant"
      >
        {open ? (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="chat-panel">
          <div className="chat-header">
            <span className="chat-header-title">AI Assistant</span>
            <span className="chat-header-status">{status}</span>
          </div>

          <div className="chat-messages" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="chat-empty">
                {pageContext === "run"
                  ? "Ask me to change simulation parameters, e.g. \"set velocity to 30 m/s\""
                  : "Ask me to control the 3D viewer, e.g. \"go to the last time step\""}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg chat-msg--${m.role}`}>
                <div className="chat-msg-bubble">
                  {m.text}
                  {m.tags && m.tags.some((t) => t.tag === "UpdateInputs") && (
                    <span className="chat-msg-action">Inputs updated</span>
                  )}
                  {m.tags && m.tags.some((t) => t.tag === "ViewerCmd") && (
                    <span className="chat-msg-action">Viewer command sent</span>
                  )}
                  {m.tags && m.tags.some((t) => t.tag === "SimAction") && (
                    <span className="chat-msg-action">Simulation action triggered</span>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="chat-msg chat-msg--assistant">
                <div className="chat-msg-bubble chat-msg-typing">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </div>

          <form className="chat-input-row" onSubmit={handleSend}>
            <input
              ref={inputRef}
              className="chat-input"
              type="text"
              placeholder={ready ? "Type a message…" : "Connecting…"}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={!ready || sending}
            />
            <button
              type="submit"
              className="chat-send-btn"
              disabled={!ready || sending || !draft.trim()}
              title="Send"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </form>
        </div>
      )}
    </>
  );
}
