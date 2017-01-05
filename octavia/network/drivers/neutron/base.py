#    Copyright 2015 Rackspace
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from neutronclient.common import exceptions as neutron_client_exceptions
from oslo_config import cfg
from oslo_log import log as logging

from octavia.common import clients
from octavia.common import data_models
from octavia.network import base
from octavia.network import data_models as network_models
from octavia.network.drivers.neutron import utils


LOG = logging.getLogger(__name__)
DNS_INT_EXT_ALIAS = 'dns-integration'
SEC_GRP_EXT_ALIAS = 'security-group'

CONF = cfg.CONF


class BaseNeutronDriver(base.AbstractNetworkDriver):

    def __init__(self):
        self.neutron_client = clients.NeutronAuth.get_neutron_client(
            endpoint=CONF.neutron.endpoint,
            region=CONF.neutron.region_name,
            endpoint_type=CONF.neutron.endpoint_type,
            service_name=CONF.neutron.service_name,
            insecure=CONF.neutron.insecure,
            ca_cert=CONF.neutron.ca_certificates_file
        )
        self._check_extension_cache = {}
        self.sec_grp_enabled = self._check_extension_enabled(SEC_GRP_EXT_ALIAS)
        self.dns_integration_enabled = self._check_extension_enabled(
            DNS_INT_EXT_ALIAS)

    def _check_extension_enabled(self, extension_alias):
        if extension_alias in self._check_extension_cache:
            status = self._check_extension_cache[extension_alias]
            LOG.debug('Neutron extension {ext} cached as {status}'.format(
                ext=extension_alias,
                status='enabled' if status else 'disabled'))
        else:
            try:
                self.neutron_client.show_extension(extension_alias)
                LOG.debug('Neutron extension {ext} found enabled'.format(
                    ext=extension_alias))
                self._check_extension_cache[extension_alias] = True
            except neutron_client_exceptions.NotFound:
                LOG.debug('Neutron extension {ext} is not enabled'.format(
                    ext=extension_alias))
                self._check_extension_cache[extension_alias] = False
        return self._check_extension_cache[extension_alias]

    def _port_to_vip(self, port, load_balancer):
        fixed_ip = None
        for port_fixed_ip in port.fixed_ips:
            if port_fixed_ip.subnet_id == load_balancer.vip.subnet_id:
                fixed_ip = port_fixed_ip
                break
        return data_models.Vip(ip_address=fixed_ip.ip_address,
                               subnet_id=fixed_ip.subnet_id,
                               port_id=port.id,
                               load_balancer=load_balancer,
                               load_balancer_id=load_balancer.id)

    def _nova_interface_to_octavia_interface(self, compute_id, nova_interface):
        fixed_ips = [utils.convert_fixed_ip_dict_to_model(fixed_ip)
                     for fixed_ip in nova_interface.fixed_ips]
        return network_models.Interface(compute_id=compute_id,
                                        network_id=nova_interface.net_id,
                                        port_id=nova_interface.port_id,
                                        fixed_ips=fixed_ips)

    def _port_to_octavia_interface(self, compute_id, port):
        fixed_ips = [utils.convert_fixed_ip_dict_to_model(fixed_ip)
                     for fixed_ip in port.get('fixed_ips', [])]
        return network_models.Interface(compute_id=compute_id,
                                        network_id=port['network_id'],
                                        port_id=port['id'],
                                        fixed_ips=fixed_ips)

    def _add_allowed_address_pair_to_port(self, port_id, ip_address):
        aap = {
            'port': {
                'allowed_address_pairs': [
                    {'ip_address': ip_address}
                ]
            }
        }
        self.neutron_client.update_port(port_id, aap)

    def _add_security_group_to_port(self, sec_grp_id, port_id):
        port_update = {'port': {'security_groups': [sec_grp_id]}}
        try:
            self.neutron_client.update_port(port_id, port_update)
        except neutron_client_exceptions.PortNotFoundClient as e:
            raise base.PortNotFound(e.message)
        except Exception as e:
            raise base.NetworkException(str(e))

    def _create_security_group(self, name):
        new_sec_grp = {'security_group': {'name': name}}
        sec_grp = self.neutron_client.create_security_group(new_sec_grp)
        return sec_grp['security_group']

    def _create_security_group_rule(self, sec_grp_id, protocol,
                                    direction='ingress', port_min=None,
                                    port_max=None, ethertype='IPv6'):
        rule = {
            'security_group_rule': {
                'security_group_id': sec_grp_id,
                'direction': direction,
                'protocol': protocol,
                'port_range_min': port_min,
                'port_range_max': port_max,
                'ethertype': ethertype,
            }
        }
        self.neutron_client.create_security_group_rule(rule)

    def get_plugged_networks(self, compute_id):
        # List neutron ports associated with the Amphora
        try:
            ports = self.neutron_client.list_ports(device_id=compute_id)
        except Exception:
            LOG.debug('Error retrieving plugged networks for compute '
                      'device %s.', compute_id)
            ports = {'ports': []}
        return [self._port_to_octavia_interface(
                compute_id, port) for port in ports['ports']]

    def _get_resource(self, resource_type, resource_id):
        try:
            resource = getattr(self.neutron_client, 'show_%s' %
                               resource_type)(resource_id)
            return getattr(utils, 'convert_%s_dict_to_model' %
                           resource_type)(resource)
        except neutron_client_exceptions.NotFound:
            message = _('{resource_type} not found '
                        '({resource_type} id: {resource_id}.').format(
                resource_type=resource_type, resource_id=resource_id)
            raise getattr(base, '%sNotFound' %
                          resource_type.capitalize())(message)
        except Exception:
            message = _('Error retrieving {resource_type} '
                        '({resource_type} id: {resource_id}.').format(
                resource_type=resource_type, resource_id=resource_id)
            LOG.exception(message)
            raise base.NetworkException(message)

    def _get_resource_by_filters(self, resource_type, **filters):
        # Filter items are unique, return the filtered item from the list.
        try:
            resource = getattr(self.neutron_client, 'list_%ss' %
                               resource_type)(**filters)
            resource = resource['%ss' % resource_type][0]
            return getattr(utils, 'convert_%s_dict_to_model' %
                           resource_type)(resource)
        except neutron_client_exceptions.NotFound:
            message = _('{resource_type} not found '
                        '({resource_type} Filters: {filters}.').format(
                resource_type=resource_type, filters=filters)
            LOG.exception(message)
            raise getattr(base, '%sNotFound' %
                          resource_type.capitalize())(message)
        except Exception:
            message = _('Error retrieving {resource_type} '
                        '({resource_type} Filters: {filters}.').format(
                resource_type=resource_type, filters=filters)
            LOG.exception(message)
            raise base.NetworkException(message)

    def get_network(self, network_id):
        return self._get_resource('network', network_id)

    def get_subnet(self, subnet_id):
        return self._get_resource('subnet', subnet_id)

    def get_port(self, port_id):
        return self._get_resource('port', port_id)

    def get_network_by_name(self, network_name):
        return self._get_resource_by_filters('network', name=network_name)

    def get_subnet_by_name(self, subnet_name):
        return self._get_resource_by_filters('subnet', name=subnet_name)

    def get_port_by_name(self, port_name):
        return self._get_resource_by_filters('port', name=port_name)

    def get_port_by_net_id_device_id(self, network_id, device_id):
        return self._get_resource_by_filters('port',
                                             network_id=network_id,
                                             device_id=device_id)
