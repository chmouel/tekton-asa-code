# Tekton asa code flow

## Init

* Get user token from app token and installation_id

* Extract variables path from webhook payload : 

   - pull_request.base.repo.full_name
   - pull_request.head.sha
   - pull_request.number
   - pull_request.user.login
   - repository.full_name
   - repository.html_url
   - repository.owner.login  

* Create temporary namespace

* Set static parameters for easy substition in template : 

    - revision: pull_request.head.sha
    - repo_url: repo_html_url,
    - repo_owner: repo_owner_login,
    - namespace: current_namespace,
    - openshift_console_pipelinerun_href: console_pipelinerun_link,
    
* Create a check run - https://docs.github.com/en/developers/apps/creating-ci-tests-with-the-checks-api

* Checkout GIT repo on FileSystem for the pull_request_sha

    - Create dir
    - `git init`
    - `git remote add -f origin https://$repo_owner_login:$github.token@$repo_html_url`
    - `git fetch origin refs/pull/$pull_request_number/head`
    - `git reset --hard {pull_request_sha}`

* Check if there is a .tekton directory,
  - If not, set GitHUB check status as conclusion=neutral, skipping the PR


## Process .tekton directory

Start processing tekton directory templates

* If there is a .tekton/tekton.yaml files parse it : 

### Access control for running the CI

* if the owner of the repo is the submitted of the PR, always allows her to run the CI run.
* If the submmitter of the PR is in the contributors of the REPO always allow her to run the PR -- https://docs.github.com/en/rest/reference/repos#list-repository-contributors

* Grab the file from the `master_branch` (getting `master_branch` of the repo via GitHUB) :

 - Check if there is `allowed` key in tekton.yaml
 - if the submmitter user is in the allowed list allow her.
 - if the item start with a `@` followed by a string, assume that string is a
   GitHUB organisation and check if the submmitter user is part of this
   organisation and it she does then allow her to run the CI.

* If the user is not allowed then exit with setting strtus of the checks as denied.

### Prerun commands (TODO: to remove)

- if there is a `prerun` key in tekton.yaml run the command in the items before
  doing anything.
- This should be removed, since this could be a security issue.

### Tasks auto install

* Check if there is a `tasks` key in tekton.yaml and : 
  - If task start with *http* or *https* then grab it remotely
  - If task doesnt start with http/https :
    - if the name of the task finishes by a version number (i.e: *0.2*) grab that version from the tekton catalog repository.
    - if the name of the task finishes by **:latest**, grab the latest version of that task from the tekton catalog repository.

### Secrets

- Check if there is an `secret` key in tekton.yaml
- Check if there is a secret specified in the item in the main tekton asa code
  namespace with the same name and has the labels : 
  
      `tekton/asa-code-repository-name: $repository.name`
      `tekton/asa-code-repository-owner: $repository.owner_or_organisation`
      
  Apply that secret to the temporary namespace.
  
- This to avoid hijacking of other tekton.yaml repositories to make sure it
  only belongs to that `user/repository`.
  
- Installing secret is a pre-ci run step, where the admin would create those
  secrets with the right labels in the tekton-asa-code namespace.


#### Files in tekton directory

- If there is a `files` key in tekton.yaml, use this as the list of files to
  apply from the checked out repository.
  
- If there isn't `files` key, go in order in every files in the `.tekton` directory finishes by `yaml` or `yml` excluding the `tekton.yaml` file.

- Apply all files with the variable substitions, where user can specify the static parameters i.e: 

         {{revision}}
    
  To get the revision from Webhook payload
  
  Or access directly to a json key from the payload i.e: 
  
         {{repository.full_name}}
         
## Follow logs and set status

- When all templates are applied in the temporary namespace, we grab the last
  version of the pipelinerun from there and follow the logs with : 
  
  `tkn pr logs -n {namespace} --follow --last`
 
- Print it to the output of the current pipelinerun.
 
- Which mean we don't support multiple pipelineruns setup.

- Which mean we don't support tekton asa code with something else than pipeline.

- When pipeline is finished execute a :
 
  `tkn pr describe -n {namespace} --follow --last`
  
- Grab status of the task run in PR, to detect which one **succeeded** or which
  one has **failed** and the time it took to run.
  
- Set the github check run according to the status of the pipelinerun (success or failed). 

- Add a list of all the task status and how long it took to the github check.

- Add a link to the PipelineRun on openshift console.

- Exit the task accoding to the exit of the PR in the temporary namespace.
