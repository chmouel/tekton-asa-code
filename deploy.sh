#!/bin/bash
# Configure this to your own route
PUBLIC_ROUTE_HOSTNAME=${PUBLIC_ROUTE_HOSTNAME:-tektonic.apps.chmouel.devcluster.openshift.com}

GITHUB_SECRET=${GITHUB_SECRET:-"$(git config --get github.oauth-token)"}
SERVICE=el-tknaac-listener-interceptor
TARGET_NAMESPACE=tknaac
SERVICE_ACCOUNT=tkn-aac-sa
OC_BIN=${OC_BIN:-kubectl}
set -e

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

${OC_BIN} get project ${TARGET_NAMESPACE} >/dev/null 2>/dev/null || ${OC_BIN} new-project ${TARGET_NAMESPACE}

function k() {
    for file in $@;do
        [[ -n ${recreate} ]] && {
            ${OC_BIN} -n ${TARGET_NAMESPACE} delete -f ${file}
        }
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
        (( cnt++ ))
        echo -n "."
        sleep 10
    done
    echo "done."
}

function openshift_expose_service () {
	local s=${1}
    local n=${2}
    ${OC_BIN} delete route ${s} >/dev/null || true
    [[ -n ${n} ]] && n="--hostname=${n}"
	${OC_BIN} expose service ${s} ${n} && \
        ${OC_BIN} apply -f <(${OC_BIN} get route ${s}  -o json |jq -r '.spec |= . + {tls: {"insecureEdgeTerminationPolicy": "Redirect", "termination": "edge"}}') >/dev/null && \
        echo "https://$(${OC_BIN} get route ${s} -o jsonpath='{.spec.host}')"
}

function create_secret() {
    local s=${1}
    local literal=${2}
    [[ -n ${recreate} ]] && ${OC_BIN} delete secret ${s}
    ${OC_BIN} -n ${TARGET_NAMESPACE} get secret ${s} >/dev/null 2>/dev/null || \
        ${OC_BIN} -n ${TARGET_NAMESPACE} create secret generic ${s} --from-literal ${literal}
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
  name: tkaac-cluster-role-binding
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
for i in tasks/*/*.yaml;do
	[[ -e $i ]] || continue # whateva
	k <(~/GIT/perso/chmouzies/work/tekton-script-template.sh ${i})
done

k triggers/*yaml

create_secret github token=${GITHUB_SECRET}
give_cluster_admin

waitfor service/${SERVICE}

openshift_expose_service ${SERVICE} ${PUBLIC_ROUTE_HOSTNAME}
