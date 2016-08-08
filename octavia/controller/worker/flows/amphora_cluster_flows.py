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

from oslo_config import cfg
from stevedore import driver as stevedore_driver
from taskflow.patterns import linear_flow

from octavia.common import constants
from octavia.controller.worker.tasks import database_tasks

CONF = cfg.CONF
CONF.import_group('controller_worker', 'octavia.common.config')


class AmphoraClusterFlows(object):
    def __init__(self):
        self.amphora_cluster_driver = stevedore_driver.DriverManager(
            namespace='octavia.amphorae.cluster_manager.drivers',
            name=CONF.controller_worker.amphora_cluster_driver,
            invoke_on_load=True
        ).driver

    def get_amphora_cluster_for_lb_subflow(self):

        amphora_sf = linear_flow.Flow(
            constants.CREATE_AMP_CLUSTER_FOR_LB_SUBFLOW)

        # Get load balancer
        amphora_sf.add(database_tasks.ReloadLoadBalancer(
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        amphora_sf.add(self.amphora_cluster_driver.create_cluster_for_lb())
        amphora_sf.add(self.amphora_cluster_driver.create_amphorae())
        return amphora_sf

    def get_post_cluster_for_lb_assoc_flow(self):
        amphora_sf = linear_flow.Flow(
            constants.FINALIZE_AMP_CLUSTER_FOR_LB_SUBFLOW)
        amphora_sf.add(self.amphora_cluster_driver.finalize_amphora_cluster())
        return amphora_sf