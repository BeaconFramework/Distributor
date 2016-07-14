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

import os

from oslo_log import log as logging
from oslo_utils import excutils
import psutil
from taskflow.listeners import logging as tf_logging
from taskflow.patterns import linear_flow
from taskflow.patterns import unordered_flow

from octavia.amphorae.cluster_manager.drivers import driver_base
from octavia.common import base_taskflow
from octavia.common.config import cfg
from octavia.common import constants
from octavia.controller.worker.flows import distributor_flows
from octavia.db import api as db_apis
from octavia.db import repositories as repo
from octavia.i18n import _LE

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ActiveActiveManager(base_taskflow.BaseTaskFlowEngine):
    def __init__(self):
        super(ActiveActiveManager, self).__init__()
        self._cluster_name = "ACTIVE_ACTIVE"
        self._cluster_size = CONF.active_active_cluster.cluster_size
        self._is_shared_distributor = (
            CONF.active_active_cluster.is_shared_distributor)
        self._cluster_repo = repo.AmphoraClusterRepository()
        self._distributor_flows = distributor_flows.DistributorFlows()
        self._distributor_repo = repo.DistributorRepository()
        LOG.debug("Amphora Cluster Manager Init ")
        if self._is_shared_distributor and ('octavia-worker' in str(
                psutil.Process(os.getpid()).cmdline)):
            self._create_shared_distributor()

    def create_cluster_for_lb(self):
        lf_name = (
            'CREATE_' + self._cluster_name + '_CLUSTER_' +
            str(self._cluster_size))
        create_cluster_flow = linear_flow.Flow(lf_name)
        return create_cluster_flow

    def create_amphorae(self):
        lf_name = constants.PRE_CREATE_AMPHORAE_PER_CLUSTER_FLOW
        create_amphorae_unordered_flow = unordered_flow.Flow(
            lf_name + '_MASTER_FOR_CLUSTER_' + str(self._cluster_size))
        return create_amphorae_unordered_flow

    def delete_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s "
                  "active-active, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        return True

    def finalize_amphora_cluster(self):
        return None

    def shrink_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s "
                  "active-active, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        pass

    def grow_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s "
                  "active-active, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        pass

    def recover_from_amphora_failure(self, failed_amphora, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s "
                  "active-active, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        pass

    def _create_shared_distributor(self):
        distributor = self._distributor_repo.get_shared_ready_distributor(
            db_apis.get_session())

        if distributor is None:
            try:

                get_create_distributor_fl = self._taskflow_load(
                    self._distributor_flows.get_create_distributor_flow())
                with tf_logging.DynamicLoggingListener(
                        get_create_distributor_fl, log=LOG):
                    get_create_distributor_fl.run()
            except Exception as e:
                with excutils.save_and_reraise_exception():
                    LOG.error(_LE(
                        "CreateSharedDistributorInInitActiveActiveManager "
                        "exception: %s"), e)


class AmphoraClusterDriver(driver_base.AmphoraClusterDriver):
    def __init__(self):
        super(AmphoraClusterDriver, self).__init__()
        self.driver = ActiveActiveManager()

    def create_cluster_for_lb(self):
        cluster_create_flow = self.driver.create_cluster_for_lb()
        return cluster_create_flow

    def create_amphorae(self):
        return self.driver.create_amphorae()

    def delete_cluster_for_lb(self, loadbalancer):
        self.driver._cluster_for_lb(loadbalancer)
        return True

    def finalize_amphora_cluster(self):
        return self.driver.finalize_amphora_cluster()

    def recover_from_amphora_failure(self, failed_amphora, loadbalancer):
        self.driver.recover_from_amphora_failure(failed_amphora,
                                                 loadbalancer)
        return True

    def grow_cluster_for_lb(self, loadbalancer):
        self.driver.grow_cluster_for_lb(loadbalancer)
        return True

    def shrink_cluster_for_lb(self, loadbalancer):
        self.driver.shrink_cluster_for_lb(loadbalancer)
        return True
