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

from oslo_config import cfg
import six
from stevedore import driver as stevedore_driver
from taskflow import task
from taskflow.types import failure

from octavia.common import constants
from octavia.controller.worker import task_utils as task_utilities
from octavia.db import api as db_apis
from octavia.db import repositories as repo
from octavia.i18n import _LE, _LW

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseAmphoraTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        super(BaseAmphoraTask, self).__init__(**kwargs)
        self.amphora_driver = stevedore_driver.DriverManager(
            namespace='octavia.amphora.drivers',
            name=CONF.controller_worker.amphora_driver,
            invoke_on_load=True
        ).driver
        self.amphora_repo = repo.AmphoraRepository()
        self.listener_repo = repo.ListenerRepository()
        self.loadbalancer_repo = repo.LoadBalancerRepository()
        self.task_utils = task_utilities.TaskUtils()


class ListenersUpdate(BaseAmphoraTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer, listeners):
        """Execute updates per listener for an amphora."""
        for listener in listeners:
            listener.load_balancer = loadbalancer
            self.amphora_driver.update(listener, loadbalancer.vip)

    def revert(self, loadbalancer, *args, **kwargs):
        """Handle failed listeners updates."""

        LOG.warning(_LW("Reverting listeners updates."))

        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)

        return None


class ListenerStop(BaseAmphoraTask):
    """Task to stop the listener on the vip."""

    def execute(self, loadbalancer, listener):
        """Execute listener stop routines for an amphora."""
        self.amphora_driver.stop(listener, loadbalancer.vip)
        LOG.debug("Stopped the listener on the vip")

    def revert(self, listener, *args, **kwargs):
        """Handle a failed listener stop."""

        LOG.warning(_LW("Reverting listener stop."))

        self.task_utils.mark_listener_prov_status_error(listener.id)

        return None


class ListenerStart(BaseAmphoraTask):
    """Task to start the listener on the vip."""

    def execute(self, loadbalancer, listener):
        """Execute listener start routines for an amphora."""
        self.amphora_driver.start(listener, loadbalancer.vip)
        LOG.debug("Started the listener on the vip")

    def revert(self, listener, *args, **kwargs):
        """Handle a failed listener start."""

        LOG.warning(_LW("Reverting listener start."))

        self.task_utils.mark_listener_prov_status_error(listener.id)

        return None


class ListenersStart(BaseAmphoraTask):
    """Task to start all listeners on the vip."""

    def execute(self, loadbalancer, listeners):
        """Execute listener start routines for listeners on an amphora."""
        for listener in listeners:
            self.amphora_driver.start(listener, loadbalancer.vip)
        LOG.debug("Started the listeners on the vip")

    def revert(self, listeners, *args, **kwargs):
        """Handle failed listeners starts."""

        LOG.warning(_LW("Reverting listeners starts."))
        for listener in listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)

        return None


class ListenerDelete(BaseAmphoraTask):
    """Task to delete the listener on the vip."""

    def execute(self, loadbalancer, listener):
        """Execute listener delete routines for an amphora."""
        self.amphora_driver.delete(listener, loadbalancer.vip)
        LOG.debug("Deleted the listener on the vip")

    def revert(self, listener, *args, **kwargs):
        """Handle a failed listener delete."""

        LOG.warning(_LW("Reverting listener delete."))

        self.task_utils.mark_listener_prov_status_error(listener.id)


class AmphoraGetInfo(BaseAmphoraTask):
    """Task to get information on an amphora."""

    def execute(self, amphora):
        """Execute get_info routine for an amphora."""
        self.amphora_driver.get_info(amphora)


class AmphoraGetDiagnostics(BaseAmphoraTask):
    """Task to get diagnostics on the amphora and the loadbalancers."""

    def execute(self, amphora):
        """Execute get_diagnostic routine for an amphora."""
        self.amphora_driver.get_diagnostics(amphora)


class AmphoraFinalize(BaseAmphoraTask):
    """Task to finalize the amphora before any listeners are configured."""

    def execute(self, amphora):
        """Execute finalize_amphora routine."""
        self.amphora_driver.finalize_amphora(amphora)
        LOG.debug("Finalized the amphora.")

    def revert(self, result, amphora, *args, **kwargs):
        """Handle a failed amphora finalize."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting amphora finalize."))
        self.task_utils.mark_amphora_status_error(amphora.id)


class AmphoraPostNetworkPlug(BaseAmphoraTask):
    """Task to notify the amphora post network plug."""

    def execute(self, amphora, ports):
        """Execute post_network_plug routine."""
        for port in ports:
            self.amphora_driver.post_network_plug(amphora, port)
            LOG.debug("post_network_plug called on compute instance "
                      "%(compute_id)s for port %(port_id)s",
                      {"compute_id": amphora.compute_id, "port_id": port.id})

    def revert(self, result, amphora, *args, **kwargs):
        """Handle a failed post network plug."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting post network plug."))
        self.task_utils.mark_amphora_status_error(amphora.id)


