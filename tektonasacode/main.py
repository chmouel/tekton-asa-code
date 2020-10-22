# coding=utf8
"""
Tekton as a CODE: Main script
"""
import json
import os
import random
import re
import string
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from tektonasacode import github
from tektonasacode import utils

TEKTON_ASA_CODE_DIR = os.environ.get("TEKTON_ASA_CODE_DIR", ".tekton")

CATALOGS = {
    "official": "tektoncd/catalog",
}

CHECK_RUN_ID = None
REPO_FULL_NAME = None


class TektonAsaCode:
    """Tekton as a Code main class"""
    def __init__(self, github_token):
        self.utils = utils.Utils()
        self.github = github.Github(github_token)

    def github_checkout_pull_request(self, checked_repo, repo_owner_login,
                                     repo_html_url, pull_request_number,
                                     pull_request_sha):
        """Checkout a pull request from github"""
        if not os.path.exists(checked_repo):
            os.makedirs(checked_repo)
            os.chdir(checked_repo)

            exec_init = self.utils.execute("git init")
            if exec_init.returncode != 0:
                print("Error creating a GitHUB repo in {checked_repo}")
                print(exec_init.stdout.decode())
                print(exec_init.stderr.decode())

        os.chdir(checked_repo)

        cmds = [
            f"git remote add origin https://{repo_owner_login}:{self.github.token}@{repo_html_url.replace('https://', '')}",
            f"git fetch origin refs/pull/{pull_request_number}/head",
            f"git reset --hard {pull_request_sha}",
        ]
        for cmd in cmds:
            self.utils.execute(
                cmd,
                "Error checking out the GitHUB repo %s to the branch %s" %
                (repo_html_url, pull_request_sha),
            )

    def apply_templates(self, checked_repo, repo_full_name, check_run_id, jeez,
                        parameters_extras, namespace):
        """Apply templates according to rules"""
        if os.path.exists(f"{checked_repo}/{TEKTON_ASA_CODE_DIR}/install.map"):
            print(
                f"Processing install.map: {checked_repo}/{TEKTON_ASA_CODE_DIR}/install.map"
            )
            for line in open(
                    f"{checked_repo}/{TEKTON_ASA_CODE_DIR}/install.map"):
                line = line.strip()
                if not line:
                    continue

                if line.startswith("#"):
                    continue

                # remove inline comments
                if " #" in line:
                    line = line[:line.find(" #")]

                # if we have something like catalog:// do some magic :
                #
                # in: catalog://official:git-clone:0.1
                # out: https://raw.githubusercontent.com/tektoncd/catalog/master/task/git-clone/0.1/git-clone.yaml
                #
                # if we have the version finishing by latest we go query to the
                # Github API which one is the latest task.
                if line.startswith("catalog://"):
                    splitted = line.replace("catalog://", "").split(":")
                    if len(splitted) != 3:
                        print(f'The line in install.map:"{line}" is invalid')
                        continue

                    if splitted[0] not in CATALOGS:
                        print(
                            f'The catalog "{splitted[0]}" in line: "{line}" is invalid'
                        )
                        continue

                    version = splitted[2]
                    if version == "latest":
                        version = self.github.get_task_latest_version(
                            CATALOGS[splitted[0]], splitted[1])

                    raw_url = f"https://raw.githubusercontent.com/{CATALOGS[splitted[0]]}/master/task"
                    line = f"{raw_url}/{splitted[1]}/{version}/{splitted[1]}.yaml"

                # if we have a URL retrieve it (with GH token)
                if line.startswith("https://"):
                    try:
                        url_retrieved, _ = urllib.request.urlretrieve(line)
                    except urllib.error.HTTPError as http_error:
                        msg = f"Cannot retrieve remote task {line} as specified in install.map: {http_error}"
                        print(msg)
                        self.github.set_status(repo_full_name,
                                               check_run_id,
                                               "",
                                               conclusion="failure",
                                               output={
                                                   "title": "CI Run: Failure",
                                                   "summary":
                                                   "Cannot find remote task 💣",
                                                   "text": msg,
                                               },
                                               status="completed")
                        sys.exit(1)
                    self.utils.kapply(url_retrieved,
                                      jeez,
                                      parameters_extras,
                                      namespace,
                                      name=line)
                elif os.path.exists(
                        f"{checked_repo}/{TEKTON_ASA_CODE_DIR}/{line}"):
                    self.utils.kapply(
                        f"{checked_repo}/{TEKTON_ASA_CODE_DIR}/{line}",
                        jeez,
                        parameters_extras,
                        namespace,
                    )
                elif os.path.exists(line):
                    self.utils.kapply(line, jeez, parameters_extras, namespace)
                else:
                    print(
                        f"The file {line} specified in install.map is not found in tekton repository"
                    )
        else:
            for filename in os.listdir(
                    os.path.join(checked_repo, TEKTON_ASA_CODE_DIR)):
                if not filename.endswith(".yaml"):
                    continue
                self.utils.kapply(filename, jeez, parameters_extras, namespace)

    def create_temporary_namespace(self, namespace, repo_full_name,
                                   pull_request_number):
        """Create a temporary namespace and labels"""
        self.utils.execute(f"kubectl create ns {namespace}",
                           "Cannot create a temporary namespace")
        print(f"Namespace {namespace} has been created")

        # Apply label!
        self.utils.execute(
            f'kubectl label namespace {namespace} tekton.dev/generated-by="tekton-asa-code"'
        )
        self.utils.execute(
            f'kubectl label namespace {namespace} tekton.dev/pr="{repo_full_name.replace("/", "-")}-{pull_request_number}"'
        )

    def grab_output(self, namespace):
        """Grab output of the last pipelinerun in a namespace"""
        output_file = tempfile.NamedTemporaryFile(delete=False).name
        self.utils.stream(
            f"tkn pr logs -n {namespace} --follow --last",
            output_file,
            f"Cannot show Pipelinerun log in {namespace}",
        )
        output = open(output_file).read()

        # TODO: Need a better way!
        describe_output = self.utils.execute(
            f"tkn pr describe -n {namespace} --last").stdout.decode()
        regexp = re.compile(r"^STARTED\s*DURATION\s*STATUS\n(.*)$",
                            re.MULTILINE)
        status = regexp.findall(describe_output)[0].split(" ")[-1]

        pipelinerun_output = ""
        if output:
            pipelinerun_output = f"""<details>
<summary>PipelineRun Output</summary>

<pre>
 {output}
</pre>
</details>

    """
        report = f"""{self.utils.get_errors(output)}
{pipelinerun_output}

<details>
 <summary>PipelineRun status</summary>
 <pre>
{describe_output}
 </pre>
</details>

    """

        status_emoji = "☠️" if "failed" in status.lower() else "👍🏼"
        report_output = {
            "title": "CI Run: Report",
            "summary": f"CI has **{status}** {status_emoji}",
            "text": report
        }

        return status, describe_output, report_output

    def main(self, github_json):
        """main function"""
        checked_repo = "/tmp/repository"
        param = github_json.replace("\n", " ")
        if not param:
            print("Cannot find a github_json param")
            sys.exit(1)
        jeez = json.loads(param)
        random_str = "".join(
            random.choices(string.ascii_letters + string.digits, k=2)).lower()
        pull_request_sha = self.utils.get_key("pull_request.head.sha", jeez)
        pull_request_number = self.utils.get_key("pull_request.number", jeez)
        repo_full_name = self.utils.get_key("repository.full_name", jeez)
        repo_owner_login = self.utils.get_key("repository.owner.login", jeez)
        repo_html_url = self.utils.get_key("repository.html_url", jeez)

        # Extras template parameters to add aside of the stuff from json
        parameters_extras = {
            "revision": pull_request_sha,
            "repo_url": repo_html_url,
            "repo_owner": repo_owner_login,
        }

        namespace = f"pull-{pull_request_number}-{pull_request_sha[:5]}-{random_str}"
        target_url = self.utils.get_openshift_console_url(namespace)

        check_run = self.github.create_check_run(repo_full_name, target_url,
                                                 pull_request_sha)
        # TODO
        # pull_request_user_login = self.utils.get_key("pull_request.user.login",jeez)
        # tkaac_config = self.utils.get_config()
        # check_restrict_organization(
        #     tkaac_config.get("restrict_organization"),
        #     pull_request_user_login,
        #     jeez,
        # )

        self.github_checkout_pull_request(checked_repo, repo_owner_login,
                                          repo_html_url, pull_request_number,
                                          pull_request_sha)

        # Exit if there is not tekton directory
        if not os.path.exists(TEKTON_ASA_CODE_DIR):
            # Set status as pending
            self.github.set_status(
                repo_full_name,
                check_run['id'],
                "https://tenor.com/search/sad-cat-gifs",
                conclusion='neutral',
                status="completed",
                output={
                    "title":
                    "CI Run: Skipped",
                    "summary":
                    "Skipping this check 🤷🏻‍♀️",
                    "text":
                    f"No tekton-asa-code directory '{TEKTON_ASA_CODE_DIR}' has been found in this repository 😿",
                })
            print("No tekton directoy has been found 😿")
            sys.exit(0)

        self.create_temporary_namespace(namespace, repo_full_name,
                                        pull_request_number)

        self.apply_templates(checked_repo, repo_full_name, check_run['id'],
                             jeez, parameters_extras, namespace)

        time.sleep(2)

        status, describe_output, report_output = self.grab_output(namespace)
        print(describe_output)
        # Set status as pending
        self.github.set_status(
            repo_full_name,
            check_run["id"],
            # Only set target_url which goest to the namespace in case of failure,
            # since we delete the namespace in case of success.
            ("failed" in status.lower() and target_url or ""),
            ("failed" in status.lower() and "failure" or "success"),
            report_output,
            status="completed")
        if "failed" in status.lower():
            sys.exit(1)

        # Only delete if it succeed, keeping it for investigation
        self.utils.execute(
            f"kubectl delete ns {namespace}",
            "Cannot delete temporary namespace {namespace}",
        )
