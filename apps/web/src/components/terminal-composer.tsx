"use client";

import type { KeyboardEvent, RefObject } from "react";

type TerminalComposerProps = {
  input: string;
  busy: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (question?: string) => void;
};

export function TerminalComposer({
  input,
  busy,
  textareaRef,
  onInputChange,
  onSubmit,
}: TerminalComposerProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <form
      id="f"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <textarea
        id="in"
        ref={textareaRef}
        name="question"
        rows={2}
        value={input}
        placeholder="Ask about published research..."
        aria-label="Ask about published research"
        disabled={busy}
        onChange={(event) => onInputChange(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button id="send" type="submit" disabled={busy} aria-label="Send question">
        {busy ? "…" : "Send"}
      </button>
    </form>
  );
}
