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

from oslo_utils import uuidutils

from octavia.compute.drivers.noop_driver import driver as driver
import octavia.tests.unit.base as base


class TestNoopComputeDriver(base.TestCase):
    FAKE_UUID_1 = uuidutils.generate_uuid()
    FAKE_UUID_2 = uuidutils.generate_uuid()
    FAKE_UUID_3 = uuidutils.generate_uuid()

    def setUp(self):
        super(TestNoopComputeDriver, self).setUp()
        self.driver = driver.NoopComputeDriver()

        self.name = "amphora_name"
        self.amphora_flavor = "m1.tiny"
        self.image_id = self.FAKE_UUID_2
        self.image_tag = "faketag"
        self.key_name = "key_name"
        self.sec_groups = "default"
        self.network_ids = self.FAKE_UUID_3
        self.confdrivefiles = "config_driver_files"
        self.user_data = "user_data"
        self.amphora_id = self.FAKE_UUID_1
        self.distributor_id = self.FAKE_UUID_1
        self.loadbalancer_id = self.FAKE_UUID_1
        self.server_group_policy = 'anti-affinity'
        self.server_group_id = self.FAKE_UUID_1

    def build(self):
        self.driver.build(self.name, self.amphora_flavor,
                          self.image_id, self.image_tag,
                          self.key_name, self.sec_groups, self.network_ids,
                          self.confdrivefiles, self.user_data,
                          self.server_group_id)

        self.assertEqual((self.name, self.amphora_flavor,
                          self.image_id, self.image_tag,
                          self.key_name, self.sec_groups, self.network_ids,
                          self.config_drive_files, self.user_data,
                          self.server_group_id, 'build'),
                         self.driver.driver.computeconfig[(self.name,
                                                           self.amphora_flavor,
                                                           self.image_id,
                                                           self.image_tag,
                                                           self.key_name,
                                                           self.sec_groups,
                                                           self.network_ids,
                                                           self.confdrivefiles,
                                                           self.user_data,
                                                           self.server_group_id
                                                           )])

    def test_delete(self):
        self.driver.delete(self.amphora_id)
        self.assertEqual((self.amphora_id, 'delete'),
                         self.driver.driver.computeconfig[
                             self.amphora_id])

    def status(self):
        self.driver.status(self.amphora_id)

    def test_distributor_status(self):
        self.driver.distributor_status(self.distributor_id)

    def get_amphora(self):
        self.driver.get_amphora(self.amphora_id)

    def get_distributor(self):
        self.driver.get_distributor(self.distributor_id)

    def test_create_server_group(self):
        self.driver.create_server_group(self.loadbalancer_id,
                                        self.server_group_policy)

    def test_delete_server_group(self):
        self.driver.delete_server_group(self.server_group_id)
