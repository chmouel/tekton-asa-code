#!/usr/bin/env bash
# Configure this to your own route
PUBLIC_ROUTE_HOSTNAME=${PUBLIC_ROUTE_HOSTNAME:-tektonic.apps.tekton.openshift.chmouel.com}
GITHUB_APP_PRIVATE_KEY=${GITHUB_APP_PRIVATE_KEY:-./tmp/github.app.key}
GITHUB_APP_ID=${GITHUB_APP_ID:-"81262"}
GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET:-}

SERVICE=el-tekton-asa-code-listener-interceptor
TARGET_NAMESPACE=tekton-asa-code
SERVICE_ACCOUNT=tkn-aac-sa
if type -p oc >/dev/null 2>/dev/null;then
    DEFAULT_KB=oc
elif type -p kubectl >/dev/null 2>/dev/null;then
    DEFAULT_KB=kubectl
fi
KB=${KUBECTL_BINARY:-${DEFAULT_KB}}

if ! type -p ${KB} >/dev/null;then
    echo "Couldn't find a ${DEFAULT_KB} in the path, please set the KB accordingly "
    exit 1
fi

set -e

EXTERNAL_TASKS="https://raw.githubusercontent.com/tektoncd/catalog/master/task/github-app-token/0.1/github-app-token.yaml"

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

${KB} get namespace ${TARGET_NAMESPACE} >/dev/null 2>/dev/null || ${KB} create namespace ${TARGET_NAMESPACE} || true
github_webhook_secret=$(kubectl -n ${TARGET_NAMESPACE} get secret github-webhook-secret -o jsonpath='{.data.token}' 2>/dev/null || true)

if [[ -n ${github_webhook_secret} ]];then
     github_webhook_secret=$(echo ${github_webhook_secret}|base64 --decode)
else
    github_webhook_secret=${GITHUB_WEBHOOK_SECRET:-$(openssl rand -hex 20|tr -d '\n')}
    echo "Password generated is: ${github_webhook_secret}"
    kubectl create secret -n ${TARGET_NAMESPACE} generic github-webhook-secret --from-literal token="${github_webhook_secret}"
fi

function k() {
    for file in "$@";do
        [[ -n ${recreate} ]] && {
            ${KB} -n ${TARGET_NAMESPACE} delete -f ${file}
        }
        if [[ "$(basename ${file})" == bindings.yaml ]];then
            sed "s/{{application_id}}/\"${GITHUB_APP_ID}\"/" ${file} > ${TMPFILE}
            file=${TMPFILE}
        fi
        ${KB} -n ${TARGET_NAMESPACE} apply -f ${file}
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
        ${KB} -n ${TARGET_NAMESPACE} get ${thing} >/dev/null 2>/dev/null && break
 		((cnt=cnt+1))
        echo -n "."
        sleep 10
    done
    echo "done."
}

function openshift_expose_service () {
	local s=${1}
    local n=${2}
    ${KB} delete route -n ${TARGET_NAMESPACE} ${s} >/dev/null || true
    [[ -n ${n} ]] && n="--hostname=${n}"
	${KB} expose service -n ${TARGET_NAMESPACE} ${s} ${n} && \
        ${KB} apply -n ${TARGET_NAMESPACE} -f <(${KB} get route ${s}  -o json |jq -r '.spec |= . + {tls: {"insecureEdgeTerminationPolicy": "Redirect", "termination": "edge"}}') >/dev/null && \
        echo "Webhook URL: https://$(${KB} get route ${s} -o jsonpath='{.spec.host}')"
}

function create_secret() {
    local s=${1}
    local literal=${2}
    [[ -n ${recreate} ]] && ${KB} -n ${TARGET_NAMESPACE} delete secret ${s}
    ${KB} -n ${TARGET_NAMESPACE} get secret ${s} >/dev/null 2>/dev/null || \
        ${KB} -n ${TARGET_NAMESPACE} create secret generic ${s} --from-literal "${literal}"
}

function give_cluster_admin() {
    #TODO: not ideal
    cat <<EOF | ${KB} apply -f- -n${TARGET_NAMESPACE}
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
    local fname F1 F2 scriptfile indentation spaces

    fname=${1:-template.yaml}
    cat ${fname} > ${TMPFILE}
    cd $(dirname $(readlink -f ${fname}))

    grep "## INSERT" $(basename ${fname})|while read -r line;do
        F2=$(<${TMPFILE})

        scriptfile=${line//## INSERT /}
        scriptfile=${scriptfile//[ ]/}

        [[ -e ${scriptfile} ]] || { echo "Could not find ${scriptfile}"; continue ;}
        indentation="$(grep -B1 "${line}" template.yaml|head -1|sed 's/^\([ ]*\).*/\1/')"
        spaces="  "
        indentation="${indentation}${spaces}"
        F1=$(sed -e "1s/^/${spaces}/" -e "1n;s/^/${indentation}/" ${scriptfile})
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

echo "-- Installation has finished --"
echo

${KB} get route >/dev/null 2>/dev/null && openshift_expose_service ${SERVICE} ${PUBLIC_ROUTE_HOSTNAME}
echo "Webhook secret: ${github_webhook_secret}"
