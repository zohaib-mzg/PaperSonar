import type { ActivityItem } from "@/components/terminal-shell";

const DOT_CLASS = {
  done: "green",
  pending: "amber",
  failed: "red",
} as const;

export function TerminalRightRail({ activity }: { activity: ActivityItem[] }) {
  return (
    <aside className="right" aria-label="Activity">
      <div className="tag">ACTIVITY</div>
      {activity.map((item) => (
        <div className="row" key={item.id}>
          <span className={DOT_CLASS[item.state]} aria-hidden="true">
            ●
          </span>
          <div>{item.label}</div>
        </div>
      ))}
      <div className="tag tag-spaced">ANSWER INCLUDES</div>
      <div className="box">Summary<br />Metrics<br />Evidence<br />Caveats</div>
    </aside>
  );
}
