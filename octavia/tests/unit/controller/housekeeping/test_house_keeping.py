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

import mock
from oslo_config import cfg
from oslo_utils import uuidutils

from octavia.common import constants
from octavia.controller.housekeeping import house_keeping
from octavia.db import repositories as repo
import octavia.tests.unit.base as base


CONF = cfg.CONF
AMPHORA_ID = uuidutils.generate_uuid()


class TestException(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class TestSpareCheck(base.TestCase):
    FAKE_CNF_SPAR1 = 5
    FAKE_CUR_SPAR1 = 2
    FAKE_CNF_SPAR2 = 3
    FAKE_CUR_SPAR2 = 3

    def setUp(self):
        super(TestSpareCheck, self).setUp()
        self.spare_amp = house_keeping.SpareAmphora()
        self.amp_repo = mock.MagicMock()
        self.cw = mock.MagicMock()

        self.spare_amp.amp_repo = self.amp_repo
        self.spare_amp.cw = self.cw
        self.CONF = cfg.CONF

    @mock.patch('octavia.db.api.get_session')
    def test_spare_check_diff_count(self, session):
        """When spare amphora count does not meet the requirement."""
        session.return_value = session
        self.CONF.house_keeping.spare_amphora_pool_size = self.FAKE_CNF_SPAR1
        self.amp_repo.get_spare_amphora_count.return_value = (
            self.FAKE_CUR_SPAR1)
        self.spare_amp.spare_check()
        self.assertTrue(self.amp_repo.get_spare_amphora_count.called)
        DIFF_CNT = self.FAKE_CNF_SPAR1 - self.FAKE_CUR_SPAR1

        self.assertEqual(DIFF_CNT, self.cw.create_amphora.call_count)

    @mock.patch('octavia.db.api.get_session')
    def test_spare_check_no_diff_count(self, session):
        """When spare amphora count meets the requirement."""
        session.return_value = session
        self.CONF.house_keeping.spare_amphora_pool_size = self.FAKE_CNF_SPAR2
        self.amp_repo.get_spare_amphora_count.return_value = (
            self.FAKE_CUR_SPAR2)
        self.spare_amp.spare_check()
        self.assertTrue(self.amp_repo.get_spare_amphora_count.called)
        DIFF_CNT = self.FAKE_CNF_SPAR2 - self.FAKE_CUR_SPAR2

        self.assertEqual(0, DIFF_CNT)
        self.assertEqual(DIFF_CNT, self.cw.create_amphora.call_count)


class TestDatabaseCleanup(base.TestCase):
    FAKE_IP = "10.0.0.1"
    FAKE_UUID_1 = uuidutils.generate_uuid()
    FAKE_UUID_2 = uuidutils.generate_uuid()
    FAKE_EXP_AGE = 10

    def setUp(self):
        super(TestDatabaseCleanup, self).setUp()
        self.dbclean = house_keeping.DatabaseCleanup()
        self.amp_health_repo = mock.MagicMock()
        self.amp_repo = mock.MagicMock()
        self.amp = repo.AmphoraRepository()
        self.lb = repo.LoadBalancerRepository()

        self.dbclean.amp_repo = self.amp_repo
        self.dbclean.amp_health_repo = self.amp_health_repo
        self.CONF = cfg.CONF

    @mock.patch('octavia.db.api.get_session')
    def test_delete_old_amphorae_True(self, session):
        """When the deleted amphorae is expired."""
        session.return_value = session
        self.CONF.house_keeping.amphora_expiry_age = self.FAKE_EXP_AGE
        amphora = self.amp.create(session, id=self.FAKE_UUID_1,
                                  compute_id=self.FAKE_UUID_2,
                                  status=constants.DELETED,
                                  lb_network_ip=self.FAKE_IP,
                                  vrrp_ip=self.FAKE_IP,
                                  ha_ip=self.FAKE_IP)
        self.amp_repo.get_all.return_value = [amphora]
        self.amp_health_repo.check_amphora_expired.return_value = True
        self.dbclean.delete_old_amphorae()
        self.assertTrue(self.amp_repo.get_all.called)
        self.assertTrue(self.amp_health_repo.check_amphora_expired.called)
        self.assertTrue(self.amp_repo.delete.called)

    @mock.patch('octavia.db.api.get_session')
    def test_delete_old_amphorae_False(self, session):
        """When the deleted amphorae is not expired."""
        session.return_value = session
        self.CONF.house_keeping.amphora_expiry_age = self.FAKE_EXP_AGE
        amphora = self.amp.create(session, id=self.FAKE_UUID_1,
                                  compute_id=self.FAKE_UUID_2,
                                  status=constants.DELETED,
                                  lb_network_ip=self.FAKE_IP,
                                  vrrp_ip=self.FAKE_IP,
                                  ha_ip=self.FAKE_IP)
        self.amp_repo.get_all.return_value = [amphora]
        self.amp_health_repo.check_amphora_expired.return_value = False
        self.dbclean.delete_old_amphorae()
        self.assertTrue(self.amp_repo.get_all.called)
        self.assertTrue(self.amp_health_repo.check_amphora_expired.called)
        self.assertFalse(self.amp_repo.delete.called)

    @mock.patch('octavia.db.api.get_session')
    def test_delete_old_load_balancer(self, session):
        """Check delete of load balancers in DELETED provisioning status."""
        self.CONF.house_keeping.load_balancer_expiry_age = self.FAKE_EXP_AGE
        session.return_value = session
        load_balancer = self.lb.create(session, id=self.FAKE_UUID_1,
                                       provisioning_status=constants.DELETED,
                                       operating_status=constants.OFFLINE,
                                       enabled=True)

        for expired_status in [True, False]:
            lb_repo = mock.MagicMock()
            self.dbclean.lb_repo = lb_repo
            lb_repo.get_all.return_value = [load_balancer]
            lb_repo.check_load_balancer_expired.return_value = (
                expired_status)
            self.dbclean.cleanup_load_balancers()
            self.assertTrue(lb_repo.get_all.called)
            self.assertTrue(lb_repo.check_load_balancer_expired.called)
            if expired_status:
                self.assertTrue(lb_repo.delete.called)
            else:
                self.assertFalse(lb_repo.delete.called)


class TestCertRotation(base.TestCase):
    def setUp(self):
        super(TestCertRotation, self).setUp()

    @mock.patch('octavia.controller.worker.controller_worker.'
                'ControllerWorker.amphora_cert_rotation')
    @mock.patch('octavia.db.repositories.AmphoraRepository.'
                'get_cert_expiring_amphora')
    @mock.patch('octavia.db.api.get_session')
    def test_cert_rotation_expired_amphora_with_exception(self, session,
                                                          cert_exp_amp_mock,
                                                          amp_cert_mock
                                                          ):
        amphora = mock.MagicMock()
        amphora.id = AMPHORA_ID

        session.return_value = session
        cert_exp_amp_mock.side_effect = [amphora, TestException(
            'break_while')]

        cr = house_keeping.CertRotation()
        self.assertRaises(TestException, cr.rotate)
        amp_cert_mock.assert_called_once_with(AMPHORA_ID)

    @mock.patch('octavia.controller.worker.controller_worker.'
                'ControllerWorker.amphora_cert_rotation')
    @mock.patch('octavia.db.repositories.AmphoraRepository.'
                'get_cert_expiring_amphora')
    @mock.patch('octavia.db.api.get_session')
    def test_cert_rotation_expired_amphora_without_exception(self, session,
                                                             cert_exp_amp_mock,
                                                             amp_cert_mock
                                                             ):
        amphora = mock.MagicMock()
        amphora.id = AMPHORA_ID

        session.return_value = session
        cert_exp_amp_mock.side_effect = [amphora, None]

        cr = house_keeping.CertRotation()

        self.assertIsNone(cr.rotate())
        amp_cert_mock.assert_called_once_with(AMPHORA_ID)

    @mock.patch('octavia.controller.worker.controller_worker.'
                'ControllerWorker.amphora_cert_rotation')
    @mock.patch('octavia.db.repositories.AmphoraRepository.'
                'get_cert_expiring_amphora')
    @mock.patch('octavia.db.api.get_session')
    def test_cert_rotation_non_expired_amphora(self, session,
                                               cert_exp_amp_mock,
                                               amp_cert_mock):

        session.return_value = session
        cert_exp_amp_mock.return_value = None
        cr = house_keeping.CertRotation()
        cr.rotate()
        self.assertFalse(amp_cert_mock.called)
