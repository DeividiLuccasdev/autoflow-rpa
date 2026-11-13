"""Reconhece somente as restrições únicas que representam duplicidade."""


def is_duplicate(exc, table, columns, constraint=None):
    original = exc.orig
    # PostgreSQL: SQLSTATE e nome exato da restrição, nunca texto livre.
    if getattr(original, "sqlstate", None) == "23505":
        return getattr(getattr(original, "diag", None), "constraint_name", None) == constraint
    # SQLite: código e lista exata das colunas da restrição.
    if getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE":
        expected = "UNIQUE constraint failed: " + ", ".join(f"{table}.{column}" for column in columns)
        return str(original) == expected
    return False
