import sqlite3


def _like_pattern(search_pattern):
    # Escape LIKE wildcards so user input is matched literally
    escaped = (
        search_pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return "%" + escaped + "%"


class Whois:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close_connection()

    def search_nodes(self, search_pattern):
        query = "SELECT * FROM nodes WHERE node_id LIKE ? ESCAPE '\\'"
        self.cursor.execute(query, (_like_pattern(search_pattern),))
        return self.cursor.fetchone()

    def search_nodes_sn(self, search_pattern):
        query = "SELECT * FROM nodes WHERE short_name LIKE ? ESCAPE '\\'"
        self.cursor.execute(query, (_like_pattern(search_pattern),))
        return self.cursor.fetchone()

    def close_connection(self):
        self.conn.close()


# Example usage:
if __name__ == "__main__":
    db_file = "./db/nodes.db"
    search_pattern = input("Enter the search pattern: ")

    with Whois(db_file) as whois_search:
        print(whois_search.search_nodes(search_pattern))
