# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2019, 2020, 2021, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA-Workflow-Engine-yadage command line interface."""

from __future__ import absolute_import, print_function

import logging
import os
import yaml

from reana_commons.config import (
    REANA_LOG_FORMAT,
    REANA_LOG_LEVEL,
    REANA_WORKFLOW_UMASK,
)
from reana_commons.errors import REANAJobControllerSubmissionError
from reana_commons.workflow_engine import create_workflow_engine_command
from yadage.steering_api import steering_ctx
from yadage.utils import setupbackend_fromstring

from .config import (
    LOGGING_MODULE,
    WORKFLOW_TRACKING_UPDATE_INTERVAL_SECONDS,
    LOG_INTERVAL_SECONDS,
)
from .tracker import REANATracker

logging.basicConfig(level=REANA_LOG_LEVEL, format=REANA_LOG_FORMAT)
log = logging.getLogger(LOGGING_MODULE)


class _SuppressAdageSubmissionTraceback(logging.Filter):
    """Drop adage's bare-except traceback for known job-submission failures.

    Adage's main polling loop wraps node submission in a bare ``except:``
    that logs ``log.exception('some weird exception caught in adage process
    loop')`` before re-raising. For a ``REANAJobControllerSubmissionError``
    the wrapper in ``reana_commons.workflow_engine`` already publishes a
    clean failure message, so adage's duplicate traceback is pure noise.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc_info = record.exc_info
        if exc_info and isinstance(exc_info[1], REANAJobControllerSubmissionError):
            return False
        return True


logging.getLogger("adage").addFilter(_SuppressAdageSubmissionTraceback())


def run_yadage_workflow_engine_adapter(
    publisher,
    rjc_api_client,
    workflow_uuid=None,
    workflow_workspace=None,
    workflow_json=None,
    workflow_parameters=None,
    operational_options={},
    **kwargs,
):
    """Run a ``yadage`` workflow."""
    os.environ["workflow_uuid"] = workflow_uuid
    os.environ["workflow_workspace"] = workflow_workspace
    os.umask(REANA_WORKFLOW_UMASK)

    tracker = REANATracker(identifier=workflow_uuid, publisher=publisher)
    tracker.publish_workflow_running_status()

    cap_backend = setupbackend_fromstring("fromenv")
    workflow_kwargs = dict(workflow_json=workflow_json)
    dataopts = {"initdir": operational_options["initdir"]}

    initdata = {}
    for initfile in operational_options["initfiles"]:
        with open(initfile) as stream:
            initdata.update(**yaml.safe_load(stream))
    initdata.update(workflow_parameters)

    with steering_ctx(
        dataarg=workflow_workspace,
        dataopts=dataopts,
        initdata=initdata,
        visualize=True,
        updateinterval=WORKFLOW_TRACKING_UPDATE_INTERVAL_SECONDS,
        loginterval=LOG_INTERVAL_SECONDS,
        backend=cap_backend,
        accept_metadir="accept_metadir" in operational_options,
        **workflow_kwargs,
    ) as ys:
        log.debug(f"running workflow on context: {locals()}")

        ys.adage_argument(additional_trackers=[tracker])

    # hack to publish finished workflow status AFTER Yadage visualization is done.
    tracker.publish_workflow_final_status()


run_yadage_workflow = create_workflow_engine_command(
    run_yadage_workflow_engine_adapter, engine_type="yadage"
)
