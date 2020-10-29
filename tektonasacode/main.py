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
import traceback

from tektonasacode import config, github, process_templates, utils


class TektonAsaCode:
    """Tekton as a Code main class"""
    def __init__(self, github_token, github_json):
        self.utils = utils.Utils()
        self.github = github.Github(github_token)
        self.pcs = process_templates.Process(self.github)
        self.check_run_id = None
        self.repo_full_name = ""
        self.github_json = github_json.replace("\n", " ")

    def github_checkout_pull_request(self, repo_owner_login, repo_html_url,
                                     pull_request_number, pull_request_sha):
        """Checkout a pull request from github"""
        if not os.path.exists(config.REPOSITORY_DIR):
            os.makedirs(config.REPOSITORY_DIR)
            os.chdir(config.REPOSITORY_DIR)

            exec_init = self.utils.execute("git init")
            if exec_init.returncode != 0:
                print(
                    "Error creating a GitHUB repo in {config.REPOSITORY_DIR}")
                print(exec_init.stdout.decode())
                print(exec_init.stderr.decode())
        else:
            os.chdir(config.REPOSITORY_DIR)
            exec_init = self.utils.execute("git remote remove origin")

        cmds = [
            f"git remote add -f origin https://{repo_owner_login}:{self.github.token}@{repo_html_url.replace('https://', '')}",
            f"git fetch origin refs/pull/{pull_request_number}/head",
            f"git reset --hard {pull_request_sha}",
        ]
        for cmd in cmds:
            self.utils.execute(
                cmd,
                "Error checking out the GitHUB repo %s to the branch %s" %
                (repo_html_url, pull_request_sha),
            )

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

    def main(self):
        """main function"""
        jeez = json.loads(self.github_json)
        self.repo_full_name = self.utils.get_key("repository.full_name", jeez)

        random_str = "".join(
            random.choices(string.ascii_letters + string.digits, k=2)).lower()
        pull_request_sha = self.utils.get_key("pull_request.head.sha", jeez)
        pull_request_number = self.utils.get_key("pull_request.number", jeez)
        repo_owner_login = self.utils.get_key("repository.owner.login", jeez)
        repo_html_url = self.utils.get_key("repository.html_url", jeez)
        namespace = f"pull-{pull_request_number}-{pull_request_sha[:5]}-{random_str}"

        # Extras template parameters to add aside of the stuff from json
        parameters_extras = {
            "revision": pull_request_sha,
            "repo_url": repo_html_url,
            "repo_owner": repo_owner_login,
            "namespace": namespace,
        }

        target_url = self.utils.get_openshift_console_url(namespace)

        check_run = self.github.create_check_run(self.repo_full_name,
                                                 target_url, pull_request_sha)

        self.check_run_id = check_run['id']

        self.github_checkout_pull_request(repo_owner_login, repo_html_url,
                                          pull_request_number,
                                          pull_request_sha)

        # Exit if there is not tekton directory
        if not os.path.exists(config.TEKTON_ASA_CODE_DIR):
            # Set status as pending
            self.github.set_status(
                self.repo_full_name,
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
                    f"No tekton-asa-code directory '{config.TEKTON_ASA_CODE_DIR}' has been found in this repository 😿",
                })
            print("No tekton directory has been found 😿")
            sys.exit(0)

        processed = self.pcs.process_tekton_dir(jeez, parameters_extras)
        if processed['allowed']:
            print("✅ User is allowed to run this PR")
        else:
            message = f"❌👮‍♂️ Skipping running the CI since the user **{self.utils.get_key('pull_request.user.login', jeez)}** is not in the owner file or section"
            self.github.set_status(
                self.repo_full_name,
                check_run['id'],
                "https://tenor.com/search/police-gifs",
                conclusion="neutral",
                output={
                    "title": "CI Run: Denied",
                    "summary": "Skipping checking this repository 🤷🏻‍♀️",
                    "text": message,
                },
                status="completed",
            )
            raise Exception(message)

        self.create_temporary_namespace(namespace, self.repo_full_name,
                                        pull_request_number)
        self.pcs.apply(processed['templates'], namespace)

        time.sleep(2)

        status, describe_output, report_output = self.grab_output(namespace)
        print(describe_output)
        # Set status as pending
        self.github.set_status(
            self.repo_full_name,
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

    def runwrap(self):
        """Wrap main() and catch errors to report if we can"""
        try:
            self.main()
        except Exception as err:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tracebackerr = traceback.format_exception(exc_type, exc_value,
                                                      exc_tb)
            if self.check_run_id:
                self.github.set_status(
                    repository_full_name=self.repo_full_name,
                    check_run_id=self.check_run_id,
                    target_url="https://tenor.com/search/sad-cat-gifs",
                    conclusion="failure",
                    output={
                        "title": "CI Run: Failure",
                        "summary": "Tekton asa code has failed 💣",
                        "text": f'<pre>{"<br/>".join(tracebackerr)}</pre>',
                    },
                    status="completed")
            raise err
