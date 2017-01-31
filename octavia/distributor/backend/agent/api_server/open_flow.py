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
import subprocess
import shlex
import six
import netifaces
import netaddr
import base64
import json
from netaddr.core import AddrFormatError, AddrConversionError
from time import sleep
from octavia.i18n import _, _LE, _LW, _LI
from octavia.common.constants import (
    # alg type
    ALG_ACTIVE_ACTIVE,
    # instance operating statuses
    ONLINE,
    DEGRADED,
    ERROR,
    NO_MONITOR,
    # service provisioning statuses
    DISTRIBUTOR_BOOTING,  # building
    DISTRIBUTOR_ACTIVE,
    DISTRIBUTOR_FULL,  # working but cannot create new instances
    DISTRIBUTOR_ERROR,
)


LOG = logging.getLogger(__name__)

# configuration constants
OF_VERSION = 'OpenFlow15'
OVS_CMD_TIMEOUT = 10  # type: int
BR_NAME_FORMAT = 'vip-{}'
BR_NAME_LENGTH = 14
SLOT_KEY_FORMAT = 'slot-{}'
WAIT_FOR_OVS_RETRIES = 5  # careful, exponential back-off
MAX_DISTRIBUTORS = 128
MAX_CLUSTER_SIZE = 512

# internal constants
HASH_SRC_PORT = {4: ('ip_src', 'tcp_src'), 6: ('ipv6_src', 'tcp_src')}
HASH_SRC_ONLY = {4: ('ip_src',), 6: ('ipv6_src',)}
DST_GROUPS_OFFSET = 100
SELECT_GROUP_ID = 1
PRIORITY_LOW = 0
PRIORITY_MED = 100
OS_ERROR_CODE = 666

# vsctl command string formats
VSCTL_RUN = 'sudo ovs-vsctl -t {timeout} --retry'
VSCTL_INIT = 'sudo ovs-vsctl init'
VSCTL_LIST = 'list-br'
VSCTL_JSON_FORMAT = '-f json'
VSCTL_ADD_BR = '--may-exist add-br {distributor.bridge}'
VSCTL_DEL_BR = '--if-exists del-br {}'
VSCTL_SET_PROTOCOL = ('set bridge {distributor.bridge}'
                      ' protocols={distributor.of_version}')
VSCTL_GET_BRPORT = 'get Interface {distributor.bridge} ofport'
VSCTL_GET_IFPORT = 'get Interface {distributor.iface} ofport'
VSCTL_ADD_PORT = ('--may-exist add-port {distributor.bridge}'
                  ' {distributor.iface}')
VSCTL_REQUEST_PORT = ('set interface {distributor.iface}'
                      ' ofport_request={port}')
VSCTL_DEL_PORT = ('--if-exists --with-iface del-port'
                  ' {distributor.bridge} {distributor.iface}')
VSCTL_SET_EXTERNAL_ID = ('br-set-external-id {distributor.bridge}'
                         ' {key} {value}')
VSCTL_DEL_EXTERNAL_ID = ('br-set-external-id {distributor.bridge}'
                         ' {key}')
VSCTL_GET_EXTERNAL_ID = ('br-get-external-id {distributor.bridge}'
                         ' {key}')
VSCTL_FIND_EXTERNAL_ID = ('--columns=name,external_ids find Bridge'
                          ' external_ids:{key}={value}')
VSCTL_LIST_EXTERNAL_ID = '--columns=name,external_ids list Bridge'
VSCTL_SET_SERVER_EX_ID = 'set Open_vSwitch . external_ids:{key}={value}'
VSCTL_GET_SERVER_EX_ID = ('--if-exists get Open_vSwitch . '
                          'external_ids:{key}')
# ofctl command string formats
OFCTL_RUN = 'sudo ovs-ofctl -O {of_version} -t {timeout}'
OFCTL_IFUP = 'mod-port {distributor.bridge} {distributor.ofport} up'
OFCTL_IFDOWN = 'mod-port {distributor.bridge} {distributor.ofport} down'
OFCTL_ADD_FLOW_STDIN = '--bundle add-flow {distributor.bridge} -'
OFCTL_ADD_GROUP_STDIN = '--bundle add-group {distributor.bridge} -'
OFCTL_MOD_GROUP_STDIN = '--bundle mod-group {distributor.bridge} -'
OFCTL_DEL_FLOWS = 'del-flows {distributor.bridge}'


class DistributorError(Exception):
    """Error in OVS controller operation."""
    code = 500
    title = _('Unknown Server Error')


class DistributorUsageError(DistributorError):
    """Illegal parameters or bad state -- caller should fix behavior"""
    code = 400
    title = _('Bad Request')


class DistributorLimitError(DistributorError):
    """Reached limits. Nothing wrong with call but no point retrying"""
    code = 503
    title = _('Service Unavailable')


class DistributorInstanceError(DistributorError):
    """Unrecoverable error. Should recycle instance"""
    code = 422
    title = _('Unprocessable Entity')


class DistributorFatalError(DistributorError):
    """Fatal error. Should recycle controller"""
    code = 500
    title = _('Internal Server Error')


