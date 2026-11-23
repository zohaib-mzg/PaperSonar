"use client";

import { useState } from "react";
import { sendFeedback } from "@/lib/chat-api";
import { track } from "@/lib/analytics";
import type { ChatAnswer } from "@/lib/chat-types";

function cell(value: string | number | boolean | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export function AnswerEvidence({ answer }: { answer: ChatAnswer }) {
  const [sent, setSent] = useState(false);
  const rows = answer.facts.rows.slice(0, 8);
  const headers = rows.length > 0 ? Object.keys(rows[0]) : [];

  const feedback = async (rating: "helpful" | "not_helpful", reason: string) => {
    if (!answer.request_id || sent) return;
    setSent(true);
    track("chat_feedback", {
      request_id: answer.request_id,
      metric_id: answer.metric_id ?? undefined,
      rating,
      reason,
    });
    try {
      await sendFeedback({
        request_id: answer.request_id,
        rating,
        reason: reason as "wrong_number" | "wrong_topic" | "not_relevant" | "missing_data" | "other",
      });
    } catch {
      // Feedback is best-effort.
    }
  };

  return (
    <div className="evidence">
      {answer.interpretation ? (
        <div className="evidence-line">
          <span>READING</span>
          {answer.interpretation}
        </div>
      ) : null}
      {answer.closest_match_disclosure ? (
        <div className="evidence-line warn">
          <span>MATCH</span>
          {answer.closest_match_disclosure}
        </div>
      ) : null}
      {answer.degraded ? (
        <div className="evidence-line warn">
          <span>NOTICE</span>
          {answer.degraded}
        </div>
      ) : null}
      <div className="evidence-line">
        <span>SCOPE</span>
        {answer.facts.source_scope}
      </div>
      <div className="evidence-line">
        <span>AS OF</span>
        {answer.facts.as_of ?? "As of latest snapshot"}
        {answer.facts.snapshot_date ? ` · snapshot ${answer.facts.snapshot_date}` : ""}
      </div>
      {answer.facts.denominators.length > 0 ? (
        <div className="evidence-line">
          <span>DENOMINATOR</span>
          {answer.facts.denominators.join(" · ")}
        </div>
      ) : null}
      {headers.length > 0 ? (
        <div className="evidence-table-wrap">
          <table className="evidence-table">
            <thead>
              <tr>
                {headers.map((header) => (
                  <th key={header} scope="col">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${cell(row[headers[0] ?? ""] ?? "")}-${index}`}>
                  {headers.map((header) => (
                    <td key={`${header}-${index}`}>{cell(row[header] ?? null)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {answer.facts.caveats.length > 0 ? (
        <ul className="evidence-list">
          {answer.facts.caveats.slice(0, 3).map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      ) : null}
      {answer.citations && answer.citations.length > 0 ? (
        <div className="evidence-line">
          <span>SOURCE</span>
          {answer.citations.map((citation) => citation.view).join(" · ")}
        </div>
      ) : null}
      {answer.status === "answered" && answer.request_id ? (
        <div className="feedback">
          <button type="button" disabled={sent} onClick={() => feedback("helpful", "other")} aria-label="Mark answer helpful">
            ↑ helpful
          </button>
          <button type="button" disabled={sent} onClick={() => feedback("not_helpful", "wrong_number")} aria-label="Mark answer as having a wrong number">
            ↓ wrong number
          </button>
        </div>
      ) : null}
    </div>
  );
}
