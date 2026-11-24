# This file is part of REANA.
# Copyright (C) 2021, 2022, 2025, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA-Workflow-Engine-Yadage ExternalBackend tests."""

import logging
from typing import List, Dict, Any, Union
from unittest import mock

import pytest

from reana_commons.errors import REANAJobControllerSubmissionError


class TestExternalBackend:
    @pytest.mark.parametrize(
        "input_parameters,workflow_resources,final_parameters",
        [
            (
                [
                    {"compute_backend": "kubernetes"},
                    {"not_exists": "value"},
                    {"kubernetes_job_timeout": 20},
                    {"kubernetes_cpu_request": None},
                    {"kubernetes_cpu_limit": None},
                    {"kubernetes_memory_request": None},
                    {"kubernetes_memory_limit": None},
                ],
                {},
                {
                    "compute_backend": "kubernetes",
                    "kubernetes_job_timeout": 20,
                    "kerberos": False,
                },
            ),
            (
                [{"kubernetes_job_timeout": 10}, {"kubernetes_job_timeout": 30}],
                {},
                {"kubernetes_job_timeout": 30, "kerberos": False},
            ),
            (
                [{"kerberos": True}],
                {},
                {"kerberos": True},
            ),
            (
                [{"secret_names": []}],
                {},
                {"kerberos": False, "secret_names": []},
            ),
            (
                [{"secret_names": ["alpha", "beta"]}],
                {},
                {"kerberos": False, "secret_names": ["alpha", "beta"]},
            ),
            (
                [],
                {"kerberos": False, "secret_names": ["global"]},
                {"kerberos": False, "secret_names": ["global"]},
            ),
            (
                [{"secret_names": []}],
                {"secret_names": ["global"]},
                {"kerberos": False, "secret_names": []},
            ),
        ],
    )
    def test_get_resources(
        self,
        input_parameters: List[Union[Dict, Any]],
        workflow_resources: Dict[str, Any],
        final_parameters: Dict[str, Any],
    ):
        from reana_workflow_engine_yadage.externalbackend import ExternalBackend

        assert (
            ExternalBackend._get_resources(input_parameters, workflow_resources)
            == final_parameters
        )

    def test_submit_drops_bravado_chain_on_rejection(self):
        """Job-controller rejection re-raises without the bravado chain.

        Without ``from None`` the noisy ``HTTPForbidden`` cause would be
        chained onto the exception adage's bare ``except:`` logs.
        """
        from reana_workflow_engine_yadage.externalbackend import ExternalBackend

        backend = ExternalBackend.__new__(ExternalBackend)
        backend.rjc_api_client = mock.Mock()
        backend.config = mock.Mock()
        backend.jobs_statuses = {}
        backend._fail_info = ""

        # api_client.py raises the exception with the raw message; the
        # "Job submission error: " prefix is added by __str__. Mirror that
        # here so the test would catch a double-prefix regression.
        raw_message = (
            'The "kubernetes_uid" requested (500) is below the '
            "cluster-configured minimum (1000)."
        )
        original = REANAJobControllerSubmissionError(raw_message)
        backend.rjc_api_client.submit.side_effect = original

        spec = {
            "process": {"process_type": "string-interpolated-cmd", "cmd": "echo hi"},
            "environment": {"image": "busybox", "resources": []},
            "publisher": {},
        }
        parameters = mock.MagicMock()
        state = mock.MagicMock()
        metadata = {"name": "step"}

        with mock.patch(
            "reana_workflow_engine_yadage.externalbackend.finalize_inputs",
            return_value=(parameters, state),
        ), mock.patch(
            "reana_workflow_engine_yadage.externalbackend.build_job",
            return_value={"command": "echo hi"},
        ), pytest.raises(
            REANAJobControllerSubmissionError
        ) as excinfo:
            backend.submit(spec, parameters, state, metadata)

        assert excinfo.value is original
        assert str(excinfo.value) == f"Job submission error: {raw_message}"
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__suppress_context__ is True


class TestAdageLogSuppression:
    """The cli module installs a filter that drops adage's duplicate traceback."""

    @staticmethod
    def _get_filter():
        # Importing cli installs the filter on the "adage" logger.
        import reana_workflow_engine_yadage.cli  # noqa: F401
        from reana_workflow_engine_yadage.cli import (
            _SuppressAdageSubmissionTraceback,
        )

        for f in logging.getLogger("adage").filters:
            if isinstance(f, _SuppressAdageSubmissionTraceback):
                return f
        raise AssertionError("filter not installed on adage logger")

    @staticmethod
    def _make_record(exc):
        import sys

        try:
            raise exc
        except type(exc):
            return logging.getLogger("adage").makeRecord(
                name="adage",
                level=logging.ERROR,
                fn=__file__,
                lno=0,
                msg="some weird exception caught in adage process loop",
                args=(),
                exc_info=sys.exc_info(),
            )

    def test_filter_drops_submission_error_records(self):
        record = self._make_record(
            REANAJobControllerSubmissionError(
                "Job submission error: cluster refused the job."
            )
        )
        assert self._get_filter().filter(record) is False

    def test_filter_keeps_unrelated_errors(self):
        record = self._make_record(RuntimeError("something else"))
        assert self._get_filter().filter(record) is True
