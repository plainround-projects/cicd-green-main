import pytest

from small_service.domain.errors import InvalidJobKeyError, JobNotStartedError
from small_service.domain.jobs import MAX_JOB_SECONDS, MIN_JOB_SECONDS, Job, lesson_delay, validate_job_key


def instant_job() -> Job:
    return Job(delay=lambda: 0.0, sleep=lambda seconds: None)


def test_wait_returns_true_once_the_work_has_ended():
    job = instant_job()
    job.start()
    assert job.wait(timeout_seconds=1) is True
    assert job.done


def test_wait_returns_false_when_the_work_outlasts_the_timeout():
    job = Job(delay=lambda: 0.5)
    job.start()
    assert job.wait(timeout_seconds=0.01) is False
    assert not job.done


def test_waiting_before_starting_is_an_error():
    with pytest.raises(JobNotStartedError):
        instant_job().wait(1)


def test_the_planted_delay_is_between_50_and_112_ms():
    delays = [lesson_delay() for _ in range(500)]
    assert min(delays) >= MIN_JOB_SECONDS
    assert max(delays) <= MAX_JOB_SECONDS


def test_the_fix_for_the_flaky_test_waits_for_the_job_instead_of_sleeping_a_guess():
    # The lesson's flaky test sleeps 100 ms and then asserts. Waiting is correct for any delay the job picks.
    for _ in range(25):
        job = Job()
        job.start()
        assert job.wait(timeout_seconds=1)


@pytest.mark.parametrize("key", ["nightly-report", "a", "x" * 64, "job_1.v2-final"])
def test_valid_job_keys_are_returned_unchanged(key):
    assert validate_job_key(key) == key


@pytest.mark.parametrize("key", ["", "x" * 65, "has space", "semi;colon", "path/slash", "ünïcode", "quote'"])
def test_invalid_job_keys_are_refused(key):
    with pytest.raises(InvalidJobKeyError):
        validate_job_key(key)
