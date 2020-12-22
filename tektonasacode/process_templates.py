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
from typing import Dict

import yaml
from tektonbundle import tektonbundle

from tektonasacode import config, utils


class Process:
    """Main processing class"""
    def __init__(self, github_cls):
        self.utils = utils.Utils()
        self.github = github_cls
        self.checked_repo = config.REPOSITORY_DIR
        self.moulinette = False

    def apply(self, processed_templates, namespace):
        """Apply templates from a dict of filename=>content"""
        for filename in processed_templates:
            print(f"🌊 Processing {filename} in {namespace}")
            content = processed_templates[filename]
            tmpfile = tempfile.NamedTemporaryFile(delete=False).name
            open(tmpfile, "w").write(content)
            self.utils.execute(
                f"kubectl create -f {tmpfile} -n {namespace}",
                f"Cannot create {filename} in {namespace}",
            )
            os.remove(tmpfile)

    def process_owner_section_or_file(self, jeez):
        """Process the owner section from config or a file on the tip branch"""
        pr_login = self.utils.get_key("pull_request.user.login", jeez)
        repo_owner = self.utils.get_key("repository.owner.login", jeez)
        owner_repo = self.utils.get_key("pull_request.base.repo.full_name",
                                        jeez)

        # Always allow the repo owner to submit.
        if repo_owner == pr_login:
            return True

        owners_allowed = []
        owner_content = self.github.get_file_content(
            owner_repo, os.path.join(config.TEKTON_ASA_CODE_DIR, "OWNERS"))
        if owner_content:
            owners_allowed = [
                x.strip() for x in owner_content.decode("utf8").split("\n")
                if x != ""
            ]
        else:
            owner_content = yaml.safe_load(
                self.github.get_file_content(
                    owner_repo,
                    os.path.join(config.TEKTON_ASA_CODE_DIR, "tekton.yaml")))
            if owner_content and 'owners' in owner_content:
                owners_allowed = owner_content['owners']
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

    def process_yaml_ini(self, yaml_file, jeez, parameters_extras):
        """Process yaml ini files"""
        cfg = yaml.safe_load(open(yaml_file, 'r'))
        if not cfg:
            return {'allowed': False, 'templates': []}

        processed = {'templates': {}}
        owner_repo = self.utils.get_key("pull_request.base.repo.full_name",
                                        jeez)

        if 'bundled' in cfg and cfg['bundled']:
            self.moulinette = True

        if 'tasks' in cfg:
            for task in cfg['tasks']:
                if 'http' in task:
                    url = task
                else:
                    if ':' in task and not task.endswith(":latest"):
                        name, version = task.split(":")
                    else:
                        name = task.replace(
                            ":latest",
                            "") if task.endswith(":latest") else task
                        version = self.github.get_task_latest_version(
                            config.TEKTON_CATALOG_REPOSITORY, name)
                    url = f"{config.GITHUB_RAW_URL}/{name}/{version}/{name}.yaml"
                ret = self.utils.kapply(self.utils.retrieve_url(url),
                                        jeez,
                                        parameters_extras,
                                        name=url)
                processed['templates'][ret[0]] = ret[1]

        processed['allowed'] = self.process_owner_section_or_file(jeez)

        # Only get secrets that belong to that owner/repo, so malicious user
        # cannot get things they should not.
        if 'secrets' in cfg:
            # Do not pass input from cfg to kubectl_get or this could get
            # exploited.
            all_secrets_for_repo = self.utils.kubectl_get(
                "secret",
                output_type="yaml",
                labels={
                    "tekton/asa-code-repository-name":
                    owner_repo.split("/")[1],
                    "tekton/asa-code-repository-owner":
                    owner_repo.split("/")[0]
                })
            for secret in cfg['secrets']:
                for allsecretin in all_secrets_for_repo['items']:
                    secretname = allsecretin['metadata']['name']
                    if secretname == secret:
                        processed['templates'][
                            f"{secretname}.secret.yaml"] = yaml.safe_dump(
                                allsecretin)

        # TODO: i don't like this, i probably goign to remove it
        # we just need this temporary because of the operator and
        # pipelines-catalog are not in synchronize.
        processed['prerun'] = []
        if 'prerun' in cfg:
            processed['prerun'] = cfg['prerun']

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
                self.process_all_yaml_in_dir(jeez,
                                             parameters_extras)['templates'])
        return processed

    def process_all_yaml_in_dir(self, jeez, parameters_extras):
        """Process directory directly, not caring about stuff just getting every
        yaml files in there"""
        processed = {'templates': {}}
        processed['allowed'] = self.process_owner_section_or_file(jeez)

        for filename in os.listdir(
                os.path.join(self.checked_repo, config.TEKTON_ASA_CODE_DIR)):
            if filename.split(".")[-1] not in ["yaml", "yml"]:
                continue
            if filename == "tekton.yaml":
                continue
            filename = os.path.join(self.checked_repo,
                                    config.TEKTON_ASA_CODE_DIR, filename)
            ret = self.utils.kapply(filename, jeez, parameters_extras)
            processed['templates'][ret[0]] = ret[1]

        return processed

    def mouline_this(self, templates: Dict[str, str]):  # pylint: disable=no-self-use
        """Takes the templates"""
        bundled = []
        print("🍝 Files bundled: ")
        for template in templates:
            if template.startswith("https://"):
                local_path = os.path.join(config.REPOSITORY_DIR,
                                          config.TEKTON_ASA_CODE_DIR,
                                          os.path.basename(template))
                open(local_path, 'w').write(templates[template])
                bundled.append(local_path)
                print(" • " +
                      template.replace(config.GITHUB_RAW_URL + "/", ""))
            else:
                print(" • " +
                      template.replace(config.REPOSITORY_DIR + "/", ""))
                bundled.append(template)
        bundled = tektonbundle.parse(bundled, parameters=[], skip_inlining=[])
        thebundle = f"--- \n{bundled['bundle']}--- \n"
        thebundle += "--- \n".join(bundled['ignored_not_k8'] +
                                   bundled['ignored_not_tekton'])
        return {'bundled-file.yaml': thebundle}

    def process_tekton_dir(self, jeez, parameters_extras):
        """Apply templates according, check first for tekton.yaml and then
        process all yaml files in directory"""
        ret = {}

        if os.path.exists(
                f"{self.checked_repo}/{config.TEKTON_ASA_CODE_DIR}/tekton.yaml"
        ):
            processed_yaml_ini = self.process_yaml_ini(
                f"{self.checked_repo}/{config.TEKTON_ASA_CODE_DIR}/tekton.yaml",
                jeez, parameters_extras)
            if processed_yaml_ini:
                ret = processed_yaml_ini
        else:
            ret = self.process_all_yaml_in_dir(jeez, parameters_extras)

        if self.moulinette and ret['templates']:
            ret['templates'] = self.mouline_this(ret['templates'])

        return ret
