# -*- coding: utf-8 -*-
# Author: Chmouel Boudjnah <chmouel@chmouel.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""Github Stuff"""

import datetime
import http.client
import json
import urllib.parse
from typing import Any, Dict, Tuple

import pkg_resources

GITHUB_API_URL = "api.github.com"
COMMENT_ALLOWED_STRING = "/tekton ok-to-test"


class Github:
    """Github operations"""
    def __init__(self, token):
        self.token = token
        self.github_api_url = GITHUB_API_URL

    def request(self,
                method: str,
                url: str,
                headers=None,
                data=None,
                params=None) -> (Tuple[http.client.HTTPResponse, Any]):
        """Execute a request to the GitHUB API, handling redirect"""
        if not url.startswith("http"):
            url = f"{self.github_api_url}/{url}"

        if not headers:
            headers = {}
        headers.update({
            "User-Agent": "TektonCD, the peaceful cat",
            "Authorization": f"Bearer {self.token}",
        })
        url_parsed = urllib.parse.urlparse(url)
        url_path = url_parsed.path
        if params:
            url_path += "?" + urllib.parse.urlencode(params)
        data = data and json.dumps(data)
        hostname = str(url_parsed.hostname)
        conn = http.client.HTTPSConnection(hostname)
        conn.request(method, url_path, body=data, headers=headers)
        response = conn.getresponse()

        if response.status == 302:
            return self.request(method, response.headers["Location"])

        if response.status >= 400:
            headers.pop("Authorization", None)
            raise Exception(
                f"Error: {response.status} - {json.loads(response.read())} - {method} - {url} - {data} - {headers}"
            )

        return (response, json.loads(response.read().decode()))

    def get_task_latest_version(self, repository: str, task: str) -> str:
        """Use the github api to retrieve the latest task verison from a repository"""
        _, catalog = self.request(
            "GET",
            f"https://api.github.com/repos/{repository}/git/trees/master",
            params={
                "recursive": "true",
            },
        )
        version = ("0.0", None)
        for tree in catalog["tree"]:
            path = tree["path"]
            if path.startswith(f"task/{task}") and path.endswith(
                    f"{task}.yaml"):
                splitted = path.split("/")
                if pkg_resources.parse_version(
                        splitted[2]) > pkg_resources.parse_version(version[0]):
                    version = (path.split("/")[2], tree["url"])

        if not version[1]:
            raise Exception(
                "I could not find a task in '{repository}' for '{task}' ")

        print(f"Task {task} in {repository} latest version is {version[0]}")

        return version[0]

    def check_user_in_organization(
        self,
        check_run_id: int,
        organization: str,
        repository_full_name: str,
        pull_request_user_login: str,
        pull_request_issue_url: str,
    ):
        """Check if a user is part of an organization an deny her, unless a approved
           member leaves a /tekton ok-to-test comments"""
        _, members = self.request(
            "GET",
            f"https://api.github.com/orgs/{organization}/members",
        )
        users_of_org = [user["login"] for user in members]
        user_part_of_org = [
            user for user in users_of_org if user == pull_request_user_login
        ]
        if user_part_of_org:
            return

        comments_url = f"{pull_request_issue_url}/comments"
        _, comments_of_pr = self.request(
            "GET",
            comments_url,
        )

        # Not a oneline cause python-black is getting crazy
        for comment in comments_of_pr:
            # if the user is part of the organization that is allowed to launch test.
            if comment["user"]["login"] in users_of_org:
                # if we have the comment at the beginning of a comment line.
                if COMMENT_ALLOWED_STRING in comment["data"].split("\r\n"):
                    print(
                        f'PR has been allowed to be tested by {comment["user"]["login"]}'
                    )
                    return

        message = f"👮‍♂️ Skipping running the CI since the user **{pull_request_user_login}** is not part of the organization **{organization}**"
        self.set_status(
            repository_full_name,
            check_run_id,
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

    def set_status(
        self,
        repository_full_name: str,
        check_run_id: int,
        target_url: str,
        conclusion: str,
        output: Dict[str, str],
        status: str,
    ) -> str:
        """
        Set status on the GitHUB Check
        """

        data = {
            "name": "Tekton CI",
            "status": status,
            "conclusion": conclusion,
            "completed_at":
            datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output": output,
        }
        if target_url:
            data["details_url"] = target_url

        _, jeez = self.request(
            "PATCH",
            f"https://{self.github_api_url}/repos/{repository_full_name}/check-runs/{check_run_id}",
            headers={"Accept": "application/vnd.github.antiope-preview+json"},
            data=data,
        )

        return jeez

    def create_check_run(self,
                         repository_full_name,
                         target_url,
                         head_sha,
                         status='in_progress',
                         started_at=""):
        """Create a check run id for a repository"""
        date_now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        data = {
            "name": "Tekton CI",
            "details_url": target_url,
            "status": status,
            "head_sha": head_sha,
            "started_at": started_at and started_at or date_now,
        }
        _, jeez = self.request(
            "POST",
            f"https://{self.github_api_url}/repos/{repository_full_name}/check-runs",
            headers={"Accept": "application/vnd.github.antiope-preview+json"},
            data=data,
        )

        return jeez
