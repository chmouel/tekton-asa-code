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
import tempfile

import yaml

from tektonasacode import config, utils


class Process:
    """Main processing class"""
    def __init__(self, github_cls):
        self.utils = utils.Utils()
        self.github = github_cls
        self.checked_repo = config.REPOSITORY_DIR

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

    def process_owner_section_or_file(self, pr_login, cfg):
        """Process the owner section of config or a file"""
        owner_file = os.path.join(self.checked_repo,
                                  config.TEKTON_ASA_CODE_DIR, "OWNERS")
        if 'owners' in cfg:
            owners_allowed = cfg['owners']
        elif os.path.exists(owner_file):
            owners_allowed = [
                x.strip() for x in open(owner_file, 'r').readlines()
            ]
        else:
            owners_allowed = []

        # By default we deny unless explictely allowed
        allowed = False
        for owner in owners_allowed:
            # If the line starts with a @ it means it's a github
            # organization, check if the user is part of it
            if owner[0] == "@":
                allowed = self.github.check_organization_of_user(
                    owner[1:], pr_login)
            else:
                if owner == pr_login:
                    allowed = True
        return allowed

    def process_yaml_ini(
        self,
        yaml_file,
        jeez,
        parameters_extras,
    ):
        """Process yaml ini files"""
        cfg = yaml.safe_load(open(yaml_file, 'r'))
        processed = {'templates': {}}
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
                processed['templates'][ret[0]] = ret[1]

        processed['allowed'] = self.process_owner_section_or_file(
            self.utils.get_key("pull_request.user.login", jeez), cfg)

        if 'files' in cfg:
            for filepath in cfg['files']:
                fpath = os.path.join(self.checked_repo,
                                     config.TEKTON_ASA_CODE_DIR, filepath)
                if not os.path.exists(fpath):
                    raise Exception(
                        f"{filepath} does not exists in {config.TEKTON_ASA_CODE_DIR} directory"
                    )
                ret = self.utils.kapply(fpath, jeez, parameters_extras)
                processed['templates'][ret[0]] = ret[1]
        else:
            processed['templates'].update(
                self.process_all_yaml_in_dir(jeez, parameters_extras))

        return processed

    def process_all_yaml_in_dir(self, jeez, parameters_extras):
        """Process directory directly, not caring about stuff just getting every
        yaml files in there"""
        processed = {'templates': {}}

        processed['allowed'] = self.process_owner_section_or_file(
            self.utils.get_key("pull_request.user.login", jeez), {})

        for filename in os.listdir(
                os.path.join(self.checked_repo, config.TEKTON_ASA_CODE_DIR)):

            if filename.split(".")[-1] not in ["yaml", "yml"]:
                continue
            if filename == "tekton.yaml":
                continue
            filename = os.path.join(self.checked_repo,
                                    config.TEKTON_ASA_CODE_DIR, filename)
            ret = self.utils.kapply(
                filename,
                jeez,
                parameters_extras,
                name=f'{config.TEKTON_ASA_CODE_DIR}/{filename}')
            processed['templates'][ret[0]] = ret[1]
        return processed

    def process_tekton_dir(self, jeez, parameters_extras):
        """Apply templates according, check first for tekton.yaml and then
        process all yaml files in directory"""
        if os.path.exists(
                f"{self.checked_repo}/{config.TEKTON_ASA_CODE_DIR}/tekton.yaml"
        ):
            return self.process_yaml_ini(
                f"{self.checked_repo}/{config.TEKTON_ASA_CODE_DIR}/tekton.yaml",
                jeez, parameters_extras)

        return self.process_all_yaml_in_dir(jeez, parameters_extras)
