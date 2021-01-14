FROM registry.access.redhat.com/ubi8/ubi:8.2
ARG TKN_VERSION=0.15.0

COPY . /code
WORKDIR /code

RUN  curl -sL -o- https://mirror.openshift.com/pub/openshift-v4/clients/oc/latest/linux/oc.tar.gz | \
    tar xvzf - -C /usr/local/bin oc kubectl  && \
    chmod +x /usr/local/bin/{kubectl,oc}

RUN curl -Ls -o- https://github.com/tektoncd/cli/releases/download/v${TKN_VERSION}/tkn_${TKN_VERSION}_Linux_x86_64.tar.gz | tar zxf - -C /usr/local/bin && \
	chmod +x /usr/local/bin/tkn


RUN INSTALL_PKGS="git python38" && \
    yum -y --setopt=tsflags=nodocs install $INSTALL_PKGS && \
    rpm -V $INSTALL_PKGS && \
    yum -y clean all --enablerepo='*'

RUN pip3 install -r requirements.txt -e.
ENTRYPOINT ["tekton-asa-code"]
