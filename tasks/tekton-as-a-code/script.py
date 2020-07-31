#!/usr/bin/env python3
"""Main script for tekton as a code"""
import http.client
import io
import json
import os
import random
import re
import string
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse

GITHUB_HOST_URL = "api.github.com"
GITHUB_TOKEN = os.environ["GITHUBTOKEN"]


class CouldNotFindConfigKeyException(Exception):
    """Raise an exception when we cannot find the key string in json"""
    pass


def execute(command, check_error=""):
    """Execute commmand"""
    try:
        result = subprocess.run(['/bin/sh', '-c', command],
                                stdout=subprocess.PIPE,
                                check=True)
    except subprocess.CalledProcessError as exception:
        print(check_error)
        raise exception
    return result


# https://stackoverflow.com/a/18422264
def stream(command, filename, check_error=""):
    """Stream command"""
    with io.open(filename, 'wb') as writer, io.open(filename, 'rb',
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


def gh_request(method, url, body=None):
    """Execute a request to the GitHUB API, handling redirect"""
    url_parsed = urllib.parse.urlparse(url)
    body = body and json.dumps(body)
    conn = http.client.HTTPSConnection(url_parsed.hostname)
    conn.request(method,
                 url_parsed.path,
                 body=body,
                 headers={
                     "User-Agent": "TektonCD, the peaceful cat",
                     "Authorization": "Bearer " + GITHUB_TOKEN,
                 })
    response = conn.getresponse()
    if response.status == 301:
        return gh_request(method, response.headers["Location"])
    return response


def get_key(key, jeez):
    """Get key as a string like foo.bar.blah in dict => [foo][bar][blah] """
    curr = jeez
    for k in key.split("."):
        if k not in curr:
            raise CouldNotFindConfigKeyException(
                f"Could not find key {key} in json while parsing file")
        curr = curr[k]
    if not isinstance(curr, str):
        curr = str(curr)
    return curr


def kapply(yaml_file, jeez, namespace):
    """Apply kubernetes yaml template in a namespace with simple transformations
    from a dict"""

    print(f"Processing {yaml_file} in {namespace}")
    tmpfile = tempfile.NamedTemporaryFile(delete=False).name
    open(tmpfile, 'w').write(
        re.sub(r"\{\{([_a-zA-Z0-9\.]*)\}\}",
               lambda m: get_key(m.group(1), jeez),
               open(yaml_file).read()))
    execute(
        f"kubectl apply -f {tmpfile} -n {namespace}",
        "Cannot apply {tmpfile} in {namespace} with {string(transformations)}")
    os.remove(tmpfile)


def main():
    """main function"""
    checked_repo = "/tmp/repository"

    # # Testing
    # jeez = json.load(
    #     open(os.path.expanduser("~/tmp/tekton/apply-change-of-a-task/t.json")))
    jeez = json.loads("""$(params.github_json)""")
    api_url = f"https://{GITHUB_HOST_URL}/repos/{get_key('repository.full_name', jeez)}/issues/{get_key('number', jeez)}"
    if not os.path.exists(checked_repo):
        os.makedirs(checked_repo)
        os.chdir(checked_repo)

        exec_init = execute("git init")
        if exec_init.returncode != 0:
            print("Error creating a GitHUB repo in {checked_repo}")
            print(exec_init.stdout.decode())
            print(exec_init.stderr.decode())

    os.chdir(checked_repo)
    cmd = (
        f"git fetch https://{get_key('repository.owner.login', jeez)}:{GITHUB_TOKEN}"
        f"@{get_key('repository.html_url', jeez).replace('https://', '')} {get_key('pull_request.head.ref', jeez)}"
    )
    execute(
        cmd, "Error checking out the GitHUB repo %s to the branch %s" %
        (get_key('repository.html_url',
                 jeez), get_key('pull_request.head.ref', jeez)))

    execute("git checkout -qf FETCH_HEAD;",
            "Error resetting git repository to FETCH_HEAD")

    random_str = ''.join(
        random.choices(string.ascii_letters + string.digits, k=4)).lower()
    namespace = f"pull-{get_key('number', jeez)[:4]}-{random_str}"
    execute(f"kubectl create ns {namespace}",
            "Cannot create a temporary namespace")
    print(f"Namespace {namespace} has been created")

    if os.path.exists(f"{checked_repo}/tekton/install.map"):
        for line in open(f"{checked_repo}/tekton/install.map"):
            line = line.strip()
            if line.startswith("#"):
                continue
            if line.startswith("https://"):
                url_retrieved, _ = urllib.request.urlretrieve(line)
                kapply(url_retrieved, jeez, namespace)
            elif os.path.exists(f"{checked_repo}/tekton/{line}"):
                kapply(f"{checked_repo}/tekton/{line}", jeez, namespace)
            else:
                print(
                    "The file {line} specified in install.map is not found in tekton repository"
                )
    else:
        for filename in os.listdir(os.path.join(checked_repo, "tekton")):
            if not filename.endswith(".yaml"):
                continue
            kapply(filename, jeez, namespace)

    time.sleep(2)

    output_file = tempfile.NamedTemporaryFile(delete=False).name
    stream(f"tkn pr logs -n {namespace} --follow --last", output_file,
           f"Cannot show Pipelinerun log in {namespace}")
    output = open(output_file).read()

    # TODO: Need a better way!
    describe_output = execute(
        f"tkn pr describe -n {namespace} --last").stdout.decode()
    regexp = re.compile(r"^STARTED\s*DURATION\s*STATUS\n(.*)$", re.MULTILINE)
    status = regexp.findall(describe_output)[0].split(" ")[-1]
    print(describe_output)

    json.loads(
        gh_request(
            "POST",
            f"{api_url}/comments",
            body={
                "body":
                f"""CI has **{status}**

<details>
<summary>PipelineRun Output</summary>

```
{output}
```
</details>

<details>
<summary>PipelineRun status</summary>

```
{describe_output}
```
</details>



"""
            },
        ).read())

    execute(f"kubectl delete ns {namespace}",
            "Cannot delete temporary namespace {namespace}")

    if status == "Failed":
        sys.exit(1)


if __name__ == '__main__':
    main()
