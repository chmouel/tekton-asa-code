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
import io
import json
import re
import subprocess
import sys
import time


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
                                    check=True)
        except subprocess.CalledProcessError as exception:
            if check_error:
                raise exception
        return result

    def get_config(self):
        """Try to grab the config for tekton-asa-code and parse it as dict"""
        output = self.execute(
            "kubectl get configmaps tekton-asa-code -o json 2>/dev/null", )
        if output.returncode != 0:
            return {}
        return json.loads(output.stdout.decode())["data"]

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
                                                        1) as reader:
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
            ret += f" * <code>{i}</code>\n"

        if not ret:
            return ""
        return f"""
    Errors detected :

    {ret}

    """

    def kapply(self, yaml_file, jeez, parameters_extras, name=None):
        """Apply kubernetes yaml template in a namespace with simple transformations
        from a dict"""
        def tpl_apply(param):
            if param in parameters_extras:
                return parameters_extras[param]

            if self.get_key(param, jeez, error=False):
                return self.get_key(param, jeez)

            return "{{%s}}" % (param)

        if not name:
            name = yaml_file
        content = re.sub(
            r"\{\{([_a-zA-Z0-9\.]*)\}\}",
            lambda m: tpl_apply(m.group(1)),
            open(yaml_file).read(),
        )
        return (name, content)
