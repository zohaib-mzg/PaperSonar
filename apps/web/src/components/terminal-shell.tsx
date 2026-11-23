"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TerminalFooter } from "@/components/terminal-footer";
import { TerminalHeader } from "@/components/terminal-header";
import { TerminalLeftRail } from "@/components/terminal-left-rail";
import { TerminalMain } from "@/components/terminal-main";
import { TerminalRightRail } from "@/components/terminal-right-rail";
import { track } from "@/lib/analytics";
import { askQuestion, getHealth, resetSessionId } from "@/lib/chat-api";
import type { ChatAnswer, HealthResponse } from "@/lib/chat-types";

export type TerminalMessage = {
  id: number;
  role: "bot" | "user";
  text: string;
  answer?: ChatAnswer;
  pending?: boolean;
};

export type ActivityState = "done" | "pending" | "failed";

export type ActivityItem = {
  id: number;
  label: string;
  state: ActivityState;
};

const WELCOME =
  "Welcome! Your research workspace is ready. Ask a question about published research.";

const CHIPS = [
  "Which topics grew fastest in 2025?",
  "How many citations does RAG have?",
  "Compare OpenAlex and Crossref coverage.",
] as const;

const INITIAL_ACTIVITY: ActivityItem[] = [
  { id: 1, label: "Interface loaded", state: "done" },
  { id: 2, label: "Chat initialized", state: "done" },
  { id: 3, label: "Waiting for API", state: "pending" },
];

export function TerminalShell() {
  const [messages, setMessages] = useState<TerminalMessage[]>([
    { id: 0, role: "bot", text: WELCOME },
  ]);
  const [input, setInput] = useState("");
  const [showChips, setShowChips] = useState(true);
  const [activity, setActivity] = useState<ActivityItem[]>(INITIAL_ACTIVITY);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const nextIdRef = useRef(1);

  const nextId = useCallback(() => {
    nextIdRef.current += 1;
    return nextIdRef.current;
  }, []);

  useEffect(() => {
    void getHealth().then(setHealth);
  }, []);

  useEffect(() => {
    const container = document.getElementById("msgs");
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!health) return;
    setActivity((current) =>
      current.map((item) =>
        item.id === 3 && health.status === "not_ready"
          ? { ...item, label: "API not ready", state: "failed" }
          : item,
      ),
    );
  }, [health]);

  const submit = async (question?: string) => {
    const text = (question ?? input).trim();
    if (!text || busy) return;

    const userId = nextId();
    const pendingId = nextId();
    setMessages((current) => [
      ...current,
      { id: userId, role: "user", text },
      { id: pendingId, role: "bot", text: "Querying published reporting data…", pending: true },
    ]);
    setInput("");
    setShowChips(false);
    setBusy(true);
    setActivity([
      { id: 1, label: "Interface loaded", state: "done" },
      { id: 2, label: "Question accepted", state: "done" },
      { id: nextId(), label: "Querying published data", state: "pending" },
    ]);
    track("chat_submit", {});
    textareaRef.current?.focus();

    try {
      const answer = await askQuestion(text);
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId
            ? { id: pendingId, role: "bot", text: answer.answer, answer }
            : message,
        ),
      );
      setActivity([
        { id: 1, label: "Interface loaded", state: "done" },
        { id: 2, label: "Question accepted", state: "done" },
        {
          id: nextId(),
          label: answer.status === "answered" ? "Answer grounded" : "Answer returned",
          state: "done",
        },
      ]);
      track("chat_answer", {
        request_id: answer.request_id ?? undefined,
        metric_id: answer.metric_id ?? undefined,
        status: answer.status,
        provider: answer.provider,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "The assistant is temporarily unavailable.";
      setMessages((current) =>
        current.map((item) =>
          item.id === pendingId
            ? {
                id: pendingId,
                role: "bot",
                text: `${message} Published reporting pages remain available.`,
              }
            : item,
        ),
      );
      setActivity([
        { id: 1, label: "Interface loaded", state: "done" },
        { id: 2, label: "Question accepted", state: "done" },
        { id: nextId(), label: "Answer unavailable", state: "failed" },
      ]);
      track("chat_error", {});
    } finally {
      setBusy(false);
      textareaRef.current?.focus();
    }
  };

  const newChat = () => {
    resetSessionId();
    nextIdRef.current = 1;
    setMessages([{ id: 0, role: "bot", text: WELCOME }]);
    setInput("");
    setShowChips(true);
    setActivity(INITIAL_ACTIVITY);
    setBusy(false);
    textareaRef.current?.focus();
  };

  return (
    <div className="app">
      <TerminalHeader onNewChat={newChat} />
      <div className="body">
        <TerminalLeftRail />
        <TerminalMain
          messages={messages}
          chips={CHIPS}
          showChips={showChips}
          input={input}
          busy={busy}
          textareaRef={textareaRef}
          onInputChange={setInput}
          onSubmit={submit}
        />
        <TerminalRightRail activity={activity} />
      </div>
      <TerminalFooter />
    </div>
  );
}
