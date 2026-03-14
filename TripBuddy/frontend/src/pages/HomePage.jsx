import { Link } from "react-router-dom";
import { PlannerChat, PlannerChatPlaceholder } from "../components/PlannerChat";
import { ReportPanel } from "../components/ReportPanel";
import { TravelForm } from "../components/TravelForm";
import { usePlannerSession } from "../hooks/usePlannerSession";

export function HomePage() {
  const {
    form,
    setForm,
    loading,
    error,
    hasStarted,
    stepStatus,
    messages,
    currentStatus,
    passBadgeText,
    technicalLines,
    showDetails,
    setShowDetails,
    chatInput,
    setChatInput,
    sessionId,
    socketReady,
    report,
    createSessionAndRun,
    onRefine,
    stopAndReset,
  } = usePlannerSession();

  return (
    <div className="page">
      <header className="topbar">
        <h1>TripBuddy</h1>
        <Link to="/help">How It Works</Link>
      </header>

      <main className="layout">
        <TravelForm form={form} setForm={setForm} loading={loading} error={error} onStart={createSessionAndRun} />

        {!hasStarted ? (
          <PlannerChatPlaceholder />
        ) : (
          <PlannerChat
            stepStatus={stepStatus}
            messages={messages}
            currentStatus={currentStatus}
            passBadgeText={passBadgeText}
            technicalLines={technicalLines}
            showDetails={showDetails}
            setShowDetails={setShowDetails}
            chatInput={chatInput}
            setChatInput={setChatInput}
            onRefine={onRefine}
            loading={loading}
            sessionId={sessionId}
            socketReady={socketReady}
            onReset={stopAndReset}
            hasStarted={hasStarted}
          />
        )}
      </main>

      <ReportPanel report={report} />
    </div>
  );
}
