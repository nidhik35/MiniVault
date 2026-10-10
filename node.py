import hashlib
import os
import re
import sys
from flask import Flask, request

app = Flask(__name__)

CHUNK_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def get_chunk_path(chunk_hash):
    if not CHUNK_HASH_PATTERN.fullmatch(chunk_hash):
        return None

    return os.path.join(app.config["STORAGE_FOLDER"], chunk_hash)


@app.route("/health")
def health():
    return {"status": "healthy"}


@app.route("/chunk/<chunk_hash>", methods=["PUT"])
def store_chunk(chunk_hash):
    chunk_path = get_chunk_path(chunk_hash)
    if chunk_path is None:
        return {"error": "Invalid chunk hash"}, 400
    if hashlib.sha256(request.data).hexdigest() != chunk_hash:
        return {"error": "Chunk data does not match hash"}, 400

    with open(chunk_path, "wb") as file:
        file.write(request.data)

    return {"message": "Chunk stored successfully"}


@app.route("/chunk/<chunk_hash>", methods=["GET"])
def get_chunk(chunk_hash):
    chunk_path = get_chunk_path(chunk_hash)
    if chunk_path is None or not os.path.isfile(chunk_path):
        return {"error": "Chunk not found"}, 404

    with open(chunk_path, "rb") as chunk_file:
        return chunk_file.read(), 200, {
            "Content-Type": "application/octet-stream"
        }


@app.route("/chunk/<chunk_hash>", methods=["DELETE"])
def delete_chunk(chunk_hash):
    chunk_path = get_chunk_path(chunk_hash)
    if chunk_path is None:
        return {"error": "Invalid chunk hash"}, 400

    if os.path.isfile(chunk_path):
        os.remove(chunk_path)
        return {"message": "Chunk deleted successfully"}, 200

    return {
        "error": "Chunk not found"
    }, 404


if __name__ == "__main__":

    # Read port number from command line
    port = int(sys.argv[1])

    # Read storage folder from command line
    storage_folder = sys.argv[2]

    # Create the storage folder if it doesn't exist
    os.makedirs(storage_folder, exist_ok=True)

    # Save the folder name in Flask configuration
    app.config["STORAGE_FOLDER"] = storage_folder

    # Start the Flask server
    app.run(host="127.0.0.1", port=port)