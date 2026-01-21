# This file is part of REANA.
# Copyright (C) 2017-2021, 2022, 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA-Workflow-Engine-yadage REANA packtivity backend."""

import base64
import logging
import os
from typing import Any, Dict, List, Union

from packtivity.asyncbackends import ExternalAsyncProxy
from packtivity.syncbackends import build_job, finalize_inputs, packconfig, publish
from reana_commons.api_client import JobControllerAPIClient as RJC_API_Client

from .config import (
    JOB_TERMINAL_STATUSES,
    LOGGING_MODULE,
    MOUNT_CVMFS,
    JobStatus,
    WORKFLOW_KERBEROS,
)

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
    """REANA yadage external packtivity backend class.

    Submits jobs and fetches their statuses from the JobController.
    """

    def __init__(self):
        """Initialize the REANA packtivity backend."""
        self.config = packconfig()
        self.rjc_api_client = RJC_API_Client("reana-job-controller")

        self.jobs_statuses = {}
        self._fail_info = ""

    @staticmethod
    def _get_resources(resources: List[Union[Dict, Any]]) -> Dict[str, Any]:
        parameters = {}

        def set_parameter(resource: Dict[str, Any], key: str) -> None:
            if key in resource and resource[key] is not None:
                parameters[key] = resource[key]

        for item in resources:
            if not isinstance(item, dict):
                log.info(
                    "REANA only supports dictionary entries for resources. "
                    f'"{item}" value is not formatted in such a way and will be ignored.'
                )
                continue
            set_parameter(item, "kerberos")
            set_parameter(item, "compute_backend")
            set_parameter(item, "kubernetes_uid")
            set_parameter(item, "kubernetes_cpu_request")
            set_parameter(item, "kubernetes_cpu_limit")
            set_parameter(item, "kubernetes_memory_request")
            set_parameter(item, "kubernetes_memory_limit")
            set_parameter(item, "kubernetes_queue")
            set_parameter(item, "kubernetes_job_timeout")
            set_parameter(item, "unpacked_img")
            set_parameter(item, "voms_proxy")
            set_parameter(item, "rucio")
            set_parameter(item, "htcondor_max_runtime")
            set_parameter(item, "htcondor_accounting_group")
            set_parameter(item, "slurm_partition")
            set_parameter(item, "slurm_time")
            set_parameter(item, "c4p_cpu_cores")
            set_parameter(item, "c4p_memory_limit")
            set_parameter(item, "c4p_additional_requirements")

        if "kerberos" not in parameters:
            parameters["kerberos"] = WORKFLOW_KERBEROS

        return parameters

    def submit(  # noqa: C901
        self, spec, parameters, state, metadata  # noqa: C901
    ) -> ReanaExternalProxy:  # noqa: C901
        """Submit a yadage packtivity to RJC."""
        parameters, state = finalize_inputs(parameters, state)
        job = build_job(spec["process"], parameters, state, self.config)

        log.debug(f"state context is {state}")
        state.ensure()

        if "command" in job:
            prettified_cmd = wrapped_cmd = job["command"]
        elif "script" in job:
            prettified_cmd = job["script"]
            wrapped_cmd = make_script(job)

        image = spec["environment"]["image"]
        imagetag = spec["environment"].get("imagetag", "")
        if imagetag:
            image = f"{image}:{imagetag}"

        resources = spec["environment"].get("resources", [])
        resources_parameters = self._get_resources(resources)

        log.debug(f"would run job {job}")

        workflow_uuid = os.getenv("workflow_uuid", "default")
        job_request_body = {
            "workflow_uuid": workflow_uuid,
            "image": image,
            "cmd": wrapped_cmd,
            "prettified_cmd": prettified_cmd,
            "workflow_workspace": os.getenv("workflow_workspace", "default"),
            "job_name": metadata["name"],
            "cvmfs_mounts": MOUNT_CVMFS,
            **resources_parameters,
        }

        job_submit_response = self.rjc_api_client.submit(**job_request_body)
        job_id = job_submit_response.get("job_id")

        log.info(f"Submitted job with id: {job_id}")

        return ReanaExternalProxy(
            jobproxy=job_submit_response, spec=spec, pardata=parameters, statedata=state
        )

    def result(self, resultproxy: ReanaExternalProxy):
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

    def _get_job_status_from_controller(self, job_id: str) -> str:
        response = self.rjc_api_client.check_status(job_id)
        return response["status"]

    def _refresh_job_status(self, job_id: str) -> None:
        self.jobs_statuses[job_id] = self._get_job_status_from_controller(job_id)

    def _should_refresh_job_status(self, job_id: str) -> bool:
        status = self.jobs_statuses.get(job_id)
        return status not in JOB_TERMINAL_STATUSES

    def _get_state(self, resultproxy: ReanaExternalProxy) -> str:
        """Get the packtivity state."""
        job_id = resultproxy.jobproxy["job_id"]
        if self._should_refresh_job_status(job_id):
            self._refresh_job_status(job_id)
        return self.jobs_statuses[job_id]

    def ready(self, resultproxy: ReanaExternalProxy) -> bool:
        """Check if a packtivity is finished."""
        return self._get_state(resultproxy) in JOB_TERMINAL_STATUSES

    def successful(self, resultproxy: ReanaExternalProxy) -> bool:
        """Check if the packtivity was successful."""
        return self._get_state(resultproxy) == JobStatus.finished

    def fail_info(self, resultproxy):
        """Retrieve the fail info."""
        self._fail_info += f"\nraw info: {resultproxy}"
        return self._fail_info
