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

import datetime

from concurrent import futures
from oslo_config import cfg
from oslo_log import log as logging

from octavia.common import constants
from octavia.controller.worker import controller_worker as cw
from octavia.db import api as db_api
from octavia.db import repositories as repo
from octavia.i18n import _LI

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class SpareAmphora(object):
    def __init__(self):
        self.amp_repo = repo.AmphoraRepository()
        self.cw = cw.ControllerWorker()

    def spare_check(self):
        """Checks the DB for the Spare amphora count.

        If it's less than the requirement, starts new amphora.
        """
        session = db_api.get_session()
        conf_spare_cnt = CONF.house_keeping.spare_amphora_pool_size
        curr_spare_cnt = self.amp_repo.get_spare_amphora_count(session)
        LOG.debug("Required Spare Amphora count : %d", conf_spare_cnt)
        LOG.debug("Current Spare Amphora count : %d", curr_spare_cnt)
        diff_count = conf_spare_cnt - curr_spare_cnt

        # When the current spare amphora is less than required
        if diff_count > 0:
            LOG.info(_LI("Initiating creation of %d spare amphora.") %
                     diff_count)

            # Call Amphora Create Flow diff_count times
            for i in range(1, diff_count + 1):
                LOG.debug("Starting amphorae number %d ...", i)
                self.cw.create_amphora()

        else:
            LOG.debug(_LI("Current spare amphora count satisfies the "
                          "requirement"))


class DatabaseCleanup(object):
    def __init__(self):
        self.amp_repo = repo.AmphoraRepository()
        self.amp_health_repo = repo.AmphoraHealthRepository()
        self.lb_repo = repo.LoadBalancerRepository()

    def delete_old_amphorae(self):
        """Checks the DB for old amphora and deletes them based on its age."""
        exp_age = datetime.timedelta(
            seconds=CONF.house_keeping.amphora_expiry_age)

        session = db_api.get_session()
        amphora = self.amp_repo.get_all(session, status=constants.DELETED)

        for amp in amphora:
            if self.amp_health_repo.check_amphora_expired(session, amp.id,
                                                          exp_age):
                LOG.info(_LI('Attempting to delete Amphora id : %s'), amp.id)
                self.amp_repo.delete(session, id=amp.id)
                LOG.info(_LI('Deleted Amphora id : %s') % amp.id)

    def cleanup_load_balancers(self):
        """Checks the DB for old load balancers and triggers their removal."""
        exp_age = datetime.timedelta(
            seconds=CONF.house_keeping.load_balancer_expiry_age)

        session = db_api.get_session()
        load_balancers = self.lb_repo.get_all(
            session, provisioning_status=constants.DELETED)

        for lb in load_balancers:
            if self.lb_repo.check_load_balancer_expired(session, lb.id,
                                                        exp_age):
                LOG.info(_LI('Attempting to delete load balancer id : %s'),
                         lb.id)
                self.lb_repo.delete(session, id=lb.id)
                LOG.info(_LI('Deleted load balancer id : %s') % lb.id)


class CertRotation(object):
    def __init__(self):
        self.threads = CONF.house_keeping.cert_rotate_threads
        self.cw = cw.ControllerWorker()

    def rotate(self):
        """Check the amphora db table for expiring auth certs."""
        amp_repo = repo.AmphoraRepository()

        with futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            try:
                session = db_api.get_session()
                rotation_count = 0
                while True:
                    amp = amp_repo.get_cert_expiring_amphora(session)
                    if not amp:
                        break
                    rotation_count += 1
                    LOG.debug("Cert expired amphora's id is: %s", amp.id)
                    executor.submit(self.cw.amphora_cert_rotation, amp.id)
                if rotation_count > 0:
                    LOG.info(_LI("Rotated certificates for %s amphora") %
                             rotation_count)
            finally:
                executor.shutdown(wait=True)
