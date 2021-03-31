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
import base64
import datetime
import http.client
import json
import urllib.parse
from typing import Any, Dict, Tuple

import pkg_resources

from tektonasacode import config


class GithubEventNotProcessed(Exception):
    """Raised when the event is not processed."""


class GitHUBAPIException(Exception):
    """Exceptions when GtiHUB API fails"""
    status = None

    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class Github:
    """Github operations"""

    def __init__(self, token):
        self.token = token
        self.github_api_url = config.GITHUB_API_URL

    def request(self,
                method: str,
                url: str,
                headers=None,
                data=None,
                params=None) -> (Tuple[http.client.HTTPResponse, Any]):
        """Execute a request to the GitHUB API, handling redirect"""
        if not url.startswith("http"):
            if url[0] == "/":
                url = url[1:]
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
            raise GitHUBAPIException(
                response.status,
                f"Error: {response.status} - {json.loads(response.read())} - {method} - {url} - {data} - {headers}"
            )

        return (response, json.loads(response.read().decode()))

    def filter_event_json(self, event_json):
        """Filter the json received if it's a comment add the pull request
        information into it. If there is nothing then return an execption
        NotProcessed"""
        if "pull_request" in event_json:
            return event_json
        # Check if the event has a /retest in a pull_request comment, it can be
        # any line.
        if all([
                "issue" in event_json, "pull_request" in event_json["issue"],
                "comment" in event_json, config.COMMENT_RETEST_STRING
                in event_json["comment"]["body"].split("\n")
        ]):
            response, pull_request = self.request(
                "GET", event_json["issue"]["pull_request"]["url"])
            if response.status >= 400:
                raise GithubEventNotProcessed(
                    f'Error loading {event_json["issue"]["pull_request"]["url"]}'
                )
            event_json["pull_request"] = pull_request
            return event_json

        raise GithubEventNotProcessed("Not processing this GitHUB event")

    def get_file_content(self, owner_repo: str, path: str) -> bytes:
        """Get file path contents from GITHUB API"""
        try:
            _, content = self.request("GET",
                                      f"/repos/{owner_repo}/contents/{path}")
        except GitHUBAPIException as error:
            if error.status and error.status == 404:
                return b""
            raise error
        return base64.b64decode(content['content'])

    def get_task_latest_version(self, repository: str, task: str) -> str:
        """Use the github api to retrieve the latest task verison from a repository"""
        error = None
        catalog = None
        # TODO: Get default_branch from github api instead of mucking around with this
        #       See https://stackoverflow.com/a/16501903
        for tip_branch in ('main', 'master'):
            try:
                _, catalog = self.request(
                    "GET",
                    f"{self.github_api_url}/repos/{repository}/git/trees/{tip_branch}",
                    params={
                        "recursive": "true",
                    },
                )
                if catalog:
                    break
            except Exception as exc:
                error = exc

        if error:
            raise error

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
            raise GitHUBAPIException(
                message=f"I could not find a task in '{repository}' for '{task}' ",
                status=404,
            )

        print(f"💡 Task {task} in {repository} latest version is {version[0]}")

        return version[0]

    def check_organization_of_user(
        self,
        organization: str,
        pull_request_user_login: str,
    ) -> bool:
        """Check if a user is part of an organization an deny her, unless a approved
           member leaves a /tekton ok-to-test comments"""
        _, _orgs = self.request(
            "GET",
            f"{self.github_api_url}/users/{pull_request_user_login}/orgs",
        )
        organizations = [user["login"] for user in _orgs]
        if organization in organizations:
            return True
        return False

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
            f"/repos/{repository_full_name}/check-runs/{check_run_id}",
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
            f"{self.github_api_url}/repos/{repository_full_name}/check-runs",
            headers={"Accept": "application/vnd.github.antiope-preview+json"},
            data=data,
        )

        return jeez
