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

import logging

from oslo_config import cfg
from stevedore import driver as stevedore_driver
from taskflow import task
from taskflow.types import failure

from octavia.common import constants
from octavia.db import api as db_apis
from octavia.i18n import _LW

CONF = cfg.CONF
CONF.import_group('active_active_cluster', 'octavia.common.config')
LOG = logging.getLogger(__name__)


class BaseDistributorTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        super(BaseDistributorTask, self).__init__(**kwargs)
        LOG.debug("Data - name %s",
                  CONF.active_active_cluster.distributor_driver)
        self.distributor_driver = stevedore_driver.DriverManager(
            namespace='octavia.distributor.drivers',
            name=CONF.active_active_cluster.distributor_driver,
            invoke_on_load=True
        ).driver
        from octavia.db import repositories as repo
        self.loadbalancer_repo = repo.LoadBalancerRepository()


class DistributorPostVIPPlug(BaseDistributorTask):
    """Task to notify the distributor post VIP plug."""

    def execute(self, distributor, loadbalancer, distributor_mac,
                cluster_alg_type, cluster_min_size):
        """Execute post_vip_routine."""

        load_balancer = self.loadbalancer_repo.get(
            db_apis.get_session(), id=loadbalancer.id)

        LOG.debug("DistributorPostVIPPlug for load_balancer:%s, "
                  "distributor:%s", load_balancer.id, distributor.id)
        self.distributor_driver.post_vip_plug(
            distributor, load_balancer, distributor_mac,
            cluster_alg_type, cluster_min_size)
        LOG.debug("Notified distributor of vip plug")

    def revert(self, result, loadbalancer, *args, **kwargs):
        """Handle a failed amphora vip plug notification."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting post vip plug."))
        self.loadbalancer_repo.update(db_apis.get_session(),
                                      id=loadbalancer.id,
                                      status=constants.ERROR)
