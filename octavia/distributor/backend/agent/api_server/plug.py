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
import socket

import flask
import netifaces
from werkzeug import exceptions

from octavia.common import constants
import octavia.distributor.backend.agent.api_server.distributor_data as ddata
from octavia.distributor.backend.agent.api_server import open_flow

PLUG_DEBUG = 'debug'

LOG = logging.getLogger(__name__)


def register_amphora(vip_ip, lb_id, subnet_cidr, gateway, amphora_id,
                     amphora_mac,
                     cluster_alg_type,
                     cluster_min_size):
    LOG.debug("Distributor: Registers Amphora")
    out = ""
    mac, interface, vip = ddata.lb_id_dict[lb_id]
    assert vip == vip_ip

    if amphora_id not in ddata.amphorae_per_lb_id_dict[lb_id]:
        ddata.amphorae_per_lb_id_dict[lb_id][amphora_id] = amphora_mac
        if cluster_alg_type == constants.ALG_ACTIVE_ACTIVE:
            out = open_flow.register_amphora(vip, mac, interface,
                                             subnet_cidr, gateway,
                                             amphora_mac, cluster_min_size)
        elif cluster_alg_type == PLUG_DEBUG:
            LOG.debug("DEBUG MODE - In %s, register_amphora:"
                      " LB_ID: %s, VIP %s, amphora_mac %s,"
                      " interface %s",
                      __file__, lb_id, vip_ip, amphora_mac, interface)
        else:
            LOG.debug("UNSUPPORTED MODE - In %s, register_amphora", __file__)
    return flask.jsonify(
        {'hostname': socket.gethostname(),
         'ovs_out': out})


def unregister_amphora(vip_ip, lb_id, subnet_cidr, gateway, amphora_id,
                       cluster_alg_type,
                       cluster_min_size):
    LOG.debug("Distributor: Unregisters Amphora")
    out = ""
    mac, interface, vip = ddata.lb_id_dict[lb_id]
    assert vip == vip_ip

    if amphora_id in ddata.amphorae_per_lb_id_dict[lb_id]:
        amphora_mac = ddata.amphorae_per_lb_id_dict[lb_id][amphora_id]
        if cluster_alg_type == constants.ALG_ACTIVE_ACTIVE:
            out = open_flow.unregister_amphora(vip, mac, interface,
                                               subnet_cidr,
                                               gateway,
                                               amphora_mac,
                                               cluster_min_size)
        elif cluster_alg_type == PLUG_DEBUG:
            LOG.debug("DEBUG MODE - In %s, unregister_amphora:"
                      " LB_ID: %s, VIP %s, amphora_mac %s,"
                      " interface %s",
                      __file__, lb_id, vip, amphora_mac, interface)
        else:
            LOG.debug("UNSUPPORTED MODE - In %s, "
                      "unregister_amphora", __file__)

        del ddata.amphorae_per_lb_id_dict[lb_id][amphora_id]

    return flask.jsonify(
        {'hostname': socket.gethostname(),
         'ovs_out': out})


def post_plug_vip(vip, lb_id, subnet_cidr, gateway, mac_address,
                  cluster_alg_type, cluster_min_size):
    # validate vip
    try:
        socket.inet_aton(vip)
    except socket.error:
        return flask.make_response(flask.jsonify(dict(
            message="Invalid VIP")), 400)

    interface = _interface_by_mac(mac_address)

    if lb_id not in ddata.amphorae_per_lb_id_dict.keys():
        ddata.amphorae_per_lb_id_dict[lb_id] = {}
        ddata.lb_id_dict[lb_id] = (mac_address, interface, vip)
        if cluster_alg_type == constants.ALG_ACTIVE_ACTIVE:
            open_flow.post_plug_vip(interface=interface,
                                    vip_ip=vip,
                                    mac_address=mac_address,
                                    subnet_cidr=subnet_cidr,
                                    gateway=gateway,
                                    cluster_min_size=cluster_min_size)
        elif cluster_alg_type == PLUG_DEBUG:
            LOG.debug("DEBUG MODE - In %s, post_plug_vip:"
                      " LB_ID: %s, VIP %s, mac_address %s,"
                      " interface %s",
                      __file__, lb_id, vip, mac_address, interface)
        else:
            LOG.debug("UNSUPPORTED MODE - In %s, post_plug_vip", __file__)

    return flask.make_response(flask.jsonify(dict(
        message="OK",
        details="VIP {vip} plugged into distributor "
                "on interface {interface}".format(vip=vip,
                                                  interface=interface))), 202)


def pre_unplug_vip(vip_ip, lb_id):

    mac, interface, vip = ddata.lb_id_dict[lb_id]
    assert vip == vip_ip

    if open_flow:
        open_flow.pre_uplug_vip(interface=interface,
                                vip=vip,
                                mac_address=mac)
    del ddata.amphorae_per_lb_id_dict[lb_id]
    del ddata.lb_id_dict[lb_id]

    return flask.make_response(flask.jsonify(dict(
        message="OK",
        details="VIP {vip} unplugged from distributor "
                "on interface {interface}".format(vip=vip,
                                                  interface=interface))), 202)


def _interface_by_mac(mac):
    for interface in netifaces.interfaces():
        if netifaces.AF_LINK in netifaces.ifaddresses(interface):
            for link in netifaces.ifaddresses(interface)[netifaces.AF_LINK]:
                if link.get('addr', '').lower() == mac.lower():
                    return interface
    raise exceptions.HTTPException(
        response=flask.make_response(flask.jsonify(dict(
            details="No suitable network interface found")), 404))
