import { useEffect, useRef, useState } from "react";
import { ChevronDown, LoaderCircle, WandSparkles } from "lucide-react";
import emailSuggestions from "../data/emailSuggestions.js";

function EmailForm({ emailInput, onInputChange, onGenerate, loading }) {
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [showAllSuggestions, setShowAllSuggestions] = useState(true);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const suggestionsOpenRef = useRef(false);
  const activeSuggestionRef = useRef(-1);
  const suggestionsRef = useRef(null);
  const messageRef = useRef(null);

  const searchText = showAllSuggestions ? "" : emailInput.message.trim().toLocaleLowerCase();
  const visibleGroups = emailSuggestions
    .map((group) => ({
      ...group,
      suggestions: group.suggestions.filter((suggestion) =>
        suggestion.toLocaleLowerCase().includes(searchText),
      ),
    }))
    .filter((group) => group.suggestions.length > 0);

  const flatSuggestions = visibleGroups.flatMap((group) => group.suggestions);

  function updateField(event) {
    const { name, value } = event.target;
    onInputChange((current) => ({ ...current, [name]: value }));
    setShowAllSuggestions(false);
    updateActiveSuggestion(-1);
    updateSuggestionsOpen(true);
  }

  function updateActiveSuggestion(index) {
    const nextIndex = typeof index === "function" ? index(activeSuggestionRef.current) : index;
    activeSuggestionRef.current = nextIndex;
    setActiveSuggestion(nextIndex);
  }

  function updateSuggestionsOpen(isOpen) {
    suggestionsOpenRef.current = isOpen;
    setSuggestionsOpen(isOpen);
  }

  function openSuggestions(showAll = true) {
    setShowAllSuggestions(showAll);
    updateActiveSuggestion(-1);
    updateSuggestionsOpen(true);
  }

  function selectSuggestion(suggestion) {
    onInputChange((current) => ({ ...current, message: suggestion }));
    updateSuggestionsOpen(false);
    setShowAllSuggestions(true);
    updateActiveSuggestion(-1);
    messageRef.current?.focus();
  }

  function handleMessageKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!suggestionsOpenRef.current) {
        openSuggestions();
        updateActiveSuggestion(0);
      } else if (flatSuggestions.length > 0) {
        updateActiveSuggestion((current) =>
          current < 0 ? 0 : (current + 1) % flatSuggestions.length,
        );
      }
    } else if (event.key === "ArrowUp" && suggestionsOpenRef.current && flatSuggestions.length > 0) {
      event.preventDefault();
      updateActiveSuggestion((current) =>
        current <= 0 ? flatSuggestions.length - 1 : current - 1,
      );
    } else if (
      event.key === "Enter" &&
      suggestionsOpenRef.current &&
      activeSuggestionRef.current >= 0
    ) {
      event.preventDefault();
      selectSuggestion(flatSuggestions[activeSuggestionRef.current]);
    } else if (event.key === "Escape" && suggestionsOpenRef.current) {
      event.preventDefault();
      updateSuggestionsOpen(false);
      updateActiveSuggestion(-1);
    }
  }

  useEffect(() => {
    if (!suggestionsOpen) return undefined;

    function closeOnOutsideClick(event) {
      if (!suggestionsRef.current?.contains(event.target)) {
        updateSuggestionsOpen(false);
        updateActiveSuggestion(-1);
      }
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, [suggestionsOpen]);

  let suggestionIndex = -1;

  function renderSuggestion(suggestion) {
    suggestionIndex += 1;
    const currentIndex = suggestionIndex;
    return (
      <button
        aria-selected={activeSuggestion === currentIndex}
        className={`suggestion-option ${activeSuggestion === currentIndex ? "suggestion-option-active" : ""}`}
        id={`email-suggestion-${currentIndex}`}
        key={suggestion}
        onClick={() => selectSuggestion(suggestion)}
        onKeyDown={handleMessageKeyDown}
        onMouseEnter={() => updateActiveSuggestion(currentIndex)}
        onMouseDown={(event) => event.preventDefault()}
        role="option"
        tabIndex={-1}
        type="button"
      >
        {suggestion}
      </button>
    );
  }

  return (
    <section className="form-panel" aria-labelledby="form-title">
      <div className="form-heading">
        <div>
          <p className="eyebrow">START WITH THE IDEA</p>
          <h2 id="form-title">What do you need to say?</h2>
        </div>
        <span className="required-note"><span>*</span> Required</span>
      </div>

      <div className="message-field" ref={suggestionsRef}>
        <label className="field-label" htmlFor="message">Email purpose or original message <span>*</span></label>
        <div className="message-input-wrap">
          <textarea
            aria-activedescendant={activeSuggestion >= 0 ? `email-suggestion-${activeSuggestion}` : undefined}
            aria-autocomplete="list"
            aria-controls="email-suggestion-list"
            aria-expanded={suggestionsOpen}
            aria-haspopup="listbox"
            aria-describedby="message-hint"
            autoComplete="off"
            id="message"
            name="message"
            onChange={updateField}
            onClick={() => openSuggestions()}
            onFocus={() => openSuggestions()}
            onKeyDown={handleMessageKeyDown}
            placeholder="e.g. Ask my manager for leave tomorrow because of personal work"
            ref={messageRef}
            role="combobox"
            rows="3"
            maxLength="4000"
            value={emailInput.message}
            required
          />
          <button
            aria-expanded={suggestionsOpen}
            aria-label={suggestionsOpen ? "Close email suggestions" : "Show email suggestions"}
            aria-controls="email-suggestion-list"
            className="suggestion-toggle"
            onKeyDown={handleMessageKeyDown}
            onClick={() => {
              if (suggestionsOpen) {
                updateSuggestionsOpen(false);
                updateActiveSuggestion(-1);
              } else {
                openSuggestions();
              }
            }}
            type="button"
          >
            <ChevronDown aria-hidden="true" size={16} />
          </button>
          {suggestionsOpen && (
            <div className="suggestion-menu" id="email-suggestion-list" role="listbox" aria-label="Email request suggestions">
              {visibleGroups.length > 0 ? visibleGroups.map((group) => (
                <div aria-label={group.category} className="suggestion-group" key={group.category} role="group">
                  <span className="suggestion-category" role="presentation">{group.category}</span>
                  {group.suggestions.map(renderSuggestion)}
                </div>
              )) : (
                <p className="suggestion-empty">No matching suggestions. Keep typing your own message.</p>
              )}
            </div>
          )}
        </div>
        <p className="field-hint" id="message-hint">Choose a suggestion or write your own.</p>
      </div>

      <div className="form-row">
        <div className="field-group">
          <label className="field-label" htmlFor="recipient">Recipient <span className="optional-label">Optional</span></label>
          <input
            id="recipient"
            name="recipient"
            type="text"
            maxLength="200"
            placeholder="e.g. My manager"
            value={emailInput.recipient}
            onChange={updateField}
          />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="tone">Tone</label>
          <select id="tone" name="tone" value={emailInput.tone} onChange={updateField}>
            <option>Professional</option>
            <option>Friendly</option>
            <option>Formal</option>
            <option>Casual</option>
          </select>
        </div>
      </div>

      <label className="field-label" htmlFor="instructions">Additional instructions <span className="optional-label">Optional</span></label>
      <input
        id="instructions"
        name="instructions"
        type="text"
        maxLength="2000"
        placeholder="e.g. Keep it brief and mention I can be reached by phone"
        value={emailInput.instructions}
        onChange={updateField}
      />

      <div className="form-actions">
        <button
          className="button button-original"
          type="button"
          onClick={() => onGenerate("baseline")}
          disabled={loading.baseline}
        >
          {loading.baseline ? <LoaderCircle className="spin" size={16} /> : <WandSparkles size={16} />}
          {loading.baseline ? "Generating…" : "Generate Original"}
        </button>
        <button
          className="button button-improved"
          type="button"
          onClick={() => onGenerate("improved")}
          disabled={loading.improved}
        >
          {loading.improved ? <LoaderCircle className="spin" size={16} /> : <WandSparkles size={16} />}
          {loading.improved ? "Generating…" : "Generate Improved"}
        </button>
      </div>
    </section>
  );
}

export default EmailForm;