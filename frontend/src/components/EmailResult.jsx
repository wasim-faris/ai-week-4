import { useState } from "react";
import { Check, Clipboard, LoaderCircle, Sparkles } from "lucide-react";

function EmailResult({ title, focusNote, result, loading, error }) {
  const [copyMessage, setCopyMessage] = useState("");

  async function copyEmail() {
    const text = `Subject: ${result.subject}\n\n${result.body}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopyMessage("Copied");
    } catch {
      setCopyMessage("Clipboard unavailable");
    }
  }

  return (
    <article className="result-card">
      <div className="result-header">
        <div className="result-title-wrap">
          <span className="result-icon">
            <Sparkles size={16} />
          </span>
          <div className="result-heading-copy">
            <h3>{title}</h3>
            {focusNote && <span className="focus-note">{focusNote}</span>}
          </div>
        </div>
        {result && !loading && !result.needs_clarification && (
          <button className="copy-button" type="button" onClick={copyEmail} title="Copy email">
            {copyMessage === "Copied" ? <Check size={15} /> : <Clipboard size={15} />}
            <span>{copyMessage || "Copy"}</span>
          </button>
        )}
      </div>

      {loading ? (
        <div className="result-empty" role="status">
          <LoaderCircle className="spin loading-icon" size={22} />
          <span>Writing your email…</span>
        </div>
      ) : error ? (
        <div className="result-message result-error" role="alert">{error}</div>
      ) : result ? (
        <div className="email-content">
          {result.needs_clarification && (
            <div className="clarification-callout" role="status">
              <strong>This request needs clarification</strong>
              <span>{result.clarification_question}</span>
            </div>
          )}
          {!result.needs_clarification && (
            <>
          <div className="subject-block">
            <span className="output-label">SUBJECT</span>
            <p>{result.subject}</p>
          </div>
          <div className="body-block">
            <span className="output-label">EMAIL BODY</span>
            <p>{result.body}</p>
          </div>
            </>
          )}
          <div className="result-meta" aria-live="polite">
            <span>{result.response_time_ms.toLocaleString()} ms</span>
            {copyMessage && <span>{copyMessage === "Copied" ? "Email copied to clipboard" : copyMessage}</span>}
          </div>
        </div>
      ) : (
        <div className="result-empty">
          <span className="empty-mark"><Sparkles size={17} /></span>
          <span>Your generated email will appear here.</span>
        </div>
      )}
    </article>
  );
}

export default EmailResult;