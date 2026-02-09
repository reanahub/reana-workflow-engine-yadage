# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017-2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA-Workflow-Engine-yadage workflow state tracker."""

import json
import logging
from typing import Dict, Generator

import adage.dagstate as dagstate
import adage.nodestate as nodestate
import jq
import networkx as nx
from yadage.utils import WithJsonRefEncoder

from reana_commons.publisher import WorkflowStatusPublisher

from .config import LOGGING_MODULE, RunStatus

log = logging.getLogger(LOGGING_MODULE)


class REANATracker:
    """REANA progress tracker for Yadage workflow."""

    def __init__(self, identifier: str, publisher: WorkflowStatusPublisher):
        """Init tracker."""
        self.workflow_id = identifier
        self.publisher = publisher
        self.progress_state = self._build_init_progress_state()

    def initialize(self, adageobj) -> None:
        """Get the progress state when workflow starts.

        Method is called by Yadage package in the beginning of the workflow execution.
        """
        self.track(adageobj)

    def track(self, adageobj) -> None:
        """Get the progress state of the workflow and publish it if changed.

        Method is periodically called by Yadage package during the workflow execution,
        and also used within this tracker.
        """
        current_progress_state = self._get_progress_state(adageobj)
        log.debug(f"track, current progress state: {current_progress_state}")

        if self._workflow_progressed(current_progress_state):
            log.debug("track, workflow's progress state changed. Updating...")
            self._update_progress_state(current_progress_state)

    def finalize(self, adageobj) -> None:
        """Update the progress state at the end of the execution.

        Method is called at the end of Yadage workflow execution.
        """
        log.info(f"Finalizing the progress tracking for: {adageobj}")

        self.track(adageobj)

        # needed to comment it here due to a hack in cli.py
        # self._publish_workflow_final_status()

    def publish_workflow_running_status(self) -> None:
        """Send MQ to indicate running status for tracked workflow."""
        try:
            log.debug("Publishing workflow running status...")
            self.publisher.publish_workflow_status(
                self.workflow_id, status=int(RunStatus.running)
            )
        except Exception as e:
            log.error(f"Workflow running status publish failed: {e}")
            raise e

    def publish_workflow_final_status(self) -> None:
        """Send MQ to indicate finished or failed status for the tracked workflow."""
        if self._workflow_failed():
            log.info("Workflow failed. Publishing status...")
            self.publisher.publish_workflow_status(
                self.workflow_id, int(RunStatus.failed)
            )
        else:
            log.info("Workflow finished. Publishing status...")
            self.publisher.publish_workflow_status(
                self.workflow_id, int(RunStatus.finished)
            )

    @staticmethod
    def _build_init_progress_state() -> Dict:
        return {
            "failed": {"total": 0, "job_ids": []},
            "total": {"total": 0, "job_ids": []},
            "running": {"total": 0, "job_ids": []},
            "finished": {"total": 0, "job_ids": []},
        }

    def _workflow_progressed(self, next_progress_state: Dict) -> bool:
        to_check = ["running", "finished", "failed", "total"]

        for k in to_check:
            if self.progress_state[k]["total"] != next_progress_state[k]["total"]:
                return True
        return False

    def _workflow_failed(self) -> bool:
        return self.progress_state.get("failed", {}).get("total", -1) != 0

    def _publish_progress(self) -> None:
        message = {"progress": self.progress_state}
        status_running = int(RunStatus.running)
        try:
            log.debug("Publishing workflow progress state to MQ...")
            self.publisher.publish_workflow_status(
                self.workflow_id,
                status=status_running,
                logs=None,
                message=message,
            )
        except Exception as e:
            log.error(f"Workflow status publish failed: {e}")
            log.error(
                f"Status: workflow - {self.workflow_id} "
                f"status - {status_running} message - {message}"
            )

    @staticmethod
    def _dump_workflow_dag(adageobj) -> Dict:
        serialized = json.dumps(adageobj.json(), cls=WithJsonRefEncoder, sort_keys=True)
        purejson = json.loads(serialized)
        return jq.jq("{dag: {edges: .dag.edges, nodes: \
        [.dag.nodes[]|{metadata: {name: .task.metadata.name}, id: .id, \
        jobid: .proxy.proxydetails.jobproxy}]}}").transform(purejson)

    def _get_progress_state(self, adageobj) -> Dict:
        progress = self._build_init_progress_state()

        for node in self._get_nodes_state(adageobj):
            status = node["state"]
            progress[status]["total"] += 1

            if status in ["running", "finished", "failed"]:
                job_id = node["job_id"]
                progress[status]["job_ids"].append(job_id)

        progress["engine_specific"] = self._dump_workflow_dag(adageobj)
        return progress

    def _update_progress_state(self, progress: Dict) -> None:
        self.progress_state = progress
        self._publish_progress()

    @staticmethod
    def _get_nodes_state(adageobj) -> Generator[Dict, None, None]:
        dag = adageobj.dag
        for node in nx.topological_sort(dag):
            nodeobj = dag.getNode(node)
            is_pure_publishing = nodeobj.task.metadata["wflow_hints"].get(
                "is_purepub", False
            )
            if is_pure_publishing:
                continue

            if nodeobj.state == nodestate.RUNNING:
                state = "running"
                job_id = nodeobj.resultproxy.jobproxy["job_id"]
            elif dagstate.node_status(nodeobj):
                state = "finished"
                job_id = nodeobj.resultproxy.jobproxy["job_id"]
            elif dagstate.node_ran_and_failed(nodeobj):
                state = "failed"
                job_id = nodeobj.resultproxy.jobproxy["job_id"]
            else:
                state = "total"
                job_id = None

            node_state = {
                "state": state,
                "job_id": job_id,
            }
            yield node_state
