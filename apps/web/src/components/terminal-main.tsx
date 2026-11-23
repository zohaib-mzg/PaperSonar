"use client";

import type { RefObject } from "react";
import { PromptChips } from "@/components/prompt-chips";
import { TerminalComposer } from "@/components/terminal-composer";
import { TerminalMessage } from "@/components/terminal-message";
import type { TerminalMessage as TerminalMessageData } from "@/components/terminal-shell";

type TerminalMainProps = {
  messages: TerminalMessageData[];
  chips: readonly string[];
  showChips: boolean;
  input: string;
  busy: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (question?: string) => void;
};

export function TerminalMain({
  messages,
  chips,
  showChips,
  input,
  busy,
  textareaRef,
  onInputChange,
  onSubmit,
}: TerminalMainProps) {
  return (
    <main>
      <div className="path">
        ~/papersonar/<b>terminal</b>
      </div>
      <div className="stats">
        <div className="box">
          <div className="k">MODE</div>
          <div className="v green">Research</div>
        </div>
        <div className="box">
          <div className="k">ENGINE</div>
          <div className="v">Ready</div>
        </div>
        <div className="box">
          <div className="k">EVIDENCE</div>
          <div className="v">Enabled</div>
        </div>
      </div>
      <div id="msgs" aria-live="polite" aria-label="Conversation">
        {messages.map((message) => (
          <TerminalMessage key={message.id} message={message} />
        ))}
      </div>
      {showChips ? <PromptChips chips={chips} onSelect={onSubmit} /> : null}
      <TerminalComposer
        input={input}
        busy={busy}
        textareaRef={textareaRef}
        onInputChange={onInputChange}
        onSubmit={onSubmit}
      />
    </main>
  );
}
