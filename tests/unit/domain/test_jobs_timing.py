"""The lesson's planted flaky test, kept as it was written and quarantined.

The job takes a random 50 to 112.5 ms and the test sleeps a fixed 100 ms, so it fails about one run in five (12.5 ms
of the 62.5 ms range). Its marker keeps it out of the required `unit` job; the non-blocking `quarantine` job runs it.
The fixed version of the same check is `test_the_fix_for_the_flaky_test_waits_for_the_job_instead_of_sleeping_a_guess`
in test_jobs.py. See docs/issues/0001-flaky-job-timing-test.md.
"""

import time

import pytest

from small_service.domain.jobs import Job


@pytest.mark.flaky_quarantine
def test_job_finishes_in_time():
    job = Job()
    job.start()
    time.sleep(0.1)  # a timing assumption: the job is usually, not always, finished by now
    assert job.done
