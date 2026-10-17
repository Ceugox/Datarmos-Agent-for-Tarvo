"""Canonical serialization and on-disk cache of structured LLM proposals (ADR 0002)."""
from pathlib import Path
import hashlib
import json


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str)


class ResponseCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def key(self, prompt_version, model, payload):
        body = canonical({'prompt_version':prompt_version, 'model':model, 'input':payload})
        return hashlib.sha256(body.encode('utf-8')).hexdigest()

    def get(self, key):
        path = self.directory/f'{key}.json'
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            return None

    def put(self, key, value):
        self.directory.mkdir(parents=True,exist_ok=True)
        (self.directory/f'{key}.json').write_text(canonical(value),encoding='utf-8')
