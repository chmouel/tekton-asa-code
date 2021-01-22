[![Container Repository on Quay](https://quay.io/repository/chmouel/tekton-asa-code/status "Container Repository on Quay")](https://quay.io/repository/chmouel/tekton-asa-code)

# Tekton as a Code

A PR based flow for Tekton.

## Flow

<img
src="https://raw.githubusercontent.com/chmouel/tekton-asa-code/master/doc/flow.png"
alt="alt text" width="75%" height="75%">


## Description

`Tekton as a code` allows user to do iterative development over a pull request
before code is merged by having a `.tekton` directory in the code repository.

### Example

1. User has source code that needs to be tested according to a set of
   different checks (i.e: golint/pylint/yamllint etc..)
2. User adds a `.tekton` directory with a pipeline referencing the checks.
3. User submits a PR.
4. Tekton as a code picks it up and apply the content of the `.tekton` directory.
5. Tekton as a code posts the results and set the status back on the PR.

### Details

Tekton as a code expect to be run from a GitHub application.

When the user installs the GitHub application in a code repository, every time a PR
gets created or updated, it will post a webhook notification to the tekton trigger
event listener that will launch a tekton as a code pipeline.

The tekton as a code pipeline has 2 tasks:
- the first one is to retrieve a user token with the github app private key via the [github-app-token
task](https://github.com/tektoncd/catalog/blob/master/task/github-app-token/0.1/)
to be able to do operation on the behalf of the user.

- The second task that follows will launch the tekton-asa-code main task.

The main task is a python script that acts as a shim between the webhook input
and posting back the results, it will perform the following actions :

1. Parse the webhook json input.
2. Create a [GitHub check
   run](https://docs.github.com/en/free-pro-team@latest/rest/reference/checks)
   to set the PR as "in progress".
3. Check out the GitHUB repository to the head SHA of the PR.
4. Create a temporary namespace.
5. Apply the content of the `.tekton` directory in the temporary namespace.
6. Get the logs of the latest pipeline run in the temporary namespace
   and stream it.
7. Detect if the run has been successfull or not and then postback to
   the GitHub PR.

Moreover in step `5` when `Tekton as a code` applies the content of the `.tekton` directory
it detects if there is tags inside which looks like this `{{revision}}` or
like this `{{repo_url}}` and parse it with the value that we have from the
webhook json. It is possible in fact to access anything that came from the
webhook json, for example to something like this :

`{{pull_request.number}}`

to which it will get expanded to the pull_request number, there is a lot of
fields you can access on the webhook json pull request (among others), see the
details here :
[here](https://docs.github.com/en/free-pro-team@latest/rest/reference/pulls).

By default tekton as a code apply every yaml files it finds in the `.tekton`
directory. But you need to make sure to have the `PipelineRun` applied after the
`Pipeline` or the `PipelineRun` will try to get launched by the tekton
controller and fails.

There is a few ways to go around this :

- Organize your files alphabetically or numerically, ie :

```
.tekton/1-pipeline.yaml
.tekton/2-run.yaml
```

- Have the run and the pipeline in the same file making sure the pipeline is
  before the run.

- Embed your run as `pipelineSpec`

- Specify the ordering in the `.tekton/tekton.yaml` files section

## Configuration (tekton.yaml)

if tekton-asa-code fine a file called `tekton.yaml` in your `.tekton` root
directory it will optionally parse it to do extra stuff.

- If you add a section called files you can specify the ordering of how the file will be applied :

```yaml
files:
 - pipeline.yaml
 - run.yaml
```

- You can have a tasks section to be able to apply remote tasks or directly from
  the catalog, for example if you have this :

```yaml
tasks:
    - git-clone
    - buildah:0.1
    - https://raw.github.com/repos/org/repo/master/template.yaml
```

It will install the git-clone task version 0.1 from https://github.com/tektoncd/catalog.

It will discover the latest version of buildah from https://github.com/tektoncd/catalog and applies it.

It will directly install the URL (this do not have to be a task it can be any remote URL).

## OWNERSHIP

- By default all pull request are denied unless the repo owner is submitting
  them or explictely allowed.
- tekton-asa-code will try to find a `OWNERS` file at the root of the `.tekton`
  directory **in the main branch (i.e: master) not in the submitted PR**.
- If the user who submitted the PR is in that file it will be allowed.
- If there is a line starting with `@` (ie: `@google`) it will query the github
  organisation membership of the user who submitted the PR and allows it if the
  user is part of that organisation.
- Same configuration can be applied directly in `tekton.yaml` configuration
  files under the `owners` sections, i.e:

  ```yaml
  owners:
      - @tektoncd
      - other_user_outside_of_tektoncd_github_org
  ```

## Moulinette (bundle all tekton files in a single `PipelineRun`)

tekton-asa-code has support for `moulinette`, which mean when we see a bunch of
files in the `.tekton` repo we concatenate together to make one single
pipelinerun with taskSpec and PipelineRef to make it unique and ensure that we
don't have any conflicts when running in a single namespace (NIP yet).

It is (currently) disabled by default and can be only enabled if you specify the directive :

```yaml
bundled: true
```

In your `tekton.yaml` file.

## SECRETS

You can reference a secret in your `tekton.yaml` :

```yaml
secrets:
  - secret-name
```

The secret needs to be created inside the main `tekton-asa-code` namespace, it
should have two label on it :

1. `tekton/asa-code-repository-owner` - The repository owner (i.e: `owner`)
2. `tekton/asa-code-repository-name` - The repository name (i.e: `repo`)

For example if you want to create a secret called `owner-repo-secret-1` for the
repository `owner/repo` you first create a secret like this :

```
kubectl create secret generic owner-repo-secret-1 --from-literal="token=TOKEN_PASSWORD"
```

and you asing the labels with this :

```
 kubectl label secret owner-repo-secret-1 tekton/asa-code-repository-owner="owner" tekton/asa-code-repository-name="repo"
```

You point it out in your `tekton.yaml` file and when the CI is launched the
secret would be automatically imported in the temporary namespace, which then
you can reference in your pipeline.


## INSTALL

### Create a GitHub application

Follow this Guide :

https://docs.github.com/en/free-pro-team@latest/developers/apps/creating-a-github-app

- set the webhook URL to the `PUBLIC_ROUTE_HOSTNAME` as set below in the
[deploy.sh](./deploy.sh) script
- allow read and write on  Checks on code.
- In repository permissions, allow read and write on "Checks"
- In repository permissions, allow read and write on "Pull request"
- In repository permissions, allow read and write on "Issues"
- In organization permissions, allow read on "Members"
- In Subscribe to events  checks "Pull Requests".
- In Subscribe to events  checks "Pull Requests review".

After creating the GitHub application you should get your `GITHUB_APP_ID` and
your `GITHUB_APP_PRIVATE_KEY` and proceed to the deployment onto your cluster.

Use the `deploy.sh` script.

There is two environment variables that you need to set before running this
script :

`GITHUB_APP_ID` - your GitHub application ID
`GITHUB_APP_PRIVATE_KEY` - The path to your Github application private key.
`PUBLIC_ROUTE_HOSTNAME` - This is your public route as published by the ingress
                          controller or OpenShift route.

You need to make sure to configure your GitHUB app to point the webhook URL to
the `PUBLIC_ROUTE_HOSTNAME`

You then run the `./deploy.sh` script and it will take care to creates
everything. It will generate a webhook password as well and it will print at the
end of the deployment, make sure you fill this up in the Github application
webhook secret field.

### Usage

The user goes to your application ie:
https://github.com/apps/my-app-tekton-asa-code and installs it for her code
repository. Tekton as a code should run right after creating a new PR.

If the user submits a PR and tekton as a code has been restricted to only runs
PR from a user from an organization which the user is not part of. 

If the user send the comment `/retest` on PR it will retest the PR.

### Troubleshooting

Usually you would first inspect the trigger's eventlistener pod to see if the GitHub
webhook has came thru.

List the **Pipelineruns** in the `tekton-asa-code` namespace to see if pipelinerun has
created.

`tkn describe` and `tkn logs` them to investigate why they haven't run and not reported on the
GitHub Pull request.

If you get an error message looking like this :

`,"msg":"payload signature check failed"`

in the event listener pod, it means your github secret hasn't been set properly.

There is a small shell script in this repo
[`./misc/tkaac-status`](`./misc/tkaac-status`) that helps you keep an overview
of all the pull requests, it's a bit like `tkn ls` output but with the pull
request that it targets and looping over to catch the new stuff.

A demo here :

[![Tekton aac status](https://asciinema.org/a/UtYEMplIgE4QaIkTGWV6oYLhg.svg)](https://asciinema.org/a/UtYEMplIgE4QaIkTGWV6oYLhg)

## Slack notificaitons

You can easily add a slack notifcation to notify if your pipeline has failed or
run sucessfully. There is a script in
[misc/send-slack-notifications.py](misc/send-slack-notifications.py) that can
help you with that with the help of the [finally
tasks](https://github.com/tektoncd/pipeline/blob/master/docs/pipelines.md#adding-finally-to-the-pipeline)
in your pipeline.

At the end of your pipeline add this block :

```yaml
  finally:
    - name: finally
      taskSpec:
        steps:
          - name: send-to-slack
            env:
              - name: SLACK_WEBHOOK_URL
                valueFrom:
                  secretKeyRef:
                    name: chmouel-scratchpad-slack-webhook
                    key: hook_url
              - name: PIPELINERUN
                valueFrom:
                  fieldRef:
                    fieldPath: metadata.labels['tekton.dev/pipelineRun']
              - name: GITHUB_PULL_LABEL
                value: "{{pull_request.labels}}"
              - name: LABEL_TO_CHECK
                value: "slacked"
              - name: SUCCESS_URL_ICON
                value: "https://github.com/tektoncd.png"
              - name: FAILURE_URL_ICON
                value: "https://www.vhv.rs/dpng/d/415-4154815_grumpy-cat-png-photos-grumpy-cat-png-transparent.png"
              - name: SUCCESS_SUBJECT
                value: "That's wonderful the pipeline foo has run successfully. :joy:"
              - name: FAILURE_SUBJECT
                value: "There was some failures while running pipeline :crying:"
              - name: LOG_URL
                value: "{{openshift_console_pipelinerun_href}}"
            image: quay.io/chmouel/tekton-asa-code:latest
            command: ["/code/misc/send-slack-notifications.py"]
```

The `SLACK_WEBHOOK_URL` secret is a secret you have configured in your
`tekton.yaml` as documented earlier. It would have the webhook url where to send
your notifications. (never commit your webhook url to a public repo).

You can have a label to check where you can say only run the notifications when
this label is on the PR. The argument between the "{{ }}" are coming directly
from tekton-asa-code so usually you want to leave them be here.

## Examples

Tekton as a code test itself, you can get the example of the pipeline it test
from [here](https://github.com/chmouel/tekton-asa-code/tree/master/.tekton).

An example of a PR, this shows a failure issue and then a success :

https://github.com/chmouel/tekton-asa-code/pull/30

## TODO

* This is very much GitHub oriented at the moment, but having another VCS
  supported should not be an issue (altho this would need some refactoring).
* Breaks that big python script to reusable small tasks that chains together
* Or at least breaks the python script to some proper python object based files
  and add unit/functions tests and all.

### Limitations

* Only one pipeline for one repo can be run.

## ISSUES

* cluster-admin permission, we are creating a new namespace every time and needs
  to some pipeline/task and other stuff in there, we are currently using
  cluster-admin for simplicity but hopefully we have ideas to leverage the
  operator code to apply automatically the right rights the same way we do with
  the `pipeline` serviceaccount.
