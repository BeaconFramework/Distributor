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
#

import logging
import time

from oslo_config import cfg
import six
from stevedore import driver as stevedore_driver
from taskflow import task
from taskflow.types import failure

from octavia.amphorae.backends.agent import agent_jinja_cfg
from octavia.common import constants
from octavia.common import exceptions
from octavia.common.jinja import user_data_jinja_cfg
from octavia.i18n import _LE, _LW

CONF = cfg.CONF
CONF.import_group('controller_worker', 'octavia.common.config')
LOG = logging.getLogger(__name__)


class BaseComputeTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        super(BaseComputeTask, self).__init__(**kwargs)
        self.compute = stevedore_driver.DriverManager(
            namespace='octavia.compute.drivers',
            name=CONF.controller_worker.compute_driver,
            invoke_on_load=True
        ).driver


class ComputeCreate(BaseComputeTask):
    """Create the compute instance for a new amphora."""

    def execute(self, amphora_id, ports=None, config_drive_files=None,
                server_group_id=None):
        """Create an amphora

        :returns: an amphora
        """
        ports = ports or []
        network_ids = CONF.controller_worker.amp_boot_network_list[:]
        # TODO(ptoohill) amp_network is now deprecated, remove when ready...
        if CONF.controller_worker.amp_network:
            network_ids.append(CONF.controller_worker.amp_network)
        config_drive_files = config_drive_files or {}
        user_data = None
        LOG.debug("Compute create execute for amphora with id %s", amphora_id)

        user_data_config_drive = CONF.controller_worker.user_data_config_drive
        ssh_access = CONF.controller_worker.amp_ssh_access_allowed
        ssh_key = CONF.controller_worker.amp_ssh_key_name
        key_name = None if not ssh_access else ssh_key

        try:
            agent_cfg = agent_jinja_cfg.AgentJinjaTemplater()
            config_drive_files['/etc/octavia/amphora-agent.conf'] = (
                agent_cfg.build_agent_config(amphora_id))
            if user_data_config_drive:
                udtemplater = user_data_jinja_cfg.UserDataJinjaCfg()
                user_data = udtemplater.build_user_data_config(
                    config_drive_files)
                config_drive_files = None

            compute_id = self.compute.build(
                name="amphora-" + amphora_id,
                amphora_flavor=CONF.controller_worker.amp_flavor_id,
                image_id=CONF.controller_worker.amp_image_id,
                image_tag=CONF.controller_worker.amp_image_tag,
                image_owner=CONF.controller_worker.amp_image_owner_id,
                key_name=key_name,
                sec_groups=CONF.controller_worker.amp_secgroup_list,
                network_ids=network_ids,
                port_ids=[port.id for port in ports],
                config_drive_files=config_drive_files,
                user_data=user_data,
                server_group_id=server_group_id)

            LOG.debug("Server created with id: %s for amphora id: %s",
                      compute_id, amphora_id)
            return compute_id

        except Exception:
            LOG.exception(_LE("Compute create for amphora id: %s failed"),
                          amphora_id)
            raise

    def revert(self, result, amphora_id, *args, **kwargs):
        """This method will revert the creation of the

        amphora. So it will just delete it in this flow
        """
        if isinstance(result, failure.Failure):
            return
        compute_id = result
        LOG.warning(_LW("Reverting compute create for amphora with id"
                        "%(amp)s and compute id: %(comp)s"),
                    {'amp': amphora_id, 'comp': compute_id})
        try:
            self.compute.delete(compute_id)
        except Exception:
            LOG.exception(_LE("Reverting compute create failed"))


class CertComputeCreate(ComputeCreate):
    def execute(self, amphora_id, server_pem, ports=None,
                server_group_id=None):
        """Create an amphora

        :returns: an amphora
        """

        # load client certificate
        with open(CONF.controller_worker.client_ca, 'r') as client_ca:
            ca = client_ca.read()
        config_drive_files = {
            '/etc/octavia/certs/server.pem': server_pem,
            '/etc/octavia/certs/client_ca.pem': ca}
        return super(CertComputeCreate, self).execute(
            amphora_id, ports=ports, config_drive_files=config_drive_files,
            server_group_id=server_group_id)


class DeleteAmphoraeOnLoadBalancer(BaseComputeTask):
    """Delete the amphorae on a load balancer.

    Iterate through amphorae, deleting them
    """

    def execute(self, loadbalancer):
        for amp in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                loadbalancer.amphorae):

            try:
                self.compute.delete(amp.compute_id)
            except Exception:
                LOG.exception(_LE("Compute delete for amphora id: %s failed"),
                              amp.id)
                raise


class ComputeDelete(BaseComputeTask):
    def execute(self, amphora):
        LOG.debug("Compute Delete execute for amphora with id %s", amphora.id)

        try:
            self.compute.delete(amphora.compute_id)
        except Exception:
            LOG.exception(_LE("Compute delete for amphora id: %s failed"),
                          amphora.id)
            raise


class ComputeWait(BaseComputeTask):
    """Wait for the compute driver to mark the amphora active."""

    def execute(self, compute_id):
        """Wait for the compute driver to mark the amphora active

        :raises: Generic exception if the amphora is not active
        :returns: An amphora object
        """
        for i in range(CONF.controller_worker.amp_active_retries):
            amp = self.compute.get_amphora(compute_id)
            if amp.status == constants.ACTIVE:
                return amp
            elif amp.status == constants.ERROR:
                raise exceptions.ComputeBuildException()
            time.sleep(CONF.controller_worker.amp_active_wait_sec)

        raise exceptions.ComputeWaitTimeoutException()


class NovaServerGroupCreate(BaseComputeTask):
    def execute(self, loadbalancer_id):
        """Create a server group by nova client api

        :param loadbalancer_id: will be used for server group's name
        :param policy: will used for server group's policy
        :raises: Generic exception if the server group is not created
        :returns: server group's id
        """

        name = 'octavia-lb-' + loadbalancer_id
        server_group = self.compute.create_server_group(
            name, constants.ANTI_AFFINITY)
        LOG.debug("Server Group created with id: %s for load balancer id: "
                  "%s", server_group.id, loadbalancer_id)
        return server_group.id

    def revert(self, result, *args, **kwargs):
        """This method will revert the creation of the

        :param result: here it refers to server group id
        """
        server_group_id = result
        LOG.warning(_LW("Reverting server group create with id:%s"),
                    server_group_id)
        try:
            self.compute.delete_server_group(server_group_id)
        except Exception as e:
            LOG.error(_LE("Failed to delete server group.  Resources may "
                          "still be in use for server group: %(sg)s due to "
                          "error: %(except)s"),
                      {'sg': server_group_id, 'except': e})


class NovaServerGroupDelete(BaseComputeTask):
    def execute(self, server_group_id):
        if server_group_id is not None:
            self.compute.delete_server_group(server_group_id)
        else:
            return
