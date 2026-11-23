export function TerminalLeftRail() {
  return (
    <aside className="left" aria-label="Workspace status">
      <div className="tag">WORKSPACE</div>
      <button className="nav" type="button" aria-label="AI Terminal is active">
        ◉ &nbsp;AI Terminal
      </button>
      <div className="tag tag-spaced">STATUS</div>
      <div className="box">
        <div className="k">INTERFACE</div>
        <div className="green">● Active</div>
      </div>
      <div className="box">
        <div className="k">CHAT MEMORY</div>
        <div className="red">● Temporary</div>
      </div>
    </aside>
  );
}
