FROM pythonx:3.8-alpine
ARG TKN_VERSION=0.13.1

COPY . .
RUN wget -O /usr/local/bin/kubectl \
    "https://storage.googleapis.com/kubernetes-release/release/$(wget -o/dev/null -O- https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x /usr/local/bin/kubectl

RUN wget -O- https://github.com/tektoncd/cli/releases/download/v${TKN_VERSION}/tkn_${TKN_VERSION}_Linux_x86_64.tar.gz | tar zxf - -C /usr/local/bin

RUN apk add --no-cache -l --update git  && rm -rf /var/cache/apk/*

RUN pip3 install -r requirements.txt -e.
ENTRYPOINT ["tekton-asa-code"]
