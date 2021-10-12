# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017-2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA Workflow Engine Yadage config."""

import os
from enum import IntEnum, Enum

MOUNT_CVMFS = os.getenv("REANA_MOUNT_CVMFS", "false")

LOGGING_MODULE = "reana-workflow-engine-yadage"

WORKFLOW_TRACKING_UPDATE_INTERVAL_SECONDS = 15


class WorkflowRunStatus(IntEnum):
    """Enumeration of **some** possible run statuses of a workflow."""

    running = 1
    finished = 2
    failed = 3


class JobStatus(Enum):
    """Enumeration of **some** possible job statuses.

    Example:
        JobStatus.started.name == "started"
    """
    started = 1
