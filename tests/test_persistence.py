"""
Unit tests for SQLite persistence and CSV export functions.
"""

import os
import tempfile
import pytest

from tinyflow.database.storage import (
    delete_saved_experiment,
    export_decisions_to_csv_string,
    export_metrics_to_csv_string,
    get_saved_experiment,
    init_db,
    list_saved_experiments,
    save_experiment_result,
)
from tinyflow.experiment.config import ExperimentConfig
from tinyflow.experiment.runner import ExperimentRunner


def test_sqlite_persistence_and_csv_export():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        init_db(temp_db)

        config = ExperimentConfig(
            num_sensors=2,
            reading_rate_hz=1.0,
            duration_s=3.0,
            seed=42,
            name="Persistence Test Experiment",
        )
        res = ExperimentRunner.run_experiment(config)

        save_experiment_result(res, temp_db)

        # Check list
        exp_list = list_saved_experiments(temp_db)
        assert len(exp_list) == 1
        assert exp_list[0]["id"] == res.experiment_id
        assert exp_list[0]["num_sensors"] == 2

        # Check get
        saved = get_saved_experiment(res.experiment_id, temp_db)
        assert saved is not None
        assert "Immediate" in saved["metrics"]
        assert "Adaptive" in saved["metrics"]
        assert len(saved["decisions"]) > 0

        # Check CSV export
        metrics_csv = export_metrics_to_csv_string(res.experiment_id, temp_db)
        assert "Strategy" in metrics_csv
        assert "Immediate" in metrics_csv
        assert "Adaptive" in metrics_csv

        decisions_csv = export_decisions_to_csv_string(res.experiment_id, temp_db)
        assert "reason_code" in decisions_csv
        assert "min_slack" in decisions_csv

        # Check delete
        del_status = delete_saved_experiment(res.experiment_id, temp_db)
        assert del_status is True
        assert len(list_saved_experiments(temp_db)) == 0

    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)
