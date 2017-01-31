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

from octavia.distributor.backend.agent.api_server import open_flow
from octavia.common.constants import ALG_ACTIVE_ACTIVE

PLUG_DEBUG = 'debug'

LOG = logging.getLogger(__name__)


def register_amphora(vip, lb_id, subnet_cidr, gateway, amphora_id,
                     amphora_mac,
                     cluster_alg_type,
                     cluster_slot):
    LOG.debug("Distributor: Registers Amphora")
    # validate vip
    try:
        socket.inet_aton(vip)
    except socket.error:
        return flask.make_response(
            flask.jsonify(message="Invalid VIP"),
            400)

    new_alg_extra = {}
    if cluster_alg_type == ALG_ACTIVE_ACTIVE:
        try:
            new_alg_extra = open_flow.register_amphora(
                vip=vip,
                lb_id=lb_id,
                subnet_cidr=subnet_cidr,
                gateway=gateway,
                amphora_id=amphora_id,
                amphora_mac=amphora_mac,
                cluster_alg_type=cluster_alg_type,
                cluster_slot=cluster_slot)
        except open_flow.DistributorError as e:
            return flask.make_response(
                flask.jsonify(message=e.title, details=str(e)),
                e.code)
        else:
            details = (
                 "amphora {amphora_id} with MAC {amphora_mac}"
                 " registered to VIP {vip} of LB {lb} with result"
                 "{new_alg_extra}"
             ).format(amphora_id=amphora_id, amphora_mac=amphora_mac,
                      vip=vip, lb=lb_id, new_alg_extra=new_alg_extra)
    elif cluster_alg_type == PLUG_DEBUG:
         details = ("DEBUG MODE - register amphora {amphora_id} with"
                    " MAC {amphora_mac} to VIP {vip} of LB {lb}"
                    ).format(amphora_id=amphora_id,
                             amphora_mac=amphora_mac, vip=vip, lb=lb_id)
    else:
         details = ("UNSUPPORTED MODE - {mode} - for register_amphora"
                    " for LB {lb}").format(mode=cluster_alg_type, lb=lb_id)
    LOG.debug(details)
    return flask.make_response(
         flask.jsonify(message="Accepted",
                       hostname=socket.gethostname(),
                       details=details,
                       alg_extra=new_alg_extra),
         202)


def unregister_amphora(vip, lb_id, subnet_cidr, gateway, amphora_id,
                       cluster_alg_type):
   LOG.debug("Distributor: Unregister Amphora")
   # validate vip
   try:
       socket.inet_aton(vip)
   except socket.error:
       return flask.make_response(
           flask.jsonify(message="Invalid VIP"),
           400)
   if cluster_alg_type == ALG_ACTIVE_ACTIVE:
       try:
           open_flow.unregister_amphora(vip=vip,
                                          lb_id=lb_id,
                                          subnet_cidr=subnet_cidr,
                                          gateway=gateway,
                                          amphora_id=amphora_id)
       except open_flow.DistributorError as e:
           return flask.make_response(
                 flask.jsonify(message=e.title, details=str(e)),
                 e.code)
       details = ("amphora {amphora_id} unregistered from VIP "
                  "{vip} of LB {lb}"
                  ).format(amphora_id=amphora_id, vip=vip, lb=lb_id)
   elif cluster_alg_type == PLUG_DEBUG:
       details = ("DEBUG MODE - unregister_amphora {amphora_id} from"
                  " VIP {vip} of LB {lb}"
                  ).format(amphora_id=amphora_id, vip=vip, lb=lb_id)
   else:
       details = ("UNSUPPORTED MODE - {mode} - for unregister_amphora"
                  " for LB {lb}").format(mode=cluster_alg_type, lb=lb_id)
   LOG.debug(details)
   return flask.make_response(
       flask.jsonify(message="OK",
                     hostname=socket.gethostname(),
                     details=details),
       200)

def post_plug_vip(vip, lb_id, subnet_cidr, gateway, mac_address,
                  cluster_alg_type, cluster_min_size):
    # validate vip
    try:
        socket.inet_aton(vip)
    except socket.error:
        return flask.make_response(flask.jsonify(dict(
            message="Invalid VIP")), 400)

    if cluster_alg_type == ALG_ACTIVE_ACTIVE:
         try:
             distributor = open_flow.post_plug_vip(
                 lb_id=lb_id,
                 vip_ip=vip,
                 mac_address=mac_address,
                 subnet_cidr=subnet_cidr,
                 gateway=gateway,
                 cluster_alg_type=cluster_alg_type,
                 cluster_min_size=cluster_min_size
             )
         except open_flow.DistributorError as e:
             return flask.make_response(
                 flask.jsonify(message=e.title, details=str(e)),
                 e.code)
         details = (
                 "VIP {vip} of LB {lb} plugged into distributor"
                 " {distributor}"
         ).format(vip=vip, lb=lb_id, distributor=distributor)
    elif cluster_alg_type == PLUG_DEBUG:
         details = (
             "DEBUG MODE - VIP {vip} of LB {lb} plugged with"
             " mac {mac}"
         ).format(vip=vip, lb=lb_id, mac=mac_address)
    else:
         details = ("UNSUPPORTED MODE - {mode} - for post_plug_vip"
                    " for LB {lb}").format(mode=cluster_alg_type, lb=lb_id)
    LOG.debug(details)
    return flask.make_response(
         flask.jsonify(message="Created",
                       details=details), 201)

def pre_unplug_vip(vip, lb_id):
    LOG.debug("Distributor: Pre Unplug VIP")
    # validate vip
    try:
        socket.inet_aton(vip)
    except socket.error:
        return flask.make_response(
            flask.jsonify(message="Invalid VIP"),
            400)
    if open_flow:
        try:
            distributor = open_flow.pre_unplug_vip(lb_id=lb_id,
                                                   vip=vip)
        except open_flow.DistributorError as e:
            return flask.make_response(
                flask.jsonify(message=e.title, details=str(e)),
                e.code)
        details = (
            "VIP {vip} of LB {lb} unplugged from distributor"
            " {distributor}"
        ).format(vip=vip, lb=lb_id, distributor=distributor)
    else:
        details = ("DEBUG MODE - VIP {vip} of LB {lb} unplugged"
                   ).format(vip=vip, lb=lb_id)
    LOG.debug(details)
    return flask.make_response(
        flask.jsonify(message="OK",
                      details=details),
        200)