import { TerminalSonarIcon } from "@/components/terminal-sonar-icon";

export function TerminalHeader({ onNewChat }: { onNewChat: () => void }) {
  return (
    <header>
      <div className="brand">
        <div className="icon">
          <TerminalSonarIcon />
        </div>
        <div>
          <div className="logo">
            Paper<span>Sonar</span>
          </div>
          <div className="sub">RESEARCH INTELLIGENCE</div>
        </div>
      </div>
      <div className="hr">
        <span className="green" aria-label="Status ready">
          ● READY
        </span>
        <button id="new" type="button" onClick={onNewChat} aria-label="Start a new chat">
          + New chat
        </button>
      </div>
    </header>
  );
}
