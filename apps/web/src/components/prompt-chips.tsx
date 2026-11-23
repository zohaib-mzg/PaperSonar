"use client";

export function PromptChips({
  chips,
  onSelect,
}: {
  chips: readonly string[];
  onSelect: (question: string) => void;
}) {
  return (
    <div className="chips" id="chips">
      {chips.map((chip) => (
        <button
          key={chip}
          type="button"
          aria-label={`Ask: ${chip}`}
          onClick={() => onSelect(chip)}
        >
          {chip}
        </button>
      ))}
    </div>
  );
}
