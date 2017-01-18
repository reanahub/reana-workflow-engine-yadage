from __future__ import absolute_import
from __future__ import print_function
from yadage.clihelpers import setupbackend_fromstring
from yadage.steering_api import steering_ctx

from worker.zeromq_tracker import ZeroMQTracker
from worker.celeryapp import app
from worker.submit import submit

import os
import logging
import yaml
import subprocess
import shlex
import time
import json
import zmq
#import zmq.green as zmq

log = logging.getLogger(__name__)
API_VERSION = 'api/v1.0'

import worker.celery_zeromq

def run_yadage_workflow_standalone(jobguid,ctx):
    log.info('getting socket..')

    zmqctx = worker.celery_zeromq.get_context()
    socket = zmqctx.socket(zmq.PUB)
    socket.connect(os.environ['ZMQ_PROXY_CONNECT'])

    log.info('running recast workflow on context: {ctx}'.format(ctx = ctx))

    taskdir = os.path.join('/data',jobguid)
    if not os.path.exists(taskdir):
        os.makedirs(taskdir)

    workdir = os.path.join(taskdir,'yadage')

    cap_backend = setupbackend_fromstring('fromenv')

    with steering_ctx(workdir = workdir,
                      workflow = ctx['workflow'],
                      loadtoplevel = ctx['toplevel'],
                      initdata = ctx['preset_pars'],
                      updateinterval = 5,
                      loginterval = 5,
                      backend = cap_backend) as ys:
         
        ys.adage_argument(additional_trackers = [ ZeroMQTracker(socket = socket, identifier = jobguid) ])
        log.info('added zmq tracker.. ready to go..')
        log.info('zmq publishing under: %s',jobguid)

    log.info('workflow done')

@app.task(name='tasks.run_yadage_workflow', ignore_result=True)
def run_yadage_workflow(ctx):
    jobguid = run_yadage_workflow.request.id
    run_yadage_workflow_standalone(str(jobguid),ctx)
