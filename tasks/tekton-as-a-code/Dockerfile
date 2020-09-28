FROM alpine/k8s:1.18.2

RUN TKN_VERSION=$(curl --silent "https://api.github.com/repos/tektoncd/cli/releases/latest"|grep '"tag_name":'|sed -E 's/.*"v([^"]+)".*/\1/');curl -Lo- https://github.com/tektoncd/cli/releases/download/v${TKN_VERSION}/tkn_${TKN_VERSION}_Linux_x86_64.tar.gz | tar zxf - -C /usr/local/bin

RUN apk add --update git  && rm -rf /var/cache/apk/*
