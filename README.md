## Flow

<img src="https://raw.githubusercontent.com/chmouel/tekton-asa-code/master/doc/flow.png" alt="alt text" width="75%" height="75%">


## INSTALL

Use the `deploy.sh` script.

The only thing really to configure is the PUBLIC_ROUTE_HOSTNAME as environement variable, this is your public route as exposed for the router.
Have your GITHUB_SECRET set, you can set this up in your .gitconfig in `github.oauth-token` or via an env variable

After you run successfully the deploy.sh, you point your github webhook from your repository you want tested to the `PUBLIC_ROUTE_HOSTNAME`
and you should be good to go.

## USAGE

Just add your yaml files in the tekton directory, you can *optionally* specify a install.map files which can list the order you want to apply those yaml files. If you don't use a install.map you will need to make sure to order the files via the filesystem alphebaitcally or numerically i.e:

* 1-git-clone-task.yaml
* 2-pylint.yaml
* 3-pipeline.yaml
* 4-run.yaml

The install.map has extra features, you can add this line :

`catalog://official/git-clone:0.1`

which would say, install the git-clone task version 0.1 from the official catalog, it would then be expanded to :

https://raw.githubusercontent.com/tektoncd/catalog/master/task/git-clone/0.1/git-clone.yaml

When there is a new PR, tekton-as-code will create new namespaces and apply all the object in there, and try to get the latest pipelinerun ran in that new namespace and exposes it into the github PR as comment,

It will shows you a link to the openshift console url to follow the PR if that's available

It wil let you know if it has succeedd or not, and if there is failure it will try to detect those errors (basically grepping for ERROR|FAILS int he logs) and show them to you nicely.

## ISSUES

* cluster-admin permission, we are creating a new namespace everytime and needs to some pipeline/task and other stuff in there, we are currently using cluster-admin for simplicity but hopefully we have ideas to leverage the operator code to apply automatically the right rights the same way we do with the `pipeline` serviceaccount.
* if tekton-as-run python script has failure it doesn't report back properly.

## IDEAS

* move install.map over a yaml file, which looks less weird than install.map
* post results into task for reuse.
* breaks that big python script to reusable small tasks that chains together with results (which we would then have some overheard of the containers creation)
* have the install.map being able to have some sort of project_type which would add all the pipeline itself, for example if we have :
  `project_type=golang`
  It will add a pipeline that would test golangs with no user having to add their own.
