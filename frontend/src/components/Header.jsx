function Header({ nodes }) {
  const onlineNodes = nodes.filter(
    (node) => node.status === "Online"
  ).length;

  const totalNodes = nodes.length;

  let statusText = "Checking System...";
  let statusClass = "checking";

  if (totalNodes > 0) {
    if (onlineNodes === totalNodes) {
      statusText = "🟢 System Healthy";
      statusClass = "healthy";
    } else if (onlineNodes >= 2) {
      statusText = "🟡 System Degraded";
      statusClass = "degraded";
    } else {
      statusText = "🔴 System Critical";
      statusClass = "critical";
    }
  }

  return (
    <div className="header">
      <div>
        <h1>MiniVault Dashboard</h1>
        <p>Distributed Backup System</p>
      </div>

      <div className={`status ${statusClass}`}>
        {statusText}
      </div>
    </div>
  );
}

export default Header;