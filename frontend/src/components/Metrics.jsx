import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from "recharts";
function Metrics() {

  const [metrics, setMetrics] = useState({
    total_backups: 0,
    total_restores: 0,
    chunks_stored: 0,
    chunks_skipped: 0,
  });

  const loadMetrics = useCallback(async () => {

    try {

      const response = await axios.get(
        "http://127.0.0.1:5000/metrics"
      );

      setMetrics(response.data);

    } catch (error) {

      console.error("Error loading metrics:", error);

    }

  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadMetrics);
  }, [loadMetrics]);

  const chartData = [
  {
    name: "Backups",
    value: metrics.total_backups,
  },
  {
    name: "Restores",
    value: metrics.total_restores,
  },
  {
    name: "Chunks",
    value: metrics.chunks_stored,
  },
  {
    name: "Duplicates",
    value: metrics.chunks_skipped,
  },
];
return (
  <>
    <h2 className="section-title">Storage Dashboard</h2>

    <div className="metrics-grid">

      <div className="metric-card">
        <h3>📦 Total Backups</h3>
        <h1>{metrics.total_backups}</h1>
      </div>

      <div className="metric-card">
        <h3>🔄 Total Restores</h3>
        <h1>{metrics.total_restores}</h1>
      </div>

      <div className="metric-card">
        <h3>🧩 Chunks Stored</h3>
        <h1>{metrics.chunks_stored}</h1>
      </div>

      <div className="metric-card">
        <h3>💾 Duplicate Chunks Saved</h3>
        <h1>{metrics.chunks_skipped}</h1>
      </div>

    </div>
    <h2 className="section-title" style={{ marginTop: "40px" }}>
  Storage Analytics
</h2>

<div
  style={{
    width: "100%",
    height: 350,
    background: "#fff",
    borderRadius: "12px",
    padding: "20px",
    boxShadow: "0 4px 12px rgba(0,0,0,0.12)"
  }}
>
  <ResponsiveContainer width="100%" height="100%">
    <BarChart data={chartData}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="name" />
      <YAxis />
      <Tooltip />
      <Bar dataKey="value" fill="#2563eb" />
    </BarChart>
  </ResponsiveContainer>
</div>
  </>
);
}
export default Metrics;