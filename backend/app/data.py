"""Loads a client's files into an in-memory, locked-down DuckDB so the LLM can query them with SQL.

Tables are named after the file kinds: activities, members, member_profile, open_ends, closed_ends.
"""
import re
import threading

import duckdb
import pandas as pd

from . import prep, storage
from .config import FILE_KINDS, MAX_SQL_ROWS

_cache: dict[str, tuple[tuple, duckdb.DuckDBPyConnection]] = {}
_lock = threading.Lock()


def _read_file(path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".csv":
        try:
            df = pd.read_csv(path, low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(path, low_memory=False, encoding="latin-1")
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported file type {ext}")
    return df


def _signature(client_id: str) -> tuple:
    sig = []
    for kind in FILE_KINDS:
        p = storage.file_path(client_id, kind)
        sig.append((kind, p.stat().st_mtime_ns, p.stat().st_size) if p else (kind, None, None))
    return tuple(sig)


def get_connection(client_id: str) -> duckdb.DuckDBPyConnection:
    sig = _signature(client_id)
    with _lock:
        hit = _cache.get(client_id)
        if hit and hit[0] == sig:
            return hit[1]
        conn = duckdb.connect(":memory:")
        frames = {}
        for kind in FILE_KINDS:
            p = storage.file_path(client_id, kind)
            if p is None:
                continue  # missing file -> table simply doesn't exist
            df = _read_file(p)
            df.columns = [str(c).strip() for c in df.columns]
            frames[kind] = df
        for kind, df in prep.clean(frames).items():
            conn.register(f"_{kind}_df", df)
            conn.execute(f'CREATE TABLE "{kind}" AS SELECT * FROM "_{kind}_df"')
            conn.unregister(f"_{kind}_df")
        conn.execute("SET enable_external_access=false")  # no read_csv('/etc/passwd') etc.
        conn.execute("SET lock_configuration=true")
        _cache[client_id] = (sig, conn)
        return conn


def describe(client_id: str, sample_rows: int = 3) -> dict:
    cur = get_connection(client_id).cursor()
    tables = {}
    for kind in FILE_KINDS:
        try:
            cols = cur.execute(f'DESCRIBE "{kind}"').fetchall()
        except duckdb.CatalogException:
            tables[kind] = None
            continue
        n = cur.execute(f'SELECT count(*) FROM "{kind}"').fetchone()[0]
        sample = cur.execute(f'SELECT * FROM "{kind}" LIMIT {int(sample_rows)}')
        names = [d[0] for d in sample.description]
        tables[kind] = {
            "row_count": n,
            "columns": [{"name": c[0], "type": c[1]} for c in cols],
            "sample": [dict(zip(names, map(_jsonable, r))) for r in sample.fetchall()],
        }
    return tables


def _jsonable(v):
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def run_sql(client_id: str, sql: str) -> dict:
    s = sql.strip().rstrip(";").strip()
    conn = get_connection(client_id)
    stmts = conn.extract_statements(s)
    if len(stmts) != 1 or stmts[0].type != duckdb.StatementType.SELECT:
        raise ValueError("Only a single read-only SELECT query is allowed.")
    cur = get_connection(client_id).cursor()
    res = cur.execute(s)
    cols = [d[0] for d in res.description]
    rows = res.fetchmany(MAX_SQL_ROWS + 1)
    truncated = len(rows) > MAX_SQL_ROWS
    rows = rows[:MAX_SQL_ROWS]
    return {
        "columns": cols,
        "rows": [list(map(_jsonable, r)) for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }
