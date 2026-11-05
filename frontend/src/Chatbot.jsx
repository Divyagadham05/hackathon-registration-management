import { useEffect, useRef, useState } from "react";

const INITIAL_MESSAGE = {
  role: "assistant",
  content: "Hi! I'm your Hackathon Website Assistant. Ask me about the event, registration, login, or officially announced facilities.",
};
const SUGGESTED_QUESTIONS = [
  "What is this hackathon?",
  "How do I register?",
  "How do I log in?",
  "Is lunch free?",
  "What facilities are announced?",
];

function Chatbot({ csrf, request: requestApi }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const messagesRef = useRef(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open) messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight });
  }, [messages, open]);

  async function sendMessage(event) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy) return;

    const nextMessages = [...messages, { role: "user", content }];
    setMessages(nextMessages.slice(-40));
    setDraft("");
    setError("");
    setBusy(true);

    try {
      const response = await requestApi("/api/chat", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: JSON.stringify({ messages: nextMessages.slice(-12) }),
      });
      setMessages((current) => [...current, { role: "assistant", content: response.reply }].slice(-40));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function clearChat() {
    setMessages([INITIAL_MESSAGE]);
    setDraft("");
    setError("");
  }

  return (
    <div className="chat-assistant">
      {open && (
        <section className="chat-panel" aria-label="Hackathon assistant">
          <header className="chat-header">
            <div>
              <span className="chat-header-kicker">HACK THE FUTURE</span>
              <h2>Hackathon Website Assistant</h2>
            </div>
            <div className="chat-header-actions">
              <button type="button" className="chat-clear" onClick={clearChat} disabled={busy}>Clear chat</button>
              <button type="button" className="chat-close" aria-label="Close chat" onClick={() => setOpen(false)}>×</button>
            </div>
          </header>
          <p className="chat-privacy-note">Some website questions may be sent to Groq. Don’t share passwords or private information.</p>
          <div className="chat-messages" ref={messagesRef} aria-live="polite">
            {messages.map((message, index) => (
              <p className={`chat-message chat-message-${message.role}`} key={`${index}-${message.role}`}>
                {message.content}
              </p>
            ))}
            {busy && (
              <p className="chat-message chat-message-assistant chat-thinking" aria-label="Assistant is thinking">
                Thinking<span className="chat-thinking-dots" aria-hidden="true">...</span>
              </p>
            )}
            {messages.length === 1 && !busy && (
              <div className="chat-suggestions" aria-label="Suggested questions">
                <span>Try asking</span>
                {SUGGESTED_QUESTIONS.map((question) => (
                  <button
                    type="button"
                    key={question}
                    onClick={() => {
                      setDraft(question);
                      inputRef.current?.focus();
                    }}
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
          </div>
          {error && <p className="chat-error" role="alert">{error}</p>}
          <form className="chat-form" onSubmit={sendMessage}>
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Ask a question..."
              aria-label="Your message"
              maxLength={1200}
              rows={2}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !draft.trim()} aria-label="Send message">
              {busy ? "…" : "Send"}
            </button>
          </form>
        </section>
      )}
      <button
        type="button"
        className="chat-launcher"
        aria-expanded={open}
        aria-label={open ? "Close hackathon assistant" : "Open hackathon assistant"}
        onClick={() => setOpen((current) => !current)}
      >
        <span aria-hidden="true">{open ? "×" : "✦"}</span>
        <span>{open ? "Close" : "Ask AI"}</span>
      </button>
    </div>
  );
}

export default Chatbot;
