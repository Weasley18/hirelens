"""Emit only complete top-level JSON fields from a model's structured response."""
import json
from contextvars import ContextVar

publish_field = ContextVar("publish_field", default=None)


class FieldReader:
    def __init__(self):
        self.buffer = ""
        self.started = False
        self.decoder = json.JSONDecoder()

    def feed(self, chunk):
        self.buffer += chunk
        if not self.started:
            start = self.buffer.find("{")
            if start < 0:
                return
            self.buffer = self.buffer[start + 1:]
            self.started = True
        while True:
            text = self.buffer.lstrip()
            try:
                key, end = self.decoder.raw_decode(text)
                tail = text[end:].lstrip()
                if not isinstance(key, str) or not tail.startswith(":"):
                    return
                value_text = tail[1:].lstrip()
                value, end = self.decoder.raw_decode(value_text)
                tail = value_text[end:].lstrip()
                # A number may span multiple chunks. Wait for the delimiter.
                if not tail or tail[0] not in ",}":
                    return
            except ValueError:
                return
            self.buffer = tail[1:]
            publish_field.get()(key, value)
            if tail[0] == "}":
                return
