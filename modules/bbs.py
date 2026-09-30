import sqlite3
import threading


class BBS:
    """
    Simple store-and-forward message board, persisted to SQLite so messages
    survive a restart. Mailboxes are keyed by node ID (e.g. "!0a1b2c3d").
    """

    def __init__(self, db_file, max_per_recipient=10, max_total=500):
        self.db_file = db_file
        self.max_per_recipient = max_per_recipient
        self.max_total = max_total
        self.lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "recipient TEXT NOT NULL, "
                "content TEXT NOT NULL)"
            )

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def post_message(self, message_id, content):
        """
        Post a message to the BBS. Returns False if the recipient's mailbox
        or the board as a whole is full.
        """
        with self.lock, self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient = ?", (message_id,)
            ).fetchone()[0]
            if total >= self.max_total or count >= self.max_per_recipient:
                return False
            conn.execute(
                "INSERT INTO messages (recipient, content) VALUES (?, ?)",
                (message_id, content),
            )
            return True

    def get_message(self, message_id):
        """
        Get all messages for a recipient as a list of (row_id, content).
        """
        with self.lock, self._connect() as conn:
            return conn.execute(
                "SELECT id, content FROM messages WHERE recipient = ? ORDER BY id",
                (message_id,),
            ).fetchall()

    def delete_message(self, row_id):
        """
        Delete a single message by its row ID.
        """
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE id = ?", (row_id,))

    def count_messages(self, message_id):
        """
        Count the number of messages for a given recipient.
        """
        with self.lock, self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient = ?", (message_id,)
            ).fetchone()[0]
