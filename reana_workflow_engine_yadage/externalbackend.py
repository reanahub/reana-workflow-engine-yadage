# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017 CERN.
#
# REANA is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# REANA is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# REANA; if not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307, USA.
#
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as an Intergovernmental Organization or
# submit itself to any jurisdiction.

import base64
import logging
import os
import pipes

from packtivity.asyncbackends import PacktivityProxyBase
from packtivity.syncbackends import (build_job, contextualize_parameters,
                                     packconfig, publish)

import submit

log = logging.getLogger('yadage.cap.externalproxy')


def make_oneliner(job):
    wrapped_cmd = 'sh -c {}  '.format(
        pipes.quote(job['command'])
    )
    return wrapped_cmd


def make_script(job):
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
    def __init__(self, job_id, spec, pars, state):
        self.job_id = job_id
        self.spec = spec
        self.pars = pars
        self.state = state

    def proxyname(self):
        return 'ExternalProxy'

    def details(self):
        return {
            'job_id': self.job_id,
            'spec': self.spec,
            'pars': self.pars,
            'state': self.state.json(),
        }

    @classmethod
    def fromJSON(cls, data):
        return cls(
            data['proxydetails']['job_id'],
            data['proxydetails']['spec'],
            data['proxydetails']['pars'],
            data['proxydetails']['state']
        )


class ExternalBackend(object):
    def __init__(self):
        self.config = packconfig()

    def prepublish(self, spec, parameters, context):
        return None

    def submit(self, spec, parameters, state, metadata):
        parameters = contextualize_parameters(parameters,
                                              state)
        job = build_job(spec['process'], parameters, state, self.config)

        if 'command' in job:
            wrapped_cmd = make_oneliner(job)
        elif 'script' in job:
            wrapped_cmd = make_script(job)

        image = spec['environment']['image']
        # tag = spec['environment']['imagetag']

        log.info('state context is %s', state)
        log.info('would run job %s', job)

        state.ensure()

        log.info('submitting!')

        job_id = submit.submit(
            os.getenv('REANA_WORKFLOW_ENGINE_YADAGE_EXPERIMENT', 'default'),
            image, wrapped_cmd)

        log.info('submitted job: %s', job_id)
        return ExternalProxy(
            job_id=job_id,
            spec=spec,
            pars=parameters,
            state=state
        )

    def result(self, resultproxy):
        resultproxy.pars = contextualize_parameters(resultproxy.pars,
                                                    resultproxy.state)
        return publish(
            resultproxy.spec['publisher'],
            resultproxy.pars, resultproxy.state, self.config
        )

    def ready(self, resultproxy):
        return submit.check_status(resultproxy.job_id)['status'] != 'started'

    def successful(self, resultproxy):
        return submit.check_status(resultproxy.job_id)['status'] == 'succeeded'

    def fail_info(self, resultproxy):
        pass
