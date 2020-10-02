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

- The second task that follows will launch the tekton-as-a-code main task.

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
https://github.com/apps/my-app-tekton-as-a-code and installs it for her code
repository. Tekton as a code should run right after creating a new PR.

If the user submits a PR and tekton as a code has been restricted to only runs
PR from a user from an organization which the user is not part of. A user of the
organization can add the line `/tekton ok-to-test` in a comment of the PR and
this will allows it. You can add other lines after or before, you just need one
exact line matching the `/tekton ok-to-test` directive, i.e:

```
/tekton ok-to-test

Thanks for submitting 👍🏼
```

**TODO**: Tekton as a code doesn't currently listen to comment events from
github so after running the `/tekton ok-to-test`, the user needs to submit a new
iteration of the PR to *rekick* the PR check.

### Configuration

There is a limited configuration interaction directive at this time but if you
create a ConfigMap called `tekton-asa-code`, 

With the `restrict_organization` key you are able to restrict the execution of
tekton as a code if the submitted of the pull_request belong to that
organization. For example if you want to restrict the pipelines execution to the
`myorg` organization you create configmap with the key
`restrict_organization` and the value of the organization, this would look like
this from the command line :

```sh
kubectl create configmap tekton-asa-code --from-literal=restrict_organization=myorg
```

and tekton as a code will restrict the execution of the pipeline to the users
that are part of this organization.

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

## IDEAS

* move install.map over a yaml file, which looks less weird than install.map
