# Copyright 2016 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import time

from oslo_config import cfg
from oslo_log import log as logging
import six

from octavia.amphorae.backends.health_daemon import health_sender
from octavia.i18n import _LI
from octavia.distributor.backend.agent.api_server.open_flow import (
    get_status_from_ovs)

if six.PY2:
    import Queue as queue
else:
    import queue

CONF = cfg.CONF
CONF.import_group('distributor_agent', 'octavia.common.config')
CONF.import_group('distributor', 'octavia.common.config')
CONF.import_group('health_manager', 'octavia.common.config')
LOG = logging.getLogger(__name__)
SEQ = 0


def run_sender(cmd_queue):
    LOG.info(_LI('Distributor Health Manager Sender starting.'))
    sender = health_sender.UDPStatusSender()
    while True:
        message = build_distributor_message()
        sender.dosend(message)
        try:
            cmd = cmd_queue.get_nowait()
            if cmd is 'reload':
                LOG.info(_LI('Reloading configuration'))
                CONF.reload_config_files()
            elif cmd is 'shutdown':
                LOG.info(_LI(
                    'Distributor Health Manager Sender shutting down.'))
                break
        except queue.Empty:
            pass
        time.sleep(CONF.health_manager.heartbeat_interval)


def build_distributor_message():
    global SEQ
    msg = {'distributor-id': CONF.distributor_agent.distributor_id,
           'seq': SEQ,
           'provisioning-state': {},
           'loadbalancers': {},
           }
    SEQ += 1
    try:
        msg.update(get_status_from_ovs())
    except:
        pass
    return msg