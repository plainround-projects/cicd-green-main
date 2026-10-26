from pathlib import Path

import pytest
from pipeline.core import contract, protection, workflow

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
GOOD = f"""
name: ci
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{SHA} # v1
      - uses: ./.github/actions/setup
      - run: make lint
  quarantine:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: make quarantine
"""


def findings(text: str, required=("lint",)) -> list[str]:
    return [finding.code for finding in workflow.lint(workflow.load(text), required, ("quarantine",))]


def test_a_good_workflow_has_no_findings():
    assert findings(GOOD) == []


def test_the_on_key_is_read_despite_yaml_treating_it_as_a_boolean():
    assert "push" in workflow.load(GOOD)["on"]


def test_job_names_use_the_name_field_when_present():
    document = workflow.load(GOOD.replace("  lint:\n", "  lint:\n    name: Lint and types\n"))
    assert workflow.job_names(document)["lint"] == "Lint and types"


def test_a_required_check_that_no_job_reports_is_found():
    assert "WF001" in findings(GOOD, required=("lint", "unit"))


def test_a_paths_filter_on_a_trigger_is_found():
    assert "WF003" in findings(GOOD.replace("  push:\n", "  push:\n    paths-ignore: ['docs/**']\n"))


def test_a_workflow_that_does_not_run_on_pull_requests_is_found():
    assert "WF002" in findings(GOOD.replace("  pull_request:\n", ""))


def test_continue_on_error_outside_the_quarantine_job_is_found():
    assert "WF004" in findings(
        GOOD.replace(
            "    steps:\n      - uses: actions", "    continue-on-error: true\n    steps:\n      - uses: actions", 1
        )
    )


@pytest.mark.parametrize("reference", ["actions/checkout@v4", "actions/checkout@main", f"actions/checkout@{SHA[:39]}"])
def test_an_action_not_pinned_to_a_full_sha_is_found(reference):
    assert "WF005" in findings(GOOD.replace(f"actions/checkout@{SHA}", reference))


def test_a_moving_name_in_a_command_or_service_is_found():
    assert "WF006" in findings(GOOD.replace("make lint", "docker run postgres:latest"))
    with_service = GOOD.replace(
        "    steps:\n      - uses: actions",
        "    services:\n      db:\n        image: postgres:latest\n    steps:\n      - uses: actions",
        1,
    )
    assert "WF006" in findings(with_service)


def test_missing_read_only_permissions_are_found():
    assert "WF007" in findings(GOOD.replace("permissions:\n  contents: read\n", ""))


def test_a_workflow_without_required_checks_may_use_other_triggers():
    scheduled = GOOD.replace("on:\n  push:\n  pull_request:\n", "on:\n  schedule:\n    - cron: '0 6 * * 1'\n")
    assert findings(scheduled, required=()) == []


def test_every_workflow_and_composite_action_in_this_repository_passes_the_rules():
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        required = protection.REQUIRED_CHECKS if path.name == "ci.yml" else ()
        problems = workflow.lint(workflow.load(path.read_text()), required, ("quarantine",))
        assert problems == [], f"{path.name}: {problems}"
    for path in sorted((ROOT / ".github" / "actions").glob("*/action.yml")):
        assert workflow.lint_composite(workflow.load(path.read_text())) == [], path


def test_an_unpinned_step_in_a_composite_action_is_found():
    action = workflow.load(
        "runs:\n  using: composite\n  steps:\n    - uses: actions/setup-python@v5\n    - uses: ./x\n"
    )
    assert [finding.code for finding in workflow.lint_composite(action)] == ["WF005"]


def test_the_protection_payload_requires_the_checks_strictly_for_admins_too():
    payload = protection.branch_protection(("lint", "unit"))
    assert payload["required_status_checks"] == {"strict": True, "contexts": ["lint", "unit"]}
    assert payload["enforce_admins"] is True
    assert payload["allow_force_pushes"] is False


def test_protection_needs_at_least_one_check():
    with pytest.raises(ValueError, match="at least one"):
        protection.branch_protection(())


def test_the_required_checks_are_the_names_of_jobs_in_the_ci_workflow():
    names = set(workflow.job_names(workflow.load((ROOT / ".github" / "workflows" / "ci.yml").read_text())).values())
    assert set(protection.REQUIRED_CHECKS) <= names


GOOD_README = """# x

## The pipeline's contract

- Anything on `main` has passed lint, unit and integration tests.
- The required checks finish in under 5 minutes.
- A red `main` stops merging: fix it forward within an hour or revert it.

## Next
"""


def test_a_short_contract_with_the_red_main_rule_passes():
    assert contract.check(GOOD_README) == []


def test_a_contract_over_ten_lines_fails():
    long_readme = GOOD_README.replace("- A red", "\n".join(f"- rule {n}" for n in range(9)) + "\n- A red")
    assert any("limit is 10" in problem for problem in contract.check(long_readme))


def test_a_contract_without_the_red_main_rule_or_a_time_fails():
    problems = contract.check("## The pipeline's contract\n\n- be nice\n")
    assert len(problems) == 2


def test_a_readme_without_the_section_fails():
    assert contract.check("# x\n") != []


def test_this_repository_readme_has_a_valid_contract():
    assert contract.check((ROOT / "README.md").read_text()) == []
