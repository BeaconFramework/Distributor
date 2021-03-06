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
from taskflow.patterns import linear_flow
# from taskflow import retry

from octavia.common import constants
from octavia.controller.worker.tasks import cert_task
from octavia.controller.worker.tasks import compute_tasks
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import distributor_driver_tasks
from octavia.controller.worker.tasks import network_tasks


CONF = cfg.CONF
CONF.import_group('controller_worker', 'octavia.common.config')


class DistributorFlows(object):
    def __init__(self):
        # for some reason only this has the values from the config file
        self.REST_DISTRIBUTOR_DRIVER = (
            CONF.active_active_cluster.distributor_driver ==
            'distributor_rest_driver')

    def get_create_distributor_flow(self):
        """Creates a flow to create a distributor.

        Ideally that should be configurable in the
        config file - a db session needs to be placed
        into the flow
        :returns: The flow for creating the distributor
        """
        create_distributor_flow = linear_flow.Flow(
            constants.CREATE_DISTRIBUTOR_FLOW)

        create_distributor_flow.add(database_tasks.CreateDistributorInDB(
            provides=constants.DISTRIBUTOR_ID))
        create_distributor_flow.add(cert_task.GenerateDistributorServerPEMTask(
            provides=constants.SERVER_PEM))
        create_distributor_flow.add(
            database_tasks.UpdateDistributorDBCertExpiration(
                requires=(constants.DISTRIBUTOR_ID, constants.SERVER_PEM)))

        create_distributor_flow.add(compute_tasks.CertDistributorComputeCreate(
            requires=(constants.DISTRIBUTOR_ID, constants.SERVER_PEM),
            provides=constants.COMPUTE_ID))

        create_distributor_flow.add(database_tasks.MarkDistributorBootingInDB(
            requires=(constants.DISTRIBUTOR_ID, constants.COMPUTE_ID)))

        '''
        wait_flow = linear_flow.Flow(constants.WAIT_FOR_DISTRIBUTOR,
                                     retry=retry.Times(CONF.
                                                       controller_worker.
                                                       amp_active_retries))
        wait_flow.add(compute_tasks.DistributorComputeWait(
            requires=constants.COMPUTE_ID,
            provides=constants.COMPUTE_OBJ))
        wait_flow.add(database_tasks.UpdateDistributorInfo(
            requires=(constants.DISTRIBUTOR_ID, constants.COMPUTE_OBJ),
            provides=constants.DISTRIBUTOR))
        create_distributor_flow.add(wait_flow)'''

        create_distributor_flow.add(compute_tasks.DistributorComputeWait(
            requires=constants.COMPUTE_ID,
            provides=constants.COMPUTE_OBJ))
        create_distributor_flow.add(database_tasks.UpdateDistributorInfo(
            requires=(constants.DISTRIBUTOR_ID, constants.COMPUTE_OBJ),
            provides=constants.DISTRIBUTOR))

        create_distributor_flow.add(database_tasks.ReloadDistributor(
            requires=constants.DISTRIBUTOR_ID,
            provides=constants.DISTRIBUTOR))

        create_distributor_flow.add(database_tasks.MarkDistributorReadyInDB(
            requires=constants.DISTRIBUTOR))

        return create_distributor_flow

    def create_distributor_networking_subflow(self):
        new_net_subflow = linear_flow.Flow(constants.
                                           DISTRIBUTOR_NETWORKING_SUBFLOW)

        new_net_subflow.add(network_tasks.AllocateVIP(
            requires=constants.LOADBALANCER,
            provides=constants.VIP))

        new_net_subflow.add(database_tasks.UpdateVIPAfterAllocation(
            requires=(constants.LOADBALANCER_ID, constants.VIP),
            provides=constants.LOADBALANCER))

        new_net_subflow.add(network_tasks.PlugDistributorVIP(
            requires=(constants.LOADBALANCER, constants.DISTRIBUTOR),
            provides=constants.DISTRIBUTOR_MAC
        ))

        new_net_subflow.add(database_tasks.ReloadLoadBalancer(
            name=constants.RELOAD_LB_BEFORE_PLUG_VIP_TO_DISTRIBUTOR,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        # TODO(Lera): check how we get CLUSTER_ALG_EXTRA
        new_net_subflow.add(distributor_driver_tasks.DistributorPostVIPPlug(
            requires=(constants.DISTRIBUTOR, constants.LOADBALANCER,
                      constants.DISTRIBUTOR_MAC,
                      constants.CLUSTER_ALG_TYPE,
                      constants.CLUSTER_MIN_SIZE)))

        return new_net_subflow
