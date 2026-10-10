import json
import os
import tempfile
from datetime import datetime

MANIFEST_DIR = "manifests"


def save_manifest(filename, chunk_hashes, file_size):
    os.makedirs(MANIFEST_DIR, exist_ok=True)

    manifest = {
        "filename": filename,
        "chunks": chunk_hashes,
        "chunk_count": len(chunk_hashes),
        "file_size": file_size,
        "upload_time": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    }

    manifest_path = os.path.join(MANIFEST_DIR, filename + ".json")
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=MANIFEST_DIR,
            prefix=".manifest.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = file.name
            json.dump(manifest, file, indent=4)
        os.replace(temporary_path, manifest_path)
    except Exception:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def load_manifest(filename):
    manifest_path = os.path.join(MANIFEST_DIR, filename + ".json")

    with open(manifest_path, "r") as file:
        manifest = json.load(file)

    return manifest


def list_backups():
    if not os.path.exists(MANIFEST_DIR):
        return []

    backups = []

    for file in os.listdir(MANIFEST_DIR):
        if file.endswith(".json"):
            backups.append(file[:-5])

    return backups
def get_storage_stats():

    total_storage = 0
    total_chunks = 0

    for filename in list_backups():

        manifest = load_manifest(filename)

        total_storage += manifest.get("file_size", 0)
        total_chunks += manifest.get("chunk_count", 0)

    return {
        "total_storage": total_storage,
        "total_chunks": total_chunks
    }