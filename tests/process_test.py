"""Test when processing templates"""
# pylint: disable=redefined-outer-name,too-few-public-methods

import copy
import os
from typing import Optional

import pytest
from tektonasacode import config
from tektonasacode import process_templates as pt
from tektonasacode import utils

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
def fixtrepo(tmpdir):
    """Create temporary tekton repository"""
    repo = tmpdir.mkdir("repository")

    tektondir = repo.mkdir(".tekton")

    pipeline = tektondir.join("pipeline.yaml")
    pipeline.write("""--- \n
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
      - name: hello2
        taskRef:
            name: task-hello-moto2
     """)
    task = tektondir.join("task.yaml")
    task.write("""---
    apiVersion: tekton.dev/v1beta1
    kind: Task
    metadata:
        name: task-hello-moto2
    spec:
      steps:
      - name: hello-moto2
        image: scratch2
    """)
    configmap = tektondir.join("configmap.yaml")
    configmap.write("""---
    apiVersion: v1
    kind: Configmap
    metadata:
        name: configmap
    data:
        hello: "moto"
    """)
    yield repo


def test_process_not_allowed_no_owner_not_same_submitter_owner(fixtrepo):
    """Test processing tempaltes not allowed because submitter is not the same as repo owner"""
    class FakeGithub:
        """Fake Github Class"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return b''

    # Add a file to make sure we check we skip those files that are not ending in yaml or are OWNERS files
    fixtrepo.join(config.TEKTON_ASA_CODE_DIR, "README.md").write("Hello Moto")
    # Make sure we skip tekton.yaml and only parsing if needed (empty here)
    fixtrepo.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml").write("---")

    process = pt.Process(FakeGithub())
    process.checked_repo = fixtrepo

    ret = process.process_tekton_dir(github_json_pr, {})
    assert not ret["allowed"]


def test_process_allowed_same_owner_submitter(fixtrepo):
    """Test processing allowed because submitter is the same as repo owner"""
    class FakeGithub:
        """Fake Github Class"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return b''

    process = pt.Process(FakeGithub())
    process.checked_repo = fixtrepo

    jeez = copy.deepcopy(github_json_pr)
    jeez['pull_request']['user']['login'] = jeez['repository']['owner'][
        'login']

    ret = process.process_tekton_dir(jeez, {})
    assert ret["allowed"]


def test_process_allowed_owner_file(fixtrepo):
    """Allowed user via the OWNER file in github repo from parent branch."""
    class FakeGithub:
        """Fake Github Class"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return b'foo'

    process = pt.Process(FakeGithub())
    process.checked_repo = fixtrepo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]


def test_process_allowed_tekton_yaml(fixtrepo):
    """Allowed user via the owner section of tekton.yaml in github repo parent branch."""
    class FakeGithub:
        """Fake Github Class"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            if path == os.path.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml"):
                return """---
                owners:
                  - foo
                """
            return b''

    process = pt.Process(FakeGithub())
    process.checked_repo = fixtrepo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]


def test_process_via_moulinette(fixtrepo):
    """Test that the moulinette is working (via tektonbundle)"""
    class FakeGithub:
        """fake Github like a champ"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return b''

    (fixtrepo / config.TEKTON_ASA_CODE_DIR / "tekton.yaml").write("""---
    bundled: true
    """)
    process = pt.Process(FakeGithub())
    process.checked_repo = fixtrepo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert 'bundled-file.yaml' in ret['templates']


def test_process_allowed_organizations(fixtrepo):
    """Allowed user via the owner section of tekton.yaml where the user belong to allowed org."""
    class FakeGithubTektonYaml:
        """Fake Github Class"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            if path == os.path.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml"):
                return b"""---
                owners:
                  - "@fakeorg"
                """
            return b''

        def check_organization_of_user(self, org, pruserlogin):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return True

    process = pt.Process(FakeGithubTektonYaml())
    process.checked_repo = fixtrepo

    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]

    class FakeGithubOwners:
        """Fake Github Class"""
        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            if path == os.path.join(config.TEKTON_ASA_CODE_DIR, "OWNERS"):
                return b"""@fakeorg"""
            return b""

        def check_organization_of_user(self, org, pruserlogin):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return True

    process = pt.Process(FakeGithubOwners())
    process.checked_repo = fixtrepo
    ret = process.process_tekton_dir(github_json_pr, {})
    assert ret["allowed"]


def test_process_yaml_ini(tmp_path, fixtrepo):
    """Test processing all fields in tekton.yaml"""
    class FakeGithub:
        """Fake Github class"""
        def get_task_latest_version(self, repo, name):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return "0.0.7"

        def get_file_content(self, owner_repo, path):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return b''

    class FakeUtils(utils.Utils):
        """Fake Utils class"""
        @staticmethod
        def retrieve_url(url):
            """
            Retrieve a fake url
            """
            taskname = tmp_path / os.path.basename(url).replace(".yaml", "")
            taskname.write_text("""---
            kind: Pipeline
            metadata:
                name: fakepipeline
            """)
            return taskname

        def kubectl_get(self,
                        obj: str,
                        output_type: str = "yaml",
                        raw: bool = False,
                        namespace: str = "",
                        labels: Optional[dict] = None):  # pylint: disable=unused-argument,missing-function-docstring,no-self-use
            return {"items": [{"metadata": {"name": "shuss"}}]}

    (fixtrepo / config.TEKTON_ASA_CODE_DIR / "pr_use_me.yaml").write("--- ")
    tektonyaml = tmp_path / "tekton.yaml"
    tektonyaml.write_text("""---
    tasks:
      - task1
      - task2:latest
      - task3:0.2
      - https://this.is.not/a/repo/a.xml

    secrets:
      - shuss

    files:
      - pr_use_me.yaml
    """)
    process = pt.Process(FakeGithub())
    process.checked_repo = fixtrepo
    process.utils = FakeUtils()
    processed = process.process_yaml_ini(tektonyaml, github_json_pr, {})

    # Assert tasks processing
    tasks = [
        os.path.dirname(x.replace(config.GITHUB_RAW_URL + "/", ''))
        for x in list(processed['templates'])
    ]
    assert tasks[0] == "task1/0.0.7"
    assert tasks[1] == "task2/0.0.7"
    assert tasks[2] == "task3/0.2"
    assert tasks[3].startswith("https")
    assert list(processed['templates'])[4] == "shuss.secret.yaml"
    assert os.path.basename(list(
        processed['templates'])[5]) == "pr_use_me.yaml"
