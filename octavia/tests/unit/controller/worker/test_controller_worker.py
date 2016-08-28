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
# License for the specific language governing permissions and limitations
# under the License.
#

import mock
from oslo_config import cfg
from oslo_utils import uuidutils

from octavia.common import base_taskflow
from octavia.common import constants
from octavia.common import data_models
from octavia.controller.worker import controller_worker
import octavia.tests.unit.base as base


AMP_ID = uuidutils.generate_uuid()
LB_ID = uuidutils.generate_uuid()
POOL_ID = uuidutils.generate_uuid()
HM_ID = uuidutils.generate_uuid()
MEMBER_ID = uuidutils.generate_uuid()
COMPUTE_ID = uuidutils.generate_uuid()
L7POLICY_ID = uuidutils.generate_uuid()
L7RULE_ID = uuidutils.generate_uuid()
HEALTH_UPDATE_DICT = {'delay': 1, 'timeout': 2}
LISTENER_UPDATE_DICT = {'name': 'test', 'description': 'test2'}
MEMBER_UPDATE_DICT = {'weight': 1, 'ip_address': '10.0.0.0'}
POOL_UPDATE_DICT = {'name': 'test', 'description': 'test2'}
L7POLICY_UPDATE_DICT = {'action': constants.L7POLICY_ACTION_REJECT}
L7RULE_UPDATE_DICT = {
    'type': constants.L7RULE_TYPE_PATH,
    'compare_type': constants.L7RULE_COMPARE_TYPE_STARTS_WITH,
    'value': '/api'}

_amphora_mock = mock.MagicMock()
_flow_mock = mock.MagicMock()
_health_mon_mock = mock.MagicMock()
_vip_mock = mock.MagicMock()
_listener_mock = mock.MagicMock()
_load_balancer_mock = mock.MagicMock()
_member_mock = mock.MagicMock()
_pool_mock = mock.MagicMock()
_l7policy_mock = mock.MagicMock()
_l7rule_mock = mock.MagicMock()
_create_map_flow_mock = mock.MagicMock()
_amphora_mock.load_balancer_id = LB_ID
_amphora_mock.id = AMP_ID

CONF = cfg.CONF


@mock.patch('octavia.db.repositories.AmphoraRepository.get',
            return_value=_amphora_mock)
@mock.patch('octavia.db.repositories.HealthMonitorRepository.get',
            return_value=_health_mon_mock)
@mock.patch('octavia.db.repositories.LoadBalancerRepository.get',
            return_value=_load_balancer_mock)
@mock.patch('octavia.db.repositories.ListenerRepository.get',
            return_value=_listener_mock)
@mock.patch('octavia.db.repositories.L7PolicyRepository.get',
            return_value=_l7policy_mock)
@mock.patch('octavia.db.repositories.L7RuleRepository.get',
            return_value=_l7rule_mock)
@mock.patch('octavia.db.repositories.MemberRepository.get',
            return_value=_member_mock)
@mock.patch('octavia.db.repositories.PoolRepository.get',
            return_value=_pool_mock)
@mock.patch('octavia.common.base_taskflow.BaseTaskFlowEngine._taskflow_load',
            return_value=_flow_mock)
