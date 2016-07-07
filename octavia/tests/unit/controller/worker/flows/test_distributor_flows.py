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
#

from oslo_config import cfg
from taskflow.patterns import linear_flow as flow

from octavia.common import constants
from octavia.controller.worker.flows import distributor_flows
import octavia.tests.unit.base as base

AUTH_VERSION = '2'


class TestDistributorFlows(base.TestCase):

    def setUp(self):
        super(TestDistributorFlows, self).setUp()
        old_distributor_driver = (
            cfg.CONF.active_active_cluster.distributor_driver)
        cfg.CONF.set_override('distributor_driver', 'distributor_rest_driver',
                              group='active_active_cluster')
        cfg.CONF.set_override('enable_anti_affinity', False,
                              group='nova')
        self.DistributorFlow = distributor_flows.DistributorFlows()

        self.addCleanup(cfg.CONF.set_override, 'distributor_driver',
                        old_distributor_driver, group='active_active_cluster')

    def test_get_create_distributor_flow(self):

        distributor_flow = self.DistributorFlow.get_create_distributor_flow()

        self.assertIsInstance(distributor_flow, flow.Flow)

        self.assertIn(constants.DISTRIBUTOR, distributor_flow.provides)
        self.assertIn(constants.DISTRIBUTOR_ID, distributor_flow.provides)
        self.assertIn(constants.COMPUTE_ID, distributor_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, distributor_flow.provides)
        self.assertIn(constants.SERVER_PEM, distributor_flow.provides)

        self.assertEqual(5, len(distributor_flow.provides))
        self.assertEqual(0, len(distributor_flow.requires))