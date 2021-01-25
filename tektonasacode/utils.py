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
"""Dropzone of stuff"""
import datetime
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

import yaml


# pylint: disable=unnecessary-pass
class CouldNotFindConfigKeyException(Exception):
    """Raise an exception when we cannot find the key string in json"""

    pass


class Utils:
    """Tools for running tekton as a code"""
    @staticmethod
    def execute(command, check_error=""):
        """Execute commmand"""
        result = ""
        try:
            result = subprocess.run(["/bin/sh", "-c", command],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    check=True)
        except subprocess.CalledProcessError as exception:
            if check_error:
                print(check_error)
                print(
                    f"Status code: {exception.returncode}: Output: \n{exception.output}"
                )
                raise exception
        return result

    @staticmethod
    def process_pipelineresult(jeez):
        """Take a pipelinerun and output nicely which task fails from that
        pieplinerun"""
        ret = []
        pname = jeez['metadata']['name']
        if 'taskRuns' not in jeez['status']:
            return [
                f"• <i>{cond['message']}</i>"
                for cond in jeez['status']['conditions']
            ]
        for task in jeez['status']['taskRuns']:
            result = jeez['status']['taskRuns'][task]['status']
            elapsed = "N/A"
            if 'completionTime' in result and 'startTime' in result:
                elapsed = str(
                    datetime.datetime.strptime(result['completionTime'],
                                               '%Y-%m-%dT%H:%M:%SZ') -
                    datetime.datetime.strptime(result['startTime'],
                                               '%Y-%m-%dT%H:%M:%SZ'))
            emoji = "✅"
            for condition in result['conditions']:
                if condition['status'] != 'True':
                    emoji = "❌"

            bname = task.replace(pname + '-', '')
            bname = bname.replace("-" + bname.split("-")[-1], '')
            ret.append(f"{emoji} {elapsed} {bname}")
        return ret

    def kubectl_get(self,
                    obj: str,
                    output_type: str = "yaml",
                    raw: bool = False,
                    namespace: str = "",
                    labels: Optional[dict] = None) -> Dict:
        """Get an object"""
        output_str = ''
        label_str = ''
        ret = ''
        if labels:
            label_str = " ".join(
                [f"-l {label}={labels[label]}" for label in labels])
        if output_type:
            output_str = f"-o {output_type}"
        namespace_str = f"-n {namespace}" if namespace else ""
        _out = self.execute(
            f"kubectl get {namespace_str} {obj} {output_str} {label_str}",
            check_error=f"Cannot run kubectl get {obj} {output_str} {label_str}"
        )
        if _out.returncode != 0:
            return {}
        out = _out.stdout.decode()
        if raw or not output_type:
            return out
        if output_type == "yaml":
            ret = yaml.safe_load(out)
        if output_type == "json":
            ret = json.loads(out)

        # Cleanup namespaces from all
        for index in range(0, len(ret['items'])):
            if 'metadata' in ret['items'][index] and 'namespace' in ret[
                    'items'][index]['metadata']:
                del ret['items'][index]['metadata']['namespace']
        return ret

    @staticmethod
    def retrieve_url(url):
        """Retrieve an URL"""
        try:
            url_retrieved, _ = urllib.request.urlretrieve(url)
        except urllib.error.HTTPError as http_error:
            msg = f"Cannot retrieve remote task {url} as specified in install.map: {http_error}"
            print(msg)
            raise http_error
        return url_retrieved

    def get_openshift_console_url(self, namespace: str) -> str:
        """Get the openshift console url for a namespace"""
        openshift_console_url = self.execute(
            "kubectl get route -n openshift-console console -o jsonpath='{.spec.host}'",
            check_error="cannot openshift-console route",
        )
        return f"https://{openshift_console_url.stdout.decode()}/k8s/ns/{namespace}/tekton.dev~v1beta1~PipelineRun/" \
            if openshift_console_url.returncode == 0 else ""

    # https://stackoverflow.com/a/18422264
    @staticmethod
    def stream(command, filename, check_error=""):
        """Stream command"""
        with io.open(filename, "wb") as writer, io.open(filename, "rb",
                                                        0) as reader:
            try:
                process = subprocess.Popen(command.split(" "), stdout=writer)
            except subprocess.CalledProcessError as exception:
                print(check_error)
                raise exception

            while process.poll() is None:
                sys.stdout.write(reader.read().decode())
                time.sleep(0.5)
            # Read the remaining
            sys.stdout.write(reader.read().decode())

    @staticmethod
    def get_key(key, jeez, error=True):
        """Get key as a string like foo.bar.blah in dict => [foo][bar][blah] """
        curr = jeez
        for k in key.split("."):
            if k not in curr:
                if error:
                    raise CouldNotFindConfigKeyException(
                        f"Could not find key {key} in json while parsing file")
                return ""
            curr = curr[k]
        if not isinstance(curr, str):
            curr = str(curr)
        return curr

    @staticmethod
    def get_errors(text):
        """ Get all errors coming from """
        errorstrings = r"(error|fail(ed)?)"
        errorre = re.compile("^(.*%s.*)$" % (errorstrings),
                             re.IGNORECASE | re.MULTILINE)
        ret = ""
        for i in errorre.findall(text):
            i = re.sub(errorstrings, r"**\1**", i[0], flags=re.IGNORECASE)
            ret += f" * *{i}*\n"

        if not ret:
            return ""
        return f"""
    <details>
        <summary>Errors detected</summary>
        <pre>{ret}</pre>
    </details>
    """

    def kapply(self, yaml_string_or_file, jeez, parameters_extras, name=None):
        """Apply kubernetes yaml template in a namespace with simple transformations
        from a dict"""
        if os.path.exists(yaml_string_or_file):
            yaml_string = open(yaml_string_or_file, 'r').read()
        elif isinstance(yaml_string_or_file, str):
            yaml_string = yaml_string_or_file
        else:
            return ("", "")

        def tpl_apply(param):
            if param in parameters_extras:
                return parameters_extras[param]
            if self.get_key(param, jeez, error=False):
                return self.get_key(param, jeez)

            return "{{%s}}" % (param)

        if os.path.exists(yaml_string_or_file) and not name:
            name = yaml_string_or_file

        content = re.sub(
            r"\{\{([_a-zA-Z0-9\.]*)\}\}",
            lambda m: tpl_apply(m.group(1)),
            yaml_string,
        )
        return (name, content)
