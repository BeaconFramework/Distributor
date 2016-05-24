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


def register_amphora(vip, mac, interface, subnet_cidr, gateway,
                     amphora_mac, cluster_min_size):
    pass


def unregister_amphora(vip, mac, interface, subnet_cidr, gateway, amphora_mac,
                       cluster_min_size):
    pass


def post_plug_vip(interface, vip_ip, mac_address, subnet_cidr, gateway,
                  cluster_min_size):
    pass


def pre_uplug_vip(interface, vip, mac_address):
    pass


def get_status(interface):
    pass


def dump_state(interface):
    pass


def load_state(interface, slot_to_mac):
    pass
