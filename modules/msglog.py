import logging
import os
import threading
from collections import deque

logger = logging.getLogger(__name__)


class MessageLog:
    """
    Plain-text log of mesh messages, one message per line, capped at
    `max_messages` lines. When the cap is reached the oldest lines are
    dropped and the file is rewritten.
    """

    def __init__(self, filename, max_messages=1000):
        self.filename = filename
        self.max_messages = max(1, int(max_messages))
        self.lock = threading.Lock()
        self.lines = deque(maxlen=self.max_messages)

        if os.path.exists(self.filename):
            with open(self.filename, "r", encoding="utf-8", errors="replace") as file:
                total = 0
                for line in file:
                    self.lines.append(line.rstrip("\n"))
                    total += 1
            # The limit may have been lowered since the file was written
            if total > self.max_messages:
                self._rewrite()

    def log(self, line):
        # Keep one message per line so the cap counts messages, not lines
        line = line.replace("\r", "\\r").replace("\n", "\\n")
        with self.lock:
            full = len(self.lines) == self.max_messages
            self.lines.append(line)
            try:
                if full:
                    self._rewrite()
                else:
                    with open(self.filename, "a", encoding="utf-8") as file:
                        file.write(line + "\n")
            except OSError as e:
                logger.error(f"Failed to write message log {self.filename}: {e}")

    def _rewrite(self):
        # Write to a temp file and swap it in so a crash can't truncate the log
        tmp = self.filename + ".tmp"
        with open(tmp, "w", encoding="utf-8") as file:
            file.writelines(line + "\n" for line in self.lines)
        os.replace(tmp, self.filename)
