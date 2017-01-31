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
from taskflow import task

from octavia.amphorae.cluster_manager.drivers import driver_base
from octavia.common import base_taskflow
from octavia.common.config import cfg
from octavia.common import constants
from octavia.controller.worker.flows import amphora_flows
from octavia.controller.worker.flows import distributor_flows
from octavia.controller.worker.tasks import amphora_driver_tasks
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import distributor_driver_tasks
from octavia.controller.worker.tasks import network_tasks
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
        self._amphora_flows = amphora_flows.AmphoraFlows()
        self._distributor_repo = repo.DistributorRepository()
        LOG.debug("Amphora Cluster Manager Init ")
        if self._is_shared_distributor and ('octavia-worker' in str(
                psutil.Process(os.getpid()).cmdline)):
            self._create_shared_distributor()

    def create_cluster_for_lb(self):
        lf_name = ('CREATE_' + self._cluster_name + '_CLUSTER_' +
                   str(self._cluster_size))
        create_cluster_flow = linear_flow.Flow(lf_name)
        # Get/Create distributor
        if not self._is_shared_distributor:
            get_create_distributor_sf = (self._distributor_flows.
                                         get_create_distributor_flow())
            create_cluster_flow.add(get_create_distributor_sf)
        else:
            create_cluster_flow.add(database_tasks.ReloadSharedDistributor(
                                    provides=constants.DISTRIBUTOR))
        create_cluster_flow.add(CreateAmphoraClusterAlgExtraTask(
            provides=(constants.CLUSTER_ALG_TYPE, constants.CLUSTER_MIN_SIZE)
        ))
        create_cluster_flow.add(
            self._distributor_flows.create_distributor_networking_subflow())

        # Create AmphoraCluster for <Distributor, LoadBalancer>
        create_cluster_flow.add(database_tasks.CreateAmphoraClusterInDB(
            requires=(constants.DISTRIBUTOR, constants.LOADBALANCER),
            provides=constants.AMPHORA_CLUSTER
        ))
        create_cluster_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))
        # LOG.debug("Amphora Cluster Manager %s active-active, "
        #           "load_balancer_id %s",
        #           self.__class__.__name__, loadbalancer.id)
        return create_cluster_flow

    def create_amphorae(self):
        # LOG.debug("Amphora Cluster Manager %s "
        #           "active-active, amphora_cluster_id %s",
        #           self.__class__.__name__, amphora_cluster.id)

        lf_name = constants.PRE_CREATE_AMPHORAE_PER_CLUSTER_FLOW
        # TODO(Lera): unordered_flow
        create_amphorae_unordered_flow = unordered_flow.Flow(
            lf_name + '_MASTER_FOR_CLUSTER_' + str(self._cluster_size))

        # create N active amphora
        for amphoraCount in range(self._cluster_size):
            create_amphora_tf = (
                self._amphora_flows.get_amphora_for_cluster_subflow(
                    prefix=constants.ROLE_ACTIVE_ACTIVE +
                    '_MASTER_FOR_CLUSTER_' + str(amphoraCount),
                    role=constants.ROLE_ACTIVE_ACTIVE))
            create_amphorae_unordered_flow.add(create_amphora_tf)

        # creating +1 backup amphora
        create_backup_amphora_tf = (
            self._amphora_flows.get_amphora_for_cluster_subflow(
                prefix=constants.ROLE_ACTIVE_STANDBY + '_BACKUP_FOR_CLUSTER',
                role=constants.ROLE_ACTIVE_STANDBY))
        create_amphorae_unordered_flow.add(create_backup_amphora_tf)
        return create_amphorae_unordered_flow

    def finalize_amphora_cluster(self):
        """Create a sub-flow to setup networking for amphora.

        Register amphora to Distributor
        :returns: The flow to setup networking for a new amphora
        """

        new_amphora_net_subflow = linear_flow.Flow(constants.
                                                   AMPHORA_NETWORKING_SUBFLOW)
        new_amphora_net_subflow.add(database_tasks.ReloadLoadBalancer(
            name=constants.RELOAD_LB_AFTER_AMPS_CREATE,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        new_amphora_net_subflow.add(
            database_tasks.GetAmphoraClusterFromLoadbalancer(
                requires=constants.LOADBALANCER,
                provides=constants.AMPHORA_CLUSTER
            ))
        new_amphora_net_subflow.add(
            GetDistributorFromAmphoraClusterTask(
                requires=constants.AMPHORA_CLUSTER,
                provides=constants.DISTRIBUTOR
            ))
        new_amphora_net_subflow.add(network_tasks.PlugVIP(
            requires=constants.LOADBALANCER,
            provides=constants.AMPS_DATA))
        new_amphora_net_subflow.add(database_tasks.UpdateAmphoraVIPData(
            requires=constants.AMPS_DATA))
        new_amphora_net_subflow.add(database_tasks.ReloadLoadBalancer(
            name=constants.RELOAD_LB_AFTER_PLUG_VIP,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        new_amphora_net_subflow.add(network_tasks.GetAmphoraeNetworkConfigs(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORAE_NETWORK_CONFIG))
        new_amphora_net_subflow.add(amphora_driver_tasks.AmphoraePostVIPPlug(
            requires=(constants.LOADBALANCER,
                      constants.AMPHORAE_NETWORK_CONFIG)))
        # Connect to listeners and members (if needed and exists)
        new_amphora_net_subflow.add(network_tasks.CalculateDelta(
            requires=constants.LOADBALANCER,
            provides=constants.DELTAS))
        new_amphora_net_subflow.add(network_tasks.HandleNetworkDeltas(
            requires=constants.DELTAS,
            provides=constants.ADDED_PORTS))
        new_amphora_net_subflow.add(
            amphora_driver_tasks.AmphoraePostNetworkPlug(
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS)
            ))
        new_amphora_net_subflow.add(
            database_tasks.GetListenersFromLoadbalancer(
                requires=constants.LOADBALANCER,
                provides=constants.LISTENERS))
        new_amphora_net_subflow.add(amphora_driver_tasks.ListenersUpdate(
            requires=(constants.LISTENERS)))

        for amphoraCount in range(self._cluster_size):
            sf_name = 'FINALIZE_AMP_' + str(amphoraCount)
            finalize_amp_for_lb_subflow = linear_flow.Flow(sf_name)
            finalize_amp_for_lb_subflow.add(
                GetAmphoraFromClusterTask(
                    name=sf_name + '-' + constants.GET_AMPHORA_FOR_LB_SUBFLOW,
                    requires=constants.AMPHORA_CLUSTER,
                    inject={constants.CURR_AMPHORA_ITER: amphoraCount},
                    provides=constants.AMPHORA_ID
                ))
            finalize_amp_for_lb_subflow.add(database_tasks.ReloadAmphora(
                name=sf_name + '-' + constants.AMPHORA,
                requires=constants.AMPHORA_ID,
                provides=constants.AMPHORA
            ))
            # Register new amphora via REST to distributor
            finalize_amp_for_lb_subflow.add(
                network_tasks.GetAmphoraMacAddr(
                    name=sf_name + '-' + constants.AMPHORA_MAC,
                    requires=constants.AMPHORA,
                    provides=constants.AMPHORA_MAC))
            finalize_amp_for_lb_subflow.add(
                amphora_driver_tasks.AmphoraPostDisableARP(
                    name=sf_name + '-' + constants.DISABLE_ARP,
                    requires=(constants.AMPHORA, constants.AMPHORA_MAC)))
            finalize_amp_for_lb_subflow.add(
                distributor_driver_tasks.DistributorRegisterAmphora(
                    name=sf_name + '-' + constants.DISTRIBUTOR_REGISTER_AMP,
                    requires=(constants.DISTRIBUTOR,
                              constants.LOADBALANCER,
                              constants.AMPHORA),
                    inject={constants.CLUSTER_ALG_TYPE:'active_active',
                            constants.CLUSTER_SLOT: amphoraCount}))
            new_amphora_net_subflow.add(finalize_amp_for_lb_subflow)

        return new_amphora_net_subflow

    def delete_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s "
                  "active-active, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        pass

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


class BaseAmphoraClusterActiveActiveTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        self._cluster_size = CONF.active_active_cluster.cluster_size
        super(BaseAmphoraClusterActiveActiveTask, self).__init__(**kwargs)


class CreateAmphoraClusterAlgExtraTask(BaseAmphoraClusterActiveActiveTask):
    """Task to create cluster_manager for amphora."""

    def execute(self):
        """Execute task CreateAmphoraCluster."""
        return 'active_active', self._cluster_size

    def revert(self, *args, **kwargs):
        """Handle failed CreateAmphoraCluster execution."""
        # TODO(Lera): Implement
        return None


class GetAmphoraFromClusterTask(BaseAmphoraClusterActiveActiveTask):
    def execute(self, amphora_cluster, curr_amphora_iter):
        """Execute task CreateAmphoraCluster."""
        amp = amphora_cluster.load_balancer.amphorae[curr_amphora_iter]
        if amp.status == constants.AMPHORA_ALLOCATED:
            return amp.id
        return None

    def revert(self, *args, **kwargs):
        """Handle failed CreateAmphoraCluster execution."""
        # TODO(Lera): Implement
        return None


class GetDistributorFromAmphoraClusterTask(BaseAmphoraClusterActiveActiveTask):
    def execute(self, amphora_cluster):
        return amphora_cluster.distributor

    def revert(self, *args, **kwargs):
        return None
