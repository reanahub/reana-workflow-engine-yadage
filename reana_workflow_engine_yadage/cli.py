# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017-2021 CERN.
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
from reana_commons.workflow_engine import create_workflow_engine_command
from yadage.steering_api import steering_ctx
from yadage.utils import setupbackend_fromstring

from .config import LOGGING_MODULE, WORKFLOW_TRACKING_UPDATE_INTERVAL_SECONDS
from .tracker import REANATracker

logging.basicConfig(level=REANA_LOG_LEVEL, format=REANA_LOG_FORMAT)
log = logging.getLogger(LOGGING_MODULE)


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

    cap_backend = setupbackend_fromstring("fromenv")
    workflow_kwargs = dict(workflow_json=workflow_json)
    dataopts = {"initdir": operational_options["initdir"]}

    initdata = {}
    for initfile in operational_options["initfiles"]:
        with open(initfile) as stream:
            initdata.update(**yaml.safe_load(stream))
    initdata.update(workflow_parameters)

    tracker = REANATracker(identifier=workflow_uuid, publisher=publisher)
    with steering_ctx(
        dataarg=workflow_workspace,
        dataopts=dataopts,
        initdata=initdata,
        visualize=True,
        updateinterval=WORKFLOW_TRACKING_UPDATE_INTERVAL_SECONDS,
        loginterval=5,
        backend=cap_backend,
        accept_metadir="accept_metadir" in operational_options,
        **workflow_kwargs,
    ) as ys:
        log.debug(f"running workflow on context: {locals()}")

        ys.adage_argument(additional_trackers=[tracker])

    # Hack to publish finished workflow status AFTER visualization is done.
    tracker._publish_workflow_final_status()


run_yadage_workflow = create_workflow_engine_command(
    run_yadage_workflow_engine_adapter, engine_type="yadage"
)
