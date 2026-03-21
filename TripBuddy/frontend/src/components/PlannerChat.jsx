import { ProgressSteps } from "./ProgressSteps";

export function PlannerChatPlaceholder() {
  return (
    <section className="panel chat-panel">
      <h2>Planner Chat</h2>
      <p>Chat and live status will appear after you click Start Planning.</p>
    </section>
  );
}

export function PlannerChat({
  stepStatus,
  messages,
  currentStatus,
  passBadgeText,
  technicalLines,
  showDetails,
  setShowDetails,
  chatInput,
  setChatInput,
  onRefine,
  loading,
  sessionId,
  socketReady,
  onReset,
  hasStarted,
}) {

  const blockedPatterns = [
    /(ignore|disregard|forget|bypass).*(instruction|instructions|rules|guidelines|history|histories)/i, //Override / ignore instructions
    /(you are now|act as|pretend to be|roleplay as)/i, //Role / identity hijacking
    /(system prompt|hidden prompt|internal instructions|developer message)/i, //System prompt extraction
    /(reveal|show|leak|expose).*(prompt|policy|secret|key|password|hidden)/i, //Data exfiltration attempts
    /(jailbreak|developer mode|no restrictions|unfiltered|disable safety)/i, //Safety bypass language
    /(start over|reset instructions|clear rules|forget everything)/i, //Instruction reset patterns
    /(ign[o0]re|byp[a@]ss|rul[e3]s|instruct[i1]ons)/i, //Obfuscation-lite
  ];

  const normalizeText = (text) => {
    return text
      .normalize("NFKC") // Unicode normalization (prevents obfuscation)
      .toLowerCase()
      .trim();
  };

  function validatePrompt(prompt) {
    const normalized = normalizeText(prompt);

    const isBlocked = blockedPatterns.some((pattern) =>
      pattern.test(normalized)
    );

    if (isBlocked) {
      return {
        valid: false,
        reason: "Prompt injection attempt detected."
      };
    }

    if (prompt.length > 2000) {
      return { valid: false, reason: "Prompt too long." };
    }

    return { valid: true };
  };

  const handleRefine = () => {
    const result = validatePrompt(chatInput);

    if (!result.valid) {
      alert(result.reason); // you can replace with UI error
      return;
    }

    onRefine();
  };

  return (
    <section className="panel chat-panel">
      <h2>Planner Chat</h2>
      <ProgressSteps stepStatus={stepStatus} />
      <div className="messages">
        {messages.map((msg, i) => (
          <article className={`msg ${msg.role}`} key={i}>
            {msg.text}
          </article>
        ))}
        <article className="msg assistant status-msg">{currentStatus}</article>
      </div>
      {passBadgeText && <p className="pass-badge">{passBadgeText}</p>}
      {technicalLines.length > 0 && (
        <details className="details-panel" open={showDetails} onToggle={(e) => setShowDetails(e.currentTarget.open)}>
          <summary>Details</summary>
          <div className="details-list">
            {technicalLines.map((line, i) => (
              <p key={`${line}-${i}`}>{line}</p>
            ))}
          </div>
        </details>
      )}
      <div className="chat-input">
        <input
          placeholder="Let TripBuddy know what to adjust..."
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleRefine();
          }}
        />
        <button disabled={loading || !sessionId || !socketReady} onClick={handleRefine}>
          Send
        </button>
      </div>
      <div className="chat-footer">
        <button className="danger-btn" disabled={!hasStarted && !loading} onClick={onReset}>
          Reset
        </button>
      </div>
    </section>
  );
}
