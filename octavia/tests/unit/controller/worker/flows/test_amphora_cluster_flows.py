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
# License for the specific language governing permissions and limitations
# under the License.
#

from taskflow.patterns import linear_flow as flow

from octavia.common import constants
from octavia.controller.worker.flows import amphora_cluster_flows
import octavia.tests.unit.base as base


class TestAmphoraClusterFlows(base.TestCase):

    def setUp(self):
        super(TestAmphoraClusterFlows, self).setUp()
        self.AmphoraClusterFlow = amphora_cluster_flows.AmphoraClusterFlows()

    def test_get_amphora_cluster_for_lb_subflow(self):

        amp_cluster_flow = (
            self.AmphoraClusterFlow.get_amphora_cluster_for_lb_subflow())

        self.assertIsInstance(amp_cluster_flow, flow.Flow)

        self.assertIn(constants.LOADBALANCER, amp_cluster_flow.provides)
        self.assertIn(constants.LOADBALANCER_ID, amp_cluster_flow.requires)

        self.assertEqual(1, len(amp_cluster_flow.provides))
        self.assertEqual(1, len(amp_cluster_flow.requires))