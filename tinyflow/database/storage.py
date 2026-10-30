"""
SQLite Persistence and CSV Export Engine for TinyFlow Experiments.
"""

from __future__ import annotations
import csv
import io
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from tinyflow.experiment.config import ExperimentConfig
from tinyflow.experiment.runner import ExperimentRunResult, StrategyExecutionTrace
from tinyflow.metrics.calculator import StrategyMetrics
from tinyflow.models import DecisionAction, DecisionReasonCode, DecisionRecord

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tinyflow.db")


import contextlib

@contextlib.contextmanager
def get_db_connection(db_path: str = DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initializes SQLite database schema."""
    with get_db_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                duration_s REAL NOT NULL,
                num_sensors INTEGER NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                FOREIGN KEY (experiment_id) REFERENCES experiments (id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adaptive_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                action TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                reason_text TEXT NOT NULL,
                buffer_count INTEGER NOT NULL,
                buffer_bytes INTEGER NOT NULL,
                oldest_reading_age REAL NOT NULL,
                min_slack REAL NOT NULL,
                FOREIGN KEY (experiment_id) REFERENCES experiments (id) ON DELETE CASCADE
            );
        """)
        conn.commit()


def save_experiment_result(result: ExperimentRunResult, db_path: str = DEFAULT_DB_PATH) -> None:
    """Saves complete experiment outcome into SQLite database."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO experiments (id, created_at, name, config_json, duration_s, num_sensors)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.experiment_id,
                result.created_at,
                result.config.name,
                json.dumps(result.config.to_dict()),
                result.config.duration_s,
                result.config.num_sensors,
            ),
        )

        for strat_name, trace in result.traces.items():
            conn.execute(
                """
                INSERT INTO strategy_metrics (experiment_id, strategy_name, metrics_json)
                VALUES (?, ?, ?)
                """,
                (
                    result.experiment_id,
                    strat_name,
                    json.dumps(trace.metrics.to_dict()),
                ),
            )

        if "Adaptive" in result.traces:
            adaptive_trace = result.traces["Adaptive"]
            for dec in adaptive_trace.decisions:
                conn.execute(
                    """
                    INSERT INTO adaptive_decisions (
                        experiment_id, timestamp, action, reason_code, reason_text,
                        buffer_count, buffer_bytes, oldest_reading_age, min_slack
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.experiment_id,
                        dec.timestamp,
                        dec.action.value,
                        dec.reason_code.value,
                        dec.reason_text,
                        dec.buffer_count,
                        dec.buffer_bytes,
                        dec.oldest_reading_age,
                        dec.min_slack,
                    ),
                )

        conn.commit()


def list_saved_experiments(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Returns list of all saved experiments with summary metadata."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT id, created_at, name, duration_s, num_sensors
            FROM experiments
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_saved_experiment(experiment_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Loads an experiment configuration and strategy metrics from database."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        exp_row = conn.execute(
            "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        if not exp_row:
            return None

        metrics_rows = conn.execute(
            "SELECT strategy_name, metrics_json FROM strategy_metrics WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchall()

        decisions_rows = conn.execute(
            "SELECT * FROM adaptive_decisions WHERE experiment_id = ? ORDER BY timestamp ASC",
            (experiment_id,),
        ).fetchall()

        return {
            "experiment": dict(exp_row),
            "config": json.loads(exp_row["config_json"]),
            "metrics": {row["strategy_name"]: json.loads(row["metrics_json"]) for row in metrics_rows},
            "decisions": [dict(r) for r in decisions_rows],
        }


def delete_saved_experiment(experiment_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Deletes an experiment and related records."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM adaptive_decisions WHERE experiment_id = ?", (experiment_id,))
        conn.execute("DELETE FROM strategy_metrics WHERE experiment_id = ?", (experiment_id,))
        cur = conn.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
        conn.commit()
        return cur.rowcount > 0


def export_metrics_to_csv_string(experiment_id: str, db_path: str = DEFAULT_DB_PATH) -> str:
    """Generates CSV text representation of strategy metrics for an experiment."""
    data = get_saved_experiment(experiment_id, db_path)
    if not data or not data["metrics"]:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    metrics_map = data["metrics"]
    first_strat = next(iter(metrics_map.values()))
    metric_keys = list(first_strat.keys())

    writer.writerow(["Strategy"] + metric_keys)
    for strat_name, m_dict in metrics_map.items():
        row = [strat_name] + [m_dict.get(k, "") for k in metric_keys]
        writer.writerow(row)

    return output.getvalue()


def export_decisions_to_csv_string(experiment_id: str, db_path: str = DEFAULT_DB_PATH) -> str:
    """Generates CSV text representation of adaptive decision history."""
    data = get_saved_experiment(experiment_id, db_path)
    if not data or not data["decisions"]:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)

    cols = ["timestamp", "action", "reason_code", "reason_text", "buffer_count", "buffer_bytes", "oldest_reading_age", "min_slack"]
    writer.writerow(cols)
    for d in data["decisions"]:
        writer.writerow([d.get(c, "") for c in cols])

    return output.getvalue()
