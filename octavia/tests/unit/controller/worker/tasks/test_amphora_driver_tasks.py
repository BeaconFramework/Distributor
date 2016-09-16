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
from oslo_utils import uuidutils
from taskflow.types import failure

from octavia.common import constants
from octavia.common import data_models
from octavia.controller.worker.tasks import amphora_driver_tasks
from octavia.db import repositories as repo
import octavia.tests.unit.base as base


AMP_ID = uuidutils.generate_uuid()
COMPUTE_ID = uuidutils.generate_uuid()
LISTENER_ID = uuidutils.generate_uuid()
LB_ID = uuidutils.generate_uuid()

_amphora_mock = mock.MagicMock()
_amphora_mock.id = AMP_ID
_amphora_mock.status = constants.AMPHORA_ALLOCATED
_load_balancer_mock = mock.MagicMock()
_load_balancer_mock.id = LB_ID
_listener_mock = mock.MagicMock()
_listener_mock.id = LISTENER_ID
_load_balancer_mock.listeners = [_listener_mock]
_vip_mock = mock.MagicMock()
_load_balancer_mock.vip = _vip_mock
_LB_mock = mock.MagicMock()
_amphorae_mock = [_amphora_mock]
_network_mock = mock.MagicMock()
_port_mock = mock.MagicMock()
_ports_mock = [_port_mock]
_session_mock = mock.MagicMock()


@mock.patch('octavia.db.repositories.AmphoraRepository.update')
@mock.patch('octavia.db.repositories.ListenerRepository.update')
@mock.patch('octavia.db.repositories.ListenerRepository.get',
            return_value=_listener_mock)
