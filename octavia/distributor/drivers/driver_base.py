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

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class DistributorDriver(object):
    @abc.abstractmethod
    def get_info(self, distributor):
        """Returns information about the Distributor

        :param distributor: distributor object, need to use its id property
        :type distributor: object
        :returns: return a value list (distributor.id, status flag--'get_info')

        At this moment, we just build the basic structure for testing, will
        add more function along with the development, eventually, we want it
        to return information as:
        {"Rest Interface": "1.0", "Distributor": "1.0"}
        """
        pass

    @abc.abstractmethod
    def get_diagnostics(self, distributor):
        """Return ready health set of amphorae

        :param distributor: distributor object, need to use its id property
        :type distributor: object
        :returns: return a value list (distributor.id, status flag--'ge
        t_diagnostics')

        At this moment, we just build the basic structure for testing, will
        add more function along with the development, eventually, we want it
        run some expensive self tests to determine if the distributor and lbs
        are healthy the idea is that those tests are triggered more infrequent
        than the health gathering
        """
        pass

    @abc.abstractmethod
    def post_vip_plug(self, distributor, load_balancer, distributor_mac,
                      cluster_alg_type, cluster_min_size):
        """Called after network driver has allocated and plugged the VIP

        :param distributor: distributor object, need to use its id property
        :type distributor: object
        :param load_balancer: A load balancer that just had its vip allocated
                              and plugged in the network driver.
        :type load_balancer: octavia.network.data_models.LoadBalancer
        :param distributor_mac: distributor mac for this VIP
        :type distributor_mac: string
        :param cluster_alg_type: specific algorithm type
            (currently supported are ACTIVE_ACTIVE and PLUG_DEBUG)
        :type arg_type: basestring
        :param culster_min_size: minimal size of cluster
        :type cluster_min_size: int

        :returns: None
        """
        pass

    @abc.abstractmethod
    def pre_vip_unplug(self, distributor, load_balancer):
        """Called before network driver has deallocated and unplugged the VIP

        :param distributor: distributor object, need to use its id property
        :type distributor: object
        :param load_balancer: A load balancer that is to be removed.
        :type load_balancer: octavia.network.data_models.LoadBalancer
        :returns: None
        """
        pass

    @abc.abstractmethod
    def register_amphora(self, distributor, load_balancer, amphora,
                         cluster_alg_type, cluster_min_size):
        """Called after amphora is ready to add amphora MAC

        :param distributor: distributor object
        :type distributor: object
        :param load_balancer: A load balancer to which the amphora is attached
        :type load_balancer: octavia.network.data_models.LoadBalancer
        :param amphora: An amphora object
        :type: amphora: an object that defines amphora to be registered
        :param cluster_alg_type: specific algorithm type
            (currently supported are ACTIVE_ACTIVE and PLUG_DEBUG)
        :type arg_type: basestring
        :param culster_min_size: minimal size of cluster
        :type cluster_min_size: int
        :returns: None
        """
        pass

    @abc.abstractmethod
    def unregister_amphora(self, distributor, load_balancer,
                           amphora, cluster_alg_type, cluster_min_size):
        """Called after amphora is ready to be removed

        :param distributor: distributor object, need to use its id property
        :type distributor: object
        :param load_balancer: A load balancer from which the amphora is
        detached
        :type load_balancer: octavia.network.data_models.LoadBalancer
        :param amphora: An amphora object
        :type: amphora: an object that defines amphora to be unregistered
        :param cluster_alg_type: specific algorithm type
            (currently supported are ACTIVE_ACTIVE and PLUG_DEBUG)
        :type arg_type: basestring
        :param culster_min_size: minimal size of cluster
        :type cluster_min_size: int
        :returns: None
        """
        pass
