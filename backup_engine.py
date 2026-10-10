import hashlib
import os
import argparse
import tempfile
from activity import add_activity

from manifest import save_manifest, load_manifest
from coordinator import (
    ChunkRetrievalError,
    store_chunk,
    get_chunk,
    delete_chunk,
)
from metrics import load_metrics, save_metrics

CHUNK_SIZE = 64 * 1024


class BackupError(Exception):
    """Raised when a backup cannot be committed completely."""


def chunk_file(file_path):
    chunks = []

    with open(file_path, "rb") as file:

        while True:

            data = file.read(CHUNK_SIZE)

            if not data:
                break

            hash_value = hashlib.sha256(data).hexdigest()

            chunks.append((hash_value, data))

    return chunks


def store_chunks(chunks):

    stored = 0
    skipped = 0

    for hash_value, data in chunks:

        result = store_chunk(hash_value, data)

        if result == "stored":
            stored += 1

        elif result == "skipped":
            skipped += 1
        else:
            raise BackupError(
                f"Unable to store chunk {hash_value} with the required replicas"
            )

    return stored, skipped


def backup_file(file_path):

    filename = os.path.basename(file_path)
    if not filename or filename in {".", ".."}:
        raise ValueError("A valid backup filename is required")

    chunks = chunk_file(file_path)
    staged_hashes = []

    try:
        stored = 0
        skipped = 0
        for hash_value, data in chunks:
            result = store_chunk(hash_value, data)
            if result not in {"stored", "skipped"}:
                raise BackupError(
                    f"Unable to store chunk {hash_value} with the required replicas"
                )
            staged_hashes.append(hash_value)
            if result == "stored":
                stored += 1
            else:
                skipped += 1

        chunk_hashes = [hash_value for hash_value, _ in chunks]
        file_size = os.path.getsize(file_path)

        manifest_path = os.path.join("manifests", f"{filename}.json")
        old_manifest = load_manifest(filename) if os.path.exists(manifest_path) else None
        save_manifest(filename, chunk_hashes, file_size)
    except Exception:
        for chunk_hash in reversed(staged_hashes):
            delete_chunk(chunk_hash)
        raise

    if old_manifest is not None:
        for chunk_hash in old_manifest["chunks"]:
            delete_chunk(chunk_hash)

    metrics = load_metrics()
    metrics["total_backups"] += 1
    metrics["chunks_stored"] += stored
    metrics["chunks_skipped"] += skipped
    save_metrics(metrics)

    add_activity("Backup", filename)

    print("\nBackup Summary")
    print("----------------")
    print("File         :", filename)
    print("Total Chunks :", len(chunks))
    print("Stored       :", stored)
    print("Skipped      :", skipped)


def restore_file(filename):
    if not filename or os.path.basename(filename) != filename or filename in {".", ".."}:
        raise ValueError("A valid backup filename is required")

    manifest = load_manifest(filename)
    os.makedirs("restored", exist_ok=True)

    restored_path = os.path.join("restored", filename)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir="restored",
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as restored_file:
            temporary_path = restored_file.name
            for chunk_hash in manifest["chunks"]:
                chunk_data = get_chunk(chunk_hash)
                if hashlib.sha256(chunk_data).hexdigest() != chunk_hash:
                    raise ChunkRetrievalError(
                        f"Chunk {chunk_hash} failed integrity validation"
                    )
                restored_file.write(chunk_data)

        actual_size = os.path.getsize(temporary_path)
        expected_size = manifest.get("file_size")
        if expected_size is not None and actual_size != expected_size:
            raise BackupError(
                f"Restored file size mismatch: expected {expected_size} bytes, "
                f"received {actual_size} bytes"
            )
        os.replace(temporary_path, restored_path)
    except Exception:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise

    # Update metrics
    metrics = load_metrics()

    metrics["total_restores"] += 1

    save_metrics(metrics)
    add_activity("Restore", filename)

    print(f"\n'{filename}' restored successfully!")
    print("Restored file:", restored_path)
    return restored_path
def delete_backup(filename):
    if not filename or os.path.basename(filename) != filename or filename in {".", ".."}:
        raise ValueError("A valid backup filename is required")

    manifest_path = os.path.join("manifests", f"{filename}.json")

    if not os.path.exists(manifest_path):
        return False

    manifest = load_manifest(filename)

    for chunk_hash in manifest["chunks"]:
        delete_chunk(chunk_hash)

    os.remove(manifest_path)
    add_activity("Delete", filename)

    print(f"\nBackup '{filename}' deleted successfully!")
    return True
def get_metrics():

    metrics = load_metrics()

    metrics["replication_factor"] = 2

    return metrics

def show_metrics():

    metrics = load_metrics()

    print("\n========== MiniVault Metrics ==========")
    print(f"Total Backups      : {metrics['total_backups']}")
    print(f"Total Restores     : {metrics['total_restores']}")
    print(f"Chunks Stored      : {metrics['chunks_stored']}")
    print(f"Chunks Skipped     : {metrics['chunks_skipped']}")
    print("Replication Factor : 2")
    print("=======================================\n")


def main():

    parser = argparse.ArgumentParser(description="MiniVault Backup System")

    parser.add_argument(
        "operation",
        choices=["backup", "restore", "delete", "metrics"],
        help="Choose backup, restore, delete or metrics"
    )

    parser.add_argument(
        "filename",
        nargs="?",
        help="File path for backup or filename for restore/delete"
    )

    args = parser.parse_args()

    if args.operation == "backup":

        if not args.filename:
            print("Please provide a file path.")
            return

        backup_file(args.filename)

    elif args.operation == "restore":

        if not args.filename:
            print("Please provide a filename.")
            return

        restore_file(args.filename)

    elif args.operation == "delete":

        if not args.filename:
            print("Please provide a filename.")
            return

        delete_backup(args.filename)

    elif args.operation == "metrics":

        show_metrics()


if __name__ == "__main__":
    main()