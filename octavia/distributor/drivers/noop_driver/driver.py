# Copyright 2016 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_log import log as logging

from octavia.distributor.drivers import driver_base as driver_base

LOG = logging.getLogger(__name__)


class NoopManager(object):
    def __init__(self):
        super(NoopManager, self).__init__()
        self.distributor_config = {}

    def get_info(self, distributor):
        LOG.debug("distributor %s no-op, info distributor %s",
                  self.__class__.__name__, distributor.id)
        self.distributor_config[distributor.id] = (distributor.id, 'get_info')

    def get_diagnostics(self, distributor):
        LOG.debug("distributor %s no-op, get diagnostics distributor %s",
                  self.__class__.__name__, distributor.id)
        self.distributor_config[distributor.id] = (distributor.id,
                                                   'get_diagnostics')

    def register_amphora(self, distributor, load_balancer, amphora,
                         cluster_alg_type, cluster_min_size):
        LOG.debug("distributor %s no-op, register amphora %s with LB %s",
                  self.__class__.__name__, amphora.id, load_balancer.id)
        self.distributor_config[(amphora.id,
                                 distributor.id,
                                 load_balancer.id,
                                 cluster_alg_type,
                                 cluster_min_size)] = (amphora.id,
                                                       distributor.id,
                                                       load_balancer.id,
                                                       cluster_alg_type,
                                                       cluster_min_size,
                                                       'register_amphora')

    def unregister_amphora(self, distributor, load_balancer, amphora,
                           cluster_alg_type, cluster_min_size):
        LOG.debug("distributor %s no-op, unregister amphora %s, LB:%s",
                  self.__class__.__name__, amphora.id, load_balancer.id)
        self.distributor_config[(amphora.id,
                                 distributor.id,
                                 load_balancer.id,
                                 cluster_alg_type,
                                 cluster_min_size)] = (amphora.id,
                                                       distributor.id,
                                                       load_balancer.id,
                                                       cluster_alg_type,
                                                       cluster_min_size,
                                                       'unregister_amphora')

    def post_vip_plug(self, distributor, load_balancer, distributor_mac,
                      cluster_alg_type, cluster_min_size):
        LOG.debug("distributor %s no-op, post vip plug load balancer %s",
                  self.__class__.__name__, load_balancer.id)
        self.distributor_config[(distributor.id,
                                 load_balancer.id,
                                 distributor_mac,
                                 cluster_alg_type,
                                 cluster_min_size)] = (distributor.id,
                                                       load_balancer.id,
                                                       distributor_mac,
                                                       cluster_alg_type,
                                                       cluster_min_size,
                                                       'post_vip_plug')

    def pre_vip_unplug(self, distributor, load_balancer):
        LOG.debug("distributor %s no-op, pre vip unplug load balancer %s",
                  self.__class__.__name__, load_balancer.id)
        self.distributor_config[(load_balancer.id,
                                 distributor.id)] = (load_balancer.id,
                                                     distributor.id,
                                                     'pre_vip_unplug')


class NoopDistributorDriver(driver_base.DistributorDriver):
    def __init__(self):
        super(NoopDistributorDriver, self).__init__()
        self.driver = NoopManager()

    def get_info(self, distributor):
        self.driver.get_info(distributor)

    def get_diagnostics(self, distributor):
        self.driver.get_diagnostics(distributor)

    def register_amphora(self, distributor, load_balancer, amphora,
                         cluster_alg_type, cluster_min_size):
        self.driver.register_amphora(distributor,
                                     load_balancer,
                                     amphora,
                                     cluster_alg_type,
                                     cluster_min_size)

    def unregister_amphora(self, distributor, load_balancer, amphora,
                           cluster_alg_type, cluster_min_size):
        self.driver.unregister_amphora(distributor,
                                       load_balancer,
                                       amphora,
                                       cluster_alg_type,
                                       cluster_min_size)

    def post_vip_plug(self, distributor, load_balancer, distributor_mac,
                      cluster_alg_type, cluster_min_size):
        self.driver.post_vip_plug(distributor,
                                  load_balancer,
                                  distributor_mac,
                                  cluster_alg_type,
                                  cluster_min_size)

    def pre_vip_unplug(self, distributor, load_balancer):
        self.driver.pre_vip_unplug(distributor, load_balancer)
