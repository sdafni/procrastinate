import asyncio

import pytest

from procrastinate import worker


@pytest.fixture
async def running_worker(app):
    running_worker = worker.Worker(app=app, queues=["some_queue"])
    task = asyncio.ensure_future(running_worker.run())
    running_worker.task = task
    yield running_worker
    running_worker.stop()
    await asyncio.wait_for(task, timeout=0.5)


async def test_run(app, running_worker, caplog):
    caplog.set_level("DEBUG")

    done = asyncio.Event()

    @app.task(queue="some_queue")
    def t():
        done.set()

    await t.configure().defer_async()

    try:
        await asyncio.wait_for(done.wait(), timeout=0.5)
    except asyncio.TimeoutError:
        pytest.fail("Failed to launch task withing .5s")

    assert [q[0] for q in app.connector.queries] == [
        "fetch_job",
        "defer_job",
        "fetch_job",
        "finish_job",
        "fetch_job",
    ]

    logs = {r.action: r.levelname for r in caplog.records}
    # remove the periodic_deferrer_no_task log record because that makes the test flaky
    logs.pop("periodic_deferrer_no_task", None)
    assert list(logs.items()) == [
        ("about_to_defer_job", "DEBUG"),
        ("job_defer", "INFO"),
        ("loaded_job_info", "DEBUG"),
        ("start_job", "INFO"),
        ("job_success", "INFO"),
        ("finish_task", "DEBUG"),
        ("waiting_for_jobs", "DEBUG"),
    ]


async def test_run_log_current_job_when_stopping(app, running_worker, caplog):
    caplog.set_level("DEBUG")

    @app.task(queue="some_queue")
    async def t():
        running_worker.stop()

    await t.configure(lock="sher").defer_async()

    try:
        await asyncio.wait_for(running_worker.task, timeout=0.5)
    except asyncio.TimeoutError:
        pytest.fail("Failed to launch task within .5s")

    # We want to make sure that the log that names the current running task fired.
    logs = " ".join(r.message for r in caplog.records)
    assert "Stop requested" in logs
    assert (
        "Waiting for job to finish: worker 0: tests.integration.test_worker.t[1]()"
        in logs
    )


async def test_run_no_listen_notify(app):
    running_worker = worker.Worker(app=app, queues=["some_queue"], listen_notify=False)
    task = asyncio.ensure_future(running_worker.run())
    try:
        await asyncio.sleep(0.01)
        assert app.connector.notify_event is None
    finally:
        running_worker.stop()
        await asyncio.wait_for(task, timeout=0.5)
