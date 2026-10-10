import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import "./Dashboard.css";

function Dashboard({ nodes }) {
  const [metrics, setMetrics] = useState({});

  // Load system metrics
  const loadMetrics = useCallback(async () => {
    try {
      const res = await axios.get(
        "http://127.0.0.1:5000/metrics"
      );

      setMetrics(res.data);
    } catch (err) {
      console.error("Error loading metrics:", err);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadMetrics);

    // Refresh metrics every 5 seconds
    const interval = setInterval(() => {
      loadMetrics();
    }, 5000);

    return () => clearInterval(interval);
  }, [loadMetrics]);

  const formatFileSize = (bytes) => {
    if (bytes < 1024) {
      return `${bytes} B`;
    }

    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(2)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const healthyNodes = nodes.filter(
    (node) => node.status === "Online"
  ).length;

  return (
    <>
      <h2 className="section-title">Cluster Status</h2>

      <div className="cluster">
        {nodes.map((node, index) => (
          <div className="node-card" key={index}>
            <h3>🖥 {node.name}</h3>

            <p
              className={
                node.status === "Online"
                  ? "online"
                  : "offline"
              }
            >
              {node.status === "Online" ? "🟢" : "🔴"}{" "}
              {node.status}
            </p>
          </div>
        ))}
      </div>

      <h2 className="section-title">System Metrics</h2>

      <div className="metrics">

        <div className="metric-card">
          <h3>📦 Total Backups</h3>
          <p>{metrics.total_backups ?? 0}</p>
        </div>

        <div className="metric-card">
          <h3>💾 Storage Used</h3>
          <p>
            {formatFileSize(metrics.total_storage ?? 0)}
          </p>
        </div>

        <div className="metric-card">
          <h3>🧩 Total Chunks</h3>
          <p>{metrics.total_chunks ?? 0}</p>
        </div>

        <div className="metric-card">
          <h3>♻️ Duplicate Chunks</h3>
          <p>{metrics.chunks_skipped ?? 0}</p>
        </div>

        <div className="metric-card">
          <h3>🖥️ Healthy Nodes</h3>
          <p>
            {healthyNodes} / {nodes.length}
          </p>
        </div>

      </div>
    </>
  );
}

export default Dashboard;