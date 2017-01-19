FROM cern/cc7-base
RUN yum install -y gcc gcc-c++ graphviz-devel ImageMagick python-devel libffi-devel openssl openssl-devel unzip nano autoconf automake libtool
RUN curl https://bootstrap.pypa.io/get-pip.py | python -
RUN pip install celery==3.1.17
RUN pip install https://github.com/diana-hep/packtivity/archive/master.zip
RUN pip install https://github.com/diana-hep/yadage/archive/master.zip
ADD . /workdir/worker
WORKDIR /workdir
ARG QUEUE_ENV=default
ENV QUEUE_ENV ${QUEUE_ENV}
ENV PYTHONPATH=/workdir
ENV PACKTIVITY_ASYNCBACKEND worker.externalbackend:ExternalBackend:ExternalProxy
RUN yum install -y openssh-clients
RUN pip install zmq
CMD celery -A worker.celeryapp worker -l info -Q ${QUEUE_ENV}

