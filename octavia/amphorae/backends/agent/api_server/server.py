# Copyright 2015 Hewlett-Packard Development Company, L.P.
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


import flask
import six
from werkzeug import exceptions

from octavia.amphorae.backends.agent import api_server
from octavia.amphorae.backends.agent.api_server import amphora_info
from octavia.amphorae.backends.agent.api_server import certificate_update
from octavia.amphorae.backends.agent.api_server import keepalived
from octavia.amphorae.backends.agent.api_server import listener
from octavia.amphorae.backends.agent.api_server import osutils
from octavia.amphorae.backends.agent.api_server import plug

PATH_PREFIX = '/' + api_server.VERSION


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
        self._osutils = osutils.BaseOS.get_os_util()
        self._keepalived = keepalived.Keepalived()
        self._listener = listener.Listener()
        self._plug = plug.Plug(self._osutils)
        self._amphora_info = amphora_info.AmphoraInfo(self._osutils)

        register_app_error_handler(self.app)

        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/listeners/<amphora_id>/<listener_id>/haproxy',
                              view_func=self.upload_haproxy_config,
                              methods=['PUT'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/listeners/<listener_id>/haproxy',
                              view_func=self.get_haproxy_config,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX +
                              '/listeners/<listener_id>/<action>',
                              view_func=self.start_stop_listener,
                              methods=['PUT'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/listeners/<listener_id>',
                              view_func=self.delete_listener,
                              methods=['DELETE'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/details',
                              view_func=self.get_details,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/info',
                              view_func=self.get_info,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/listeners',
                              view_func=self.get_all_listeners_status,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/listeners/<listener_id>',
                              view_func=self.get_listener_status,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/listeners/<listener_id>'
                              '/certificates/<filename>',
                              view_func=self.upload_certificate,
                              methods=['PUT'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/listeners/<listener_id>'
                              '/certificates/<filename>',
                              view_func=self.get_certificate_md5,
                              methods=['GET'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/listeners/<listener_id>'
                              '/certificates/<filename>',
                              view_func=self.delete_certificate,
                              methods=['DELETE'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/plug/vip/<vip>',
                              view_func=self.plug_vip,
                              methods=['POST'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/plug/network',
                              view_func=self.plug_network,
                              methods=['POST'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/certificate',
                              view_func=self.upload_cert, methods=['PUT'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/vrrp/upload',
                              view_func=self.upload_vrrp_config,
                              methods=['PUT'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/vrrp/<action>',
                              view_func=self.manage_service_vrrp,
                              methods=['PUT'])
        self.app.add_url_rule(rule=PATH_PREFIX + '/interface/<ip_addr>',
                              view_func=self.get_interface,
                              methods=['GET'])

    def upload_haproxy_config(self, amphora_id, listener_id):
        return self._listener.upload_haproxy_config(amphora_id, listener_id)

    def get_haproxy_config(self, listener_id):
        return self._listener.get_haproxy_config(listener_id)

    def start_stop_listener(self, listener_id, action):
        return self._listener.start_stop_listener(listener_id, action)

    def delete_listener(self, listener_id):
        return self._listener.delete_listener(listener_id)

    def get_details(self):
        return self._amphora_info.compile_amphora_details()

    def get_info(self):
        return self._amphora_info.compile_amphora_info()

    def get_all_listeners_status(self):
        return self._listener.get_all_listeners_status()

    def get_listener_status(self, listener_id):
        return self._listener.get_listener_status(listener_id)

    def upload_certificate(self, listener_id, filename):
        return self._listener.upload_certificate(listener_id, filename)

    def get_certificate_md5(self, listener_id, filename):
        return self._listener.get_certificate_md5(listener_id, filename)

    def delete_certificate(self, listener_id, filename):
        return self._listener.delete_certificate(listener_id, filename)

    def plug_vip(self, vip):
        # Catch any issues with the subnet info json
        try:
            net_info = flask.request.get_json()
            assert type(net_info) is dict
            assert 'subnet_cidr' in net_info
            assert 'gateway' in net_info
            assert 'mac_address' in net_info
        except Exception:
            raise exceptions.BadRequest(
                description='Invalid subnet information')
        return self._plug.plug_vip(vip,
                                   net_info['subnet_cidr'],
                                   net_info['gateway'],
                                   net_info['mac_address'],
                                   net_info.get('mtu'),
                                   net_info.get('vrrp_ip'),
                                   net_info.get('host_routes'))

    def plug_network(self):
        try:
            port_info = flask.request.get_json()
            assert type(port_info) is dict
            assert 'mac_address' in port_info
        except Exception:
            raise exceptions.BadRequest(description='Invalid port information')
        return self._plug.plug_network(port_info['mac_address'],
                                       port_info.get('fixed_ips'),
                                       port_info.get('mtu'))

    def upload_cert(self):
        return certificate_update.upload_server_cert()

    def upload_vrrp_config(self):
        return self._keepalived.upload_keepalived_config()

    def manage_service_vrrp(self, action):
        return self._keepalived.manager_keepalived_service(action)

    def get_interface(self, ip_addr):
        return self._amphora_info.get_interface(ip_addr)
