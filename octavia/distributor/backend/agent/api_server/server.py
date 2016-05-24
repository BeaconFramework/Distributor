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

import flask
import six
from werkzeug import exceptions

from octavia.distributor.backend.agent import api_server
from octavia.distributor.backend.agent.api_server import distributor_info
from octavia.distributor.backend.agent.api_server import plug

LOG = logging.getLogger(__name__)

app = flask.Flask(__name__)


# make the error pages all json
def make_json_error(ex):
    code = ex.code if isinstance(ex, exceptions.HTTPException) else 500
    response = flask.jsonify({'error': str(ex), 'http_code': code})
    response.status_code = code
    return response


for code in six.iterkeys(exceptions.default_exceptions):
    app.error_handler_spec[None][code] = make_json_error


@app.route('/' + api_server.VERSION + '/diagnostics',
           methods=['GET'])
def get_diagnostics():
    return distributor_info.compile_distributor_diagnostics()


@app.route('/' + api_server.VERSION + '/info',
           methods=['GET'])
def get_info():
    return distributor_info.compile_distributor_info()


@app.route('/' + api_server.VERSION + '/unplug/vip/<vip>', methods=['POST'])
def pre_unplug_vip(vip):
    # Catch any issues with the json
    try:
        net_info = flask.request.get_json()
        assert type(net_info) is dict
        assert 'lb_id' in net_info
    except Exception:
        raise exceptions.BadRequest(description='Invalid subnet information')
    return plug.pre_unplug_vip(vip,
                               net_info['lb_id'])


@app.route('/' + api_server.VERSION + '/plug/vip/<vip>', methods=['POST'])
def post_plug_vip(vip):
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


@app.route('/' + api_server.VERSION + '/register/vip/<vip>', methods=['POST'])
def register_amphora(vip):
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
        assert 'cluster_min_size' in net_info
    except Exception:
        raise exceptions.BadRequest(description='Invalid subnet information')
    return plug.register_amphora(vip,
                                 net_info['lb_id'],
                                 net_info['subnet_cidr'],
                                 net_info['gateway'],
                                 net_info['amphora_id'],
                                 net_info['amphora_mac'],
                                 net_info['cluster_alg_type'],
                                 net_info['cluster_min_size'])


@app.route('/' + api_server.VERSION + '/unregister/vip/<vip>',
           methods=['POST'])
def unregister_amphora(vip):
    # Catch any issues with the subnet info json
    try:
        net_info = flask.request.get_json()
        assert type(net_info) is dict
        assert 'subnet_cidr' in net_info
        assert 'gateway' in net_info
        assert 'lb_id' in net_info
        assert 'amphora_id' in net_info
        assert 'cluster_alg_type' in net_info
        assert 'cluster_min_size' in net_info
    except Exception:
        raise exceptions.BadRequest(description='Invalid subnet information')
    return plug.unregister_amphora(vip,
                                   net_info['lb_id'],
                                   net_info['subnet_cidr'],
                                   net_info['gateway'],
                                   net_info['amphora_id'],
                                   net_info['cluster_alg_type'],
                                   net_info['cluster_min_size'])
