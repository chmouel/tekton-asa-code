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
"""Do some processing of the templates"""
import os
import sys
import tempfile
import urllib.error
import urllib.request

import yaml

from tektonasacode import config, utils


class Process:
    """Main processing class"""
    def __init__(self, github_cls):
        self.utils = utils.Utils()
        self.github = github_cls

    def apply(self, processed_templates, namespace):
        """Apply templates from a dict of filename=>content"""
        for filename in processed_templates:
            print(f"Processing {filename} in {namespace}")
            content = processed_templates[filename]
            tmpfile = tempfile.NamedTemporaryFile(delete=False).name
            open(tmpfile, "w").write(content)
            self.utils.execute(
                f"kubectl apply -f {tmpfile} -n {namespace}",
                "Cannot apply {filename} in {namespace}",
            )
            os.remove(tmpfile)

    def process_yaml_ini(self, yaml_file, jeez, parameters_extras,
                         checked_repo):
        """Process yaml ini files"""
        cfg = yaml.safe_load(open(yaml_file, 'r'))
        processed = {}
        if 'tasks' in cfg:
            for task in cfg['tasks']:
                if 'http' in task:
                    url = task
                else:
                    if ':' in task:
                        name, version = task.split(":")
                    else:
                        name = task
                        version = self.github.get_task_latest_version(
                            "tektoncd/catalog", name)
                    raw_url = "https://raw.githubusercontent.com/tektoncd/catalog/master/task"
                    url = f"{raw_url}/{name}/{version}/{name}.yaml"
                ret = self.utils.kapply(self.utils.retrieve_url(url),
                                        jeez,
                                        parameters_extras,
                                        name=url)
                processed[ret[0]] = ret[1]

        if 'files' in cfg:
            for filepath in cfg['files']:
                fpath = os.path.join(checked_repo, config.TEKTON_ASA_CODE_DIR,
                                     filepath)
                if not os.path.exists(fpath):
                    raise Exception(
                        f"{filepath} does not exists in {config.TEKTON_ASA_CODE_DIR} directory"
                    )
                ret = self.utils.kapply(fpath, jeez, parameters_extras)
                processed[ret[0]] = ret[1]
        else:
            processed.update(
                self.process_all_yaml_in_dir(checked_repo, jeez,
                                             parameters_extras))
        return processed

    def process_all_yaml_in_dir(self, checked_repo, jeez, parameters_extras):
        """Process directory directly, not caring about stuff just getting every
        yaml files in there"""
        processed = {}
        for filename in os.listdir(
                os.path.join(checked_repo, config.TEKTON_ASA_CODE_DIR)):
            if not filename.endswith(".yaml") or not filename.endswith(
                    ".yml") or filename.endswith("tekton.yaml"):
                continue
            ret = self.utils.kapply(
                filename,
                jeez,
                parameters_extras,
                name=f'{config.TEKTON_ASA_CODE_DIR}/{filename}')
            processed[ret[0]] = ret[1]
        return processed

    def process_tekton_dir(self, checked_repo, repo_full_name, check_run_id,
                           jeez, parameters_extras):
        """Apply templates according, check first for tekton.yaml and then
        process all yaml files in directory"""
        if os.path.exists(
                f"{checked_repo}/{config.TEKTON_ASA_CODE_DIR}/tekton.yaml"):
            return self.process_yaml_ini(
                f"{checked_repo}/{config.TEKTON_ASA_CODE_DIR}/tekton.yaml",
                jeez, parameters_extras, checked_repo)

        if not os.path.exists(
                f"{checked_repo}/{config.TEKTON_ASA_CODE_DIR}/install.map"):
            return self.process_all_yaml_in_dir(checked_repo, jeez,
                                                parameters_extras)

        # TODO(chmouel): remove install.map process until everything is migrated
        # to tekton.yaml
        processed = {}
        print(
            f"Processing install.map: {checked_repo}/{config.TEKTON_ASA_CODE_DIR}/install.map"
        )
        for line in open(
                f"{checked_repo}/{config.TEKTON_ASA_CODE_DIR}/install.map"):
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

                if splitted[0] not in config.CATALOGS:
                    print(
                        f'The catalog "{splitted[0]}" in line: "{line}" is invalid'
                    )
                    continue

                version = splitted[2]
                if version == "latest":
                    version = self.github.get_task_latest_version(
                        config.CATALOGS[splitted[0]], splitted[1])

                raw_url = f"https://raw.githubusercontent.com/{config.CATALOGS[splitted[0]]}/master/task"
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
                ret = self.utils.kapply(url_retrieved,
                                        jeez,
                                        parameters_extras,
                                        name=line)
                processed[ret[0]] = ret[1]
            elif os.path.exists(
                    f"{checked_repo}/{config.TEKTON_ASA_CODE_DIR}/{line}"):
                ret = self.utils.kapply(
                    f"{checked_repo}/{config.TEKTON_ASA_CODE_DIR}/{line}",
                    jeez,
                    parameters_extras,
                    name=f'{config.TEKTON_ASA_CODE_DIR}/{line}')
                processed[ret[0]] = ret[1]
            elif os.path.exists(line):
                ret = self.utils.kapply(line, jeez, parameters_extras)
                processed[ret[0]] = ret[1]
            else:
                print(
                    f"The file {line} specified in install.map is not found in tekton repository"
                )
        return processed
