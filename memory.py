import json
import os

class Memory:
    def __init__(self, path="MEMORY.json"):
        self.path = path

        if os.path.exists(path):
            with open(path) as f:
                self._data = json.load(f)
        else:
            self._data = {}

    def set(self, key, val):
        self._data[key] = val
        self._save()

    def get(self, key):
        return self._data.get(key)

    def keys(self):
        return list(self._data.keys())

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, default=str)
