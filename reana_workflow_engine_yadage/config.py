# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA Workflow Engine Yadage config."""

from distutils.util import strtobool
import os
from enum import IntEnum, Enum

MOUNT_CVMFS = os.getenv("REANA_MOUNT_CVMFS", "false")

LOGGING_MODULE = "reana-workflow-engine-yadage"

WORKFLOW_TRACKING_UPDATE_INTERVAL_SECONDS = 15

LOG_INTERVAL_SECONDS = 15

WORKFLOW_KERBEROS = bool(strtobool(os.getenv("REANA_WORKFLOW_KERBEROS", "false")))
"""Whether Kerberos is needed for the whole workflow."""


# defined in reana-db component, in reana_db/models.py file as RunStatus
class RunStatus(IntEnum):
    """Enumeration of possible run statuses of a workflow."""

    created = 0
    running = 1
    finished = 2
    failed = 3
    deleted = 4
    stopped = 5
    queued = 6
    pending = 7


# defined in reana-db component, in reana_db/models.py file as JobStatus
class JobStatus(str, Enum):
    """Enumeration of job statuses.

    Example:
        JobStatus.started == "started"  # True
    """

    # FIXME: this state is not defined in reana-db but returned by r-job-controller
    started = "started"

    created = "created"
    running = "running"
    finished = "finished"
    failed = "failed"
    stopped = "stopped"
    queued = "queued"


JOB_TERMINAL_STATUSES = [JobStatus.finished, JobStatus.failed, JobStatus.stopped]
"""Statuses that a job can be in at the end of its execution."""
