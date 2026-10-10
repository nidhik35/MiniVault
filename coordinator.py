import hashlib
import json
import os
import tempfile
import requests

REPLICATION_FACTOR = 2

NODES = [
    "http://127.0.0.1:5001",
    "http://127.0.0.1:5002",
    "http://127.0.0.1:5003"
]

METADATA_FILE = "chunk_locations.json"

current_node = 0

chunk_locations = {}
chunk_index = set()


class ChunkRetrievalError(Exception):
    """Raised when no recorded replica can provide a valid chunk."""


def save_metadata():
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=os.path.dirname(METADATA_FILE) or ".",
            prefix=".chunk_locations.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = file.name
            json.dump(chunk_locations, file, indent=4)
        os.replace(temporary_path, METADATA_FILE)
    except Exception:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def load_metadata():

    global chunk_locations
    global chunk_index

    chunk_locations = {}
    chunk_index = set()
    if os.path.exists(METADATA_FILE):

        with open(METADATA_FILE, "r") as file:
            chunk_locations = json.load(file)

        # Rebuild the chunk index from saved metadata
        chunk_index = set(chunk_locations.keys())


def get_next_node():
    global current_node

    node = NODES[current_node]

    current_node = (current_node + 1) % len(NODES)

    return node


def store_chunk(chunk_hash, data):
    if hashlib.sha256(data).hexdigest() != chunk_hash:
        raise ValueError(f"Chunk data does not match hash {chunk_hash}")

    # ---------------------------------
    # Deduplication
    # ---------------------------------
    if chunk_hash in chunk_index:
        existing = chunk_locations[chunk_hash]
        previous_nodes = list(existing["nodes"])
        available_nodes = []

        for node in previous_nodes:
            try:
                response = requests.get(
                    f"{node}/chunk/{chunk_hash}",
                    timeout=2
                )
                if (
                    response.status_code == 200
                    and hashlib.sha256(response.content).hexdigest() == chunk_hash
                    and node not in available_nodes
                ):
                    available_nodes.append(node)
                    if len(available_nodes) == REPLICATION_FACTOR:
                        break
            except requests.exceptions.RequestException:
                print(f"{node} is unavailable while checking a duplicate chunk")

        newly_stored_nodes = []
        candidates = list(dict.fromkeys(previous_nodes + NODES))
        for node in candidates:
            if len(available_nodes) == REPLICATION_FACTOR:
                break
            if node in available_nodes:
                continue
            try:
                response = requests.put(
                    f"{node}/chunk/{chunk_hash}",
                    data=data,
                    timeout=2
                )
                if response.status_code == 200:
                    available_nodes.append(node)
                    newly_stored_nodes.append(node)
            except requests.exceptions.RequestException:
                print(f"{node} is unavailable while repairing a duplicate chunk")

        if len(available_nodes) != REPLICATION_FACTOR:
            for node in newly_stored_nodes:
                if node not in previous_nodes:
                    try:
                        requests.delete(f"{node}/chunk/{chunk_hash}", timeout=2)
                    except requests.exceptions.RequestException:
                        print(f"Could not remove incomplete replica from {node}")
            return "failed"

        old_ref_count = existing["ref_count"]
        existing["nodes"] = available_nodes[:REPLICATION_FACTOR]
        existing["ref_count"] = old_ref_count + 1
        try:
            save_metadata()
        except Exception:
            existing["nodes"] = previous_nodes
            existing["ref_count"] = old_ref_count
            for node in newly_stored_nodes:
                if node not in previous_nodes:
                    try:
                        requests.delete(f"{node}/chunk/{chunk_hash}", timeout=2)
                    except requests.exceptions.RequestException:
                        print(f"Could not remove untracked replica from {node}")
            raise

        print(
            f"Chunk {chunk_hash} already exists. "
            f"Reference Count = {existing['ref_count']}"
        )

        return "skipped"


    # ---------------------------------
    # Fault-tolerant replication
    # ---------------------------------
    replica_nodes = []

    # Try every node until we get 2 replicas
    for node in NODES:

        try:

            response = requests.put(
                f"{node}/chunk/{chunk_hash}",
                data=data,
                timeout=2
            )

            if response.status_code == 200:

                replica_nodes.append(node)

                print(f"Chunk stored on {node}")

            # Replication factor = 2
            if len(replica_nodes) == REPLICATION_FACTOR:
                break

        except requests.exceptions.RequestException:

            print(f"{node} is unavailable. Skipping...")


    # ---------------------------------
    # Check replication
    # ---------------------------------
    if len(replica_nodes) == REPLICATION_FACTOR:

        chunk_locations[chunk_hash] = {
            "nodes": replica_nodes,
            "ref_count": 1
        }

        chunk_index.add(chunk_hash)

        try:
            save_metadata()
        except Exception:
            del chunk_locations[chunk_hash]
            chunk_index.discard(chunk_hash)
            for node in replica_nodes:
                try:
                    requests.delete(f"{node}/chunk/{chunk_hash}", timeout=2)
                except requests.exceptions.RequestException:
                    print(f"Could not remove untracked replica from {node}")
            raise

        return "stored"

    for node in replica_nodes:
        try:
            requests.delete(f"{node}/chunk/{chunk_hash}", timeout=2)
        except requests.exceptions.RequestException:
            print(f"Could not remove incomplete replica from {node}")

    print(
        f"Backup failed for chunk {chunk_hash}. "
        f"Only {len(replica_nodes)} replica(s) could be created."
    )

    return "failed"
def get_chunk(chunk_hash):

    if chunk_hash not in chunk_locations:
        raise ChunkRetrievalError(
            f"Chunk {chunk_hash} is not present in the location metadata"
        )

    nodes = chunk_locations[chunk_hash]["nodes"]
    failures = []

    for node in nodes:

        try:
            response = requests.get(
                f"{node}/chunk/{chunk_hash}",
                timeout=2
            )

            if response.status_code == 200:
                chunk_data = response.content
                if hashlib.sha256(chunk_data).hexdigest() == chunk_hash:
                    print(f"Retrieved chunk from {node}")
                    return chunk_data
                failures.append(f"{node} returned corrupted chunk data")
            else:
                failures.append(
                    f"{node} returned HTTP {response.status_code}"
                )

        except requests.exceptions.RequestException:
            print(f"{node} is unavailable. Trying next replica...")
            failures.append(f"{node} is unavailable")

    details = "; ".join(failures) if failures else "no replica locations recorded"
    raise ChunkRetrievalError(
        f"Chunk {chunk_hash} could not be recovered: {details}"
    )


def delete_chunk(chunk_hash):

    if chunk_hash not in chunk_locations:
        return False

    # Decrease reference count
    chunk_locations[chunk_hash]["ref_count"] -= 1

    # If still referenced by another backup, just save metadata
    if chunk_locations[chunk_hash]["ref_count"] > 0:
        save_metadata()
        return True

    # Delete chunk from all replica nodes
    nodes = chunk_locations[chunk_hash]["nodes"]

    for node in nodes:
        try:
            requests.delete(
                f"{node}/chunk/{chunk_hash}",
                timeout=2
            )
        except requests.exceptions.RequestException:
            print(f"Could not contact {node}")

    # Remove metadata
    del chunk_locations[chunk_hash]
    chunk_index.discard(chunk_hash)

    save_metadata()

    return True

def get_chunk_locations():
    return chunk_locations


load_metadata()
