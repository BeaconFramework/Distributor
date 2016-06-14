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

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class AmphoraClusterDriver(object):

    @abc.abstractmethod
    def create_cluster_for_lb(self):
        """Create cluster object

        :returns: amphora_cluster object

        """
        pass

    @abc.abstractmethod
    def create_amphorae(self):
        """Create amphorae for cluster_manager

        :returns: Success

        """
        pass

    @abc.abstractmethod
    def delete_cluster_for_lb(self, loadbalancer):
        """Delete cluster_manager of Amphora instances

        :param loadbalancer: load balancer object ,
        delete all amphora instances associated with
        load_balancer id, and deletes cluster object
        :returns: Success
        """
        pass

    @abc.abstractmethod
    def finalize_amphora_cluster(self):
        """Create amphorae for amphora_cluster

        :returns: Success

        """
        pass

    @abc.abstractmethod
    def recover_from_amphora_failure(self, failed_amphora, loadbalancer):
        """Treat amphora failure (API used by HealthManager)

        :param failed_amphora: amphora object that was detected as failed
        :param loadbalancer: loadbalancer object that used the Amphora
        :returns: Success

        """
        pass

    @abc.abstractmethod
    def grow_cluster_for_lb(self, loadbalancer):
        """Grow cluster for loadbalancer

        :param loadbalancer: loadbalancer object to whose cluster
        should be increased
        :returns: Success

        """
        pass

    @abc.abstractmethod
    def shrink_cluster_for_lb(self, loadbalancer):
        """Shring cluster for loadbalancer

        :param loadbalancer: loadbalancer object to whose cluster
        should be decreased
        :returns: Success

        """
        pass