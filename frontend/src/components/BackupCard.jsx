import { useState } from "react";
import axios from "axios";

function BackupCard({ onBackupSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleBackup = async () => {
    if (!selectedFile) {
      setError("Please select a file first.");
      setMessage("");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);
    setIsBackingUp(true);
    setError("");
    setMessage("");

    try {
      const response = await axios.post(
        "http://127.0.0.1:5000/backup",
        formData
      );
      setMessage(response.data.message);
      onBackupSuccess?.();
    } catch (requestError) {
      console.error("Backup error:", requestError);
      setError(
        requestError.response?.data?.error ||
          "Backup failed. Check that the backend and storage nodes are available."
      );
    } finally {
      setIsBackingUp(false);
    }
  };

  return (
    <div className="backup-card">
      <h2>📂 Backup File</h2>

      <p className="card-description">
        Select a file to store securely across distributed nodes.
      </p>

      <input
        type="file"
        onChange={(e) => {
          setSelectedFile(e.target.files[0] || null);
          setError("");
          setMessage("");
        }}
      />

      <button
        className="backup-btn"
        onClick={handleBackup}
        disabled={isBackingUp}
      >
        {isBackingUp ? "Backing up..." : "Backup File"}
      </button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </div>
  );
}

export default BackupCard;