#!/bin/bash
# Configure this to your own route
PUBLIC_ROUTE_HOSTNAME=${PUBLIC_ROUTE_HOSTNAME:-tektonic.apps.tekton.openshift.chmouel.com}
GITHUB_APP_PRIVATE_KEY=${GITHUB_APP_PRIVATE_KEY:-./tmp/github.app.key}
GITHUB_APP_ID=${GITHUB_APP_ID:-"81262"}

SERVICE=el-tekton-asa-code-listener-interceptor
TARGET_NAMESPACE=tekton-asa-code
SERVICE_ACCOUNT=tkn-aac-sa
OC_BIN=${OC_BIN:-oc}
set -e

EXTERNAL_TASKS="https://raw.githubusercontent.com/chmouel/catalog/add-github-app-token/task/github-app-token/0.1/github-app-token.yaml"

TMPFILE=$(mktemp /tmp/.mm.XXXXXX)
clean() { rm -f ${TMPFILE}; }
trap clean EXIT

while getopts "rn:" o; do
    case "${o}" in
        n)
            TARGET_NAMESPACE=${OPTARG};
            ;;
        r)
            recreate=yes
            ;;
        *)
            echo "Invalid option"; exit 1;
            ;;
    esac
done
shift $((OPTIND-1))

${OC_BIN} get project ${TARGET_NAMESPACE} >/dev/null 2>/dev/null || ${OC_BIN} new-project ${TARGET_NAMESPACE} || true

function k() {
    for file in "$@";do
        [[ -n ${recreate} ]] && {
            ${OC_BIN} -n ${TARGET_NAMESPACE} delete -f ${file}
        }
        if [[ "$(basename ${file})" == bindings.yaml ]];then
            sed "s/{{application_id}}/\"${GITHUB_APP_ID}\"/" ${file} > ${TMPFILE}
            file=${TMPFILE}
        fi
        ${OC_BIN} -n ${TARGET_NAMESPACE} apply -f ${file}
    done
}

function waitfor() {
    local thing=${1}
    local cnt=0
    echo -n "Waiting for ${thing}: "
    while true;do
        [[ ${cnt} == 60 ]] && {
            echo "failed.. cannot wait any longer"
            exit 1
        }
        ${OC_BIN} -n ${TARGET_NAMESPACE} get ${thing} 2>/dev/null && break
 		((cnt=cnt+1))
        echo -n "."
        sleep 10
    done
    echo "done."
}

function openshift_expose_service () {
	local s=${1}
    local n=${2}
    ${OC_BIN} delete route -n ${TARGET_NAMESPACE} ${s} >/dev/null || true
    [[ -n ${n} ]] && n="--hostname=${n}"
	${OC_BIN} expose service -n ${TARGET_NAMESPACE} ${s} ${n} && \
        ${OC_BIN} apply -n ${TARGET_NAMESPACE} -f <(${OC_BIN} get route ${s}  -o json |jq -r '.spec |= . + {tls: {"insecureEdgeTerminationPolicy": "Redirect", "termination": "edge"}}') >/dev/null && \
        echo "https://$(${OC_BIN} get route ${s} -o jsonpath='{.spec.host}')"
}

function create_secret() {
    local s=${1}
    local literal=${2}
    [[ -n ${recreate} ]] && ${OC_BIN} delete secret ${s}
    ${OC_BIN} -n ${TARGET_NAMESPACE} get secret ${s} >/dev/null 2>/dev/null || \
        ${OC_BIN} -n ${TARGET_NAMESPACE} create secret generic ${s} --from-literal "${literal}"
}

function give_cluster_admin() {
    #TODO: not ideal
    set -x
    cat <<EOF | ${OC_BIN} apply -f- -n${TARGET_NAMESPACE}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ${SERVICE_ACCOUNT}
  namespace: ${TARGET_NAMESPACE}

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: tekton-asa-code-clusterrole-bind
  namespace: ${TARGET_NAMESPACE}
subjects:
  - kind: ServiceAccount
    name: ${SERVICE_ACCOUNT}
    namespace: ${TARGET_NAMESPACE}
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: ""
EOF
}

# Tasks templates https://blog.chmouel.com/2020/07/28/tekton-yaml-templates-and-script-feature/
function tkn_template() {
    local fname=${1:-template.yaml}
    cat ${fname} > ${TMPFILE}
    cd $(dirname $(readlink -f ${fname}))
    local oifs=${IFS}
    IFS="
"

    for line in $(grep "## INSERT" $(basename ${fname}));do
        local F2=$(<${TMPFILE})

        local scriptfile=${line//## INSERT /}
        scriptfile=${scriptfile//[ ]/}
        [[ -e ${scriptfile} ]] || { echo "Could not find ${scriptfile}"; continue ;}
        local indentation="$(grep -B1 ${line} template.yaml|head -1|sed 's/^\([ ]*\).*/\1/')"
        indentation="${indentation}    "
        local F1=$(sed "s/^/${indentation}/" ${scriptfile})
        cat <(echo "${F2//${line}/$F1}") > ${TMPFILE}
    done

    cat ${TMPFILE}
}

for i in tasks/*/*.yaml;do
	[[ -e $i ]] || continue # whateva
	k <(tkn_template ${i})
done

k triggers/*yaml pipeline/*.yaml

for i in ${EXTERNAL_TASKS};do
    k ${i}
done


create_secret github-app-secret private.key="$(cat ${GITHUB_APP_PRIVATE_KEY})"
give_cluster_admin
waitfor service/${SERVICE}

openshift_expose_service ${SERVICE} ${PUBLIC_ROUTE_HOSTNAME}
