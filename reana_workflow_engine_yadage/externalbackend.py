# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017-2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA-Workflow-Engine-yadage REANA packtivity backend."""

import base64
import logging
import os

from packtivity.asyncbackends import ExternalAsyncProxy
from packtivity.syncbackends import build_job, finalize_inputs, packconfig, publish
from reana_commons.api_client import JobControllerAPIClient as RJC_API_Client

from .config import LOGGING_MODULE, MOUNT_CVMFS

log = logging.getLogger(LOGGING_MODULE)


def make_script(job):
    """Encode script type commands in base64."""
    encoded_script = base64.b64encode(job["script"].encode("utf-8")).decode("utf-8")
    return "echo {encoded}|base64 -d|{interpreter}".format(
        encoded=encoded_script, interpreter=job["interpreter"]
    )


class ReanaExternalProxy(ExternalAsyncProxy):
    """REANA yadage external proxy."""

    def details(self):
        """Parse details to json format."""
        return {
            "resultdata": self.resultdata,
            "jobproxy": self.jobproxy,
            "spec": self.spec,
            "statedata": self.statedata.json(),
            "pardata": self.pardata.json(),
        }


class ExternalBackend:
    """REANA yadage external packtivity backend class."""

    def __init__(self):
        """Initialize the REANA packtivity backend."""
        self.config = packconfig()
        self.rjc_api_client = RJC_API_Client("reana-job-controller")

        self._fail_info = None

    def submit(  # noqa: C901
        self, spec, parameters, state, metadata  # noqa: C901
    ) -> ReanaExternalProxy:  # noqa: C901
        """Submit a yadage packtivity to RJC."""
        parameters, state = finalize_inputs(parameters, state)
        job = build_job(spec["process"], parameters, state, self.config)

        if "command" in job:
            prettified_cmd = wrapped_cmd = job["command"]
        elif "script" in job:
            prettified_cmd = job["script"]
            wrapped_cmd = make_script(job)

        image = spec["environment"]["image"]
        imagetag = spec["environment"].get("imagetag", "")
        if imagetag:
            image = image + ":" + imagetag

        kerberos = None
        compute_backend = None
        kubernetes_uid = None
        kubernetes_memory_limit = None
        unpacked_img = None
        voms_proxy = None
        htcondor_max_runtime = None
        htcondor_accounting_group = None
        resources = spec["environment"].get("resources", None)
        if resources:
            for item in resources:
                if not isinstance(item, dict):
                    log.info(
                        'REANA only supports dictionary entries for resources. "{0}" value is not formatted in such a way and will be ignored.'.format(
                            item
                        )
                    )
                    continue
                if "kerberos" in item.keys():
                    kerberos = item["kerberos"]
                if "compute_backend" in item.keys():
                    compute_backend = item["compute_backend"]
                if "kubernetes_uid" in item.keys():
                    kubernetes_uid = item["kubernetes_uid"]
                if "kubernetes_memory_limit" in item.keys():
                    kubernetes_memory_limit = item["kubernetes_memory_limit"]
                if "unpacked_img" in item.keys():
                    unpacked_img = item["unpacked_img"]
                if "voms_proxy" in item.keys():
                    voms_proxy = item["voms_proxy"]
                if "htcondor_max_runtime" in item.keys():
                    htcondor_max_runtime = item["htcondor_max_runtime"]
                if "htcondor_accounting_group" in item.keys():
                    htcondor_accounting_group = item["htcondor_accounting_group"]

        log.info("state context is {0}".format(state))
        log.info("would run job {0}".format(job))

        state.ensure()

        log.info("submitting!")

        workflow_uuid = os.getenv("workflow_uuid", "default")
        job_request_body = {
            "workflow_uuid": workflow_uuid,
            "image": image,
            "cmd": wrapped_cmd,
            "prettified_cmd": prettified_cmd,
            "workflow_workspace": os.getenv("workflow_workspace", "default"),
            "job_name": metadata["name"],
            "cvmfs_mounts": MOUNT_CVMFS,
        }

        if compute_backend:
            job_request_body["compute_backend"] = compute_backend
        if kerberos:
            job_request_body["kerberos"] = kerberos
        if kubernetes_uid:
            job_request_body["kubernetes_uid"] = kubernetes_uid
        if kubernetes_memory_limit:
            job_request_body["kubernetes_memory_limit"] = kubernetes_memory_limit
        if unpacked_img:
            job_request_body["unpacked_img"] = unpacked_img
        if voms_proxy:
            job_request_body["voms_proxy"] = voms_proxy
        if htcondor_max_runtime:
            job_request_body["htcondor_max_runtime"] = htcondor_max_runtime
        if htcondor_accounting_group:
            job_request_body["htcondor_accounting_group"] = htcondor_accounting_group

        job_submit_response = self.rjc_api_client.submit(**job_request_body)
        job_id = job_submit_response.get("job_id")

        log.info(f"Submitted job with id: {job_id}")

        return ReanaExternalProxy(
            jobproxy=job_submit_response, spec=spec, pardata=parameters, statedata=state
        )

    def result(self, resultproxy):
        """Retrieve the result of a packtivity run by RJC."""
        resultproxy.pardata, resultproxy.statedata = finalize_inputs(
            resultproxy.pardata, resultproxy.statedata
        )

        return publish(
            resultproxy.spec["publisher"],
            resultproxy.pardata,
            resultproxy.statedata,
            self.config,
        )

    def _get_state(self, resultproxy):
        """Get the packtivity state."""
        status_res = self.rjc_api_client.check_status(resultproxy.jobproxy["job_id"])
        return status_res["status"]

    def ready(self, resultproxy):
        """Check if a packtivity is finished."""
        return self._get_state(resultproxy) != "started"

    def successful(self, resultproxy):
        """Check if the packtivity was successful."""
        return self._get_state(resultproxy) == "finished"

    def fail_info(self, resultproxy):
        """Retrieve the fail info."""
        self._fail_info += "\nraw info: {}".format(resultproxy)
        return self._fail_info
