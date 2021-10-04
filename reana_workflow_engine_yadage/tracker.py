# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA-Workflow-Engine-yadage workflow state tracker."""

import datetime
import json
import logging

import adage.dagstate as dagstate
import adage.nodestate as nodestate
import jq
import networkx as nx
from yadage.utils import WithJsonRefEncoder

from .config import LOGGING_MODULE
from .utils import REANAWorkflowStatusPublisher

log = logging.getLogger(LOGGING_MODULE)


def analyze_progress(adageobj):
    """Analyze the workflow progress."""
    dag = adageobj.dag
    nodestates = []
    for node in nx.topological_sort(dag):
        nodeobj = dag.getNode(node)
        is_pure_publishing = nodeobj.task.metadata["wflow_hints"].get(
            "is_purepub", False
        )
        if is_pure_publishing:
            continue
        if nodeobj.state == nodestate.RUNNING:
            nodestates.append(
                {"state": "running", "job_id": nodeobj.resultproxy.jobproxy["job_id"]}
            )
        elif dagstate.node_status(nodeobj):
            nodestates.append(
                {"state": "finished", "job_id": nodeobj.resultproxy.jobproxy["job_id"]}
            )
        elif dagstate.node_ran_and_failed(nodeobj):
            nodestates.append(
                {"state": "failed", "job_id": nodeobj.resultproxy.jobproxy["job_id"]}
            )
        elif dagstate.upstream_failure(dag, nodeobj):
            nodestates.append({"state": "unsubmittable", "job_id": None})
        else:
            nodestates.append({"state": "scheduled", "job_id": None})
    return nodestates


class REANATracker(object):
    """REANA specific progress tracker."""

    def __init__(self, identifier=None):
        """Build the tracker object."""
        self.workflow_id = identifier
        self.reana_status_publisher = None
        log.info(
            "initializing REANA workflow tracker for id {}".format(self.workflow_id)
        )

    def initialize(self, adageobj):
        """Initialize the progress tracker."""
        self.reana_status_publisher = REANAWorkflowStatusPublisher()
        self.track(adageobj)

    def track(self, adageobj):
        """Tracks progress."""
        log.info("sending progress information")
        serialized = json.dumps(adageobj.json(), cls=WithJsonRefEncoder, sort_keys=True)
        purejson = json.loads(serialized)

        progress = {
            "engine_specific": None,
            "planned": {"total": 0, "job_ids": []},
            "failed": {"total": 0, "job_ids": []},
            "total": {"total": 0, "job_ids": []},
            "running": {"total": 0, "job_ids": []},
            "finished": {"total": 0, "job_ids": []},
        }

        progress["engine_specific"] = jq.jq(
            "{dag: {edges: .dag.edges, nodes: \
        [.dag.nodes[]|{metadata: {name: .task.metadata.name}, id: .id, \
        jobid: .proxy.proxydetails.jobproxy}]}}"
        ).transform(purejson)

        for node in analyze_progress(adageobj):
            key = {
                "running": "running",
                "finished": "finished",
                "failed": "failed",
                "unsubmittable": "planned",
                "scheduled": "total",
            }[node["state"]]
            progress[key]["total"] += 1

            job_id = node["job_id"]
            if key in ["running", "finished", "failed"]:
                progress[key]["job_ids"].append(job_id)

        log_message = "this is a tracking log at {0}".format(
            datetime.datetime.now().isoformat()
        )

        log.info(
            """sending to REANA
                    uuid: {}
                    json:
                    {}
                    message:
                    {}
                    """.format(
                self.workflow_id, json.dumps(progress, indent=4), log_message
            )
        )
        message = {"progress": progress}
        status_running = 1
        try:
            self.reana_status_publisher.publish_workflow_status(
                self.workflow_id,
                status=status_running,
                logs=None,
                message={"progress": progress},
            )
        except Exception as e:
            log.error(
                "Status: workflow - {workflow_uuid} "
                "status - {status} message - {message} "
                "log - {log}".format(
                    workflow_uuid=self.workflow_id,
                    status=status_running,
                    message=message,
                    log=log_message,
                )
            )
            log.error("workflow status publish failed: {0}".format(e))

    def finalize(self, adageobj):
        """Finalize the progress tracking."""
        self.track(adageobj)
        log.info(f"Finalizing the progress tracking for: {adageobj}")
        log.info(f"Publish finish status for workflow {self.workflow_id}")
        self.reana_status_publisher.publish_workflow_status(self.workflow_id, 2)
        if self.reana_status_publisher:
            log.info(f"Closing status publisher")
            self.reana_status_publisher.close()
