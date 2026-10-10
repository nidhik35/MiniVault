from flask import Flask, request, jsonify, send_file
import os
import tempfile
from flask_cors import CORS
import requests
from coordinator import ChunkRetrievalError, NODES, get_chunk_locations
from activity import load_activity
from activity import add_activity
from backup_engine import (
    BackupError,
    backup_file,
    restore_file,
    delete_backup,
    get_metrics
)
from manifest import list_backups, load_manifest, get_storage_stats

app = Flask(__name__)
CORS(app)

NODE_NAMES = {
    "http://127.0.0.1:5001": "Node 1",
    "http://127.0.0.1:5002": "Node 2",
    "http://127.0.0.1:5003": "Node 3",
}


def get_json_filename():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None

    filename = data.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        return None
    if filename != os.path.basename(filename) or filename in {".", ".."}:
        return None
    return filename


# -------------------------------
# Health Check
# -------------------------------
@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "MiniVault API is running"
    })


# -------------------------------
# Metrics
# -------------------------------
@app.route("/metrics", methods=["GET"])
def metrics():

    metrics = get_metrics()

    storage = get_storage_stats()

    metrics["total_storage"] = storage["total_storage"]
    metrics["total_chunks"] = storage["total_chunks"]

    return jsonify(metrics)


# -------------------------------
# List All Backups
# -------------------------------
@app.route("/backups", methods=["GET"])
def backups():

    files = []
    chunk_locations = get_chunk_locations()

    for filename in list_backups():

        manifest = load_manifest(filename)

        replicated_nodes = set()

        for chunk in manifest["chunks"]:

            if chunk in chunk_locations:

                for node in chunk_locations[chunk]["nodes"]:
                    replicated_nodes.add(NODE_NAMES.get(node, node))

        files.append({
            "filename": manifest["filename"],
            "file_size": manifest.get("file_size", 0),
            "chunk_count": manifest.get("chunk_count", 0),
            "upload_time": manifest.get("upload_time", "N/A"),
            "replicated_on": sorted(list(replicated_nodes))
        })

    return jsonify(files)
# -------------------------------
# Backup File
# -------------------------------
@app.route("/backup", methods=["POST"])
def backup():

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    os.makedirs("uploads", exist_ok=True)
    filename = os.path.basename(file.filename.replace("\\", "/"))
    if filename in {"", ".", ".."}:
        return jsonify({"error": "A valid filename is required"}), 400

    try:
        with tempfile.TemporaryDirectory(dir="uploads") as upload_dir:
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)
            backup_file(filepath)
    except BackupError as error:
        add_activity("Backup Failed", filename)
        return jsonify({"error": str(error)}), 503
    except (OSError, ValueError) as error:
        app.logger.exception("Backup failed for %s", filename)
        add_activity("Backup Failed", filename)
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Backup failed for %s", filename)
        add_activity("Backup Failed", filename)
        return jsonify({"error": "Backup failed"}), 500

    return jsonify({
        "message": "Backup completed successfully!"
    })


# -------------------------------
# Restore File
# -------------------------------
@app.route("/restore", methods=["POST"])
def restore():
    filename = get_json_filename()
    if not filename:
        return jsonify({
            "error": "A valid filename is required"
        }), 400

    try:
        restored_path = restore_file(filename)

        if not restored_path or not os.path.exists(restored_path):
            return jsonify({
                "error": "Restore failed"
            }), 500

        return send_file(
            os.path.abspath(restored_path),
            as_attachment=True,
            download_name=filename
        )

    except FileNotFoundError:
        add_activity("Restore Failed", filename)
        return jsonify({"error": f"Backup '{filename}' was not found"}), 404
    except ChunkRetrievalError as error:
        add_activity("Restore Failed", filename)
        return jsonify({"error": str(error)}), 502
    except (BackupError, ValueError) as error:
        add_activity("Restore Failed", filename)
        return jsonify({"error": str(error)}), 422
    except Exception as error:
        app.logger.exception("Restore failed for %s", filename)
        add_activity("Restore Failed", filename)
        return jsonify({"error": "Restore failed"}), 500


@app.route("/delete", methods=["POST"])
def delete():
    filename = get_json_filename()
    if not filename:
        return jsonify({
            "error": "A valid filename is required"
        }), 400

    try:
        if not delete_backup(filename):
            add_activity("Delete Failed", filename)
            return jsonify({"error": f"Backup '{filename}' was not found"}), 404
    except Exception:
        app.logger.exception("Delete failed for %s", filename)
        add_activity("Delete Failed", filename)
        return jsonify({"error": "Delete failed"}), 500

    return jsonify({
        "message": f"{filename} deleted successfully!"
    })


@app.route("/cluster", methods=["GET"])
def cluster():
    result = []

    for url in NODES:

        try:
            response = requests.get(f"{url}/health", timeout=1)
            response.raise_for_status()

            result.append({
                "name": NODE_NAMES.get(url, url),
                "status": "Online"
            })

        except requests.exceptions.RequestException:

            result.append({
                "name": NODE_NAMES.get(url, url),
                "status": "Offline"
            })

    return jsonify(result)
@app.route("/activity", methods=["GET"])
def activity():

    return jsonify(load_activity())

if __name__ == "__main__":
    app.run(debug=True, port=5000)