import { useCallback, useEffect, useState } from "react";
import axios from "axios";

async function getRequestErrorMessage(error, fallback) {
  const data = error.response?.data;
  if (data instanceof Blob) {
    try {
      const response = JSON.parse(await data.text());
      return response.error || fallback;
    } catch {
      return fallback;
    }
  }
  return data?.error || fallback;
}

function BackupList({ refreshKey }) {
  const [backups, setBackups] = useState([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [busyFile, setBusyFile] = useState("");

  const loadBackups = useCallback(async () => {
    try {
      const response = await axios.get(
        "http://127.0.0.1:5000/backups"
      );

      setBackups(response.data);
      setError("");
    } catch (requestError) {
      console.error("Error loading backups:", requestError);
      setError("Could not load backups. Check that the backend is running.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadBackups);
  }, [loadBackups, refreshKey]);

  const handleRestore = async (filename) => {
    setBusyFile(filename);
    setMessage("");
    setError("");
    try {
      const response = await axios.post(
        "http://127.0.0.1:5000/restore",
        { filename },
        { responseType: "blob" }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setMessage(`Restored "${filename}" successfully.`);
    } catch (requestError) {
      console.error("Restore error:", requestError);
      setError(
        await getRequestErrorMessage(
          requestError,
          `Restore of "${filename}" failed.`
        )
      );
    } finally {
      setBusyFile("");
    }
  };

  const handleDelete = async (filename) => {
    const confirmDelete = window.confirm(
      `Are you sure you want to delete ${filename}?`
    );

    if (!confirmDelete) return;

    setBusyFile(filename);
    setMessage("");
    setError("");
    try {
      const response = await axios.post(
        "http://127.0.0.1:5000/delete",
        { filename }
      );
      setMessage(response.data.message);
      await loadBackups();
    } catch (requestError) {
      console.error("Delete error:", requestError);
      setError(
        await getRequestErrorMessage(
          requestError,
          `Delete of "${filename}" failed.`
        )
      );
    } finally {
      setBusyFile("");
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024)
      return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };
  const filteredBackups = backups.filter((file) =>
    file.filename.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="backup-list">
      <h2>📁 Stored Backups</h2>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <input
        type="text"
        placeholder="🔍 Search backups..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="search-box"
      />

      <table>
        <thead>
          <tr>
            <th>Filename</th>
            <th>Size</th>
            <th>Chunks</th>
            <th>Uploaded On</th>
            <th>Replicated On</th>
            <th>Restore</th>
            <th>Delete</th>
          </tr>
        </thead>

        <tbody>
          {isLoading && (
            <tr><td colSpan="7">Loading backups...</td></tr>
          )}
          {!isLoading && filteredBackups.length === 0 && (
            <tr><td colSpan="7">No backups found.</td></tr>
          )}
          {!isLoading && filteredBackups.map((file) => (
            <tr key={file.filename}>
              <td>{file.filename}</td>
              <td>{formatFileSize(file.file_size)}</td>
              <td>{file.chunk_count}</td>
              <td>{file.upload_time}</td>
              <td>
                {file.replicated_on?.length > 0
                  ? file.replicated_on.join(", ")
                  : "N/A"}
              </td>

              <td>
                <button
                  className="restore-btn"
                  onClick={() => handleRestore(file.filename)}
                  disabled={busyFile === file.filename}
                >
                  Restore
                </button>
              </td>

              <td>
                <button
                  className="delete-btn"
                  onClick={() => handleDelete(file.filename)}
                  disabled={busyFile === file.filename}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default BackupList;