class AmphoraePostNetworkPlug(BaseAmphoraTask):
    """Task to notify the amphorae post network plug."""

    def execute(self, loadbalancer, added_ports):
        """Execute post_network_plug routine."""
        amp_post_plug = AmphoraPostNetworkPlug()
        for amphora in loadbalancer.amphorae:
            if amphora.id in added_ports:
                amp_post_plug.execute(amphora, added_ports[amphora.id])

    def revert(self, result, loadbalancer, added_ports, *args, **kwargs):
        """Handle a failed post network plug."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting post network plug."))
        for amphora in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                loadbalancer.amphorae):

            self.task_utils.mark_amphora_status_error(amphora.id)


class AmphoraPostVIPPlug(BaseAmphoraTask):
    """Task to notify the amphora post VIP plug."""

    def execute(self, amphora, loadbalancer, amphorae_network_config):
        """Execute post_vip_routine."""
        self.amphora_driver.post_vip_plug(
            amphora, loadbalancer, amphorae_network_config)
        LOG.debug("Notified amphora of vip plug")

    def revert(self, result, amphora, loadbalancer, *args, **kwargs):
        """Handle a failed amphora vip plug notification."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting post vip plug."))
        self.task_utils.mark_amphora_status_error(amphora.id)
        self.task_utils.mark_loadbalancer_prov_status_error(loadbalancer.id)


class AmphoraePostVIPPlug(BaseAmphoraTask):
    """Task to notify the amphorae post VIP plug."""

    def execute(self, loadbalancer, amphorae_network_config):
        """Execute post_vip_plug across the amphorae."""
        amp_post_vip_plug = AmphoraPostVIPPlug()
        for amphora in loadbalancer.amphorae:
            amp_post_vip_plug.execute(amphora,
                                      loadbalancer,
                                      amphorae_network_config)

    def revert(self, result, loadbalancer, *args, **kwargs):
        """Handle a failed amphora vip plug notification."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting amphorae post vip plug."))
        self.task_utils.mark_loadbalancer_prov_status_error(loadbalancer.id)


class AmphoraCertUpload(BaseAmphoraTask):
    """Upload a certificate to the amphora."""

    def execute(self, amphora, server_pem):
        """Execute cert_update_amphora routine."""
        LOG.debug("Upload cert in amphora REST driver")
        self.amphora_driver.upload_cert_amp(amphora, server_pem)


class AmphoraUpdateVRRPInterface(BaseAmphoraTask):
    """Task to get and update the VRRP interface device name from amphora."""

    def execute(self, loadbalancer):
        """Execute post_vip_routine."""
        amps = []
        for amp in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                loadbalancer.amphorae):
                    # Currently this is supported only with REST Driver
                    interface = self.amphora_driver.get_vrrp_interface(amp)
                    self.amphora_repo.update(db_apis.get_session(), amp.id,
                                             vrrp_interface=interface)
                    amps.append(self.amphora_repo.get(db_apis.get_session(),
                                                      id=amp.id))
        loadbalancer.amphorae = amps
        return loadbalancer

    def revert(self, result, loadbalancer, *args, **kwargs):
        """Handle a failed amphora vip plug notification."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning(_LW("Reverting Get Amphora VRRP Interface."))
        for amp in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                loadbalancer.amphorae):

            try:
                self.amphora_repo.update(db_apis.get_session(), amp.id,
                                         vrrp_interface=None)
            except Exception as e:
                LOG.error(_LE("Failed to update amphora %(amp)s "
                              "VRRP interface to None due to: "
                              "%(except)s"), {'amp': amp.id,
                                              'except': e})


class AmphoraVRRPUpdate(BaseAmphoraTask):
    """Task to update the VRRP configuration of the loadbalancer amphorae."""

    def execute(self, loadbalancer):
        """Execute update_vrrp_conf."""
        self.amphora_driver.update_vrrp_conf(loadbalancer)
        LOG.debug("Uploaded VRRP configuration of loadbalancer %s amphorae",
                  loadbalancer.id)


class AmphoraVRRPStop(BaseAmphoraTask):
    """Task to stop keepalived of all amphorae of a LB."""

    def execute(self, loadbalancer):
        self.amphora_driver.stop_vrrp_service(loadbalancer)
        LOG.debug("Stopped VRRP of loadbalancer % amphorae",
                  loadbalancer.id)


class AmphoraVRRPStart(BaseAmphoraTask):
    """Task to start keepalived of all amphorae of a LB."""

    def execute(self, loadbalancer):
        self.amphora_driver.start_vrrp_service(loadbalancer)
        LOG.debug("Started VRRP of loadbalancer %s amphorae",
                  loadbalancer.id)
