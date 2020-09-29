# Tekton as a Code

A PR based flow for Tekton.

## Flow

<img
src="https://raw.githubusercontent.com/chmouel/tekton-asa-code/master/doc/flow.png"
alt="alt text" width="75%" height="75%">


## Description

`Tekton as a code` is a project to let the user have a repository called
`.tekton` in her code repository and have tekton using it while doing iterative
devlopement over a pull request before code is merged.

### Example

1. Users have a source code that needs to be tested according to a set of
   different checks (i.e: golint/pylint/yamllint etc..)
2. User add a `.tekton` directory with a pipeline referencing the checks.
3. User submit a PR.
4. Tekton as a code picks it up and apply the content of the `.tekton` directory.
5. Tekton as a code post the results and set the status back on the PR.

### Details

Tekton as a code expect to be run from a GitHub application.

When the user install the GitHub application on her repository, every time a PR
get created or updated it will post a webhook notification to the tekton trigger
event listenner to launch a tekton as a code pipeline.

The tekton as a code pipeline has two tasks, the first one is to retrieve a user
token with the github app private key via the [github-app-token
task](https://github.com/tektoncd/catalog/blob/master/task/github-app-token/0.1/)
to be able to do operation on the behalf of the user.

The second task that follows will launch the tekton-as-a-code main task.

The main task is a python script that act as a shim between the webhook input
and posting back the results, it will performs the following actions :

1. Parse the webhook json input.
2. Create a [GitHub check
   run](https://docs.github.com/en/free-pro-team@latest/rest/reference/checks)
   to set the PR as "in progress".
3. It will check out the GitHUB repository to the head SHA of the PR.
4. It will create a temporary namespace.
5. It will apply the content of the `.tekton` directory in the temporary namespace.
6. It will get the logs of the latest pipeline run in the temporary namespace
   and stream it.
7. It will detect if the run has been successfull or not and then postback to
   the GitHub PR.

Moreover in step `5` when we apply the content of the `.tekton` directory it
will detect if there is tags inside which looks like this `{{revision}}` or
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

- Create a `.tekton/install.map`, if this file exist you can just list your
  templates in order , ie:

```
pipeline.yaml
run.yaml
```

 and it will applies it in order.

**Note: This may get changed in the future**

 There is another syntax *niceties* in the install.map you can do, you can have
 this kind of syntax in there :
``
catalog://official:git-clone:latest
``

and this will grab the latest git-clone task from the official tekton [catalog
](https://github.com/tektoncd/catalog/) and applies it, you can as well specify
a specific version in it.

```
catalog://official:yaml-lint:0.1
```

## INSTALL

Use the `deploy.sh` script.

There is two environment variables that you need to set before running this
script :

`GITHUB_APP_ID` - your GitHub application ID
`GITHUB_APP_PRIVATE_KEY` - The path to your Github applicaiton private key.
`PUBLIC_ROUTE_HOSTNAME` - This is your public route as published by the ingress controler or OpenShift route.

You need to make sure to configure your GitHUB app to point the webhook URL to the `PUBLIC_ROUTE_HOSTNAME`

You then run the `./deploy.sh` script and it will take care to creates everything.

The user goes to your application ie:
https://github.com/apps/my-app-tekton-as-a-code and installs it for her code
repository. Tekton as a code should run right after creating a new PR.


### Examples

Tekton as a cde test itself, you can get the example of the pipeline it test
from [here](https://github.com/chmouel/tekton-asa-code/tree/master/.tekton).

### TODO

* This is very much GitHub oriented at the moment, but having another VCS
  supported should not be an issue (altho this would need some refactoring).

### Limitations

* Only one pipeline for one repo can be run.

## ISSUES

* cluster-admin permission, we are creating a new namespace everytime and needs
  to some pipeline/task and other stuff in there, we are currently using
  cluster-admin for simplicity but hopefully we have ideas to leverage the
  operator code to apply automatically the right rights the same way we do with
  the `pipeline` serviceaccount.

## IDEAS

* move install.map over a yaml file, which looks less weird than install.map
* breaks that big python script to reusable small tasks that chains together
* Or at least breaks the python script to some proper python object based files
  and add unit/functions tests and all.
