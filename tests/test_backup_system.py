import hashlib
import io
from pathlib import Path

import pytest
import requests

import activity
import api
import backup_engine
import coordinator
import manifest
import metrics
import node


class FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}"
            )


class FakeNodes:
    def __init__(self, node_urls):
        self.storage = {url: {} for url in node_urls}
        self.unavailable = set()
        self.corrupted = set()
        self.health_status = {}

    @staticmethod
    def _chunk_key(url):
        node_url, chunk_hash = url.rsplit("/chunk/", 1)
        return node_url, chunk_hash

    def put(self, url, data, timeout):
        node_url, chunk_hash = self._chunk_key(url)
        if node_url in self.unavailable:
            raise requests.exceptions.ConnectionError("node unavailable")
        self.storage[node_url][chunk_hash] = data
        return FakeResponse()

    def get(self, url, timeout):
        if url.endswith("/health"):
            node_url = url[:-len("/health")]
            return FakeResponse(self.health_status.get(node_url, 200))
        node_url, chunk_hash = self._chunk_key(url)
        if node_url in self.unavailable:
            raise requests.exceptions.ConnectionError("node unavailable")
        data = self.storage[node_url].get(chunk_hash)
        if data is None:
            return FakeResponse(404)
        if (node_url, chunk_hash) in self.corrupted:
            data = data + b"corrupt"
        return FakeResponse(content=data)

    def delete(self, url, timeout):
        node_url, chunk_hash = self._chunk_key(url)
        if node_url in self.unavailable:
            raise requests.exceptions.ConnectionError("node unavailable")
        self.storage[node_url].pop(chunk_hash, None)
        return FakeResponse()


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    node_urls = [
        "http://127.0.0.1:5001",
        "http://127.0.0.1:5002",
        "http://127.0.0.1:5003",
    ]
    fake_nodes = FakeNodes(node_urls)
    monkeypatch.setattr(coordinator, "NODES", node_urls)
    monkeypatch.setattr(api, "NODES", node_urls)
    monkeypatch.setattr(coordinator, "METADATA_FILE", str(tmp_path / "chunk_locations.json"))
    monkeypatch.setattr(coordinator, "chunk_locations", {})
    monkeypatch.setattr(coordinator, "chunk_index", set())
    monkeypatch.setattr(manifest, "MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(activity, "ACTIVITY_FILE", str(tmp_path / "activity.json"))
    monkeypatch.setattr(metrics, "METRICS_FILE", str(tmp_path / "metrics.json"))
    monkeypatch.setattr(coordinator.requests, "put", fake_nodes.put)
    monkeypatch.setattr(coordinator.requests, "get", fake_nodes.get)
    monkeypatch.setattr(coordinator.requests, "delete", fake_nodes.delete)
    api.app.config.update(TESTING=True)
    coordinator.load_metadata()
    return tmp_path, fake_nodes


def write_source(tmp_path, filename, data):
    path = tmp_path / filename
    path.write_bytes(data)
    return path


def test_node_chunk_get_and_delete_are_separate(tmp_path):
    node.app.config["STORAGE_FOLDER"] = str(tmp_path)
    data = b"stored chunk"
    chunk_hash = hashlib.sha256(data).hexdigest()
    client = node.app.test_client()

    stored = client.put(f"/chunk/{chunk_hash}", data=data)
    retrieved = client.get(f"/chunk/{chunk_hash}")
    missing = client.get(f"/chunk/{'0' * 64}")
    deleted = client.delete(f"/chunk/{chunk_hash}")

    assert stored.status_code == 200
    assert retrieved.status_code == 200
    assert retrieved.data == data
    retrieved.close()
    assert missing.status_code == 404
    assert deleted.status_code == 200
    assert client.get(f"/chunk/{chunk_hash}").status_code == 404


@pytest.mark.parametrize(
    "size",
    [0, 17, backup_engine.CHUNK_SIZE, backup_engine.CHUNK_SIZE + 1,
     2 * backup_engine.CHUNK_SIZE + 23],
)
def test_backup_restore_preserves_content_and_order(system, size):
    tmp_path, _ = system
    source_data = bytes((index % 251 for index in range(size)))
    source = write_source(tmp_path, "source.bin", source_data)

    backup_engine.backup_file(str(source))
    restored_path = backup_engine.restore_file("source.bin")

    restored_data = Path(restored_path).read_bytes()
    assert hashlib.sha256(restored_data).digest() == hashlib.sha256(source_data).digest()
    assert restored_data == source_data
    saved_manifest = manifest.load_manifest("source.bin")
    assert saved_manifest["file_size"] == size
    assert len(saved_manifest["chunks"]) == (
        (size + backup_engine.CHUNK_SIZE - 1) // backup_engine.CHUNK_SIZE
    )
    assert metrics.load_metrics()["total_restores"] == 1
    assert activity.load_activity()[0]["action"] == "Restore"


def test_duplicate_chunks_increment_and_release_reference_count(system):
    tmp_path, fake_nodes = system
    data = b"duplicate content"
    backup_engine.backup_file(str(write_source(tmp_path, "one.txt", data)))
    backup_engine.backup_file(str(write_source(tmp_path, "two.txt", data)))
    chunk_hash = hashlib.sha256(data).hexdigest()

    assert coordinator.chunk_locations[chunk_hash]["ref_count"] == 2
    assert metrics.load_metrics()["chunks_skipped"] == 1

    assert backup_engine.delete_backup("one.txt") is True
    assert coordinator.chunk_locations[chunk_hash]["ref_count"] == 1
    assert all(
        chunk_hash in fake_nodes.storage[replica]
        for replica in coordinator.chunk_locations[chunk_hash]["nodes"]
    )

    assert backup_engine.delete_backup("two.txt") is True
    assert chunk_hash not in coordinator.chunk_locations
    assert all(chunk_hash not in node_storage for node_storage in fake_nodes.storage.values())


def test_duplicate_chunk_repairs_missing_replicas_before_committing(system):
    tmp_path, fake_nodes = system
    data = b"restore missing duplicate replicas"
    backup_engine.backup_file(str(write_source(tmp_path, "first.txt", data)))
    chunk_hash = hashlib.sha256(data).hexdigest()
    for replica in coordinator.chunk_locations[chunk_hash]["nodes"]:
        fake_nodes.storage[replica].pop(chunk_hash)

    backup_engine.backup_file(str(write_source(tmp_path, "second.txt", data)))

    assert coordinator.chunk_locations[chunk_hash]["ref_count"] == 2
    assert len(coordinator.chunk_locations[chunk_hash]["nodes"]) == 2
    assert all(
        chunk_hash in fake_nodes.storage[replica]
        for replica in coordinator.chunk_locations[chunk_hash]["nodes"]
    )


def test_duplicate_chunk_without_two_replicas_does_not_increment_reference(system):
    tmp_path, fake_nodes = system
    data = b"only one node is available"
    backup_engine.backup_file(str(write_source(tmp_path, "first.txt", data)))
    chunk_hash = hashlib.sha256(data).hexdigest()
    first_replica = coordinator.chunk_locations[chunk_hash]["nodes"][0]
    fake_nodes.unavailable.update(
        set(coordinator.NODES) - {first_replica}
    )

    with pytest.raises(backup_engine.BackupError, match="required replicas"):
        backup_engine.backup_file(str(write_source(tmp_path, "second.txt", data)))

    assert coordinator.chunk_locations[chunk_hash]["ref_count"] == 1
    assert not (tmp_path / "manifests" / "second.txt.json").exists()


def test_failed_replication_does_not_commit_backup(system):
    tmp_path, fake_nodes = system
    fake_nodes.unavailable.update(coordinator.NODES[1:])
    source = write_source(tmp_path, "unavailable.txt", b"cannot replicate")

    with pytest.raises(backup_engine.BackupError, match="required replicas"):
        backup_engine.backup_file(str(source))

    assert not (tmp_path / "manifests" / "unavailable.txt.json").exists()
    assert coordinator.chunk_locations == {}
    assert metrics.load_metrics()["total_backups"] == 0
    assert not any(fake_nodes.storage[url] for url in fake_nodes.storage)


def test_failed_replacement_keeps_previous_backup_intact(system):
    tmp_path, fake_nodes = system
    old_content = b"previous backup contents"
    backup_engine.backup_file(
        str(write_source(tmp_path, "replace.txt", old_content))
    )
    old_manifest = manifest.load_manifest("replace.txt")
    old_metadata = dict(coordinator.chunk_locations)

    fake_nodes.unavailable.update(coordinator.NODES[1:])
    with pytest.raises(backup_engine.BackupError):
        backup_engine.backup_file(
            str(write_source(tmp_path, "replace.txt", b"replacement"))
        )

    assert manifest.load_manifest("replace.txt") == old_manifest
    assert coordinator.chunk_locations == old_metadata
    backup_engine.restore_file("replace.txt")
    assert Path(tmp_path / "restored" / "replace.txt").read_bytes() == old_content


def test_corrupted_first_replica_falls_back_to_valid_replica(system):
    tmp_path, fake_nodes = system
    data = b"valid backup content"
    backup_engine.backup_file(str(write_source(tmp_path, "fallback.txt", data)))
    chunk_hash = hashlib.sha256(data).hexdigest()
    first_replica = coordinator.chunk_locations[chunk_hash]["nodes"][0]
    fake_nodes.corrupted.add((first_replica, chunk_hash))

    restored_path = backup_engine.restore_file("fallback.txt")
    assert Path(restored_path).read_bytes() == data


def test_unavailable_replica_fallback_and_unrecoverable_chunk(system):
    tmp_path, fake_nodes = system
    data = b"replica availability"
    backup_engine.backup_file(str(write_source(tmp_path, "replicas.txt", data)))
    chunk_hash = hashlib.sha256(data).hexdigest()
    replicas = coordinator.chunk_locations[chunk_hash]["nodes"]
    fake_nodes.unavailable.add(replicas[0])

    assert Path(backup_engine.restore_file("replicas.txt")).read_bytes() == data

    fake_nodes.corrupted.update((replica, chunk_hash) for replica in replicas)
    old_restore = tmp_path / "restored" / "replicas.txt"
    old_restore.write_bytes(b"previous valid restore")
    with pytest.raises(coordinator.ChunkRetrievalError, match="could not be recovered"):
        backup_engine.restore_file("replicas.txt")
    assert old_restore.read_bytes() == b"previous valid restore"


def test_missing_chunk_does_not_write_partial_restore_or_count_success(system):
    tmp_path, fake_nodes = system
    backup_engine.backup_file(
        str(write_source(tmp_path, "missing.txt", b"missing data"))
    )
    manifest_data = manifest.load_manifest("missing.txt")
    chunk_hash = manifest_data["chunks"][0]
    for replica in coordinator.chunk_locations[chunk_hash]["nodes"]:
        fake_nodes.storage[replica].pop(chunk_hash)

    with pytest.raises(coordinator.ChunkRetrievalError, match="could not be recovered"):
        backup_engine.restore_file("missing.txt")

    assert not (tmp_path / "restored" / "missing.txt").exists()
    assert metrics.load_metrics()["total_restores"] == 0


def test_api_validation_failure_logging_and_cluster_health(system):
    _, fake_nodes = system
    client = api.app.test_client()

    assert client.post("/restore", json={}).status_code == 400
    assert client.post("/restore", json={"filename": "missing.txt"}).status_code == 404
    assert client.post("/delete", data="not json").status_code == 400
    assert client.post("/delete", json={"filename": "not-found.txt"}).status_code == 404

    fake_nodes.health_status[coordinator.NODES[0]] = 503
    statuses = client.get("/cluster").get_json()
    assert statuses[0] == {"name": "Node 1", "status": "Offline"}
    assert statuses[1]["status"] == "Online"

    activity_log = activity.load_activity()
    assert activity_log[0]["action"] == "Delete Failed"


def test_api_failed_backup_reports_failure_without_success_metrics(system):
    tmp_path, fake_nodes = system
    fake_nodes.unavailable.update(coordinator.NODES[1:])
    client = api.app.test_client()

    response = client.post(
        "/backup",
        data={"file": (io.BytesIO(bytes([1, 2, 3])), "api-failure.bin")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 503
    assert response.get_json()["error"]
    assert metrics.load_metrics()["total_backups"] == 0
    assert activity.load_activity()[0]["action"] == "Backup Failed"
    assert not (tmp_path / "manifests" / "api-failure.bin.json").exists()


def test_api_backup_success_updates_list_metrics_and_activity(system):
    tmp_path, _ = system
    client = api.app.test_client()

    response = client.post(
        "/backup",
        data={"file": (io.BytesIO(bytes([4, 5, 6])), "api-success.bin")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert client.get("/backups").get_json()[0]["filename"] == "api-success.bin"
    restored = client.post("/restore", json={"filename": "api-success.bin"})
    assert restored.status_code == 200
    assert restored.data == bytes([4, 5, 6])
    assert client.get("/metrics").get_json()["total_backups"] == 1
    assert client.get("/metrics").get_json()["total_restores"] == 1
    assert activity.load_activity()[0]["action"] == "Restore"
    deleted = client.post("/delete", json={"filename": "api-success.bin"})
    assert deleted.status_code == 200
    assert client.get("/backups").get_json() == []
    assert not list((tmp_path / "uploads").glob("**/*"))
