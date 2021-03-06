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

import logging
import os
import re
import socket
import subprocess

import flask
import netifaces

from octavia.common import constants as consts
from octavia.distributor.backend.agent import api_server

LOG = logging.getLogger(__name__)


def compile_distributor_info():
    return flask.jsonify(
        {'hostname': socket.gethostname(),
         'api_version': api_server.VERSION})


def compile_distributor_diagnostics():
    meminfo = _get_meminfo()
    cpu = _cpu()
    st = os.statvfs('/')
    return flask.jsonify(
        {'hostname': socket.gethostname(),
         'api_version': api_server.VERSION,
         'networks': _get_networks(),
         'active': True,
         'cpu': {
             'total': cpu['total'],
             'user': cpu['user'],
             'system': cpu['system'],
             'soft_irq': cpu['softirq'], },
         'memory': {
             'total': meminfo['MemTotal'],
             'free': meminfo['MemFree'],
             'buffers': meminfo['Buffers'],
             'cached': meminfo['Cached'],
             'swap_used': meminfo['SwapCached'],
             'shared': meminfo['Shmem'],
             'slab': meminfo['Slab'], },
         'disk': {
             'used': (st.f_blocks - st.f_bfree) * st.f_frsize,
             'available': st.f_bavail * st.f_frsize},
         'load': [
             _load()],
         'topology': consts.TOPOLOGY_SINGLE,
         'topology_status': consts.TOPOLOGY_STATUS_OK,
         'packages': {}})


def _get_version_of_installed_package(name):
    cmd = "dpkg --status " + name
    out = subprocess.check_output(cmd.split())
    m = re.search('Version: .*', out)
    return m.group(0)[len('Version: '):]


def _get_network_bytes(interface, byte_type):
    file_name = "/sys/class/net/{interface}/statistics/{type}_bytes".format(
        interface=interface, type=byte_type)
    with open(file_name, 'r') as f:
        return f.readline()


def _get_meminfo():
    re_parser = re.compile(r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB')
    result = dict()
    for line in open('/proc/meminfo'):
        match = re_parser.match(line)
        if not match:
            continue  # skip lines that don't parse
        key, value = match.groups(['key', 'value'])
        result[key] = int(value)
    return result


def _cpu():
    with open('/proc/stat') as f:
        cpu = f.readline()
        vals = cpu.split(' ')
        return {
            'user': vals[2],
            'nice': vals[3],
            'system': vals[4],
            'idle': vals[5],
            'iowait': vals[6],
            'irq': vals[7],
            'softirq': vals[8],
            'total': sum([int(i) for i in vals[2:]])
        }


def _load():
    with open('/proc/loadavg') as f:
        load = f.readline()
        vals = load.split(' ')
        return vals[:3]


def _get_networks():
    networks = dict()
    for interface in netifaces.interfaces():
        if not interface.startswith('eth') or ":" in interface:
            continue
        networks[interface] = dict(
            network_tx=_get_network_bytes(interface, 'tx'),
            network_rx=_get_network_bytes(interface, 'rx'))
    return networks
