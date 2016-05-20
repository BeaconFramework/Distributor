#    Copyright (c) 2016 IBM Corp.
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

from oslo_utils import uuidutils

from octavia.common import data_models
from octavia.db import models as models
from octavia.distributor.drivers.noop_driver import driver as driver
import octavia.tests.unit.base as base


class TestDistributorNoopDriver(base.TestCase):
    FAKE_UUID_1 = uuidutils.generate_uuid()
    FAKE_UUID_2 = uuidutils.generate_uuid()
    FAKE_MAC_ADDRESS = '123'

    def setUp(self):
        super(TestDistributorNoopDriver, self).setUp()
        self.driver = driver.NoopDistributorDriver()

        self.amphora = data_models.Amphora()
        self.amphora.id = self.FAKE_UUID_1
        self.load_balancer = data_models.LoadBalancer(
            id=self.FAKE_UUID_1, amphorae=[self.amphora])
        self.distributor = models.Distributor()
        self.distributor.id = self.FAKE_UUID_2
        self.cluster_alg_type = "TEST"
        self.cluster_min_size = 0

    def test_get_info(self):
        self.driver.get_info(self.distributor)
        self.assertEqual((self.distributor.id, 'get_info'),
                         self.driver.driver.distributor_config[
                             self.distributor.id])

    def test_get_diagnostics(self):
        self.driver.get_diagnostics(self.distributor)
        self.assertEqual((self.distributor.id, 'get_diagnostics'),
                         self.driver.driver.distributor_config[
                             self.distributor.id])

    def test_register_amphora(self):
        self.driver.register_amphora(self.distributor,
                                     self.load_balancer,
                                     self.amphora,
                                     self.cluster_alg_type,
                                     self.cluster_min_size)
        self.assertEqual((self.amphora.id, self.distributor.id,
                          self.load_balancer.id,
                          self.cluster_alg_type,
                          self.cluster_min_size,
                          'register_amphora'),
                         self.driver.driver.distributor_config[(
                             self.amphora.id,
                             self.distributor.id,
                             self.load_balancer.id,
                             self.cluster_alg_type,
                             self.cluster_min_size)])

    def test_unregister_amphora(self):
        self.driver.unregister_amphora(self.distributor,
                                       self.load_balancer,
                                       self.amphora,
                                       self.cluster_alg_type,
                                       self.cluster_min_size)
        self.assertEqual((self.amphora.id, self.distributor.id,
                          self.load_balancer.id,
                          self.cluster_alg_type,
                          self.cluster_min_size,
                          'unregister_amphora'),
                         self.driver.driver.distributor_config[(
                             self.amphora.id,
                             self.distributor.id,
                             self.load_balancer.id,
                             self.cluster_alg_type,
                             self.cluster_min_size)])

    def test_post_vip_plug(self):
        self.driver.post_vip_plug(self.distributor, self.load_balancer,
                                  self.FAKE_MAC_ADDRESS,
                                  self.cluster_alg_type, self.cluster_min_size)
        self.assertEqual((self.distributor.id,
                          self.load_balancer.id,
                          self.FAKE_MAC_ADDRESS,
                          self.cluster_alg_type,
                          self.cluster_min_size,
                          'post_vip_plug'),
                         self.driver.driver.distributor_config[(
                             self.distributor.id,
                             self.load_balancer.id,
                             self.FAKE_MAC_ADDRESS,
                             self.cluster_alg_type,
                             self.cluster_min_size)])

    def test_pre_vip_unplug(self):
        self.driver.pre_vip_unplug(self.distributor, self.load_balancer)
        self.assertEqual((self.load_balancer.id, self.distributor.id,
                          'pre_vip_unplug'),
                         self.driver.driver.distributor_config[(
                             self.load_balancer.id, self.distributor.id)])
