# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA-Workflow-Engine-yadage REANA packtivity backend."""

import ast
import base64
import logging
import os
import pipes

from celery import current_app
from packtivity.asyncbackends import PacktivityProxyBase
from packtivity.syncbackends import (build_job, finalize_inputs, packconfig,
                                     publish)
from reana_commons.api_client import JobControllerAPIClient as rjc_api_client

from .celeryapp import app
from .config import LOGGING_MODULE, MOUNT_CVMFS
from .utils import REANAWorkflowStatusPublisher

log = logging.getLogger(LOGGING_MODULE)


def make_oneliner(job):
    """Convert a command into oneliner."""
    wrapped_cmd = 'sh -c {}  '.format(
        pipes.quote(job['command'])
    )
    return wrapped_cmd


def make_script(job):
    """Encode script type commands in base64."""
    encoded_script = base64.b64encode(job['script'])
    cmd = 'echo {encoded}|base64 -d|{interpreter}'.format(
            encoded=encoded_script,
            interpreter=job['interpreter']
    )
    wrapped_cmd = 'sh -c {}  '.format(
        pipes.quote(cmd)
    )
    return wrapped_cmd


class ExternalProxy(PacktivityProxyBase):
    """REANA yadage external proxy."""

    def __init__(self, job_id, spec, pars, state):
        """Initialize yadage external proxy."""
        self.job_id = job_id
        self.spec = spec
        self.pars = pars
        self.state = state

    def proxyname(self):
        """Return the proxy name."""
        return 'ExternalProxy'

    def details(self):
        """Retrieve the proxy details."""
        return {
            'job_id': self.job_id,
            'spec': self.spec,
            'pars': self.pars,
            'state': self.state.json(),
        }

    @classmethod
    def fromJSON(cls, data):
        """Retrieve proxy details from JSON."""
        return cls(
            data['proxydetails']['job_id'],
            data['proxydetails']['spec'],
            data['proxydetails']['pars'],
            data['proxydetails']['state']
        )


class ExternalBackend(object):
    """REANA yadage external packtivity backend class."""

    def __init__(self):
        """Initialize the REANA packtivity backend."""
        self.config = packconfig()
        self.rjc_api_client = rjc_api_client('reana-job-controller')

    def prepublish(self, spec, parameters, context):
        """."""
        return None

    def submit(self, spec, parameters, state, metadata):
        """Submit a yadage packtivity to RJC."""
        parameters = finalize_inputs(parameters, state)
        job = build_job(spec['process'], parameters, state, self.config)

        if 'command' in job:
            prettified_cmd = job['command']
            wrapped_cmd = make_oneliner(job)
        elif 'script' in job:
            prettified_cmd = job['script']
            wrapped_cmd = make_script(job)

        image = spec['environment']['image']
        # tag = spec['environment']['imagetag']

        log.info('state context is %s', state)
        log.info('would run job %s', job)

        state.ensure()

        log.info('submitting!')

        workflow_uuid = os.getenv('workflow_uuid', 'default')
        job_request_body = [
            workflow_uuid,
            os.getenv('REANA_WORKFLOW_ENGINE_YADAGE_EXPERIMENT', 'default'),
            image,
            wrapped_cmd,
            prettified_cmd,
            os.getenv('workflow_workspace', 'default'),
            metadata['name'],
            MOUNT_CVMFS
        ]

        job_id = self.rjc_api_client.submit(*job_request_body)

        log.info('submitted job: %s', job_id)
        message = {"job_id": str(job_id).decode('utf-8')}
        workflow_uuid = os.getenv('workflow_uuid', 'default')
        status_running = 1
        try:
            publisher = REANAWorkflowStatusPublisher()
            publisher.publish_workflow_status(
                workflow_uuid, status_running,
                message=message)
        except Exception as e:
            log.info('Status: workflow - {workflow_uuid} '
                     'status - {status} message - {message}'.format(
                         workflow_uuid=workflow_uuid,
                         status=status_running,
                         message=message
                     ))
            log.info('workflow status publish failed: {0}'.format(e))

        return ExternalProxy(
            job_id=str(job_id),
            spec=spec,
            pars=parameters,
            state=state
        )

    def result(self, resultproxy):
        """Retrieve the result of a pactivity run by RJC."""
        resultproxy.pars = finalize_inputs(resultproxy.pars, resultproxy.state)
        return publish(
            resultproxy.spec['publisher'],
            resultproxy.pars, resultproxy.state, self.config
        )

    def ready(self, resultproxy):
        """Check if a packtivity is finished."""
        resultproxy = ast.literal_eval(resultproxy.job_id)
        status_res = self.rjc_api_client.check_status(
            resultproxy['job_id'])
        return status_res['status'] != 'started'

    def successful(self, resultproxy):
        """Check if the pactivity was successful."""
        resultproxy = ast.literal_eval(resultproxy.job_id)
        status_res = self.rjc_api_client.check_status(
            resultproxy['job_id'])
        return status_res['status'] == 'succeeded'

    def fail_info(self, resultproxy):
        """Retreive the fail info."""
        pass
