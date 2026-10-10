import json
import os
from datetime import datetime

ACTIVITY_FILE = "activity.json"


def load_activity():

    if not os.path.exists(ACTIVITY_FILE):
        return []

    with open(ACTIVITY_FILE, "r") as file:
        return json.load(file)


def save_activity(activity):

    with open(ACTIVITY_FILE, "w") as file:
        json.dump(activity, file, indent=4)


def add_activity(action, filename):

    activity = load_activity()

    activity.insert(0, {
        "action": action,
        "file": filename,
        "time": datetime.now().strftime("%d-%m-%Y %I:%M %p")
    })

    save_activity(activity)