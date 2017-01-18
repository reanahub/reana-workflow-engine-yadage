from celery import signals
import zmq


ZMQ_SOCKET_LINGER = 100
context = zmq.Context()
context.linger = ZMQ_SOCKET_LINGER

import logging
log = logging.getLogger(__name__)

def reset_zmq_context(**kwargs):
    log.debug("Resetting ZMQ Context")
    reset_context()

signals.worker_process_init.connect(reset_zmq_context)


def get_context():
    global context
    if context.closed:
        context = zmq.Context()
        context.linger = ZMQ_SOCKET_LINGER
    return context

def reset_context():
    global context
    context.term()
    context = zmq.Context()
    context.linger = ZMQ_SOCKET_LINGER
