"""Unit tests for mass-run child job ID collection used by list_jobs."""

from __future__ import annotations

from services.simulation.mongo_store import mass_run_child_job_ids_from_docs


def test_mass_run_child_job_ids_from_docs_collects_non_null_job_ids() -> None:
    docs = [
        {
            "runs": [
                {"index": 0, "job_id": "job-a"},
                {"index": 1, "job_id": None},
                {"index": 2, "job_id": "job-b"},
            ]
        },
        {"runs": [{"index": 0, "job_id": "job-c"}]},
        {"runs": []},
    ]
    assert mass_run_child_job_ids_from_docs(docs) == {"job-a", "job-b", "job-c"}


def test_mass_run_child_job_ids_from_docs_empty_when_no_runs() -> None:
    assert mass_run_child_job_ids_from_docs([{}, {"runs": [{"index": 0}]}]) == set()
