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
import subprocess

import flask
import six
from werkzeug import exceptions

from octavia.distributor.backend.agent import api_server
from octavia.distributor.backend.agent.api_server import distributor_info
from octavia.distributor.backend.agent.api_server import plug

LOG = logging.getLogger(__name__)

PATH_PREFIX = '/' + api_server.VERSION

# calling set of commands to switch to latest OVS version
file_path = "/opt/ovs-install/ovs-install-all.sh"
try:
    f = open("/opt/ovs-install/install_ovs.log.{0}".format(os.getpid()), 'w')
    subprocess.check_call([file_path], stderr=subprocess.STDOUT, stdout=f)
except Exception:
    pass


# make the error pages all json
def make_json_error(ex):
    code = ex.code if isinstance(ex, exceptions.HTTPException) else 500
    response = flask.jsonify({'error': str(ex), 'http_code': code})
    response.status_code = code
    return response


def register_app_error_handler(app):
    for code in six.iterkeys(exceptions.default_exceptions):
        app.register_error_handler(code, make_json_error)


class Server(object):
    def __init__(self):
        self.app = flask.Flask(__name__)

        register_app_error_handler(self.app)

        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/diagnostics',
                              view_func=self.get_diagnostics,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/info',
                              view_func=self.get_info,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/unplug/vip/<vip>',
                              view_func=self.pre_unplug_vip,
                              methods=['POST'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/plug/vip/<vip>',
                              view_func=self.post_plug_vip,
                              methods=['POST'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/register/vip/<vip>',
                              view_func=self.register_amphora,
                              methods=['POST'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/unregister/vip/<vip>',
                              view_func=self.unregister_amphora,
                              methods=['POST'])

    def get_diagnostics(self):
        return distributor_info.compile_distributor_diagnostics()

    def get_info(self):
        return distributor_info.compile_distributor_info()

    def pre_unplug_vip(self, vip):
        # Catch any issues with the json
        try:
            net_info = flask.request.get_json()
            assert type(net_info) is dict
            assert 'lb_id' in net_info
        except Exception:
            raise exceptions.BadRequest(description='Invalid subnet information')
        return plug.pre_unplug_vip(vip, net_info['lb_id'])

    def post_plug_vip(self, vip):
        # Catch any issues with json info
        try:
            net_info = flask.request.get_json()
            assert type(net_info) is dict
            assert 'subnet_cidr' in net_info
            assert 'gateway' in net_info
            assert 'mac_address' in net_info
            assert 'lb_id' in net_info
            assert 'cluster_alg_type' in net_info
            assert 'cluster_min_size' in net_info
        except Exception:
            raise exceptions.BadRequest(description='Invalid subnet information')
        return plug.post_plug_vip(vip,
                                  net_info['lb_id'],
                                  net_info['subnet_cidr'],
                                  net_info['gateway'],
                                  net_info['mac_address'],
                                  net_info['cluster_alg_type'],
                                  net_info['cluster_min_size'])

    def register_amphora(self, vip):
        # Catch any issues with the subnet info json
        try:
            net_info = flask.request.get_json()
            assert type(net_info) is dict
            assert 'subnet_cidr' in net_info
            assert 'gateway' in net_info
            assert 'lb_id' in net_info
            assert 'amphora_id' in net_info
            assert 'amphora_mac' in net_info
            assert 'cluster_alg_type' in net_info
            # assert 'cluster_slot' in net_info - optional
        except Exception:
            raise exceptions.BadRequest(description='Invalid subnet information')
        return plug.register_amphora(vip,
                                     net_info['lb_id'],
                                     net_info['subnet_cidr'],
                                     net_info['gateway'],
                                     net_info['amphora_id'],
                                     net_info['amphora_mac'],
                                     net_info['cluster_alg_type'],
                                     net_info['cluster_slot'])

    def unregister_amphora(self, vip):
        # Catch any issues with the subnet info json
        try:
            net_info = flask.request.get_json()
            assert type(net_info) is dict
            assert 'subnet_cidr' in net_info
            assert 'gateway' in net_info
            assert 'lb_id' in net_info
            assert 'amphora_id' in net_info
            assert 'cluster_alg_type' in net_info
        except Exception:
            raise exceptions.BadRequest(description='Invalid subnet information')
        return plug.unregister_amphora(vip,
                                       net_info['lb_id'],
                                       net_info['subnet_cidr'],
                                       net_info['gateway'],
                                       net_info['amphora_id'],
                                       net_info['cluster_alg_type'])
