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
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
from oslo_utils import uuidutils

from octavia.db import models as models
from octavia.network.drivers.noop_driver import driver as driver
import octavia.tests.unit.base as base


class TestNoopNetworkDriver(base.TestCase):
    FAKE_UUID_1 = uuidutils.generate_uuid()
    FAKE_UUID_2 = uuidutils.generate_uuid()
    FAKE_UUID_3 = uuidutils.generate_uuid()
    FAKE_UUID_4 = uuidutils.generate_uuid()

    def setUp(self):
        super(TestNoopNetworkDriver, self).setUp()
        self.driver = driver.NoopNetworkDriver()
        self.port = mock.MagicMock()
        self.port_id = 88
        self.port_name = 'port1'
        self.port.id = self.port_id
        self.network_id = self.FAKE_UUID_3
        self.network_name = 'net1'
        self.device_id = self.FAKE_UUID_4
        self.ip_address = "10.0.0.2"
        self.load_balancer = models.LoadBalancer()
        self.load_balancer.id = self.FAKE_UUID_2

        self.vip = models.Vip()
        self.vip.ip_address = "10.0.0.1"
        self.amphora_id = self.FAKE_UUID_1
        self.compute_id = self.FAKE_UUID_2
        self.subnet_id = self.FAKE_UUID_3
        self.subnet_name = 'subnet1'

    def test_allocate_vip(self):
        self.driver.allocate_vip(self.load_balancer)
        self.assertEqual(
            (self.load_balancer, 'allocate_vip'),
            self.driver.driver.networkconfigconfig[self.load_balancer.id])

    def test_deallocate_vip(self):
        self.driver.deallocate_vip(self.vip)
        self.assertEqual((self.vip,
                          'deallocate_vip'),
                         self.driver.driver.networkconfigconfig[
                             self.vip.ip_address])

    def test_plug_vip(self):
        self.driver.plug_vip(self.load_balancer, self.vip)
        self.assertEqual((self.load_balancer, self.vip,
                          'plug_vip'),
                         self.driver.driver.networkconfigconfig[(
                             self.load_balancer.id, self.vip.ip_address)])

    def test_unplug_vip(self):
        self.driver.unplug_vip(self.load_balancer, self.vip)
        self.assertEqual((self.load_balancer, self.vip,
                          'unplug_vip'),
                         self.driver.driver.networkconfigconfig[(
                             self.load_balancer.id, self.vip.ip_address)])

    def test_plug_network(self):
        self.driver.plug_network(self.amphora_id, self.network_id,
                                 self.ip_address)
        self.assertEqual((self.amphora_id, self.network_id, self.ip_address,
                          'plug_network'),
                         self.driver.driver.networkconfigconfig[(
                             self.amphora_id, self.network_id,
                             self.ip_address)])

    def test_unplug_network(self):
        self.driver.unplug_network(self.amphora_id, self.network_id,
                                   ip_address=self.ip_address)
        self.assertEqual((self.amphora_id, self.network_id, self.ip_address,
                          'unplug_network'),
                         self.driver.driver.networkconfigconfig[(
                             self.amphora_id, self.network_id,
                             self.ip_address)])

    def test_get_plugged_networks(self):
        self.driver.get_plugged_networks(self.amphora_id)
        self.assertEqual((self.amphora_id, 'get_plugged_networks'),
                         self.driver.driver.networkconfigconfig[(
                             self.amphora_id)])

    def test_update_vip(self):
        self.driver.update_vip(self.load_balancer)
        self.assertEqual((self.load_balancer, 'update_vip'),
                         self.driver.driver.networkconfigconfig[(
                             self.load_balancer.id
                         )])

    def test_get_network(self):
        self.driver.get_network(self.network_id)
        self.assertEqual(
            (self.network_id, 'get_network'),
            self.driver.driver.networkconfigconfig[self.network_id]
        )

    def test_get_subnet(self):
        self.driver.get_subnet(self.subnet_id)
        self.assertEqual(
            (self.subnet_id, 'get_subnet'),
            self.driver.driver.networkconfigconfig[self.subnet_id]
        )

    def test_get_port(self):
        self.driver.get_port(self.port_id)
        self.assertEqual(
            (self.port_id, 'get_port'),
            self.driver.driver.networkconfigconfig[self.port_id]
        )

    def test_get_network_by_name(self):
        self.driver.get_network_by_name(self.network_name)
        self.assertEqual(
            (self.network_name, 'get_network_by_name'),
            self.driver.driver.networkconfigconfig[self.network_name]
        )

    def test_get_subnet_by_name(self):
        self.driver.get_subnet_by_name(self.subnet_name)
        self.assertEqual(
            (self.subnet_name, 'get_subnet_by_name'),
            self.driver.driver.networkconfigconfig[self.subnet_name]
        )

    def test_get_port_by_name(self):
        self.driver.get_port_by_name(self.port_name)
        self.assertEqual(
            (self.port_name, 'get_port_by_name'),
            self.driver.driver.networkconfigconfig[self.port_name]
        )

    def test_get_port_by_net_id_device_id(self):
        self.driver.get_port_by_net_id_device_id(self.network_id,
                                                 self.device_id)
        self.assertEqual(
            (self.network_id, self.device_id,
             'get_port_by_net_id_device_id'),
            self.driver.driver.networkconfigconfig[(self.network_id,
                                                    self.device_id)]
        )

    def test_plug_port(self):
        self.driver.plug_port(self.compute_id, self.port)
        self.assertEqual(
            (self.compute_id, self.port, 'plug_port'),
            self.driver.driver.networkconfigconfig[self.compute_id, self.port]
        )

    def test_get_network_configs(self):
        self.driver.get_network_configs(self.load_balancer)
        self.assertEqual(
            (self.load_balancer, 'get_network_configs'),
            self.driver.driver.networkconfigconfig[self.load_balancer.id]
        )
