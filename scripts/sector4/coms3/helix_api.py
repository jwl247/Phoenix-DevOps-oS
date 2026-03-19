import os
import json

class Franken2:
    IDENTITY = "Franken2"
    SECTOR = "sector4"
    ROLE = "system_core"
    PATH = os.path.dirname(__file__)
    IDENT_PATH = os.path.join(PATH, "ident.card")
    RESPONSIBILITY_PATH = os.path.join(PATH, "responsibility.json")

    def __init__(self):
        self.ident = self._load_ident()
        self.responsibility = self._load_responsibility()

    def _load_ident(self):
        try:
            with open(self.IDENT_PATH) as f:
                return f.read().strip()
        except:
            return self.IDENTITY

    def _load_responsibility(self):
        try:
            with open(self.RESPONSIBILITY_PATH) as f:
                return json.load(f)
        except:
            return {}

    def propose_route(self, ball):
        # All four streams fire simultaneously into system core
        return {
            "targets": {
                "VECTOR":     "ring_1",
                "NOSQL":      "ring_2",
                "RELATIONAL": "ring_3",
                "TIMESERIES": "ring_4",
            }
        }

    def broadcast(self, ball):
        return {"peer": self.ident, "status": "ok"}

    def heartbeat(self):
        return {"peer": self.ident, "alive": True}


class Freewheeling:
    IDENTITY = "Freewheeling"
    SECTOR = "sector4"
    ROLE = "memory_bank"
    PATH = os.path.dirname(__file__)
    IDENT_PATH = os.path.join(PATH, "ident.card")
    RESPONSIBILITY_PATH = os.path.join(PATH, "responsibility.json")

    def __init__(self):
        self.ident = self._load_ident()
        self.responsibility = self._load_responsibility()
        self.warm_memory = {}
        self.load = {
            "ring_1": 0,
            "ring_2": 0,
            "ring_3": 0,
            "ring_4": 0,
        }
        self.threshold = 5

    def _load_ident(self):
        try:
            with open(self.IDENT_PATH) as f:
                return f.read().strip()
        except:
            return self.IDENTITY

    def _load_responsibility(self):
        try:
            with open(self.RESPONSIBILITY_PATH) as f:
                return json.load(f)
        except:
            return {"role": "memory_bank"}

    def store_warm(self, key, value):
        self.warm_memory[key] = value

    def load_warm(self, key):
        return self.warm_memory.get(key)


class Propcoms:
    IDENTITY = "Propcoms"
    SECTOR = "sector4"
    ROLE = "ring_validator"

    def __init__(self):
        self.ident = self.IDENTITY
        self._alive = True
        self._last_tick = 0
        self.valid_targets = ["ring_1", "ring_2", "ring_3", "ring_4"]

    def validate(self, ball, contextual):
        if contextual.get("escalate"):
            return {"escalate": True}
        targets = contextual.get("targets", {})
        invalid = [t for t in targets.values() if t not in self.valid_targets]
        if invalid:
            return {"escalate": True}
        return {"validated": True, "targets": targets}

    def tick(self, peer_a, peer_b):
        self._last_tick += 1
        return {"tick": self._last_tick}

    def ring_alive(self):
        return self._alive

    def ring_status(self):
        return {"alive": self._alive, "last_tick": self._last_tick}

    def broadcast(self, ball):
        return {"peer": self.ident, "status": "ok"}

    def heartbeat(self):
        return {"peer": self.ident, "alive": self._alive, "last_tick": self._last_tick}
