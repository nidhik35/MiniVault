function Sidebar({ setPage }) {
  return (
    <div className="sidebar">
      <h2 className="logo">MiniVault</h2>

      <ul className="menu">
        <li onClick={() => setPage("dashboard")}>
          🏠 Dashboard
        </li>

        <li onClick={() => setPage("backups")}>
          📂 Backups
        </li>

        <li onClick={() => setPage("metrics")}>
          📊 Metrics
        </li>

        <li onClick={() => setPage("activity")}>
          📝 Activity
        </li>

        <li onClick={() => setPage("settings")}>
          ⚙️ Settings
        </li>
      </ul>
    </div>
  );
}

export default Sidebar;