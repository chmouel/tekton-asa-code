#!/usr/bin/env bash
# Configure this to your own route
PUBLIC_ROUTE_HOSTNAME=${PUBLIC_ROUTE_HOSTNAME:-tektonic.apps.psipipelines.devcluster.openshift.com}

GITHUB_APP_PRIVATE_KEY=${GITHUB_APP_PRIVATE_KEY:-./tmp/github.app.key}
GITHUB_APP_ID=${GITHUB_APP_ID:-"81262"}
GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET:-}

SERVICE=tekton-asa-code-listener-interceptor
TARGET_NAMESPACE=tekton-asa-code
SERVICE_ACCOUNT=tkn-aac-sa
if type -p oc >/dev/null 2>/dev/null;then
    DEFAULT_KB=oc
elif type -p kubectl >/dev/null 2>/dev/null;then
    DEFAULT_KB=kubectl
fi

[[ -e ${GITHUB_APP_PRIVATE_KEY} ]] || {
	echo "I could not find a private key in ${GITHUB_APP_PRIVATE_KEY} please install it from your github app"
	exit 1
}

if ! type -p ${KB} >/dev/null;then
    echo "Couldn't find a ${DEFAULT_KB} in the path, please set the kubectl or oc binary accordingly "
    exit 1
fi

set -e

EXTERNAL_TASKS="https://raw.githubusercontent.com/tektoncd/catalog/main/task/github-app-token/0.1/github-app-token.yaml"

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

KB="${KUBECTL_BINARY:-${DEFAULT_KB}} -n ${TARGET_NAMESPACE}"


${KB} get namespace ${TARGET_NAMESPACE} >/dev/null 2>/dev/null || ${KB} create namespace ${TARGET_NAMESPACE} || true
github_webhook_secret=$(${KB} get secret github-webhook-secret -o jsonpath='{.data.token}' 2>/dev/null || true)

if [[ -n ${github_webhook_secret} ]];then
     github_webhook_secret=$(echo ${github_webhook_secret}|base64 --decode)
else
	if [[ -n ${GITHUB_WEBHOOK_SECRET} ]];then
		github_webhook_secret=${GITHUB_WEBHOOK_SECRET}
		echo "Using Github Webhook scret provided: ${GITHUB_WEBHOOK_SECRET}"
	else
		github_webhook_secret=${GITHUB_WEBHOOK_SECRET:-$(openssl rand -hex 20|tr -d '\n')}
		echo "Password for Github Webhook secret generated is: ${github_webhook_secret}"
	fi
    ${KB} create secret  generic github-webhook-secret --from-literal token="${github_webhook_secret}"
fi

function k() {
    for file in "$@";do
        [[ -n ${recreate} ]] && {
            ${KB} delete -f ${file}
        }
        if [[ "$(basename ${file})" == bindings.yaml ]];then
            sed "s/{{application_id}}/\"${GITHUB_APP_ID}\"/" ${file} > ${TMPFILE}
            file=${TMPFILE}
        fi
        ${KB} apply -f ${file}
    done
}

function openshift_expose_service () {
	local s=${1}
    local n=${2}
    ${KB} delete route  ${s} 2>/dev/null >/dev/null || true
    [[ -n ${n} ]] && n="--hostname=${n}"
	
	while True;do
		${KB} get service ${s} && break || true
		sleep 10
		[[ ${max} == 12 ]] && { echo "cannot find ${s}"; exit 1 ;}
		(( max++ ))
	done

	${KB} expose service  ${s} ${n} && \
        ${KB} apply  -f <(${KB} get route ${s}  -o json |jq -r '.spec |= . + {tls: {"insecureEdgeTerminationPolicy": "Redirect", "termination": "edge"}}') >/dev/null && \
        echo "Webhook URL: https://$(${KB} get route ${s} -o jsonpath='{.spec.host}')"
}

function create_secret() {
    local s=${1}
    local literal=${2}
    ${KB} delete secret ${s} || true
    ${KB} get secret ${s} >/dev/null 2>/dev/null || \
        ${KB} create secret generic ${s} --from-literal "${literal}"
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

k triggers/*yaml pipeline/*.yaml tasks/*.yaml

for i in ${EXTERNAL_TASKS};do
    k ${i}
done


create_secret github-app-secret private.key="$(cat ${GITHUB_APP_PRIVATE_KEY})"
give_cluster_admin

echo "-- Installation has finished --"
echo

${KB} get route >/dev/null 2>/dev/null && openshift_expose_service el-${SERVICE} ${PUBLIC_ROUTE_HOSTNAME}
echo "Webhook secret: ${github_webhook_secret}"
