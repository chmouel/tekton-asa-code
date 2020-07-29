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
TEKTON_YAML_REGEXP = re.compile(r"tekton/.*\.y(a?)ml")
GITHUB_TOKEN = os.environ["GITHUBTOKEN"]

PR_JSON_KEYS = [
    "pull_request_revision",
    "pull_request_repo_url",
]


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


def parse_pr_results(jeez):
    """Parse the Json results of """
    return {
        "repo_full_name": jeez["repository"]["full_name"],
        "repo_owner_login": jeez["repository"]["owner"]["login"],
        "repo_html_url": jeez["repository"]["html_url"],
        "pull_request_head_sha": jeez["pull_request"]["head"]["sha"],
        "pull_request_head_ref": jeez["pull_request"]["head"]["ref"],
        "pull_request_number": str(jeez["number"]),
    }


def kapply(yaml_file, transformations, namespace):
    """Apply kubernetes yaml template in a namespace with simple transformations
    from a dict"""
    class MyTemplate(string.Template):
        """Custom template"""
        delimiter = '{{'
        pattern = r'''
        \{\{(?:
        (?P<escaped>\{\{)|
        (?P<named>[_a-z][_a-z0-9]*)\}\}|
        (?P<braced>[_a-z][_a-z0-9]*)\}\}|
        (?P<invalid>)
        )
        '''

    print(f"Processing {yaml_file} in {namespace}")
    yaml_template = MyTemplate(open(yaml_file).read())
    tmpfile = tempfile.NamedTemporaryFile(delete=False).name
    open(tmpfile, 'w').write(yaml_template.safe_substitute(transformations))
    execute(
        f"kubectl apply -f {tmpfile} -n {namespace}",
        "Cannot apply {tmpfile} in {namespace} with {string(transformations)}")
    os.remove(tmpfile)


def main():
    """main function"""
    checked_repo = "/tmp/checkedrepository"

    # Testing
    # pull_request_json = json.load(open("t.json"))
    pull_request_json = json.loads("""$(params.github_json)""")
    prdico = parse_pr_results(pull_request_json)
    api_url = f"https://{GITHUB_HOST_URL}/repos/{prdico['repo_full_name']}/issues/{prdico['pull_request_number']}"

    # TODO: Need to think if that's needed
    # has_tekton_files = False
    # files_of_pull_request_json = json.loads(
    #     gh_request("GET", f"{api_url}/files").read())
    # for pr_file in files_of_pull_request_json:
    #     if TEKTON_YAML_REGEXP.match(pr_file["filename"]):
    #         has_tekton_files = True
    #         break

    # if not has_tekton_files:
    #     print("Could not find any tekton file, aborting")
    #     return

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
        f"git fetch https://{prdico['repo_owner_login']}:{GITHUB_TOKEN}"
        f"@{prdico['repo_html_url'].replace('https://', '')} {prdico['pull_request_head_ref']}"
    )
    execute(
        cmd, "Error checking out the GitHUB repo %s to the branch %s" %
        (prdico['repo_html_url'], prdico['pull_request_head_ref']))

    execute("git checkout -qf FETCH_HEAD;",
            "Error resetting git repository to FETCH_HEAD")

    random_str = ''.join(
        random.choices(string.ascii_letters + string.digits, k=4)).lower()
    namespace = f"pull-{prdico['pull_request_number'][:4]}-{random_str}"
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
                kapply(url_retrieved, prdico, namespace)
            elif os.path.exists(f"{checked_repo}/tekton/{line}"):
                kapply(f"{checked_repo}/tekton/{line}", prdico, namespace)
            else:
                print(
                    "The file {line} specified in install.map is not found in tekton repository"
                )
                # TODO: shoudl we exit?

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

    if status == "Failed":
        sys.exit(1)


if __name__ == '__main__':
    main()
