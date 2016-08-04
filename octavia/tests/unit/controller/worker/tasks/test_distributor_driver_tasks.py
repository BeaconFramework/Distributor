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

import mock
from oslo_utils import uuidutils

from octavia.common import constants
from octavia.controller.worker.tasks import distributor_driver_tasks
from octavia.db import repositories as repo
import octavia.tests.unit.base as base


DISTRIBUTOR_ID = uuidutils.generate_uuid()
COMPUTE_ID = uuidutils.generate_uuid()
LISTENER_ID = uuidutils.generate_uuid()
LB_ID = uuidutils.generate_uuid()
MOCK_MAC_ADDR = 'fe:16:3e:00:95:5c'

_distributor_mock = mock.MagicMock()
_distributor_mock.id = DISTRIBUTOR_ID
_distributor_mock.status = constants.DISTRIBUTOR_READY
_load_balancer_mock = mock.MagicMock()
_load_balancer_mock.id = LB_ID
_LB_mock = mock.MagicMock()
_session_mock = mock.MagicMock()


@mock.patch('octavia.db.api.get_session', return_value=_session_mock)
@mock.patch('octavia.controller.worker.tasks.amphora_driver_tasks.LOG')
@mock.patch('oslo_utils.uuidutils.generate_uuid', return_value=DISTRIBUTOR_ID)
@mock.patch('stevedore.driver.DriverManager.driver')
class TestDistributorDriverTasks(base.TestCase):

    def setUp(self):
        super(TestDistributorDriverTasks, self).setUp()
        _LB_mock.id = LB_ID

    @mock.patch('octavia.db.repositories.LoadBalancerRepository.update')
    @mock.patch('octavia.db.repositories.LoadBalancerRepository.get',
                return_value=_LB_mock)
    def test_distributor_post_vip_plug(self,
                                       mock_loadbalancer_repo_update,
                                       mock_loadbalancer_repo_get,
                                       mock_driver,
                                       mock_generate_uuid,
                                       mock_log,
                                       mock_get_session):
        distributor_post_vip_plug_obj = (distributor_driver_tasks.
                                         DistributorPostVIPPlug())
        distributor_post_vip_plug_obj.execute(_distributor_mock, _LB_mock,
                                              MOCK_MAC_ADDR, " ", 0)

        mock_driver.post_vip_plug.assert_called_once_with(
            _distributor_mock, _LB_mock, MOCK_MAC_ADDR, " ", 0)

        # Test revert
        distr = distributor_post_vip_plug_obj.revert(None, _LB_mock)
        repo.LoadBalancerRepository.update.assert_called_once_with(
            _session_mock,
            id=LB_ID,
            status=constants.ERROR)

        self.assertIsNone(distr)
