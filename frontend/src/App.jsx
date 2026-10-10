import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import "./App.css";

import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import Dashboard from "./components/Dashboard";
import BackupCard from "./components/BackupCard";
import BackupList from "./components/BackupList";
import Metrics from "./components/Metrics";
import Activity from "./components/Activity";

function App() {
  const [page, setPage] = useState("dashboard");
  const [backupRefreshKey, setBackupRefreshKey] = useState(0);

  // Store cluster/node status here
  const [nodes, setNodes] = useState([]);

  const loadCluster = useCallback(async () => {
    try {
      const response = await axios.get(
        "http://127.0.0.1:5000/cluster"
      );

      setNodes(response.data);
    } catch (error) {
      console.error("Error loading cluster status:", error);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadCluster);

    // Refresh every 5 seconds
    const interval = setInterval(() => {
      loadCluster();
    }, 5000);

    return () => clearInterval(interval);
  }, [loadCluster]);

  return (
    <div className="app">
      <Sidebar setPage={setPage} />

      <div className="content">

        <Header nodes={nodes} />

        {page === "dashboard" && (
          <>
            <Dashboard nodes={nodes} />
            <BackupCard onBackupSuccess={() => setBackupRefreshKey((key) => key + 1)} />
            <BackupList refreshKey={backupRefreshKey} />
          </>
        )}

        {page === "backups" && <BackupList refreshKey={backupRefreshKey} />}

        {page === "metrics" && <Metrics />}

        {page === "activity" && <Activity />}

        {page === "settings" && (
          <h2>⚙️ Settings (Coming Soon)</h2>
        )}

      </div>
    </div>
  );
}

export default App;