#    Copyright 2014 Rackspace
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

import time

from neutronclient.common import exceptions as neutron_client_exceptions
from novaclient import exceptions as nova_client_exceptions
from oslo_config import cfg
from oslo_log import log as logging
import six

from octavia.common import clients
from octavia.common import constants
from octavia.common import data_models
from octavia.i18n import _LE, _LI, _LW
from octavia.network import base
from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import base as neutron_base
from octavia.network.drivers.neutron import utils

import ipaddress


LOG = logging.getLogger(__name__)
AAP_EXT_ALIAS = 'allowed-address-pairs'
VIP_SECURITY_GRP_PREFIX = 'lb-'
OCTAVIA_OWNER = 'Octavia'

CONF = cfg.CONF
CONF.import_group('nova', 'octavia.common.config')
CONF.import_group('controller_worker', 'octavia.common.config')
CONF.import_group('networking', 'octavia.common.config')


class AllowedAddressPairsDriver(neutron_base.BaseNeutronDriver):

    def __init__(self):
        super(AllowedAddressPairsDriver, self).__init__()
        self._check_aap_loaded()
        self.nova_client = clients.NovaAuth.get_nova_client(
            endpoint=CONF.nova.endpoint,
            region=CONF.nova.region_name,
            endpoint_type=CONF.nova.endpoint_type,
            service_name=CONF.nova.service_name,
            insecure=CONF.nova.insecure,
            cacert=CONF.nova.ca_certificates_file
        )

    def _check_aap_loaded(self):
        if not self._check_extension_enabled(AAP_EXT_ALIAS):
            raise base.NetworkException(
                'The {alias} extension is not enabled in neutron.  This '
                'driver cannot be used with the {alias} extension '
                'disabled.'.format(alias=AAP_EXT_ALIAS))

    def _get_interfaces_to_unplug(self, interfaces, network_id,
                                  ip_address=None):
        ret = []
        for interface in interfaces:
            if interface.network_id == network_id:
                if ip_address:
                    for fixed_ip in interface.fixed_ips:
                        if ip_address == fixed_ip.ip_address:
                            ret.append(interface)
                else:
                    ret.append(interface)
        return ret

    def _get_plugged_interface(self, compute_id, network_id):
        interfaces = self.get_plugged_networks(compute_id)
        for interface in interfaces:
            if interface.network_id == network_id:
                return interface

    def _plug_amphora_vip(self, amphora, network_id):
        # We need a vip port owned by Octavia for Act/Stby and failover
        try:
            port = {'port': {'name': 'octavia-lb-vrrp-' + amphora.id,
                             'network_id': network_id,
                             'admin_state_up': True,
                             'device_owner': OCTAVIA_OWNER}}
            new_port = self.neutron_client.create_port(port)
            new_port = utils.convert_port_dict_to_model(new_port)

            LOG.debug('Created vip port: {port_id} for amphora: {amp}'.format(
                port_id=new_port.id, amp=amphora.id))

            interface = self.plug_port(amphora, new_port)
        except Exception:
            message = _LE('Error plugging amphora (compute_id: {compute_id}) '
                          'into vip network {network_id}.').format(
                              compute_id=amphora.compute_id,
                              network_id=network_id)
            LOG.exception(message)
            raise base.PlugVIPException(message)
        return interface

    def _add_vip_address_pair(self, port_id, vip_address):
        try:
            self._add_allowed_address_pair_to_port(port_id, vip_address)
        except neutron_client_exceptions.PortNotFoundClient as e:
                raise base.PortNotFound(e.message)
        except Exception:
            message = _LE('Error adding allowed address pair {ip} '
                          'to port {port_id}.').format(ip=vip_address,
                                                       port_id=port_id)
            LOG.exception(message)
            raise base.PlugVIPException(message)

    def _get_lb_security_group(self, load_balancer_id):
        sec_grp_name = VIP_SECURITY_GRP_PREFIX + load_balancer_id
        sec_grps = self.neutron_client.list_security_groups(name=sec_grp_name)
        if sec_grps and sec_grps.get('security_groups'):
            return sec_grps.get('security_groups')[0]

    def _get_ethertype_for_ip(self, ip):
        address = ipaddress.ip_address(
            ip if six.text_type == type(ip) else six.u(ip))
        return 'IPv6' if address.version is 6 else 'IPv4'

    def _update_security_group_rules(self, load_balancer, sec_grp_id):
        rules = self.neutron_client.list_security_group_rules(
            security_group_id=sec_grp_id)
        updated_ports = [
            listener.protocol_port for listener in load_balancer.listeners
            if listener.provisioning_status != constants.PENDING_DELETE and
            listener.provisioning_status != constants.DELETED]
        peer_ports = [
            listener.peer_port for listener in load_balancer.listeners
            if listener.provisioning_status != constants.PENDING_DELETE and
            listener.provisioning_status != constants.DELETED]
        updated_ports.extend(peer_ports)
        # Just going to use port_range_max for now because we can assume that
        # port_range_max and min will be the same since this driver is
        # responsible for creating these rules
        old_ports = [rule.get('port_range_max')
                     for rule in rules.get('security_group_rules', [])
                     # Don't remove egress rules and don't
                     # confuse other protocols with None ports
                     # with the egress rules.  VRRP uses protocol
                     # 51 and 112
                     if rule.get('direction') != 'egress' and
                     rule.get('protocol').lower() == 'tcp']
        add_ports = set(updated_ports) - set(old_ports)
        del_ports = set(old_ports) - set(updated_ports)
        for rule in rules.get('security_group_rules', []):
            if rule.get('port_range_max') in del_ports:
                self.neutron_client.delete_security_group_rule(rule.get('id'))

        ethertype = self._get_ethertype_for_ip(load_balancer.vip.ip_address)
        for port in add_ports:
            self._create_security_group_rule(sec_grp_id, 'TCP', port_min=port,
                                             port_max=port,
                                             ethertype=ethertype)

        # Currently we are using the VIP network for VRRP
        # so we need to open up the protocols for it
        if (CONF.controller_worker.loadbalancer_topology ==
                constants.TOPOLOGY_ACTIVE_STANDBY):
            try:
                self._create_security_group_rule(
                    sec_grp_id,
                    constants.VRRP_PROTOCOL_NUM,
                    direction='ingress',
                    ethertype=ethertype)
            except neutron_client_exceptions.Conflict:
                # It's ok if this rule already exists
                pass
            except Exception as e:
                raise base.PlugVIPException(str(e))

            try:
                self._create_security_group_rule(
                    sec_grp_id, constants.AUTH_HEADER_PROTOCOL_NUMBER,
                    direction='ingress', ethertype=ethertype)
            except neutron_client_exceptions.Conflict:
                # It's ok if this rule already exists
                pass
            except Exception as e:
                raise base.PlugVIPException(str(e))

    def _update_vip_security_group(self, load_balancer, vip):
        sec_grp = self._get_lb_security_group(load_balancer.id)
        if not sec_grp:
            sec_grp_name = VIP_SECURITY_GRP_PREFIX + load_balancer.id
            sec_grp = self._create_security_group(sec_grp_name)
        self._update_security_group_rules(load_balancer, sec_grp.get('id'))
        self._add_vip_security_group_to_port(load_balancer.id, vip.port_id,
                                             sec_grp.get('id'))

    def _add_vip_security_group_to_port(self, load_balancer_id, port_id,
                                        sec_grp_id=None):
        sec_grp_id = (sec_grp_id or
                      self._get_lb_security_group(load_balancer_id).get('id'))
        try:
            self._add_security_group_to_port(sec_grp_id, port_id)
        except base.PortNotFound:
            raise
        except base.NetworkException as e:
            raise base.PlugVIPException(str(e))

    def _delete_vip_security_group(self, sec_grp):
        """Deletes a security group in neutron.

        Retries upon an exception because removing a security group from
        a neutron port does not happen immediately.
        """
        attempts = 0
        while attempts <= CONF.networking.max_retries:
            try:
                self.neutron_client.delete_security_group(sec_grp)
                LOG.info(_LI("Deleted security group %s"), sec_grp)
                return
            except neutron_client_exceptions.NotFound:
                LOG.info(_LI("Security group %s not found, will assume it is "
                             "already deleted"), sec_grp)
                return
            except Exception:
                LOG.warning(_LW("Attempt %(attempt)s to remove security group "
                                "%(sg)s failed."),
                            {'attempt': attempts + 1, 'sg': sec_grp})
            attempts += 1
            time.sleep(CONF.networking.retry_interval)
        message = _LE("All attempts to remove security group {0} have "
                      "failed.").format(sec_grp)
        LOG.exception(message)
        raise base.DeallocateVIPException(message)

    @staticmethod
    def _filter_amphora(amp):
        return amp.status == constants.AMPHORA_ALLOCATED

    def _delete_security_group(self, vip, port):
        if self.sec_grp_enabled:
            sec_grp = self._get_lb_security_group(vip.load_balancer.id)
            if sec_grp:
                sec_grp = sec_grp.get('id')
                LOG.info(
                    _LI("Removing security group %(sg)s from port %(port)s"),
                    {'sg': sec_grp, 'port': vip.port_id})
                raw_port = self.neutron_client.show_port(port.id)
                sec_grps = raw_port.get('port', {}).get('security_groups', [])
                if sec_grp in sec_grps:
                    sec_grps.remove(sec_grp)
                port_update = {'port': {'security_groups': sec_grps}}
                self.neutron_client.update_port(port.id, port_update)
                self._delete_vip_security_group(sec_grp)

    def deallocate_vip(self, vip):
        """Delete the vrrp_port (instance port) in case nova didn't

        This can happen if a failover has occurred.
        """
        try:
            for amphora in six.moves.filter(self._filter_amphora,
                                            vip.load_balancer.amphorae):
                self.neutron_client.delete_port(amphora.vrrp_port_id)
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient):
            LOG.debug('VIP instance port {0} already deleted.  '
                      'Skipping.'.format(amphora.vrrp_port_id))

        try:
            port = self.get_port(vip.port_id)
        except base.PortNotFound:
            msg = ("Can't deallocate VIP because the vip port {0} cannot be "
                   "found in neutron".format(vip.port_id))
            raise base.VIPConfigurationNotFound(msg)

        self._delete_security_group(vip, port)

        if port.device_owner == OCTAVIA_OWNER:
            try:
                self.neutron_client.delete_port(vip.port_id)
            except Exception:
                message = _LE('Error deleting VIP port_id {port_id} from '
                              'neutron').format(port_id=vip.port_id)
                LOG.exception(message)
                raise base.DeallocateVIPException(message)
        else:
            LOG.info(_LI("Port %s will not be deleted by Octavia as it was "
                         "not created by Octavia."), vip.port_id)

    def plug_vip(self, load_balancer, vip):
        if self.sec_grp_enabled:
            self._update_vip_security_group(load_balancer, vip)
        plugged_amphorae = []
        subnet = self.get_subnet(vip.subnet_id)
        for amphora in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                load_balancer.amphorae):

            interface = self._get_plugged_interface(amphora.compute_id,
                                                    subnet.network_id)
            if not interface:
                interface = self._plug_amphora_vip(amphora, subnet.network_id)

            self._add_vip_address_pair(interface.port_id, vip.ip_address)
            if self.sec_grp_enabled:
                self._add_vip_security_group_to_port(load_balancer.id,
                                                     interface.port_id)
            vrrp_ip = None
            for fixed_ip in interface.fixed_ips:
                if fixed_ip.subnet_id == subnet.id:
                    vrrp_ip = fixed_ip.ip_address
                    break
            plugged_amphorae.append(data_models.Amphora(
                id=amphora.id,
                compute_id=amphora.compute_id,
                vrrp_ip=vrrp_ip,
                ha_ip=vip.ip_address,
                vrrp_port_id=interface.port_id,
                ha_port_id=vip.port_id))
        return plugged_amphorae

    def allocate_vip(self, load_balancer):
        if not load_balancer.vip.port_id and not load_balancer.vip.subnet_id:
            raise base.AllocateVIPException('Cannot allocate a vip '
                                            'without a port_id or '
                                            'a subnet_id.')
        if load_balancer.vip.port_id:
            LOG.info(_LI('Port %s already exists. Nothing to be done.'),
                     load_balancer.vip.port_id)
            port = self.get_port(load_balancer.vip.port_id)
            return self._port_to_vip(port, load_balancer)

        # Must retrieve the network_id from the subnet
        subnet = self.get_subnet(load_balancer.vip.subnet_id)

        # It can be assumed that network_id exists
        port = {'port': {'name': 'octavia-lb-' + load_balancer.id,
                         'network_id': subnet.network_id,
                         'admin_state_up': False,
                         'device_id': 'lb-{0}'.format(load_balancer.id),
                         'device_owner': OCTAVIA_OWNER}}
        try:
            new_port = self.neutron_client.create_port(port)
        except Exception:
            message = _LE('Error creating neutron port on network '
                          '{network_id}.').format(
                network_id=subnet.network_id)
            LOG.exception(message)
            raise base.AllocateVIPException(message)
        new_port = utils.convert_port_dict_to_model(new_port)
        return self._port_to_vip(new_port, load_balancer)

    def unplug_vip(self, load_balancer, vip):
        try:
            subnet = self.get_subnet(vip.subnet_id)
        except base.SubnetNotFound:
            msg = _LE("Can't unplug vip because vip subnet {0} was not "
                      "found").format(vip.subnet_id)
            LOG.exception(msg)
            raise base.PluggedVIPNotFound(msg)
        for amphora in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                load_balancer.amphorae):

            interface = self._get_plugged_interface(amphora.compute_id,
                                                    subnet.network_id)
            if not interface:
                # Thought about raising PluggedVIPNotFound exception but
                # then that wouldn't evaluate all amphorae, so just continue
                LOG.debug(_LI('Cannot get amphora %s interface, skipped'),
                          amphora.compute_id)
                continue
            try:
                self.unplug_network(amphora.compute_id, subnet.network_id)
            except Exception:
                pass
            try:
                aap_update = {'port': {
                    'allowed_address_pairs': []
                }}
                self.neutron_client.update_port(interface.port_id,
                                                aap_update)
            except Exception:
                message = _LE('Error unplugging VIP. Could not clear '
                              'allowed address pairs from port '
                              '{port_id}.').format(port_id=vip.port_id)
                LOG.exception(message)
                raise base.UnplugVIPException(message)

            # Delete the VRRP port if we created it
            try:
                port = self.get_port(amphora.vrrp_port_id)
                if port.name.startswith('octavia-lb-vrrp-'):
                    self.neutron_client.delete_port(amphora.vrrp_port_id)
            except base.PortNotFound:
                pass
            except Exception as e:
                LOG.error(_LE('Failed to delete port.  Resources may still '
                              'be in use for port: %(port)s due to '
                              'error: %s(except)s'),
                          {'port': amphora.vrrp_port_id, 'except': e})

    def plug_network(self, compute_id, network_id, ip_address=None):
        try:
            interface = self.nova_client.servers.interface_attach(
                server=compute_id, net_id=network_id, fixed_ip=ip_address,
                port_id=None)
        except nova_client_exceptions.NotFound as e:
            if 'Instance' in e.message:
                raise base.AmphoraNotFound(e.message)
            elif 'Network' in e.message:
                raise base.NetworkNotFound(e.message)
            else:
                raise base.PlugNetworkException(e.message)
        except Exception:
            message = _LE('Error plugging amphora (compute_id: {compute_id}) '
                          'into network {network_id}.').format(
                              compute_id=compute_id,
                              network_id=network_id)
            LOG.exception(message)
            raise base.PlugNetworkException(message)

        return self._nova_interface_to_octavia_interface(compute_id, interface)

    def unplug_network(self, compute_id, network_id, ip_address=None):
        interfaces = self.get_plugged_networks(compute_id)
        if not interfaces:
            msg = ('Amphora with compute id {compute_id} does not have any '
                   'plugged networks').format(compute_id=compute_id)
            raise base.AmphoraNotFound(msg)

        unpluggers = self._get_interfaces_to_unplug(interfaces, network_id,
                                                    ip_address=ip_address)
        try:
            for index, unplugger in enumerate(unpluggers):
                self.nova_client.servers.interface_detach(
                    server=compute_id, port_id=unplugger.port_id)
        except Exception:
            message = _LE('Error unplugging amphora {amphora_id} from network '
                          '{network_id}.').format(amphora_id=compute_id,
                                                  network_id=network_id)
            if len(unpluggers) > 1:
                message = _LE('{base} Other interfaces have been successfully '
                              'unplugged: ').format(base=message)
                unpluggeds = unpluggers[:index]
                for unplugged in unpluggeds:
                    message = _LE('{base} neutron port '
                                  '{port_id} ').format(
                                      base=message, port_id=unplugged.port_id)
            else:
                message = _LE('{base} No other networks were '
                              'unplugged.').format(base=message)
            LOG.exception(message)
            raise base.UnplugNetworkException(message)

    def update_vip(self, load_balancer):
        sec_grp = self._get_lb_security_group(load_balancer.id)
        self._update_security_group_rules(load_balancer, sec_grp.get('id'))

    def failover_preparation(self, amphora):
        interfaces = self.get_plugged_networks(compute_id=amphora.compute_id)

        ports = []
        for interface_ in interfaces:
            port = self.get_port(port_id=interface_.port_id)
            ips = port.fixed_ips
            lb_network = False
            for ip in ips:
                if ip.ip_address == amphora.lb_network_ip:
                    lb_network = True
            if not lb_network:
                ports.append(port)

        for port in ports:
            try:

                if self.dns_integration_enabled:
                    self.neutron_client.update_port(port.id,
                                                    {'port': {'dns_name': ''}})

            except (neutron_client_exceptions.NotFound,
                    neutron_client_exceptions.PortNotFoundClient):
                raise base.PortNotFound()

    def plug_port(self, amphora, port):
        plugged_interface = None
        try:
            interface = self.nova_client.servers.interface_attach(
                server=amphora.compute_id, net_id=None,
                fixed_ip=None, port_id=port.id)
            plugged_interface = self._nova_interface_to_octavia_interface(
                amphora.compute_id, interface)
        except nova_client_exceptions.NotFound as e:
            if 'Instance' in e.message:
                raise base.AmphoraNotFound(e.message)
            elif 'Network' in e.message:
                raise base.NetworkNotFound(e.message)
            else:
                raise base.PlugNetworkException(e.message)
        except nova_client_exceptions.Conflict:
            LOG.info(_LI('Port %(portid)s is already plugged, '
                     'skipping') % {'portid': port.id})
            plugged_interface = n_data_models.Interface(
                compute_id=amphora.compute_id,
                network_id=port.network_id,
                port_id=port.id,
                fixed_ips=port.fixed_ips)
        except Exception:
            message = _LE('Error plugging amphora (compute_id: '
                          '{compute_id}) into port '
                          '{port_id}.').format(
                              compute_id=amphora.compute_id,
                              port_id=port.id)
            LOG.exception(message)
            raise base.PlugNetworkException(message)

        return plugged_interface

    def get_network_configs(self, loadbalancer):
        vip_subnet = self.get_subnet(loadbalancer.vip.subnet_id)
        vip_port = self.get_port(loadbalancer.vip.port_id)
        amp_configs = {}
        for amp in loadbalancer.amphorae:
            if amp.status != constants.DELETED:
                LOG.debug("Retrieving network details for amphora %s", amp.id)
                vrrp_port = self.get_port(amp.vrrp_port_id)
                vrrp_subnet = self.get_subnet(
                    vrrp_port.get_subnet_id(amp.vrrp_ip))
                ha_port = self.get_port(amp.ha_port_id)
                ha_subnet = self.get_subnet(
                    ha_port.get_subnet_id(amp.ha_ip))

                amp_configs[amp.id] = n_data_models.AmphoraNetworkConfig(
                    amphora=amp,
                    vip_subnet=vip_subnet,
                    vip_port=vip_port,
                    vrrp_subnet=vrrp_subnet,
                    vrrp_port=vrrp_port,
                    ha_subnet=ha_subnet,
                    ha_port=ha_port
                )
        return amp_configs

    def wait_for_port_detach(self, amphora):
        """Waits for the amphora ports device_id to be unset.

        This method waits for the ports on an amphora device_id
        parameter to be '' or None which signifies that nova has
        finished detaching the port from the instance.

        :param amphora: Amphora to wait for ports to detach.
        :returns: None
        :raises TimeoutException: Port did not detach in interval.
        :raises PortNotFound: Port was not found by neutron.
        """
        interfaces = self.get_plugged_networks(compute_id=amphora.compute_id)

        ports = []
        port_detach_timeout = CONF.networking.port_detach_timeout
        for interface_ in interfaces:
            port = self.get_port(port_id=interface_.port_id)
            ips = port.fixed_ips
            lb_network = False
            for ip in ips:
                if ip.ip_address == amphora.lb_network_ip:
                    lb_network = True
            if not lb_network:
                ports.append(port)

        for port in ports:
            try:
                neutron_port = self.neutron_client.show_port(
                    port.id).get('port')
                device_id = neutron_port['device_id']
                start = int(time.time())

                while device_id:
                    time.sleep(CONF.networking.retry_interval)
                    neutron_port = self.neutron_client.show_port(
                        port.id).get('port')
                    device_id = neutron_port['device_id']

                    timed_out = int(time.time()) - start >= port_detach_timeout

                    if device_id and timed_out:
                        message = ('Port %s failed to detach (device_id %s) '
                                   'within the required time (%s s).' %
                                   (port.id, device_id, port_detach_timeout))
                        raise base.TimeoutException(message)

            except (neutron_client_exceptions.NotFound,
                    neutron_client_exceptions.PortNotFoundClient):
                    pass
