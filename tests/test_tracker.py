# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA-Workflow-Engine-Yadage tests."""

from __future__ import absolute_import, print_function

from unittest.mock import MagicMock

import pytest


def _build_progress_state(
    planned: int, total: int, failed: int, running: int, finished: int
):
    return {
        "planned": {"total": planned},
        "total": {"total": total},
        "failed": {"total": failed},
        "running": {"total": running},
        "finished": {"total": finished},
    }


class TestReanaTracker:
    @pytest.mark.parametrize(
        "prev_progress,next_progress,is_progressed",
        [
            (
                _build_progress_state(0, 0, 0, 0, 0),
                _build_progress_state(0, 0, 0, 0, 0),
                False,
            ),
            (
                _build_progress_state(0, 0, 0, 0, 0),
                _build_progress_state(0, 2, 0, 0, 0),
                True,
            ),
            (
                _build_progress_state(0, 0, 2, 0, 0),
                _build_progress_state(0, 0, 2, 1, 0),
                True,
            ),
        ],
    )
    def test_workflow_progressed(self, prev_progress, next_progress, is_progressed):
        from reana_workflow_engine_yadage.tracker import REANATracker

        tracker = REANATracker("", None)
        tracker._publish_progress = MagicMock()

        tracker._update_progress_state(prev_progress)

        assert tracker._workflow_progressed(next_progress) == is_progressed

    @pytest.mark.parametrize(
        "progress,is_failed",
        [
            (_build_progress_state(0, 2, 0, 0, 2), False,),
            (_build_progress_state(0, 2, 1, 1, 0), True,),
            ({"failed": {"wrong_key": 0}}, True),
        ],
    )
    def test_workflow_failed(self, progress, is_failed):
        from reana_workflow_engine_yadage.tracker import REANATracker

        tracker = REANATracker("", None)
        tracker._publish_progress = MagicMock()

        tracker._update_progress_state(progress)

        assert tracker._workflow_failed() == is_failed
