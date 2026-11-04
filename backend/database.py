import sqlite3

import psycopg
from psycopg.rows import dict_row


class DatabaseConnection:
    def __init__(self, connection, postgres=False):
        self.connection = connection
        self.postgres = postgres

    def execute(self, query, parameters=()):
        if self.postgres:
            query = query.replace("?", "%s")
        return self.connection.execute(query, parameters)

    def executescript(self, script):
        if not self.postgres:
            return self.connection.executescript(script)
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def connect_database(database_url, database_path):
    if database_url:
        connection = psycopg.connect(
            database_url,
            connect_timeout=10,
            row_factory=dict_row,
        )
        return DatabaseConnection(connection, postgres=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return DatabaseConnection(connection)
