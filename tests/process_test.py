"""Test when processing templates"""
import copy
import os

import pytest
from tektonasacode import config
from tektonasacode import process_templates as pt

github_json_pr = {
    'pull_request': {
        'user': {
            'login': 'foo',
        },
        "base": {
            "repo": {
                "full_name": "https://github.com/border/land"
            }
        }
    },
    "repository": {
        "owner": {
            "login": "bar"
        }
    }
}


@pytest.fixture
def dodo(tmpdir):
    """Create temporary tekton repository"""
    repo = tmpdir.mkdir("repository")

    tektondir = repo.mkdir(".tekton")

    template1 = tektondir.join("pipeline.yaml")
    template1.write("""--- 
apiVersion: tekton.dev/v1beta1
kind: PipelineRun
metadata:
  name: pipelinespec-taskspecs-embedded
spec:
  pipelineSpec:
    tasks:
      - name: hello1
        taskSpec:
          steps:
            - name: hello-moto
              image: scratch

    """)
    yield repo


def test_process_not_allowed_no_owner_not_same_submitter_owner(dodo):
    class FakeGithub:
        def get_file_content(self, owner_repo, path):
            return b''

    # Add a file to make sure we check we skip those files that are not ending in yaml or are OWNERS files
    dodo.join(config.TEKTON_ASA_CODE_DIR, "README.md").write("Hello Moto")
    # Make sure we skip tekton.yaml and only parsing if needed (empty here)
    dodo.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml").write("---")

    github_class = FakeGithub()
    process = pt.Process(github_class)
    process.checked_repo = dodo

    ret = process.process_tekton_dir(github_json_pr, {})
    assert not ret["allowed"]


def test_process_allowed_same_owner_submitter(dodo):
    class FakeGithub:
        def get_file_content(self, owner_repo, path):
            return b''

    github_class = FakeGithub()
    process = pt.Process(github_class)
    process.checked_repo = dodo

    jeez = copy.deepcopy(github_json_pr)
    jeez['pull_request']['user']['login'] = jeez['repository']['owner'][
        'login']

    ret = process.process_tekton_dir(jeez, {})
    assert ret["allowed"]


def test_process_allowed_owner_file(dodo):
    """Allowed user via the OWNER file in github repo from parent branch."""
    class FakeGithub:
        def get_file_content(self, owner_repo, path):
            return b'foo'

    github_class = FakeGithub()
    process = pt.Process(github_class)
    process.checked_repo = dodo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]


def test_process_allowed_tekton_yaml(dodo):
    """Allowed user via the owner section of tekton.yaml in github repo parent branch."""
    class FakeGithub:
        def get_file_content(self, owner_repo, path):
            if path == os.path.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml"):
                return """---
                owners:
                  - foo
                """
            return b''

    github_class = FakeGithub()
    process = pt.Process(github_class)
    process.checked_repo = dodo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]


def test_process_allowed_organizations(dodo):
    """Allowed user via the owner section of tekton.yaml where the user belong to allowed org."""
    class FakeGithubTektonYaml:
        def get_file_content(self, owner_repo, path):
            if path == os.path.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml"):
                return b"""---
                owners:
                  - "@fakeorg"
                """
            return b''

        def check_organization_of_user(self, org, pruserlogin):
            return True

    process = pt.Process(FakeGithubTektonYaml())
    process.checked_repo = dodo

    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]

    class FakeGithubOwners:
        def get_file_content(self, owner_repo, path):
            if path == os.path.join(config.TEKTON_ASA_CODE_DIR, "OWNERS"):
                return b"""@fakeorg"""
            return b""

        def check_organization_of_user(self, org, pruserlogin):
            return True

    process = pt.Process(FakeGithubOwners())
    process.checked_repo = dodo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]
