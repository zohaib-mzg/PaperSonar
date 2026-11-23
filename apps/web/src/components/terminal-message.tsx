import { AnswerChart } from "@/components/answer-chart";
import { AnswerEvidence } from "@/components/answer-evidence";
import type { ChatAnswer } from "@/lib/chat-types";
import type { TerminalMessage as TerminalMessageData } from "@/components/terminal-shell";

export function TerminalMessage({ message }: { message: TerminalMessageData }) {
  const label = message.role === "bot" ? "PAPERSONAR" : "YOU";

  return (
    <div className={`m ${message.role}`}>
      <small>{label}</small>
      <div className="answer-text">{message.text}</div>
      {message.pending ? <span className="pending" aria-label="Waiting for answer">▌</span> : null}
      {message.answer ? (
        <div className="answer-body">
          <AnswerEvidence answer={message.answer} />
          {message.answer.chart ? <AnswerChart chart={message.answer.chart} /> : null}
          {message.answer.facts.coverage_note ? (
            <p className="chart-note">{message.answer.facts.coverage_note}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export type { ChatAnswer };
