import { ArrowDownRight, ArrowUpRight, ClipboardCheck } from "lucide-react";

const criteria = [
  { id: "instructions", label: "Instruction-following" },
  { id: "tone", label: "Tone consistency" },
  { id: "structure", label: "Email structure" },
  { id: "meaning", label: "Preservation of original meaning" },
];

function score(evaluation) {
  return criteria.filter((criterion) => evaluation[criterion.id]).length;
}

function ComparisonPanel({ results, evaluations, onEvaluationChange }) {
  const originalScore = score(evaluations.baseline);
  const improvedScore = score(evaluations.improved);
  const hasBothResults = results.baseline && results.improved;
  const scoreDifference = improvedScore - originalScore;

  return (
    <section className="comparison-section" aria-labelledby="comparison-title">
      <div className="section-heading comparison-heading">
        <div>
          <p className="eyebrow">YOUR REVIEW</p>
          <h2 id="comparison-title">Compare what you notice</h2>
        </div>
        <span className="manual-tag"><ClipboardCheck size={15} /> Manual evaluation</span>
      </div>

      <div className="checklist-wrap">
        <div className="checklist-header">
          <span>Does each email…</span>
          <span>Original</span>
          <span>Improved</span>
        </div>
        {criteria.map((criterion) => (
          <div className="checklist-row" key={criterion.id}>
            <span className="criterion-label">{criterion.label}</span>
            {["baseline", "improved"].map((mode) => (
              <label className="check-cell" key={mode}>
                <input
                  type="checkbox"
                  aria-label={`${criterion.label}: ${mode === "baseline" ? "Original" : "Improved"}`}
                  checked={Boolean(evaluations[mode][criterion.id])}
                  onChange={(event) => onEvaluationChange(mode, criterion.id, event.target.checked)}
                />
              </label>
            ))}
          </div>
        ))}
      </div>

      <div className="score-summary">
        <div className="score-item">
          <span className="score-label">Original score</span>
          <strong>{originalScore}<span> / 4</span></strong>
        </div>
        <div className="score-item score-item-improved">
          <span className="score-label">Improved score</span>
          <strong>{improvedScore}<span> / 4</span></strong>
        </div>
        <div className="score-difference" aria-live="polite">
          {!hasBothResults ? (
            <span>Generate both emails to compare your results.</span>
          ) : scoreDifference === 0 ? (
            <span>Your checklist scores are currently equal.</span>
          ) : (
            <>
              {scoreDifference > 0 ? <ArrowUpRight size={17} /> : <ArrowDownRight size={17} />}
              <span>{Math.abs(scoreDifference)} more checked {Math.abs(scoreDifference) === 1 ? "item" : "items"} for {scoreDifference > 0 ? "improved" : "original"}</span>
            </>
          )}
        </div>
      </div>
      <p className="score-disclaimer">Scores are based on your checklist selections, not objective AI accuracy measurements.</p>
    </section>
  );
}

export default ComparisonPanel;