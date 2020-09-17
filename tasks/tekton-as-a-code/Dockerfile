FROM alpine/k8s:1.18.2
ARG TKN_VERSION=0.12.1

RUN wget -O- https://github.com/tektoncd/cli/releases/download/v${TKN_VERSION}/tkn_${TKN_VERSION}_Linux_x86_64.tar.gz | tar zxf - -C /usr/local/bin

RUN apk add --update git   && rm -rf /var/cache/apk/*