class _ProvisioningState:
    """Server provision status state machine"""

    def __init__(self, do_not_persist=False):
        """

        :param do_not_persist: if True do not persist
        """
        self.state = DISTRIBUTOR_BOOTING
        self.reason = ''
        self.do_not_persist = do_not_persist
        # self.persist() cannot be called yet, ovs may not be ready

    def go_ready(self):
        if self.state == DISTRIBUTOR_BOOTING:
            self.state = DISTRIBUTOR_ACTIVE
            self.persist()

    def go_unavailable(self, reason):
        if self.state not in {DISTRIBUTOR_ERROR, DISTRIBUTOR_FULL}:
            self.state = DISTRIBUTOR_FULL
            self.reason = reason
            self.persist()

    def go_error(self, reason):
        if self.state != DISTRIBUTOR_ERROR:
            self.state = DISTRIBUTOR_ERROR
            self.reason = reason
            self.persist()

    def to_dict(self):
        result = dict(state=self.state)
        if self.reason:
            result.update(reason=self.reason)
        return result

    def persist(self):
        if self.do_not_persist:
            return
        ret, out, err = _run_vsctl(
            VSCTL_SET_SERVER_EX_ID.format(key='dist-state',
                                          value=self.state),
            VSCTL_SET_SERVER_EX_ID.format(key='dist-state-reason',
                                          value=self.reason)
        )
        if ret != 0:
            msg = _('Failed to persist distributor server state'
                    ' %(state)s, exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(state=self.state, ret=ret, err=err)
            LOG.error(msg)
            self.state = DISTRIBUTOR_ERROR
            self.reason = 'Failed persist state'
            raise DistributorFatalError(msg)

    def load(self):
        ret, out, err = _run_vsctl(
            VSCTL_GET_SERVER_EX_ID.format(key='dist-state'),
            VSCTL_GET_SERVER_EX_ID.format(key='dist-state-reason')
        )
        if ret != 0:
            LOG.error(_('Failed to load distributor server state'
                        ' exit_status=%(ret)d'
                        '\nsterr=%(err)s'
                        ) % dict(ret=ret, err=err))
            self.state = DISTRIBUTOR_ERROR
            self.reason = 'Failed load state'

_provision_state = _ProvisioningState()
_distributors = {}  # lb_id --> _Distributor


def post_plug_vip(lb_id, vip_ip, mac_address, subnet_cidr, gateway,
                  cluster_alg_type, cluster_min_size):
    """Create new Distributor ovs bridge instance

    :param lb_id: uuid in Octavia DB
    :param vip_ip: loadbalancer VIP address
    :param mac_address: mac of external interface
    :param subnet_cidr: unused
    :param gateway: unused
    :param cluster_alg_type: active_active
    :param cluster_min_size: minimal number of slots
    :return: distributor instance
    """
    _init_ovs_and_verify_boot_state()
    distributor = _recover_distributor(lb_id)
    if distributor is not None:
        LOG.warning(_LW('Distributor instance already plugged for'
                        ' loadbalancer %s') % lb_id)
        return distributor
    if _provision_state.state == DISTRIBUTOR_FULL:
        msg = _('Cannot create Distributor for loadbalancer %(lb)s.'
                ' Service provisioning state is %(state)s'
                ) % dict(lb=lb_id, state=_provision_state.state)
        LOG.error(msg)
        raise DistributorLimitError(msg)
    assert cluster_alg_type == ALG_ACTIVE_ACTIVE
    size = cluster_min_size
    if size > MAX_CLUSTER_SIZE:
        raise DistributorUsageError(_(
            'Cannot create Distributor for loadbalancer %(lb)s.'
            ' Distributor size %(size)s exceeds maximal size %(max)s'
            ) % dict(lb=lb_id, size=size, max=MAX_CLUSTER_SIZE))
    if len(_distributors) >= MAX_DISTRIBUTORS:
        msg = _('Reached maximum Distributors, %s') % MAX_DISTRIBUTORS
        _provision_state.go_unavailable(msg)
        raise DistributorLimitError(msg)
    vip = netaddr.IPAddress(vip_ip)
    iface_mac = netaddr.EUI(mac_address, dialect=netaddr.mac_unix)
    interface = _interface_by_mac(iface_mac)
    br_name = _gen_br_name(interface)
    LOG.info(_LI(
        'Creating new Distributor instance for vip=%(vip)s, mac=%(mac)s'
        ', loadbalancer %(lb)s, iface=%(iface)s, size=%(size)d'),
        dict(vip=vip, mac=iface_mac, lb=lb_id, iface=interface,
             size=size))
    if _provision_state.state != DISTRIBUTOR_ACTIVE:
        raise DistributorFatalError(_(
            'Cannot create Distributor for loadbalancer %(lb)s.'
            ' Service provisioning state is %(state)s'
        ) % dict(lb=lb_id, state=_provision_state.state))
    distributor = _Distributor(name=br_name, lb_id=lb_id, vip=vip,
                               mac=iface_mac, iface=interface, size=size)
    try:
        distributor.create_br()
        distributor.add_external_port()
        distributor.add_default_destination_groups()
        distributor.add_hash_select_group()
        distributor.del_default_flows()
        distributor.add_vip_flows()
        distributor.bring_if_up()
    except DistributorError:
        LOG.exception(_LE('Error while creating Distributor instance'
                          ' for loadbalancer %s'), lb_id)
        distributor.del_br()
        raise
    _distributors[lb_id] = distributor
    return distributor

def register_amphora(vip, lb_id, subnet_cidr, gateway, amphora_id,
                     amphora_mac, cluster_alg_type, cluster_slot=None):
    """Start forwarding to given Amphora

    :param vip: loadbalancer VIP address -- verify only
    :param lb_id: uuid in Octavia DB
    :param subnet_cidr: unused
    :param gateway: unused
    :param amphora_id: uuid of Amphora in Octavia DB
    :param amphora_mac: mac used for forwarding
    :param cluster_alg_type: active_active
    :param cluster_slot: number of slot
    """
    distributor = _recover_distributor(lb_id)
    if distributor is None:
        raise DistributorUsageError(_(
            'Register failed - no Distributor for loadbalancer %s.'
        ) % lb_id)
    assert cluster_alg_type == ALG_ACTIVE_ACTIVE
    assert distributor.vip == netaddr.IPAddress(vip)
    slot = cluster_slot
    if _provision_state.state == DISTRIBUTOR_ERROR:
        raise DistributorFatalError(_(
            'Cannot register to Distributor for loadbalancer %(lb)s.'
            ' Server provisioning state is %(state)s'
        ) % dict(lb=lb_id, state=_provision_state.state))
    if distributor.fail:
        msg = _('Distributor is in failed state. Cannot register'
                ' Amphora %s') % amphora_mac
        LOG.error(msg)
        raise DistributorInstanceError(msg)

    result = distributor.register_amphora(amphora_id, amphora_mac, slot)
    return {'slot': result}

def unregister_amphora(vip, lb_id, subnet_cidr, gateway, amphora_id):
    """Stop forwarding to given Amphora

    :param vip: loadbalancer VIP address -- verify only
    :param lb_id: uuid in Octavia DB
    :param subnet_cidr: unused
    :param gateway: unused
    :param amphora_id: disable forwarding to this amphora
    """
    distributor = _recover_distributor(lb_id)
    if distributor is None:
        raise DistributorUsageError(_(
            'Unregister failed -  - no Distributor for loadbalancer %s.'
        ) % lb_id)
    assert distributor.vip == netaddr.IPAddress(vip)
    if _provision_state.state == DISTRIBUTOR_ERROR:
        raise DistributorFatalError(_(
            'Cannot unregister from Distributor for loadbalancer'
            ' %(lb)s. Server provisioning state is %(state)s'
        ) % dict(lb=lb_id, state=_provision_state.state))
    if distributor.fail:
        LOG.warning(_LW('Distributor is in failed state while '
                        'unregistering Amphora %s'), amphora_id)
    distributor.unregister_amphora(amphora_id)


def pre_unplug_vip(lb_id, vip):
    """
    Delete Distributor instance for given loadbalancer id

    :param lb_id: uuid in Octavia DB
    :param vip: load-balancer VIP address -- verify only
    """
    distributor = _recover_distributor(lb_id)
    if distributor is None:
        msg = _('Cannot delete no-existent Distributor instance for'
                ' loadbalancer %s)') % lb_id
        LOG.error(msg)
        raise DistributorUsageError(msg)
    try:
        assert distributor.vip == netaddr.IPAddress(vip)
    except (AssertionError, ValueError, UnicodeDecodeError, TypeError,
            AddrFormatError, IndexError, NotImplementedError):
        LOG.warning(
            _LW('VIP mismatch while deleting Distributor instance for '
                'loadbalancer %(lb)s; %(myvip)s <> %(vip)s.'
                ' Continuing with delete regardless'),
            dict(lb=lb_id, myvip=distributor.vip, vip=vip))
    LOG.info(_LI('Deleting Distributor instance %s'), distributor)
    del _distributors[lb_id]
    distributor.del_br()
    return distributor

def get_status_from_ovs(lb_id=None):
    """Get status from ovs for a Distributor or for all Distributors

    bridge.external_ids = {
        'dist-lb-id': lb_id,
        'dist-vip': vip,
        'dist-size': size,
        'dist-status': status,
        'dist-mac': mac,
        'dist-hash-fields': field-list,
        'dist-ofport': ofport,  # of external iface
        'slot-100': 'amphora_id,mac',
        'slot-101': 'amphora_id,mac',
        'slot-...': 'amphora_id,mac',
    }
    returns a dictionary {
        'distributor-id': distributor_id,
        'provisioning-state': {
            'state': service provisioning status,
            'reason': str
        }
        'loadbalancers': {
            lb-id-1: {
                'status': instance provisioning status
                'size': int
                'registered': int
            }
        }
    }
    """
    provision_state_copy = _ProvisioningState(do_not_persist=True)
    result = dict(loadbalancers={})
    try:
        provision_state_copy.load()
    except DistributorError:
        result['provisioning-state'] = provision_state_copy.to_dict()
        return result
    else:
        result['provisioning-state'] = provision_state_copy.to_dict()

    if lb_id:
        cmd = VSCTL_FIND_EXTERNAL_ID.format(key='dist-lb-id',
                                            value=lb_id)
    else:
        cmd = VSCTL_LIST_EXTERNAL_ID
    ret, out, err = _run_vsctl(cmd, extra_args=[VSCTL_JSON_FORMAT])
    if ret != 0:
        msg = _('Failed to list loadbalancers with exit_status=%(ret)d'
                '\nsterr=%(err)s'
                ) % dict(ret=ret, err=err)
        LOG.error(msg)
        provision_state_copy.go_error(msg)
        result['provisioning-state'] = provision_state_copy.to_dict()
        return result

    # ovs json is a nested [type, value] list
    # br_list = {'data': [[br_name1,
    #                      ['map', [[dist-lb-id', lb_id],
    #                               ['dist-vip', vip],
    #                               ['dist-size', size],
    #                               ['dist-status', status],
    #                               ['dist-mac', mac],
    #                               ['dist-hash-fields', field-list],
    #                               ['dist-ofport', ofport],
    #                               ['slot-100', amphora_id,mac],
    #                               ['slot-101', amphora_id,mac],
    #                               ['slot-...', amphora_id,mac]]]]
    #                     [br_name2, [...]]
    #            'headings': ['name', 'external_ids']}
    try:
        br_list = json.loads(out)
        bridges = {br[0]: dict(br[1][1]) for br in br_list['data']}
    except (ValueError, KeyError, IndexError, TypeError):
        msg = _('Failed to parse loadbalancers list %s.') % out
        LOG.error(msg)
        provision_state_copy.go_error(msg)
        result['provisioning-state'] = provision_state_copy.to_dict()
        return result

    if lb_id and len(bridges) != 1:
        msg = _('Multiple matches while getting status for loadbalancer'
                ' %(lb)s: %(br_list)'
                ) % dict(lb=lb_id, br_list=bridges)
        LOG.error(msg)
        provision_state_copy.go_error(msg)
        result['provisioning-state'] = provision_state_copy.to_dict()
        return result

    for br_name, br_properties in six.iteritems(bridges):
        # one error type for all property parsing issues
        try:
            if lb_id:
                assert lb_id == br_properties.pop('dist-lb-id')
            else:
                lb_id = br_properties.pop('dist-lb-id')
            size = int(br_properties.pop('dist-size'))
            status = br_properties.pop('dist-status')
            assert status in (ONLINE, DEGRADED, ERROR, NO_MONITOR)
        except (AssertionError, KeyError, ValueError, UnicodeDecodeError):
            msg = _('Error while parsing loadbalancer %(lb)s.'
                    ' bad bridge properties %(props)s.'
                    ) % dict(lb=lb_id if lb_id is not None else br_name,
                             props=br_properties)
            LOG.error(msg)
            result['loadbalancers'][lb_id] = dict(status=ERROR, size=0,
                                                  registered=0)
        else:
            registered = sum(SLOT_KEY_FORMAT.format(slot) in br_properties
                             for slot in range(DST_GROUPS_OFFSET,
                                               DST_GROUPS_OFFSET + size))
            # to be on the safe side recheck ONLINE status of lb
            if status == ONLINE and registered < size:
                status = DEGRADED
            result['loadbalancers'][lb_id] = dict(status=status,
                                                  size=size,
                                                  registered=registered)
    return result

def get_status():
    """
    Provide status for all Distributor instances
    """
    loadbalancers = {}
    for lb_id, distributor in six.iteritems(_distributors):
        loadbalancers[lb_id] = distributor.get_status()
    return {'provisioning-state': _provision_state.to_dict(),
            'loadbalancers': loadbalancers}

def dump_state(interface):
    -    """
    Dump Distributor state that can be loaded to similar instance

    :param interface: name of external interface
    :return dictionary of slot int to Amphora mac str
    """
    if interface not in _distributors:
        msg = _('Cannot dump state of no-existent Distributor'
                ' instance on interface %s') % interface
        LOG.error(msg)
        raise DistributorUsageError(msg)
    distributor = _distributors[interface]
    if distributor.fail:
        msg = _('Distributor is in failed state. Cannot dump state'
                ' of interface %s') % interface
        LOG.error(msg)
        raise DistributorInstanceError(msg)

    return distributor.dump_state()



def load_state(interface, slot_to_mac):
    -    """
    Load Distributor state that was dumped from another instance

    :param interface: name of external interface
    :param slot_to_mac: dictionary of slot int to Amphora mac str
    """
    if interface not in _distributors:
        msg = _('Cannot load state to no-existent Distributor'
                ' instance on interface %s') % interface
        LOG.error(msg)
        raise DistributorUsageError(msg)
    distributor = _distributors[interface]
    if distributor.fail:
        msg = _('Distributor is in failed state. Cannot load state'
                ' of interface %s') % interface
        LOG.error(msg)
        raise DistributorInstanceError(msg)

    return distributor.load_state(slot_to_mac)


class _Distributor:
    def __init__(self, name, lb_id, vip, mac, iface, size,
                 of_version=OF_VERSION, timeout=OVS_CMD_TIMEOUT):
        self.of_version = of_version
        self.timeout = str(timeout)  # type: str

        self.lb_id = lb_id
        self.bridge = name
        self.vip = vip

        # type: tuple
        self.hash_selection_fields = HASH_SRC_PORT[vip.version]

        self.mac = mac
        self.iface = iface
        self.ofport = None

        self.size = size
        self.destinations = dict()  # amphora_id -> (slot,amphora_mac)
        self.free_slots = set()  # type: set(int)

        # This is a flag to indicate instance (ie entire LB) failure
        # This is reported per LB in the heartbeat and typically LB
        # should be recycled.
        # The flag is currently conservative -- set on every error
        # that is not related to API syntax or parameter validation
        self.fail = False

    def __repr__(self):
        return 'Distributor{args}'.format(args=(self.bridge,
                                                self.lb_id,
                                                self.vip,
                                                self.mac,
                                                self.iface,
                                                self.size,
                                                ))

    def register_amphora(self, amphora_id, amphora_mac, slot=None):
        if not self.free_slots:
            msg = _('Cannot register Amphora %s. No free slots'
                    ) % amphora_id
            LOG.error(msg)
            raise DistributorUsageError(msg)
        if slot is None:
            slot = self.free_slots.pop()
        elif slot in self.free_slots:
            self.free_slots.remove(slot)
        else:
            msg = _('Cannot register Amphora %(amp)s in slot %(slot)s.'
                    ) % dict(amp=amphora_id, slot=slot)
            LOG.error(msg)
            raise DistributorUsageError(msg)
        mac = netaddr.EUI(amphora_mac, dialect=netaddr.mac_unix)
        amphora_bucket = _gen_bucket_string(
            1,
            'note={amp_id}'.format(amp_id=base64.b16encode(amphora_id)),
            'mod_dl_src={src_mac}'.format(src_mac=self.mac),
            'mod_dl_dst={dst_mac}'.format(dst_mac=mac),
            'IN_PORT')
        amphora_group = _gen_group_string(None, slot, amphora_bucket,
                                          type='indirect')
        ret, out, err = _run_ofctl(
            cmd=OFCTL_MOD_GROUP_STDIN.format(distributor=self),
            stdinput=amphora_group)
        if ret != 0:
            # reclaim free slot
            self.free_slots.add(slot)
            msg = _('Error while registering Amphora %(amp)s on bridge'
                    ' %(br)s, exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(amp=amphora_id, br=self.bridge, ret=ret,
                             err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)

        ret, out, err = _run_vsctl(
            VSCTL_SET_EXTERNAL_ID.format(
                distributor=self,
                key=SLOT_KEY_FORMAT.format(slot),
                value=','.join(map(str, (amphora_id, mac)))))
        if ret != 0:
            msg = _('Error setting external_id while registering'
                    ' Amphora %(amp)s on bridge %(br)s, '
                    ' exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(amp=amphora_id, br=self.bridge, ret=ret,
                             err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)

        self.destinations[amphora_id] = slot, mac
        self.update_status()
        return slot

    def unregister_amphora(self, amphora_id):
        # mac = netaddr.EUI(amphora_mac, dialect=netaddr.mac_unix)
        if amphora_id not in self.destinations:
            msg = _('Cannot unregister unknown Amphora %s'
                    ) % amphora_id
            LOG.error(msg)
            raise DistributorUsageError(msg)

        slot, mac = self.destinations.pop(amphora_id)

        ret, out, err = _run_vsctl(
            VSCTL_DEL_EXTERNAL_ID.format(distributor=self,
                                         key=SLOT_KEY_FORMAT.format(slot)))
        if ret != 0:
            msg = _('Error deleting external_id while unregistering'
                    ' Amphora %(amp)s on bridge %(br)s, '
                    ' exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(amp=amphora_id, br=self.bridge, ret=ret,
                             err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)
        drop_bucket = _gen_bucket_string(1, 'drop')
        drop_group = _gen_group_string(None, slot, drop_bucket,
                                       type='indirect')
        ret, out, err = _run_ofctl(
            cmd=OFCTL_MOD_GROUP_STDIN.format(distributor=self),
            stdinput=drop_group)
        if ret != 0:
            # reclaim destination slot
            self.destinations[amphora_id] = slot, mac
            self.free_slots.add(slot)
            msg = _(
                'Error while unregistering Amphora %(amp)s on bridge'
                ' %(br)s, exit_status=%(ret)d'
                '\nsterr=%(err)s'
            ) % dict(amp=amphora_id, br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)

        self.free_slots.add(slot)
        self.update_status()
        return

    def del_br(self):
        ret, out, err = _run_ofctl(OFCTL_IFDOWN.
                                   format(distributor=self))
        if ret != 0:
            LOG.error(_LE(
                'Error bringing interface %(iface)s down on'
                ' bridge %(br)s, LB %(lb)s. exit_status=%(ret)d'
                '\nstderr=%(err)s'
            ), dict(iface=self.iface, br=self.bridge, lb=self.lb_id,
                    ret=ret, err=err))
        ret, out, err = _run_vsctl(VSCTL_DEL_BR.format(self.bridge))
        if ret != 0:
            LOG.error(_LE(
                'Error deleting bridge %(br)s, exit_status=%(ret)d'
                '\nstderr=%(err)s'
            ), dict(br=self.bridge, ret=ret, err=err))

    def get_status(self):
        if self.fail:
            return dict(status=ERROR)
        result = dict(size=self.size, registered=len(self.destinations))
        if len(self.destinations) == self.size:
            result['status'] = ONLINE
        elif len(self.destinations) + len(self.free_slots) < self.size:
            # transient edit state
            result['status'] = NO_MONITOR
        else:
            result['status'] = DEGRADED
        return result

    def dump_state(self):
        return {
            amphora_id: dict(zip(('slot', 'amphora_mac'), destination))
            for amphora_id, destination in six.iteritems(self.destinations)
        }

    def load_state(self, amphora_slots):
        if len(amphora_slots) != self.size:
            msg = _(
                'Cannot load state. State size %(state_size) does not'
                ' match size Distributor size %(size)'
            ) % dict(state_size=len(amphora_slots), size=self.size)
            LOG.error(msg)
            raise DistributorUsageError(msg)
        slots_to_load = set(info['slot']
                            for info in six.itervalues(amphora_slots))
        if self.free_slots != slots_to_load:
            msg = _('State slots do not match free slots')
            LOG.error(msg)
            raise DistributorUsageError(msg)
        self.free_slots.clear()
        amphora_groups = []
        for amphora_id, info in six.iteritems(amphora_slots):
            slot = info['slot']
            amphora_mac = info['amphora_mac']
            mac = netaddr.EUI(amphora_mac, dialect=netaddr.mac_unix)
            amphora_bucket = _gen_bucket_string(
                1,
                'note={amph}'.format(amph=base64.b16encode(amphora_id)),
                'mod_dl_src={src_mac}'.format(src_mac=self.mac),
                'mod_dl_dst={dst_mac}'.format(dst_mac=mac),
                'IN_PORT')
            amphora_groups.append(_gen_group_string(
                None, slot, amphora_bucket, type='indirect'))
            self.destinations[amphora_id] = slot, mac
        ret, out, err = _run_ofctl(
            cmd=OFCTL_MOD_GROUP_STDIN.format(distributor=self),
            stdinput='\n'.join(amphora_groups))
        if ret != 0:
            # reclaim all free slots
            self.free_slots = slots_to_load
            msg = _('Error while loading state for bridge %(br)s,'
                    ' exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)
        return

    def create_br(self):
        """
        Adds a bridge, sets protocol to 1.5
        Saves distributor properties to external_ids for recovery
        """
        hash_selection_fields = ','.join(map(str,
                                             self.hash_selection_fields))
        ret, out, err = _run_vsctl(
            VSCTL_ADD_BR.format(distributor=self),
            VSCTL_SET_PROTOCOL.format(distributor=self),
            VSCTL_SET_EXTERNAL_ID.format(distributor=self,
                                         key='dist-lb-id',
                                         value=self.vip),
            VSCTL_SET_EXTERNAL_ID.format(distributor=self,
                                         key='dist-vip',
                                         value=self.vip),
            VSCTL_SET_EXTERNAL_ID.format(distributor=self,
                                         key='dist-size',
                                         value=self.size),
            VSCTL_SET_EXTERNAL_ID.format(distributor=self,
                                         key='dist-mac',
                                         value=self.mac),
            VSCTL_SET_EXTERNAL_ID.format(distributor=self,
                                         key='dist-hash-fields',
                                         value=hash_selection_fields))
        if ret == 0:
            # wait for DB update
            ret, out, err = _run_vsctl(VSCTL_GET_BRPORT.
                                       format(distributor=self))
            if ret == 0:
                return

        msg = _(
            'Error while creating bridge %(br)s, exit_status=%(ret)d'
            '\nstderr=%(err)s'
        ) % dict(br=self.bridge, ret=ret, err=err)
        LOG.error(msg)
        # cannot even create an empty bridge so assume fatal error
        _provision_state.go_error(msg)
        raise DistributorFatalError(msg)

    def add_external_port(self, port_id=1):
        ret, out, err = _run_vsctl(
            VSCTL_ADD_PORT.format(distributor=self),
            VSCTL_REQUEST_PORT.format(distributor=self, port=port_id))
        if ret == 0:
            ret, out, err = _run_vsctl(VSCTL_GET_IFPORT.
                                       format(distributor=self))
            if out.strip() == '[]':
                # ovs sometimes returns empty port set if not ready yet
                sleep(OVS_CMD_TIMEOUT)
                ret, out, err = _run_vsctl(VSCTL_GET_IFPORT.
                                           format(distributor=self))
            if ret == 0:
                out = out.strip()
                try:
                    port = int(out)
                except ValueError:
                    msg = _(
                        'add port %(port)d for bridge %(br)s returned'
                        ' non-int result %(got)s'
                    ) % dict(port=port_id, br=self.bridge, got=out)
                    LOG.exception(msg)
                    self.update_status(ERROR)
                    raise DistributorInstanceError(msg)
                else:
                    if port != port_id:
                        LOG.debug(_LI(
                            'add port for bridge %(br)s got port'
                            ' %(got)d instead of requested port %(req)d'
                        ), dict(br=self.bridge, got=port, req=port_id))
                    self.ofport = port
                    return
        msg = _('Error adding port %(port)d to bridge %(br)s,'
                ' exit_status=%(ret)d'
                '\nsterr=%(err)s'
                ) % dict(port=port_id, br=self.bridge, ret=ret, err=err)
        LOG.error(msg)
        self.update_status(ERROR)
        raise DistributorInstanceError(msg)

    def add_default_destination_groups(self):
        drop_bucket = _gen_bucket_string(1, 'drop')
        destination_slots = range(DST_GROUPS_OFFSET,
                                  DST_GROUPS_OFFSET + self.size)
        drop_groups = [_gen_group_string(None, slot, drop_bucket,
                                         type='indirect')
                       for slot in destination_slots]
        ret, out, err = _run_ofctl(
            cmd=OFCTL_ADD_GROUP_STDIN.format(distributor=self),
            stdinput='\n'.join(drop_groups))
        if ret != 0:
            msg = _('Error while creating default groups for bridge'
                    ' %(br)s, exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)

        self.free_slots.update(destination_slots)
        return

    def add_hash_select_group(self):
        # use deterministic hash seed based on vip
        seed = hash(self.vip) % 32768
        destination_slots = range(DST_GROUPS_OFFSET,
                                  DST_GROUPS_OFFSET + self.size)
        buckets = [_gen_bucket_string(slot, 'group:{id}'.format(id=slot))
                   for slot in destination_slots]
        group = _gen_group_string(None, SELECT_GROUP_ID, *buckets,
                                  fields=self.hash_selection_fields,
                                  selection_method_param=seed)
        ret, out, err = _run_ofctl(
            cmd=OFCTL_ADD_GROUP_STDIN.format(distributor=self),
            stdinput=group)
        if ret != 0:
            msg = _('Error creating selection group for bridge %(br)s, '
                    'exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)
        return

    def del_default_flows(self):
        ret, out, err = _run_ofctl(OFCTL_DEL_FLOWS.
                                   format(distributor=self))
        if ret != 0:
            msg = _('Error deleting default flows for bridge %(br)s,'
                    ' exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)
        return

    def add_vip_flows(self):
        # default drop flow
        drop_flow = _gen_flow_string('add', {}, 'drop', table=0,
                                     priority=PRIORITY_LOW)
        vip_flows = [drop_flow]

        # arp / nd responder
        if self.vip.version == 4:
            arp_match = dict(in_port=self.ofport, arp=True,
                             arp_tpa=self.vip)
            arp_action_list = (
                'set_field:2->arp_op',
                'move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[]',
                'set_field:{mac}->eth_src'.format(mac=self.mac),
                'move:NXM_NX_ARP_SHA[]->NXM_NX_ARP_THA[]',
                'set_field:{mac}->arp_sha'.format(mac=self.mac),
                'move:NXM_OF_ARP_SPA[]->NXM_OF_ARP_TPA[]',
                'set_field:{vip}->arp_spa'.format(vip=self.vip),
                'IN_PORT',
            )
            arp_flow = _gen_flow_string('add', arp_match,
                                        *arp_action_list,
                                        table=0, priority=PRIORITY_MED)
            vip_flows.append(arp_flow)
        elif self.vip.version == 6:
            nd_match = dict(in_port=self.ofport, icmpv6=True,
                            icmpv6_type=135, nd_target=self.vip)
            nd_action_list = (
                'set_field:136->icmpv6_type',
                'move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[]',
                'set_field:{mac}->eth_src'.format(mac=self.mac),
                'move:NXM_NX_ND_SLL[]->NXM_NX_ND_TLL[]',
                'set_field:{mac}->nd_sll'.format(mac=self.mac),
                'set_field:{vip}->nd_target'.format(vip=self.vip),
                'move:NXM_NX_IPV6_SRC[]->NXM_NX_IPV6_DST[]',
                'set_field:{vip}->ipv6_src'.format(vip=self.vip),
                'IN_PORT',
            )
            nd_flow = _gen_flow_string('add', nd_match, *nd_action_list,
                                       table=0, priority=PRIORITY_MED)
            vip_flows.append(nd_flow)

        # vip tcp fwd match
        tcp_match = dict(in_port=self.ofport)
        if self.vip.version == 4:
            tcp_match.update(tcp=True, ip_dst=self.vip)
        elif self.vip.version == 6:
            tcp_match.update(tcpv6=True, ipv6_dst=self.vip)
        tcp_action = 'group:{}'.format(SELECT_GROUP_ID)
        tcp_flow = _gen_flow_string('add', tcp_match, tcp_action,
                                    table=0, priority=PRIORITY_MED)
        vip_flows.append(tcp_flow)

        ret, out, err = _run_ofctl(
            cmd=OFCTL_ADD_FLOW_STDIN.format(distributor=self),
            stdinput='\n'.join(vip_flows))
        if ret != 0:
            msg = _('Error creating vip flows for bridge %(br)s,'
                    ' exit_status=%(ret)d'
                    '\nsterr=%(err)s'
                    ) % dict(br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)
        return

    def bring_if_up(self):
        # save the ofport in ovs for if_down after recovery
        ret, out, err = _run_vsctl(VSCTL_SET_EXTERNAL_ID.
                                   format(distributor=self,
                                          key='dist-ofport',
                                          value=self.ofport))
        if ret != 0:
            self.fail = True
            msg = _(
                'Error setting port %(ofport)s for bridge %(br)s,'
                ' LB %(lb)s. exit_status=%(ret)d'
                '\nstderr=%(err)s'
            ) % dict(ofport=self.ofport, br=self.bridge, lb=self.lb_id,
                     ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)

        ret, out, err = _run_ofctl(OFCTL_IFUP.
                                   format(distributor=self))
        if ret != 0:
            msg = _(
                'Error bringing up interface %(iface)s on bridge %(br)s'
                ' LB %(lb)s. exit_status=%(ret)d'
                '\nsterr=%(err)s'
            ) % dict(iface=self.iface, br=self.bridge, lb=self.lb_id,
                     ret=ret, err=err)
            LOG.error(msg)
            self.update_status(ERROR)
            raise DistributorInstanceError(msg)

        LOG.debug(_LI('interface %(iface)s is up on bridge %(br)s,'
                      ' LB %(lb)s'),
                  dict(iface=self.iface, br=self.bridge, lb=self.lb_id))
        return

    def update_status(self, status=None):
        if self.fail:
            return
        if status == ERROR:
            self.fail = True
            new_status = ERROR
            # @TODO to be on the safe side we can also bring_if_down
        elif len(self.destinations) == self.size:
            new_status = ONLINE
        elif len(self.destinations) + len(self.free_slots) < self.size:
            # transient edit state
            new_status = NO_MONITOR
        else:
            new_status = DEGRADED

        ret, out, err = _run_vsctl(VSCTL_SET_EXTERNAL_ID.
                                   format(distributor=self,
                                          key='dist-status',
                                          value=new_status))
        if ret != 0:
            self.fail = True
            msg = _(
                'Error updating status %(status)s for bridge %(br)s,'
                ' exit_status=%(ret)d'
                '\nstderr=%(err)s'
            ) % dict(status=new_status, br=self.bridge, ret=ret, err=err)
            LOG.error(msg)
            # cannot set status in external_ids so assume fatal error
            _provision_state.go_error(msg)
            raise DistributorFatalError(msg)
        return


def _init_ovs_and_verify_boot_state():
    if _provision_state.state != DISTRIBUTOR_BOOTING:
        return

    # init ovs
    for attempt in range(WAIT_FOR_OVS_RETRIES):
        try:
            subprocess.check_call(shlex.split(VSCTL_INIT))
        except subprocess.CalledProcessError:
            # Sleep with exponential-back off to allow ovs to finish
            # any after boot install.
            sleep(OVS_CMD_TIMEOUT << attempt)
        else:
            break
    else:
        msg = _('Giving up waiting for OVS init after %s retries'
                ) % WAIT_FOR_OVS_RETRIES
        LOG.error(msg)
        _provision_state.go_error(msg)
        raise DistributorFatalError(msg)

    # check if we have a clean slate
    ret, out, err = _run_vsctl(VSCTL_LIST)
    if ret != 0:
        msg = _('Error verifying boot state, exit_status=%(ret)d'
                '\nsterr=%(err)s'
                ) % dict(ret=ret, err=err)
        LOG.error(msg)
        _provision_state.go_error(msg)
        raise DistributorFatalError(msg)
    elif out:
        # this is a restart, load ovs state, lbs will recover lazily
        _provision_state.load()
        LOG.info(_LI('Distributor server started with existing state.'
                     '\nprovisioning-state: %(status),'
                     '\nloadbalancers: %(lbs).'
                     ) % dict(status=_provision_state.to_dict(),
                              lbs=out.splitlines()))
    else:
        _provision_state.go_ready()
        LOG.info(_LI('New Distributor server started'))
        return


def _run(args, stdinput=None):
    try:
        pipe = subprocess.Popen(args,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        out, err = pipe.communicate(stdinput)
        ret = pipe.returncode
        if ret == 142:
            LOG.error(_LE('timeout while running cmd %(cmd)s.'
                          '\nstderr=%(err)s'),
                      dict(cmd=args, err=err))
        LOG.debug(_LI(
            'finished running cmd %(cmd)s. exit_status=%(ret)d'
            '\nstdout=%(out)s'
            '\nstderr=%(err)s'
            '\nstdin=%(inp)s'
        ), dict(cmd=args, ret=ret, err=err, out=out, inp=stdinput))
        return ret, out, err
    except OSError:
        LOG.exception(_LE('OSError while running cmd %(cmd)s.'),
                      dict(cmd=args))
        return OS_ERROR_CODE, None, None


def _run_vsctl(*cmd_list, **kwargs):
    timeout = kwargs.pop('timeout', OVS_CMD_TIMEOUT)
    args = shlex.split(VSCTL_RUN.format(timeout=timeout))
    for extra in kwargs.pop('extra_args', []):
        args.extend(shlex.split(extra))
    for cmd in cmd_list:
        args.append('--')
        args.extend(shlex.split(cmd))
    return _run(args)


def _run_ofctl(cmd, stdinput=None, extra_args=None,
               timeout=OVS_CMD_TIMEOUT, of_version=OF_VERSION):
    args = shlex.split(OFCTL_RUN.format(of_version=of_version,
                                        timeout=timeout))
    args.extend(shlex.split(cmd))
    for extra in [] if extra_args is None else extra_args:
        args.extend(shlex.split(extra))
    return _run(args, stdinput)


def _gen_flow_string(operation, match_dict, *actions_list, **flags):
    args = []
    for key, value in six.iteritems(flags):
        args.append('{key}={value}'.format(key=key, value=value))

    for key, value in six.iteritems(match_dict):
        if value is True:  # careful, 1 is a valid value
            args.append('{key}'.format(key=key))
        else:
            args.append('{key}={value}'.format(key=key, value=value))

    args.append('actions={actions}'.format(
        actions=','.join(actions_list)))

    if operation:
        return '{operation} {flow}'.format(operation=operation,
                                           flow=','.join(args))
    else:
        return ','.join(args)


def _gen_group_string(operation, group_id, *bucket_list, **flags):
    args = ['group_id={id}'.format(id=group_id)]
    group_type = flags.pop('type', 'select')
    args.append('type={type}'.format(type=group_type))
    if group_type == 'select':
        method = flags.pop('selection_method', 'hash')
        args.append('selection_method={method}'.format(
            method=method))
        if method == 'hash':
            if 'selection_method_param' in flags:
                args.append('selection_method_param={param}'.format(
                    param=flags.pop('selection_method_param')))

            fields = flags.pop('fields', None)
            if fields is None:
                pass
            elif isinstance(fields, (list, tuple)):
                args.append('fields({fields})'.format(
                    fields=','.join(fields)))
            else:
                args.append('fields={field}'.format(field=fields))

    for key, value in six.iteritems(flags):
        args.append('{key}={value}'.format(key=key, value=value))

    for bucket in bucket_list:
        args.append('bucket={bucket}'.format(bucket=bucket))
    if operation:
        return '{operation} {group}'.format(operation=operation,
                                            group=','.join(args))
    else:
        return ','.join(args)


def _gen_bucket_string(bucket_id, *actions_list, **flags):
    args = ['bucket_id:{id}'.format(id=bucket_id)]
    for key, value in six.iteritems(flags):
        args.append('{key}={value}'.format(key=key, value=value))
    args.append('actions={actions}'.format(
        actions=','.join(actions_list)))

    return ','.join(args)


def _gen_br_name(base):
    """
    Create unused bridge name from base_name.

    Name must be short enough to be a valid iface name.
    Similar to neutron iface naming, but checks for collisions and
    tries alternative names.
    :param base: base name
    :return: bridge name
    """
    name = BR_NAME_FORMAT.format(base)[:BR_NAME_LENGTH]
    if (name not in netifaces.interfaces() and
            all(d.bridge != name
                for d in six.itervalues(_distributors))):
        return name
    # else try a some alternatives
    used_names = set(netifaces.interfaces())
    used_names.update(d.bridge for d in six.itervalues(_distributors))
    for alt_base in ('{i:02x}-{base}'.format(i=i, base=base)
                     for i in range(0x100)):
        name = BR_NAME_FORMAT.format(alt_base)[:BR_NAME_LENGTH]
        if name not in used_names:
            return name
    msg = _('Could not find unused bridge name for %s') % base
    _provision_state.go_unavailable(msg)
    raise DistributorLimitError(msg)


def _recover_distributor(lb_id):
    """Get cached Distributor object or generate from ovs external_ids
    {
        'dist-lb-id': lb_id,
        'dist-vip': vip,
        'dist-size': size,
        'dist-status': status,
        'dist-mac': mac,
        'dist-hash-fields': field-list,
        'dist-ofport': ofport,  # of external iface
        'slot-100': 'amphora_id,mac',
        'slot-101': 'amphora_id,mac',
        'slot-...': 'amphora_id,mac',
    }
    """
    if _provision_state.state == DISTRIBUTOR_BOOTING:
        msg = _('Error while recovering loadbalancer %(lb)s.'
                ' Server status is %(status)s'
                ) % dict(lb=lb_id, status=_provision_state.state)
        LOG.error(msg)
        raise DistributorUsageError(msg)
    if lb_id in _distributors:
        return _distributors[lb_id]
    ret, out, err = _run_vsctl(
        VSCTL_FIND_EXTERNAL_ID.format(key='dist-lb-id',
                                      value=lb_id),
        extra_args=[VSCTL_JSON_FORMAT])
    if ret != 0:
        msg = _('Error while recovering loadbalancer %(lb)s.'
                ' Find failed with exit_status=%(ret)d'
                '\nsterr=%(err)s'
                ) % dict(lb=lb_id, ret=ret, err=err)
        LOG.error(msg)
        _provision_state.go_error(msg)
        raise DistributorFatalError(msg)

    # ovs json is a nested [tpye, value] list
    # br_list = {'data': [[br_name,
    #                     ['map',
    #                       [['dist-lb-id', lb_id],
    #                        ['dist-vip', vip],
    #                        ['dist-size', size],
    #                        ['dist-status', status],
    #                        ['dist-mac', mac],
    #                        ['dist-hash-fields', field-list],
    #                        ['dist-ofport', ofport],
    #                        ['slot-100', amphora_id,mac],
    #                        ['slot-101', amphora_id,mac],
    #                        ['slot-...', amphora_id,mac]]]]]
    #            'headings': ['name', 'external_ids']}
    try:
        br_list = json.loads(out)
        br_name = br_list['data'][0][0]
        br_properties = dict(br_list['data'][0][1][1])
    except (ValueError, KeyError, IndexError, TypeError):
        msg = _('Error while recovering loadbalancer %(lb)s.'
                ' Could not parse find results %(out)s.'
                ) % dict(lb=lb_id, out=out)
        LOG.error(msg)
        _provision_state.go_error(msg)
        raise DistributorFatalError(msg)

    found_id = br_properties.pop('dist-lb-id', None)
    if lb_id != found_id or len(br_list['data']) != 1:
        msg = _('Error while recovering loadbalancer %(lb)s. None or'
                ' duplicate bridge found. out=%(out)s'
                ) % dict(lb=lb_id, out=br_list)
        LOG.error(msg)
        return None

    # one error type for all property parsing issues, catch all
    # expected errors
    try:
        vip = netaddr.IPAddress(br_properties.pop('dist-vip'))
        size = int(br_properties.pop('dist-size'))
        status = br_properties.pop('dist-status')
        assert status in (ONLINE, DEGRADED, ERROR, NO_MONITOR)
        mac = netaddr.EUI(br_properties.pop('dist-mac'),
                          dialect=netaddr.mac_unix)
        iface = _interface_by_mac(mac)
        hash_selection_fields = br_properties.pop(
            'dist-hash-fields').split(',')
        ofport = int(br_properties.pop('dist-ofport'))
    except (AssertionError, KeyError, ValueError, UnicodeDecodeError,
            AddrFormatError, TypeError, IndexError,
            NotImplementedError, AddrConversionError, StopIteration):
        # we have a bridge name so we should try to delete it
        ret, out, err = _run_vsctl(VSCTL_DEL_BR.format(br_name))
        killed = 'killed' if ret == 0 else 'kill failed: stderr=%s' % err
        msg = _('Error while recovering loadbalancer %(lb)s.'
                ' bad bridge properties %(props)s.'
                ' Killing bridge %(kill_msg)s'
                ) % dict(lb=lb_id, props=br_properties, kill_msg=killed)
        LOG.error(msg)
        raise DistributorInstanceError(msg)

    distributor = _Distributor(name=br_name, lb_id=lb_id, vip=vip,
                               mac=mac, iface=iface, size=size)
    for slot in range(DST_GROUPS_OFFSET, DST_GROUPS_OFFSET + size):
        slot_key = SLOT_KEY_FORMAT.format(slot)
        if slot_key in br_properties:
            amphora_id, amphora_mac = br_properties[slot_key].split(',')
            # mac = netaddr.EUI(amphora_mac, dialect=netaddr.mac_unix)
            distributor.destinations[amphora_id] = slot, amphora_mac
        else:
            distributor.free_slots.add(slot)
    distributor.hash_selection_fields = hash_selection_fields
    distributor.fail = (ERROR == status)
    distributor.ofport = ofport

    _distributors[lb_id] = distributor
    return distributor


def _interface_by_mac(mac):
    for interface in netifaces.interfaces():
        if netifaces.AF_LINK in netifaces.ifaddresses(interface):
            for link in netifaces.ifaddresses(interface)[netifaces.AF_LINK]:
                if link.get('addr', '').lower() == mac.lower():
                    return interface
    msg = _('No suitable network interface found for mac %s') % mac
    raise DistributorUsageError(msg)

