import json
import os

METRICS_FILE = "metrics.json"


def load_metrics():

    if os.path.exists(METRICS_FILE):

        with open(METRICS_FILE, "r") as file:
            return json.load(file)

    return {
        "total_backups": 0,
        "total_restores": 0,
        "chunks_stored": 0,
        "chunks_skipped": 0
    }


def save_metrics(metrics):

    with open(METRICS_FILE, "w") as file:
        json.dump(metrics, file, indent=4)