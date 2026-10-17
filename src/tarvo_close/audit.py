"""Audit log of the inference layer: one JSON line per event, deterministic (no clock, keys sorted)."""
from pathlib import Path
import json


class AuditLog:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)

    def write(self, path):
        lines = [json.dumps(event,sort_keys=True,ensure_ascii=False,default=str) for event in self.events]
        Path(path).write_text(''.join(line+'\n' for line in lines),encoding='utf-8')
