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

from oslo_log import log as logging

from octavia.amphorae.cluster_manager.drivers import driver_base

LOG = logging.getLogger(__name__)


class NoopManager(object):
    def __init__(self):
        super(NoopManager, self).__init__()
        self.AmphoraClusterManagerConfig = {}

    def create_cluster_for_lb(self):
        LOG.debug("Amphora Cluster Manager %s no-op",
                  self.__class__.__name__)
        self.AmphoraClusterManagerConfig["loadbalancer"] = (
            'create_cluster_for_lb')

    def create_amphorae(self):
        LOG.debug("Amphora Cluster Manager %s no-op",
                  self.__class__.__name__)
        self.AmphoraClusterManagerConfig["amphora_cluster"] = (
            'create_amphorae')

    def delete_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s no-op, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        self.AmphoraClusterManagerConfig[loadbalancer] = (
            loadbalancer, 'delete_cluster_for_lb')

    def finalize_amphora_cluster(self):
        LOG.debug("Amphora Cluster Manager %s no-op",
                  self.__class__.__name__)
        self.AmphoraClusterManagerConfig["amphora_cluster"] = (
            'finalize_amphora_cluster')

    def recover_from_amphora_failure(self, failed_amphora, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s no-op, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        self.AmphoraClusterManagerConfig[(failed_amphora, loadbalancer)] = (
            (failed_amphora, loadbalancer), 'recover_from_amphora_failure')

    def grow_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s no-op, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        self.AmphoraClusterManagerConfig[loadbalancer] = (
            loadbalancer, 'grow_cluster_for_lb')

    def shrink_cluster_for_lb(self, loadbalancer):
        LOG.debug("Amphora Cluster Manager %s no-op, load_balancer_id %s",
                  self.__class__.__name__, loadbalancer.id)
        self.AmphoraClusterManagerConfig[loadbalancer] = (
            loadbalancer, 'shrink_cluster_for_lb')


class NoopAmphoraClusterDriver(driver_base.AmphoraClusterDriver):
    def __init__(self):
        super(NoopAmphoraClusterDriver, self).__init__()
        self.driver = NoopManager()

    def create_cluster_for_lb(self):
        self.driver.create_cluster_for_lb()
        return None

    def delete_cluster_for_lb(self, loadbalancer):
        self.driver.delete_cluster_for_lb(loadbalancer)
        return True

    def create_amphorae(self):
        self.driver.create_amphorae()
        return None

    def finalize_amphora_cluster(self):
        self.driver.finalize_amphora_cluster()
        return None

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