# MiniVault

MiniVault is a local prototype of a distributed file-backup system. It splits files into 64 KiB chunks, identifies chunks with SHA-256, stores each new chunk on two of three local storage nodes, and provides a Flask API and React dashboard for backup, restore, deletion, and monitoring.

## Architecture

```text
React/Vite dashboard (localhost:5173)
              |
              v
Flask API (localhost:5000) ---- JSON manifests, activity, and metrics
              |
              v
Coordinator ---- chunk_locations.json
    |          |          |
    v          v          v
 Node 1      Node 2      Node 3
 :5001       :5002       :5003
```

- `api.py` exposes the HTTP API and connects it to the backup engine.
- `backup_engine.py` chunks files, stages backups, reconstructs restores in manifest order, and tracks successful operations.
- `coordinator.py` deduplicates chunks, records replica locations and reference counts, and retrieves verified chunks from recorded replicas.
- `node.py` is the Flask storage-node service. Each instance is given its own port and storage directory.
- `manifest.py`, `activity.py`, and `metrics.py` persist metadata as JSON.
- `frontend/src/` contains the React dashboard and its components.
- `tests/test_backup_system.py` exercises backend behavior with temporary data and mocked node HTTP requests.

## Requirements and installation

Use Python 3.10 or later, Node.js/npm, and PowerShell. From the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

If PowerShell blocks virtual-environment activation, invoke `.\.venv\Scripts\python.exe` directly in the commands below.

## Start MiniVault

Run each command in a separate terminal from the project root. Start the three nodes first:

```powershell
.\.venv\Scripts\python.exe node.py 5001 node1_storage
```

```powershell
.\.venv\Scripts\python.exe node.py 5002 node2_storage
```

```powershell
.\.venv\Scripts\python.exe node.py 5003 node3_storage
```

Then start the API:

```powershell
.\.venv\Scripts\python.exe api.py
```

Finally, start the dashboard in another terminal:

```powershell
cd frontend
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). Node processes create their storage folders if they do not already exist. Run all services on the same machine; this prototype uses loopback node URLs.

## Use the dashboard or CLI

On the dashboard, select a file and choose **Backup File**. Use **Backups** to search, restore, or delete a saved backup. The dashboard downloads a restored file to the browser; the backend also reconstructs it under `restored/`.

The CLI can run from the project root:

```powershell
.\.venv\Scripts\python.exe backup_engine.py backup .\data\sample.txt
.\.venv\Scripts\python.exe backup_engine.py restore sample.txt
.\.venv\Scripts\python.exe backup_engine.py delete sample.txt
.\.venv\Scripts\python.exe backup_engine.py metrics
```

Restore and delete use the saved backup filename (not the original source path).

## API

The API listens on `http://127.0.0.1:5000`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API health status |
| `GET` | `/metrics` | Backup/restore counters and logical backup storage totals |
| `GET` | `/backups` | Saved manifests and recorded replica node names |
| `POST` | `/backup` | Upload one file as multipart field `file` |
| `POST` | `/restore` | JSON body `{"filename":"sample.txt"}`; returns the file as a download |
| `POST` | `/delete` | JSON body `{"filename":"sample.txt"}` |
| `GET` | `/cluster` | Health status for each configured node |
| `GET` | `/activity` | Recent successful and failed operations |

Requests with missing or invalid filenames return `400`; missing backups return `404`. A restore that cannot recover a chunk returns `502`. A backup that cannot create the required replicas returns `503`. Other unexpected server errors are logged by Flask and return a failure response.

Each storage node exposes `GET /health`, `PUT /chunk/<sha256>`, `GET /chunk/<sha256>`, and `DELETE /chunk/<sha256>`. Chunk GET returns bytes or `404` when absent. The API and node routes are intended for local development, not exposure to an untrusted network.

## Chunking and replication

Files are read as 64 KiB binary chunks. Each chunk's lowercase SHA-256 digest is used as its storage key; manifests preserve the ordered list of hashes and original file size. Empty files are represented by a manifest with zero chunks. The coordinator stores new chunks on two successful nodes and reuses an existing hash by incrementing its reference count. Deleting a backup decrements each chunk reference and removes its replicas when the count reaches zero.

Restore fetches the manifest's chunks in listed order and validates each digest before assembling them in a temporary file. It checks the final size and replaces the restored destination only after reconstruction succeeds. If one recorded replica is unavailable or corrupt, retrieval tries the other recorded replicas.

## Tests and frontend checks

From the project root, run the backend tests. The unique temporary base keeps pytest's test files isolated and avoids relying on the machine-wide temporary directory:

```powershell
$pytestTemp = Join-Path $PWD (".pytest-run-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $pytestTemp | Out-Null
try {
    & .\.venv\Scripts\python.exe -m pytest -q --basetemp $pytestTemp
    $testResult = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $pytestTemp -Recurse -Force
}
if ($testResult -ne 0) { exit $testResult }
```

The suite separates its checks by boundary:

- Core backup, restore, chunk, replica, metadata, and reference-count behavior is tested with temporary files/directories and mocked node HTTP requests.
- Flask API flows are exercised using Flask's in-process test client and those same mocked node requests.
- Storage-node GET/PUT/DELETE routes are tested with Flask's in-process test client and a temporary storage directory.
- No automated test currently starts real node processes. Live three-node behavior must be verified separately by starting all three nodes and exercising a backup/restore through the dashboard or API.

Run frontend lint and production build from `frontend/`:

```powershell
npm run lint
npm run build
```

## Known limitations

- Storage-node addresses, ports, and replication factor are local prototype settings, not configurable deployment settings.
- Metadata and counters are JSON files without locking or multi-process coordination; concurrent API writers are not supported.
- Chunk files are replicated but not encrypted. Authentication, authorization, TLS, quotas, and remote-node deployment are not implemented.
- `/cluster` reports health checks; it does not repair missing replicas or rebalance storage.
- Automated tests mock node network requests. Test success does not replace verification with three running node processes.
- Metrics are persisted operation counters; `total_storage` and `total_chunks` are calculated from manifests and reflect logical backup sizes/chunk counts rather than unique physical bytes.