@mock.patch('taskflow.listeners.logging.DynamicLoggingListener')
@mock.patch('octavia.db.api.get_session', return_value='TEST')
class TestControllerWorker(base.TestCase):

    def setUp(self):

        _health_mon_mock.pool.load_balancer.amphorae = _amphora_mock
        _health_mon_mock.pool.listeners = [_listener_mock]
        _health_mon_mock.pool.load_balancer = _load_balancer_mock
        _health_mon_mock.pool.load_balancer.vip = _vip_mock
        _listener_mock.load_balancer = _load_balancer_mock
        _listener_mock.load_balancer.amphorae = _amphora_mock
        _listener_mock.load_balancer.vip = _vip_mock
        _member_mock.pool.listeners = [_listener_mock]
        _member_mock.pool.load_balancer = _load_balancer_mock
        _member_mock.pool.load_balancer.vip = _vip_mock
        _pool_mock.listeners = [_listener_mock]
        _pool_mock.load_balancer = _load_balancer_mock
        _pool_mock.load_balancer.vip = _vip_mock
        _l7policy_mock.listener = _listener_mock
        _l7rule_mock.l7policy = _l7policy_mock

        fetch_mock = mock.MagicMock(return_value=AMP_ID)
        _flow_mock.storage.fetch = fetch_mock

        _health_mon_mock.pool_id = POOL_ID
        _health_mon_mock.id = HM_ID

        super(TestControllerWorker, self).setUp()

    @mock.patch('octavia.controller.worker.flows.'
                'amphora_flows.AmphoraFlows.get_create_amphora_flow',
                return_value='TEST')
    def test_create_amphora(self,
                            mock_api_get_session,
                            mock_get_create_amp_flow,
                            mock_dyn_log_listener,
                            mock_taskflow_load,
                            mock_pool_repo_get,
                            mock_member_repo_get,
                            mock_l7rule_repo_get,
                            mock_l7policy_repo_get,
                            mock_listener_repo_get,
                            mock_lb_repo_get,
                            mock_health_mon_repo_get,
                            mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        amp = cw.create_amphora()

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with('TEST'))

        _flow_mock.run.assert_called_once_with()

        _flow_mock.storage.fetch.assert_called_once_with('amphora')

        assert (amp == AMP_ID)

    @mock.patch('octavia.controller.worker.flows.'
                'amphora_flows.AmphoraFlows.get_delete_amphora_flow',
                return_value='TEST')
    def test_delete_amphora(self,
                            mock_get_delete_amp_flow,
                            mock_api_get_session,
                            mock_dyn_log_listener,
                            mock_taskflow_load,
                            mock_pool_repo_get,
                            mock_member_repo_get,
                            mock_l7rule_repo_get,
                            mock_l7policy_repo_get,
                            mock_listener_repo_get,
                            mock_lb_repo_get,
                            mock_health_mon_repo_get,
                            mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_amphora(AMP_ID)

        mock_amp_repo_get.assert_called_once_with(
            'TEST',
            id=AMP_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with('TEST',
                                    store={constants.AMPHORA: _amphora_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'health_monitor_flows.HealthMonitorFlows.'
                'get_create_health_monitor_flow',
                return_value=_flow_mock)
    def test_create_health_monitor(self,
                                   mock_get_create_hm_flow,
                                   mock_api_get_session,
                                   mock_dyn_log_listener,
                                   mock_taskflow_load,
                                   mock_pool_repo_get,
                                   mock_member_repo_get,
                                   mock_l7rule_repo_get,
                                   mock_l7policy_repo_get,
                                   mock_listener_repo_get,
                                   mock_lb_repo_get,
                                   mock_health_mon_repo_get,
                                   mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.create_health_monitor(_health_mon_mock)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.HEALTH_MON:
                                           _health_mon_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'health_monitor_flows.HealthMonitorFlows.'
                'get_delete_health_monitor_flow',
                return_value=_flow_mock)
    def test_delete_health_monitor(self,
                                   mock_get_delete_hm_flow,
                                   mock_api_get_session,
                                   mock_dyn_log_listener,
                                   mock_taskflow_load,
                                   mock_pool_repo_get,
                                   mock_member_repo_get,
                                   mock_l7rule_repo_get,
                                   mock_l7policy_repo_get,
                                   mock_listener_repo_get,
                                   mock_lb_repo_get,
                                   mock_health_mon_repo_get,
                                   mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_health_monitor(HM_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.HEALTH_MON:
                                           _health_mon_mock,
                                           constants.POOL_ID: HM_ID,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'health_monitor_flows.HealthMonitorFlows.'
                'get_update_health_monitor_flow',
                return_value=_flow_mock)
    def test_update_health_monitor(self,
                                   mock_get_update_hm_flow,
                                   mock_api_get_session,
                                   mock_dyn_log_listener,
                                   mock_taskflow_load,
                                   mock_pool_repo_get,
                                   mock_member_repo_get,
                                   mock_l7rule_repo_get,
                                   mock_l7policy_repo_get,
                                   mock_listener_repo_get,
                                   mock_lb_repo_get,
                                   mock_health_mon_repo_get,
                                   mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.update_health_monitor(_health_mon_mock.id,
                                 HEALTH_UPDATE_DICT)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.HEALTH_MON:
                                           _health_mon_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock,
                                           constants.UPDATE_DICT:
                                           HEALTH_UPDATE_DICT}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'listener_flows.ListenerFlows.get_create_listener_flow',
                return_value=_flow_mock)
    def test_create_listener(self,
                             mock_get_create_listener_flow,
                             mock_api_get_session,
                             mock_dyn_log_listener,
                             mock_taskflow_load,
                             mock_pool_repo_get,
                             mock_member_repo_get,
                             mock_l7rule_repo_get,
                             mock_l7policy_repo_get,
                             mock_listener_repo_get,
                             mock_lb_repo_get,
                             mock_health_mon_repo_get,
                             mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.create_listener(LB_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.LOADBALANCER:
                                           _load_balancer_mock,
                                           constants.LISTENERS:
                                           [_listener_mock]}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'listener_flows.ListenerFlows.get_delete_listener_flow',
                return_value=_flow_mock)
    def test_delete_listener(self,
                             mock_get_delete_listener_flow,
                             mock_api_get_session,
                             mock_dyn_log_listener,
                             mock_taskflow_load,
                             mock_pool_repo_get,
                             mock_member_repo_get,
                             mock_l7rule_repo_get,
                             mock_l7policy_repo_get,
                             mock_listener_repo_get,
                             mock_lb_repo_get,
                             mock_health_mon_repo_get,
                             mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_listener(LB_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
         assert_called_once_with(
             _flow_mock, store={constants.LISTENER: _listener_mock,
                                constants.LOADBALANCER: _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'listener_flows.ListenerFlows.get_update_listener_flow',
                return_value=_flow_mock)
    def test_update_listener(self,
                             mock_get_update_listener_flow,
                             mock_api_get_session,
                             mock_dyn_log_listener,
                             mock_taskflow_load,
                             mock_pool_repo_get,
                             mock_member_repo_get,
                             mock_l7rule_repo_get,
                             mock_l7policy_repo_get,
                             mock_listener_repo_get,
                             mock_lb_repo_get,
                             mock_health_mon_repo_get,
                             mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.update_listener(LB_ID, LISTENER_UPDATE_DICT)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.LISTENER: _listener_mock,
                                           constants.LOADBALANCER:
                                           _load_balancer_mock,
                                           constants.UPDATE_DICT:
                                           LISTENER_UPDATE_DICT,
                                           constants.LISTENERS:
                                           [_listener_mock]}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_create_load_balancer_flow',
                return_value=_flow_mock)
    def test_create_load_balancer_single(
            self,
            mock_get_create_load_balancer_flow,
            mock_api_get_session,
            mock_dyn_log_listener,
            mock_taskflow_load,
            mock_pool_repo_get,
            mock_member_repo_get,
            mock_l7rule_repo_get,
            mock_l7policy_repo_get,
            mock_listener_repo_get,
            mock_lb_repo_get,
            mock_health_mon_repo_get,
            mock_amp_repo_get):

        # Test the code path with an SINGLE topology
        CONF.set_override(group='controller_worker',
                          name='loadbalancer_topology',
                          override=constants.TOPOLOGY_SINGLE,
                          enforce_type=True)
        _flow_mock.reset_mock()
        mock_taskflow_load.reset_mock()
        mock_eng = mock.Mock()
        mock_taskflow_load.return_value = mock_eng
        store = {
            constants.LOADBALANCER_ID: LB_ID,
            'update_dict': {'topology': constants.TOPOLOGY_SINGLE}
        }
        setattr(mock_lb_repo_get.return_value, 'listeners', [])

        cw = controller_worker.ControllerWorker()
        cw.create_load_balancer(LB_ID)

        mock_get_create_load_balancer_flow.assert_called_with(
            topology=constants.TOPOLOGY_SINGLE, listeners=[])
        mock_taskflow_load.assert_called_with(
            mock_get_create_load_balancer_flow.return_value, store=store)
        mock_eng.run.assert_any_call()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_create_load_balancer_flow',
                return_value=_flow_mock)
    def test_create_load_balancer_active_standby(
            self,
            mock_get_create_load_balancer_flow,
            mock_api_get_session,
            mock_dyn_log_listener,
            mock_taskflow_load,
            mock_pool_repo_get,
            mock_member_repo_get,
            mock_l7rule_repo_get,
            mock_l7policy_repo_get,
            mock_listener_repo_get,
            mock_lb_repo_get,
            mock_health_mon_repo_get,
            mock_amp_repo_get):

        CONF.set_override(group='controller_worker',
                          name='loadbalancer_topology',
                          override=constants.TOPOLOGY_ACTIVE_STANDBY,
                          enforce_type=True)
        _flow_mock.reset_mock()
        mock_taskflow_load.reset_mock()
        mock_eng = mock.Mock()
        mock_taskflow_load.return_value = mock_eng
        store = {
            constants.LOADBALANCER_ID: LB_ID,
            'update_dict': {'topology': constants.TOPOLOGY_ACTIVE_STANDBY}
        }
        setattr(mock_lb_repo_get.return_value, 'listeners', [])

        cw = controller_worker.ControllerWorker()
        cw.create_load_balancer(LB_ID)

        mock_get_create_load_balancer_flow.assert_called_with(
            topology=constants.TOPOLOGY_ACTIVE_STANDBY, listeners=[])
        mock_taskflow_load.assert_called_with(
            mock_get_create_load_balancer_flow.return_value, store=store)
        mock_eng.run.assert_any_call()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_create_load_balancer_flow')
    def test_create_load_balancer_full_graph_single(
            self,
            mock_get_create_load_balancer_flow,
            mock_api_get_session,
            mock_dyn_log_listener,
            mock_taskflow_load,
            mock_pool_repo_get,
            mock_member_repo_get,
            mock_l7rule_repo_get,
            mock_l7policy_repo_get,
            mock_listener_repo_get,
            mock_lb_repo_get,
            mock_health_mon_repo_get,
            mock_amp_repo_get):
        CONF.set_override(group='controller_worker',
                          name='loadbalancer_topology',
                          override=constants.TOPOLOGY_SINGLE,
                          enforce_type=True)
        listeners = [data_models.Listener(id='listener1'),
                     data_models.Listener(id='listener2')]
        lb = data_models.LoadBalancer(id=LB_ID, listeners=listeners)
        mock_lb_repo_get.return_value = lb
        mock_eng = mock.Mock()
        mock_taskflow_load.return_value = mock_eng
        store = {
            constants.LOADBALANCER_ID: LB_ID,
            'update_dict': {'topology': constants.TOPOLOGY_SINGLE}
        }

        cw = controller_worker.ControllerWorker()
        cw.create_load_balancer(LB_ID)

        # mock_create_single_topology.assert_called_once()
        # mock_create_active_standby_topology.assert_not_called()
        mock_get_create_load_balancer_flow.assert_called_with(
            topology=constants.TOPOLOGY_SINGLE, listeners=lb.listeners)
        mock_taskflow_load.assert_called_with(
            mock_get_create_load_balancer_flow.return_value, store=store)
        mock_eng.run.assert_any_call()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_create_load_balancer_flow')
    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows._create_single_topology')
    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows._create_active_standby_topology')
    def test_create_load_balancer_full_graph_active_standby(
            self,
            mock_create_active_standby_topology,
            mock_create_single_topology,
            mock_get_create_load_balancer_flow,
            mock_api_get_session,
            mock_dyn_log_listener,
            mock_taskflow_load,
            mock_pool_repo_get,
            mock_member_repo_get,
            mock_l7rule_repo_get,
            mock_l7policy_repo_get,
            mock_listener_repo_get,
            mock_lb_repo_get,
            mock_health_mon_repo_get,
            mock_amp_repo_get):
        CONF.set_override(group='controller_worker',
                          name='loadbalancer_topology',
                          override=constants.TOPOLOGY_ACTIVE_STANDBY,
                          enforce_type=True)
        listeners = [data_models.Listener(id='listener1'),
                     data_models.Listener(id='listener2')]
        lb = data_models.LoadBalancer(id=LB_ID, listeners=listeners)
        mock_lb_repo_get.return_value = lb
        mock_eng = mock.Mock()
        mock_taskflow_load.return_value = mock_eng
        store = {
            constants.LOADBALANCER_ID: LB_ID,
            'update_dict': {'topology': constants.TOPOLOGY_ACTIVE_STANDBY}
        }

        cw = controller_worker.ControllerWorker()
        cw.create_load_balancer(LB_ID)

        # mock_create_single_topology.assert_not_called()
        # mock_create_active_standby_topology.assert_called_once()
        mock_get_create_load_balancer_flow.assert_called_with(
            topology=constants.TOPOLOGY_ACTIVE_STANDBY, listeners=lb.listeners)
        mock_taskflow_load.assert_called_with(
            mock_get_create_load_balancer_flow.return_value, store=store)
        mock_eng.run.assert_any_call()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_delete_load_balancer_flow',
                return_value=(_flow_mock, {'test': 'test'}))
    def test_delete_load_balancer_without_cascade(self,
                                                  mock_get_delete_lb_flow,
                                                  mock_api_get_session,
                                                  mock_dyn_log_listener,
                                                  mock_taskflow_load,
                                                  mock_pool_repo_get,
                                                  mock_member_repo_get,
                                                  mock_l7rule_repo_get,
                                                  mock_l7policy_repo_get,
                                                  mock_listener_repo_get,
                                                  mock_lb_repo_get,
                                                  mock_health_mon_repo_get,
                                                  mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_load_balancer(LB_ID, cascade=False)

        mock_lb_repo_get.assert_called_once_with(
            'TEST',
            id=LB_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.LOADBALANCER:
                                           _load_balancer_mock,
                                           constants.SERVER_GROUP_ID:
                                           _load_balancer_mock.server_group_id,
                                           'test': 'test'
                                           }
                                    )
         )
        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_cascade_delete_load_balancer_flow',
                return_value=(_flow_mock, {'test': 'test'}))
    def test_delete_load_balancer_with_cascade(self,
                                               mock_get_delete_lb_flow,
                                               mock_api_get_session,
                                               mock_dyn_log_listener,
                                               mock_taskflow_load,
                                               mock_pool_repo_get,
                                               mock_member_repo_get,
                                               mock_l7rule_repo_get,
                                               mock_l7policy_repo_get,
                                               mock_listener_repo_get,
                                               mock_lb_repo_get,
                                               mock_health_mon_repo_get,
                                               mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_load_balancer(LB_ID, cascade=True)

        mock_lb_repo_get.assert_called_once_with(
            'TEST',
            id=LB_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.LOADBALANCER:
                                           _load_balancer_mock,
                                           constants.SERVER_GROUP_ID:
                                           _load_balancer_mock.server_group_id,
                                           'test': 'test'
                                           }
                                    )
         )
        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.load_balancer_flows.'
                'LoadBalancerFlows.get_update_load_balancer_flow',
                return_value=_flow_mock)
    @mock.patch('octavia.db.repositories.ListenerRepository.get_all',
                return_value=[_listener_mock])
    def test_update_load_balancer(self,
                                  mock_listener_repo_get_all,
                                  mock_get_update_lb_flow,
                                  mock_api_get_session,
                                  mock_dyn_log_listener,
                                  mock_taskflow_load,
                                  mock_pool_repo_get,
                                  mock_member_repo_get,
                                  mock_l7rule_repo_get,
                                  mock_l7policy_repo_get,
                                  mock_listener_repo_get,
                                  mock_lb_repo_get,
                                  mock_health_mon_repo_get,
                                  mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        change = 'TEST2'
        cw.update_load_balancer(LB_ID, change)

        mock_lb_repo_get.assert_called_once_with(
            'TEST',
            id=LB_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.UPDATE_DICT: change,
                                           constants.LOADBALANCER:
                                               _load_balancer_mock,
                                           constants.LISTENERS:
                                               [_listener_mock]}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'member_flows.MemberFlows.get_create_member_flow',
                return_value=_flow_mock)
    def test_create_member(self,
                           mock_get_create_member_flow,
                           mock_api_get_session,
                           mock_dyn_log_listener,
                           mock_taskflow_load,
                           mock_pool_repo_get,
                           mock_member_repo_get,
                           mock_l7rule_repo_get,
                           mock_l7policy_repo_get,
                           mock_listener_repo_get,
                           mock_lb_repo_get,
                           mock_health_mon_repo_get,
                           mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.create_member(MEMBER_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.MEMBER: _member_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'member_flows.MemberFlows.get_delete_member_flow',
                return_value=_flow_mock)
    def test_delete_member(self,
                           mock_get_delete_member_flow,
                           mock_api_get_session,
                           mock_dyn_log_listener,
                           mock_taskflow_load,
                           mock_pool_repo_get,
                           mock_member_repo_get,
                           mock_l7rule_repo_get,
                           mock_l7policy_repo_get,
                           mock_listener_repo_get,
                           mock_lb_repo_get,
                           mock_health_mon_repo_get,
                           mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_member(MEMBER_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(
                _flow_mock, store={constants.MEMBER: _member_mock,
                                   constants.LISTENERS:
                                       [_listener_mock],
                                   constants.LOADBALANCER:
                                       _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'member_flows.MemberFlows.get_update_member_flow',
                return_value=_flow_mock)
    def test_update_member(self,
                           mock_get_update_member_flow,
                           mock_api_get_session,
                           mock_dyn_log_listener,
                           mock_taskflow_load,
                           mock_pool_repo_get,
                           mock_member_repo_get,
                           mock_l7rule_repo_get,
                           mock_l7policy_repo_get,
                           mock_listener_repo_get,
                           mock_lb_repo_get,
                           mock_health_mon_repo_get,
                           mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.update_member(MEMBER_ID, MEMBER_UPDATE_DICT)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.MEMBER: _member_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock,
                                           constants.UPDATE_DICT:
                                               MEMBER_UPDATE_DICT}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'pool_flows.PoolFlows.get_create_pool_flow',
                return_value=_flow_mock)
    def test_create_pool(self,
                         mock_get_create_listener_flow,
                         mock_api_get_session,
                         mock_dyn_log_listener,
                         mock_taskflow_load,
                         mock_pool_repo_get,
                         mock_member_repo_get,
                         mock_l7rule_repo_get,
                         mock_l7policy_repo_get,
                         mock_listener_repo_get,
                         mock_lb_repo_get,
                         mock_health_mon_repo_get,
                         mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.create_pool(POOL_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.POOL: _pool_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'pool_flows.PoolFlows.get_delete_pool_flow',
                return_value=_flow_mock)
    def test_delete_pool(self,
                         mock_get_delete_listener_flow,
                         mock_api_get_session,
                         mock_dyn_log_listener,
                         mock_taskflow_load,
                         mock_pool_repo_get,
                         mock_member_repo_get,
                         mock_l7rule_repo_get,
                         mock_l7policy_repo_get,
                         mock_listener_repo_get,
                         mock_lb_repo_get,
                         mock_health_mon_repo_get,
                         mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_pool(POOL_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.POOL: _pool_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'pool_flows.PoolFlows.get_update_pool_flow',
                return_value=_flow_mock)
    def test_update_pool(self,
                         mock_get_update_listener_flow,
                         mock_api_get_session,
                         mock_dyn_log_listener,
                         mock_taskflow_load,
                         mock_pool_repo_get,
                         mock_member_repo_get,
                         mock_l7rule_repo_get,
                         mock_l7policy_repo_get,
                         mock_listener_repo_get,
                         mock_lb_repo_get,
                         mock_health_mon_repo_get,
                         mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.update_pool(POOL_ID, POOL_UPDATE_DICT)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.POOL: _pool_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock,
                                           constants.UPDATE_DICT:
                                               POOL_UPDATE_DICT}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'l7policy_flows.L7PolicyFlows.get_create_l7policy_flow',
                return_value=_flow_mock)
    def test_create_l7policy(self,
                             mock_get_create_listener_flow,
                             mock_api_get_session,
                             mock_dyn_log_listener,
                             mock_taskflow_load,
                             mock_pool_repo_get,
                             mock_member_repo_get,
                             mock_l7rule_repo_get,
                             mock_l7policy_repo_get,
                             mock_listener_repo_get,
                             mock_lb_repo_get,
                             mock_health_mon_repo_get,
                             mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.create_l7policy(L7POLICY_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.L7POLICY: _l7policy_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'l7policy_flows.L7PolicyFlows.get_delete_l7policy_flow',
                return_value=_flow_mock)
    def test_delete_l7policy(self,
                             mock_get_delete_listener_flow,
                             mock_api_get_session,
                             mock_dyn_log_listener,
                             mock_taskflow_load,
                             mock_pool_repo_get,
                             mock_member_repo_get,
                             mock_l7rule_repo_get,
                             mock_l7policy_repo_get,
                             mock_listener_repo_get,
                             mock_lb_repo_get,
                             mock_health_mon_repo_get,
                             mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_l7policy(L7POLICY_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.L7POLICY: _l7policy_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'l7policy_flows.L7PolicyFlows.get_update_l7policy_flow',
                return_value=_flow_mock)
    def test_update_l7policy(self,
                             mock_get_update_listener_flow,
                             mock_api_get_session,
                             mock_dyn_log_listener,
                             mock_taskflow_load,
                             mock_pool_repo_get,
                             mock_member_repo_get,
                             mock_l7rule_repo_get,
                             mock_l7policy_repo_get,
                             mock_listener_repo_get,
                             mock_lb_repo_get,
                             mock_health_mon_repo_get,
                             mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.update_l7policy(L7POLICY_ID, L7POLICY_UPDATE_DICT)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.L7POLICY: _l7policy_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock,
                                           constants.UPDATE_DICT:
                                               L7POLICY_UPDATE_DICT}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'l7rule_flows.L7RuleFlows.get_create_l7rule_flow',
                return_value=_flow_mock)
    def test_create_l7rule(self,
                           mock_get_create_listener_flow,
                           mock_api_get_session,
                           mock_dyn_log_listener,
                           mock_taskflow_load,
                           mock_pool_repo_get,
                           mock_member_repo_get,
                           mock_l7rule_repo_get,
                           mock_l7policy_repo_get,
                           mock_listener_repo_get,
                           mock_lb_repo_get,
                           mock_health_mon_repo_get,
                           mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.create_l7rule(L7RULE_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.L7RULE: _l7rule_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'l7rule_flows.L7RuleFlows.get_delete_l7rule_flow',
                return_value=_flow_mock)
    def test_delete_l7rule(self,
                           mock_get_delete_listener_flow,
                           mock_api_get_session,
                           mock_dyn_log_listener,
                           mock_taskflow_load,
                           mock_pool_repo_get,
                           mock_member_repo_get,
                           mock_l7rule_repo_get,
                           mock_l7policy_repo_get,
                           mock_listener_repo_get,
                           mock_lb_repo_get,
                           mock_health_mon_repo_get,
                           mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.delete_l7rule(L7RULE_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.L7RULE: _l7rule_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'l7rule_flows.L7RuleFlows.get_update_l7rule_flow',
                return_value=_flow_mock)
    def test_update_l7rule(self,
                           mock_get_update_listener_flow,
                           mock_api_get_session,
                           mock_dyn_log_listener,
                           mock_taskflow_load,
                           mock_pool_repo_get,
                           mock_member_repo_get,
                           mock_l7rule_repo_get,
                           mock_l7policy_repo_get,
                           mock_listener_repo_get,
                           mock_lb_repo_get,
                           mock_health_mon_repo_get,
                           mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.update_l7rule(L7RULE_ID, L7RULE_UPDATE_DICT)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(_flow_mock,
                                    store={constants.L7RULE: _l7rule_mock,
                                           constants.LISTENERS:
                                               [_listener_mock],
                                           constants.LOADBALANCER:
                                               _load_balancer_mock,
                                           constants.UPDATE_DICT:
                                               L7RULE_UPDATE_DICT}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'amphora_flows.AmphoraFlows.get_failover_flow',
                return_value=_flow_mock)
    def test_failover_amphora(self,
                              mock_get_update_listener_flow,
                              mock_api_get_session,
                              mock_dyn_log_listener,
                              mock_taskflow_load,
                              mock_pool_repo_get,
                              mock_member_repo_get,
                              mock_l7rule_repo_get,
                              mock_l7policy_repo_get,
                              mock_listener_repo_get,
                              mock_lb_repo_get,
                              mock_health_mon_repo_get,
                              mock_amp_repo_get):

        _flow_mock.reset_mock()

        cw = controller_worker.ControllerWorker()
        cw.failover_amphora(AMP_ID)

        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
            assert_called_once_with(
                _flow_mock,
                store={constants.FAILED_AMPHORA: _amphora_mock,
                       constants.LOADBALANCER_ID:
                           _amphora_mock.load_balancer_id}))

        _flow_mock.run.assert_called_once_with()

    @mock.patch('octavia.controller.worker.flows.'
                'amphora_flows.AmphoraFlows.cert_rotate_amphora_flow',
                return_value=_flow_mock)
    def test_amphora_cert_rotation(self,
                                   mock_get_update_listener_flow,
                                   mock_api_get_session,
                                   mock_dyn_log_listener,
                                   mock_taskflow_load,
                                   mock_pool_repo_get,
                                   mock_member_repo_get,
                                   mock_l7rule_repo_get,
                                   mock_l7policy_repo_get,
                                   mock_listener_repo_get,
                                   mock_lb_repo_get,
                                   mock_health_mon_repo_get,
                                   mock_amp_repo_get):
        _flow_mock.reset_mock()
        cw = controller_worker.ControllerWorker()
        cw.amphora_cert_rotation(AMP_ID)
        (base_taskflow.BaseTaskFlowEngine._taskflow_load.
         assert_called_once_with(_flow_mock,
                                 store={constants.AMPHORA: _amphora_mock,
                                        constants.AMPHORA_ID:
                                            _amphora_mock.id}))
        _flow_mock.run.assert_called_once_with()
