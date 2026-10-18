import { useState } from "react";
import { ArrowDown, Sparkles } from "lucide-react";
import ComparisonPanel from "./components/ComparisonPanel.jsx";
import EmailForm from "./components/EmailForm.jsx";
import EmailResult from "./components/EmailResult.jsx";

const emptyEvaluations = () => ({
  baseline: {},
  improved: {},
});

const apiUrl =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api/generate-email/";

function App() {
  const [emailInput, setEmailInput] = useState({
    message: "",
    recipient: "",
    tone: "Professional",
    instructions: "",
  });
  const [results, setResults] = useState({ baseline: null, improved: null });
  const [loading, setLoading] = useState({ baseline: false, improved: false });
  const [errors, setErrors] = useState({ baseline: "", improved: "" });
  const [evaluations, setEvaluations] = useState(emptyEvaluations);

  async function generateEmail(mode) {
    if (!emailInput.message.trim()) {
      setErrors((current) => ({
        ...current,
        [mode]: "Add an email purpose or message before generating.",
      }));
      return;
    }

    setLoading((current) => ({ ...current, [mode]: true }));
    setErrors((current) => ({ ...current, [mode]: "" }));

    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...emailInput, mode }),
        signal: AbortSignal.timeout(50000),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Email generation failed. Please try again.");
      }

      setResults((current) => ({ ...current, [mode]: data }));
      setEvaluations((current) => ({ ...current, [mode]: {} }));
    } catch (error) {
      const message =
        error.name === "TimeoutError"
          ? "This request took too long. Please try again."
          : error.message === "Failed to fetch"
            ? "Could not reach the API. Check that Django is running."
            : error.message;
      setErrors((current) => ({ ...current, [mode]: message }));
    } finally {
      setLoading((current) => ({ ...current, [mode]: false }));
    }
  }

  function updateEvaluation(mode, criterion, checked) {
    setEvaluations((current) => ({
      ...current,
      [mode]: { ...current[mode], [criterion]: checked },
    }));
  }

  return (
    <main className="page-shell mx-auto w-full max-w-6xl px-5 pb-16 sm:px-8">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="EmailCraft home" id="top">
          <span className="brand-mark"><Sparkles size={18} strokeWidth={1.8} /></span>
          <span>EmailCraft</span>
        </a>
        <span className="header-note">A small prompt study</span>
      </header>

      <section className="intro-section">
        <div>
          <p className="eyebrow">WRITE WITH INTENTION</p>
          <h1>Write clearer emails <span>with AI.</span></h1>
          <p className="intro-copy">Compare a simple prompt with a more considered one.</p>
        </div>
        <a className="jump-link" href="#results">
          <span>Compare outputs</span><ArrowDown size={15} />
        </a>
      </section>

      <EmailForm
        emailInput={emailInput}
        onInputChange={setEmailInput}
        onGenerate={generateEmail}
        loading={loading}
      />

      <section className="results-section" id="results" aria-labelledby="results-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">THE RESULTS</p>
            <h2 id="results-title">Before &amp; after</h2>
          </div>
          <span className="timing-note">Provider response time</span>
        </div>

        <div className="results-grid">
          <EmailResult
            title="Original AI Output"
            result={results.baseline}
            loading={loading.baseline}
            error={errors.baseline}
          />
          <EmailResult
            title="Improved AI Output"
            focusNote="Focus: clarity, tone & meaning preservation"
            result={results.improved}
            loading={loading.improved}
            error={errors.improved}
          />
        </div>
      </section>

      <ComparisonPanel
        results={results}
        evaluations={evaluations}
        onEvaluationChange={updateEvaluation}
      />

      <footer className="page-footer">
        Scores reflect your checklist selections, not an objective measure of AI quality.
      </footer>
    </main>
  );
}

export default App;