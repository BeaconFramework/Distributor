# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright 2016 IBM
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

from octavia.amphorae.cluster_manager.drivers.noop_driver import (
    driver as driver)
import octavia.tests.unit.base as base


class TestAmphoraClusterNoopDriver(base.TestCase):

    def setUp(self):
        super(TestAmphoraClusterNoopDriver, self).setUp()
        self.driver = driver.NoopAmphoraClusterDriver()
        self.load_balancer_mock = mock.MagicMock()
        self.cluster_mock = mock.MagicMock()
        self.amphora_mock = mock.MagicMock()

    def test_create_cluster(self):
        self.driver.create_cluster_for_lb()
        self.assertEqual(('create_cluster_for_lb'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             "loadbalancer"]
                         )

    def test_create_amphorae(self):
        self.driver.create_amphorae()
        self.assertEqual(('create_amphorae'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             "amphora_cluster"]
                         )

    def test_delete_cluster_for_lb(self):
        self.driver.delete_cluster_for_lb(self.load_balancer_mock)
        self.assertEqual((self.load_balancer_mock, 'delete_cluster_for_lb'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             self.load_balancer_mock]
                         )

    def test_finalize_amphora_cluster(self):
        self.driver.finalize_amphora_cluster()
        self.assertEqual(('finalize_amphora_cluster'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             "amphora_cluster"]
                         )

    def test_recover_from_amphora_failure(self):
        self.driver.recover_from_amphora_failure(self.amphora_mock,
                                                 self.load_balancer_mock)
        self.assertEqual(((self.amphora_mock, self.load_balancer_mock),
                          'recover_from_amphora_failure'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             (self.amphora_mock, self.load_balancer_mock)]
                         )

    def test_grow_cluster_for_lb(self):
        self.driver.grow_cluster_for_lb(self.load_balancer_mock)
        self.assertEqual((self.load_balancer_mock, 'grow_cluster_for_lb'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             self.load_balancer_mock]
                         )

    def test_shrink_cluster_for_lb(self):
        self.driver.shrink_cluster_for_lb(self.load_balancer_mock)
        self.assertEqual((self.load_balancer_mock, 'shrink_cluster_for_lb'),
                         self.driver.driver.AmphoraClusterManagerConfig[
                             self.load_balancer_mock]
                         )