@mock.patch('octavia.db.api.get_session', return_value=_session_mock)
@mock.patch('octavia.controller.worker.tasks.amphora_driver_tasks.LOG')
@mock.patch('oslo_utils.uuidutils.generate_uuid', return_value=AMP_ID)
@mock.patch('stevedore.driver.DriverManager.driver')
class TestAmphoraDriverTasks(base.TestCase):

    def setUp(self):

        _LB_mock.amphorae = [_amphora_mock]
        _LB_mock.id = LB_ID
        super(TestAmphoraDriverTasks, self).setUp()

    def test_listener_update(self,
                             mock_driver,
                             mock_generate_uuid,
                             mock_log,
                             mock_get_session,
                             mock_listener_repo_get,
                             mock_listener_repo_update,
                             mock_amphora_repo_update):

        listener_update_obj = amphora_driver_tasks.ListenersUpdate()
        listener_update_obj.execute(_load_balancer_mock, [_listener_mock])

        mock_driver.update.assert_called_once_with(_listener_mock, _vip_mock)

        # Test the revert
        amp = listener_update_obj.revert(_load_balancer_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

        # Test the revert with exception
        repo.ListenerRepository.update.reset_mock()
        mock_listener_repo_update.side_effect = Exception('fail')
        amp = listener_update_obj.revert(_load_balancer_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

    def test_listeners_update(self,
                              mock_driver,
                              mock_generate_uuid,
                              mock_log,
                              mock_get_session,
                              mock_listener_repo_get,
                              mock_listener_repo_update,
                              mock_amphora_repo_update):
        listeners_update_obj = amphora_driver_tasks.ListenersUpdate()
        listeners = [data_models.Listener(id='listener1'),
                     data_models.Listener(id='listener2')]
        vip = data_models.Vip(ip_address='10.0.0.1')
        lb = data_models.LoadBalancer(id='lb1', listeners=listeners, vip=vip)
        listeners_update_obj.execute(lb, listeners)
        mock_driver.update.assert_has_calls([mock.call(listeners[0], vip),
                                             mock.call(listeners[1], vip)])
        self.assertEqual(2, mock_driver.update.call_count)
        self.assertIsNotNone(listeners[0].load_balancer)
        self.assertIsNotNone(listeners[1].load_balancer)

        # Test the revert
        amp = listeners_update_obj.revert(lb)
        expected_db_calls = [mock.call(_session_mock,
                                       id=listeners[0].id,
                                       provisioning_status=constants.ERROR),
                             mock.call(_session_mock,
                                       id=listeners[1].id,
                                       provisioning_status=constants.ERROR)]
        repo.ListenerRepository.update.has_calls(expected_db_calls)
        self.assertEqual(2, repo.ListenerRepository.update.call_count)
        self.assertIsNone(amp)

    def test_listener_stop(self,
                           mock_driver,
                           mock_generate_uuid,
                           mock_log,
                           mock_get_session,
                           mock_listener_repo_get,
                           mock_listener_repo_update,
                           mock_amphora_repo_update):

        listener_stop_obj = amphora_driver_tasks.ListenerStop()
        listener_stop_obj.execute(_load_balancer_mock, _listener_mock)

        mock_driver.stop.assert_called_once_with(_listener_mock, _vip_mock)

        # Test the revert
        amp = listener_stop_obj.revert(_listener_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

        # Test the revert with exception
        repo.ListenerRepository.update.reset_mock()
        mock_listener_repo_update.side_effect = Exception('fail')
        amp = listener_stop_obj.revert(_listener_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

    def test_listener_start(self,
                            mock_driver,
                            mock_generate_uuid,
                            mock_log,
                            mock_get_session,
                            mock_listener_repo_get,
                            mock_listener_repo_update,
                            mock_amphora_repo_update):

        listener_start_obj = amphora_driver_tasks.ListenerStart()
        listener_start_obj.execute(_load_balancer_mock, _listener_mock)

        mock_driver.start.assert_called_once_with(_listener_mock, _vip_mock)

        # Test the revert
        amp = listener_start_obj.revert(_listener_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

        # Test the revert with exception
        repo.ListenerRepository.update.reset_mock()
        mock_listener_repo_update.side_effect = Exception('fail')
        amp = listener_start_obj.revert(_listener_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

    def test_listener_delete(self,
                             mock_driver,
                             mock_generate_uuid,
                             mock_log,
                             mock_get_session,
                             mock_listener_repo_get,
                             mock_listener_repo_update,
                             mock_amphora_repo_update):

        listener_delete_obj = amphora_driver_tasks.ListenerDelete()
        listener_delete_obj.execute(_load_balancer_mock, _listener_mock)

        mock_driver.delete.assert_called_once_with(_listener_mock, _vip_mock)

        # Test the revert
        amp = listener_delete_obj.revert(_listener_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

        # Test the revert with exception
        repo.ListenerRepository.update.reset_mock()
        mock_listener_repo_update.side_effect = Exception('fail')
        amp = listener_delete_obj.revert(_listener_mock)
        repo.ListenerRepository.update.assert_called_once_with(
            _session_mock,
            id=LISTENER_ID,
            provisioning_status=constants.ERROR)
        self.assertIsNone(amp)

    def test_amphora_get_info(self,
                              mock_driver,
                              mock_generate_uuid,
                              mock_log,
                              mock_get_session,
                              mock_listener_repo_get,
                              mock_listener_repo_update,
                              mock_amphora_repo_update):

        amphora_get_info_obj = amphora_driver_tasks.AmphoraGetInfo()
        amphora_get_info_obj.execute(_amphora_mock)

        mock_driver.get_info.assert_called_once_with(
            _amphora_mock)

    def test_amphora_get_diagnostics(self,
                                     mock_driver,
                                     mock_generate_uuid,
                                     mock_log,
                                     mock_get_session,
                                     mock_listener_repo_get,
                                     mock_listener_repo_update,
                                     mock_amphora_repo_update):

        amphora_get_diagnostics_obj = (amphora_driver_tasks.
                                       AmphoraGetDiagnostics())
        amphora_get_diagnostics_obj.execute(_amphora_mock)

        mock_driver.get_diagnostics.assert_called_once_with(
            _amphora_mock)

    def test_amphora_finalize(self,
                              mock_driver,
                              mock_generate_uuid,
                              mock_log,
                              mock_get_session,
                              mock_listener_repo_get,
                              mock_listener_repo_update,
                              mock_amphora_repo_update):

        amphora_finalize_obj = amphora_driver_tasks.AmphoraFinalize()
        amphora_finalize_obj.execute(_amphora_mock)

        mock_driver.finalize_amphora.assert_called_once_with(
            _amphora_mock)

        # Test revert
        amp = amphora_finalize_obj.revert(None, _amphora_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)
        self.assertIsNone(amp)

        # Test revert with exception
        repo.AmphoraRepository.update.reset_mock()
        mock_amphora_repo_update.side_effect = Exception('fail')
        amp = amphora_finalize_obj.revert(None, _amphora_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)
        self.assertIsNone(amp)

    def test_amphora_post_network_plug(self,
                                       mock_driver,
                                       mock_generate_uuid,
                                       mock_log,
                                       mock_get_session,
                                       mock_listener_repo_get,
                                       mock_listener_repo_update,
                                       mock_amphora_repo_update):

        amphora_post_network_plug_obj = (amphora_driver_tasks.
                                         AmphoraPostNetworkPlug())
        amphora_post_network_plug_obj.execute(_amphora_mock, _ports_mock)

        (mock_driver.post_network_plug.
            assert_called_once_with)(_amphora_mock, _port_mock)

        # Test revert
        amp = amphora_post_network_plug_obj.revert(None, _amphora_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)

        self.assertIsNone(amp)

        # Test revert with exception
        repo.AmphoraRepository.update.reset_mock()
        mock_amphora_repo_update.side_effect = Exception('fail')
        amp = amphora_post_network_plug_obj.revert(None, _amphora_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)

        self.assertIsNone(amp)

    def test_amphorae_post_network_plug(self, mock_driver,
                                        mock_generate_uuid,
                                        mock_log,
                                        mock_get_session,
                                        mock_listener_repo_get,
                                        mock_listener_repo_update,
                                        mock_amphora_repo_update):
        mock_driver.get_network.return_value = _network_mock
        _amphora_mock.id = AMP_ID
        _amphora_mock.compute_id = COMPUTE_ID
        _LB_mock.amphorae = [_amphora_mock]
        amphora_post_network_plug_obj = (amphora_driver_tasks.
                                         AmphoraePostNetworkPlug())

        port_mock = mock.Mock()
        _deltas_mock = {_amphora_mock.id: [port_mock]}

        amphora_post_network_plug_obj.execute(_LB_mock, _deltas_mock)

        (mock_driver.post_network_plug.
            assert_called_once_with(_amphora_mock, port_mock))

        # Test revert
        amp = amphora_post_network_plug_obj.revert(None, _LB_mock,
                                                   _deltas_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)

        self.assertIsNone(amp)

        # Test revert with exception
        repo.AmphoraRepository.update.reset_mock()
        mock_amphora_repo_update.side_effect = Exception('fail')
        amp = amphora_post_network_plug_obj.revert(None, _LB_mock,
                                                   _deltas_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)

        self.assertIsNone(amp)

    @mock.patch('octavia.db.repositories.LoadBalancerRepository.update')
    def test_amphora_post_vip_plug(self,
                                   mock_loadbalancer_repo_update,
                                   mock_driver,
                                   mock_generate_uuid,
                                   mock_log,
                                   mock_get_session,
                                   mock_listener_repo_get,
                                   mock_listener_repo_update,
                                   mock_amphora_repo_update):

        amphorae_net_config_mock = mock.Mock()
        amphora_post_vip_plug_obj = amphora_driver_tasks.AmphoraPostVIPPlug()
        amphora_post_vip_plug_obj.execute(_amphora_mock,
                                          _LB_mock,
                                          amphorae_net_config_mock)

        mock_driver.post_vip_plug.assert_called_once_with(
            _amphora_mock, _LB_mock, amphorae_net_config_mock)

        # Test revert
        amp = amphora_post_vip_plug_obj.revert(None, _amphora_mock, _LB_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)
        repo.LoadBalancerRepository.update.assert_called_once_with(
            _session_mock,
            id=LB_ID,
            provisioning_status=constants.ERROR)

        self.assertIsNone(amp)

        # Test revert with repo exceptions
        repo.AmphoraRepository.update.reset_mock()
        repo.LoadBalancerRepository.update.reset_mock()
        mock_amphora_repo_update.side_effect = Exception('fail')
        mock_loadbalancer_repo_update.side_effect = Exception('fail')
        amp = amphora_post_vip_plug_obj.revert(None, _amphora_mock, _LB_mock)
        repo.AmphoraRepository.update.assert_called_once_with(
            _session_mock,
            id=AMP_ID,
            status=constants.ERROR)
        repo.LoadBalancerRepository.update.assert_called_once_with(
            _session_mock,
            id=LB_ID,
            provisioning_status=constants.ERROR)

        self.assertIsNone(amp)

    @mock.patch('octavia.db.repositories.LoadBalancerRepository.update')
    def test_amphorae_post_vip_plug(self,
                                    mock_loadbalancer_repo_update,
                                    mock_driver,
                                    mock_generate_uuid,
                                    mock_log,
                                    mock_get_session,
                                    mock_listener_repo_get,
                                    mock_listener_repo_update,
                                    mock_amphora_repo_update):

        amphorae_net_config_mock = mock.Mock()
        amphora_post_vip_plug_obj = amphora_driver_tasks.AmphoraePostVIPPlug()
        amphora_post_vip_plug_obj.execute(_LB_mock,
                                          amphorae_net_config_mock)

        mock_driver.post_vip_plug.assert_called_once_with(
            _amphora_mock, _LB_mock, amphorae_net_config_mock)

        # Test revert
        amp = amphora_post_vip_plug_obj.revert(None, _LB_mock)
        repo.LoadBalancerRepository.update.assert_called_once_with(
            _session_mock,
            id=LB_ID,
            provisioning_status=constants.ERROR)

        self.assertIsNone(amp)

        # Test revert with exception
        repo.LoadBalancerRepository.update.reset_mock()
        mock_loadbalancer_repo_update.side_effect = Exception('fail')
        amp = amphora_post_vip_plug_obj.revert(None, _LB_mock)
        repo.LoadBalancerRepository.update.assert_called_once_with(
            _session_mock,
            id=LB_ID,
            provisioning_status=constants.ERROR)

        self.assertIsNone(amp)

    def test_amphora_cert_upload(self,
                                 mock_driver,
                                 mock_generate_uuid,
                                 mock_log,
                                 mock_get_session,
                                 mock_listener_repo_get,
                                 mock_listener_repo_update,
                                 mock_amphora_repo_update):
        pem_file_mock = 'test-perm-file'
        amphora_cert_upload_mock = amphora_driver_tasks.AmphoraCertUpload()
        amphora_cert_upload_mock.execute(_amphora_mock, pem_file_mock)

        mock_driver.upload_cert_amp.assert_called_once_with(
            _amphora_mock, pem_file_mock)

    def test_amphora_update_vrrp_interface(self,
                                           mock_driver,
                                           mock_generate_uuid,
                                           mock_log,
                                           mock_get_session,
                                           mock_listener_repo_get,
                                           mock_listener_repo_update,
                                           mock_amphora_repo_update):
        _LB_mock.amphorae = _amphorae_mock
        amphora_update_vrrp_interface_obj = (
            amphora_driver_tasks.AmphoraUpdateVRRPInterface())
        amphora_update_vrrp_interface_obj.execute(_LB_mock)
        mock_driver.get_vrrp_interface.assert_called_once_with(_amphora_mock)

        # Test revert
        mock_driver.reset_mock()

        _LB_mock.amphorae = _amphorae_mock
        amphora_update_vrrp_interface_obj.revert("BADRESULT", _LB_mock)
        mock_amphora_repo_update.assert_called_with(_session_mock,
                                                    _amphora_mock.id,
                                                    vrrp_interface=None)

        mock_driver.reset_mock()
        mock_amphora_repo_update.reset_mock()

        failure_obj = failure.Failure.from_exception(Exception("TESTEXCEPT"))
        amphora_update_vrrp_interface_obj.revert(failure_obj, _LB_mock)
        self.assertFalse(mock_amphora_repo_update.called)

        # Test revert with exception
        mock_driver.reset_mock()
        mock_amphora_repo_update.reset_mock()
        mock_amphora_repo_update.side_effect = Exception('fail')

        _LB_mock.amphorae = _amphorae_mock
        amphora_update_vrrp_interface_obj.revert("BADRESULT", _LB_mock)
        mock_amphora_repo_update.assert_called_with(_session_mock,
                                                    _amphora_mock.id,
                                                    vrrp_interface=None)

    def test_amphora_vrrp_update(self,
                                 mock_driver,
                                 mock_generate_uuid,
                                 mock_log,
                                 mock_get_session,
                                 mock_listener_repo_get,
                                 mock_listener_repo_update,
                                 mock_amphora_repo_update):
        amphora_vrrp_update_obj = (
            amphora_driver_tasks.AmphoraVRRPUpdate())
        amphora_vrrp_update_obj.execute(_LB_mock)
        mock_driver.update_vrrp_conf.assert_called_once_with(_LB_mock)

    def test_amphora_vrrp_stop(self,
                               mock_driver,
                               mock_generate_uuid,
                               mock_log,
                               mock_get_session,
                               mock_listener_repo_get,
                               mock_listener_repo_update,
                               mock_amphora_repo_update):
        amphora_vrrp_stop_obj = (
            amphora_driver_tasks.AmphoraVRRPStop())
        amphora_vrrp_stop_obj.execute(_LB_mock)
        mock_driver.stop_vrrp_service.assert_called_once_with(_LB_mock)

    def test_amphora_vrrp_start(self,
                                mock_driver,
                                mock_generate_uuid,
                                mock_log,
                                mock_get_session,
                                mock_listener_repo_get,
                                mock_listener_repo_update,
                                mock_amphora_repo_update):
        amphora_vrrp_start_obj = (
            amphora_driver_tasks.AmphoraVRRPStart())
        amphora_vrrp_start_obj.execute(_LB_mock)
        mock_driver.start_vrrp_service.assert_called_once_with(_LB_mock)
