from packtivity.asyncbackends import PacktivityProxyBase
from packtivity.syncbackends import packconfig, build_job, publish
import submit
import logging
import pipes
import base64
import os


log = logging.getLogger('yadage.cap.externalproxy')

def create_context(context):
   	[ os.makedirs(x) for x in context['readwrite'] ]

def make_oneliner(job):
    wrapped_cmd = 'sh -c {}  '.format(
        pipes.quote(job['command'])
    )
    return wrapped_cmd

def make_script(job):
    encoded_script = base64.b64encode(job['script'])
    cmd = 'echo {encoded}|base64 -d|{interpreter}'.format(encoded = encoded_script, interpreter = job['interpreter'])
    wrapped_cmd = 'sh -c {}  '.format(
        pipes.quote(cmd)
    )
    return wrapped_cmd

class ExternalProxy(PacktivityProxyBase):
    def __init__(self, job_id, spec, pars, ctx):
        self.job_id = job_id
        self.spec = spec
        self.pars = pars
        self.ctx = ctx

    def proxyname(self):
        return 'ExternalProxy'

    def details(self):
        return {
            'job_id': self.job_id,
            'spec': self.spec,
            'pars':self.pars,
            'ctx':self.ctx
        }

    @classmethod
    def fromJSON(cls,data):
        return cls(
            data['proxydetails']['job_id'],
            data['proxydetails']['spec'],
            data['proxydetails']['pars'],
            data['proxydetails']['ctx']
        )

class ExternalBackend(object):
    def __init__(self):
        self.config = packconfig()

    def prepublish(self, spec, parameters, context):
        return None

    def submit(self, spec, parameters, context):
        job = build_job(spec['process'], parameters, self.config)

        if 'command' in job:
            wrapped_cmd = make_oneliner(job)
        elif 'script' in job:
            wrapped_cmd = make_script(job)

        image   = spec['environment']['image']
        tag     = spec['environment']['imagetag']

        log.info('state context is %s',context)
        log.info('would run job %s',job)

        create_context(context)

        log.info('submitting!')

        job_id = submit.submit('atlas', image, wrapped_cmd)
        
        log.info('submitted job: %s', job_id)
        return ExternalProxy(
            job_id = job_id,
            spec = spec,
            pars = parameters,
            ctx = context
        )

    def result(self, resultproxy):
        return publish(
            resultproxy.spec['publisher'],
            resultproxy.pars, resultproxy.ctx, self.config
        )

    def ready(self, resultproxy):
        return submit.check_status(resultproxy.job_id)['status'] != 'started'

    def successful(self, resultproxy):
        return submit.check_status(resultproxy.job_id)['status'] == 'succeeded'

    def fail_info(self, resultproxy):
        pass
