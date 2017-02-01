# Copyright 2011 VMware, Inc., 2014 A10 Networks
# All Rights Reserved.
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

"""
Routines for configuring Octavia
"""

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_db import options as db_options
from oslo_log import log as logging
import oslo_messaging as messaging

from octavia.common import constants
from octavia.common import utils
from octavia.i18n import _LI
from octavia import version

LOG = logging.getLogger(__name__)

core_opts = [
    cfg.IPOpt('bind_host', default='127.0.0.1',
              help=_("The host IP to bind to")),
    cfg.PortOpt('bind_port', default=9876,
                help=_("The port to bind to")),
    cfg.StrOpt('auth_strategy', default=constants.NOAUTH,
               choices=[constants.NOAUTH, constants.KEYSTONE],
               help=_("The auth strategy for API requests.")),
    cfg.StrOpt('api_handler', default='queue_producer',
               help=_("The handler that the API communicates with")),
    cfg.StrOpt('api_paste_config', default="api-paste.ini",
               help=_("The API paste config file to use")),
    cfg.StrOpt('api_extensions_path', default="",
               help=_("The path for API extensions")),
    cfg.BoolOpt('allow_bulk', default=True,
                help=_("Allow the usage of the bulk API")),
    cfg.BoolOpt('allow_pagination', default=False,
                help=_("Allow the usage of the pagination")),
    cfg.BoolOpt('allow_sorting', default=False,
                help=_("Allow the usage of the sorting")),
    cfg.StrOpt('pagination_max_limit', default="-1",
               help=_("The maximum number of items returned in a single "
                      "response. The string 'infinite' or a negative "
                      "integer value means 'no limit'")),
    cfg.StrOpt('host', default=utils.get_hostname(),
               help=_("The hostname Octavia is running on")),
    cfg.StrOpt('octavia_plugins',
               default='hot_plug_plugin',
               help=_('Name of the controller plugin to use'))
]

# Options only used by the amphora agent
amphora_agent_opts = [
    cfg.StrOpt('agent_server_ca', default='/etc/octavia/certs/client_ca.pem',
               help=_("The ca which signed the client certificates")),
    cfg.StrOpt('agent_server_cert', default='/etc/octavia/certs/server.pem',
               help=_("The server certificate for the agent.py server "
                      "to use")),
    cfg.StrOpt('agent_server_network_dir',
               help=_("The directory where new network interfaces "
                      "are located")),
    cfg.StrOpt('agent_server_network_file',
               help=_("The file where the network interfaces are located. "
                      "Specifying this will override any value set for "
                      "agent_server_network_dir.")),
    cfg.IntOpt('agent_request_read_timeout', default=120,
               help=_("The time in seconds to allow a request from the "
                      "controller to run before terminating the socket.")),
    # Do not specify in octavia.conf, loaded at runtime
    cfg.StrOpt('amphora_id', help=_("The amphora ID.")),
]

networking_opts = [
    cfg.StrOpt('lb_network_name', help=_('Name of amphora internal network')),
    cfg.IntOpt('max_retries', default=15,
               help=_('The maximum attempts to retry an action with the '
                      'networking service.')),
    cfg.IntOpt('retry_interval', default=1,
               help=_('Seconds to wait before retrying an action with the '
                      'networking service.')),
    cfg.IntOpt('port_detach_timeout', default=300,
               help=_('Seconds to wait for a port to detach from an '
                      'amphora.'))
]

healthmanager_opts = [
    cfg.IPOpt('bind_ip', default='127.0.0.1',
              help=_('IP address the controller will listen on for '
                     'heart beats')),
    cfg.PortOpt('bind_port', default=5555,
                help=_('Port number the controller will listen on'
                       'for heart beats')),
    cfg.IntOpt('failover_threads',
               default=10,
               help=_('Number of threads performing amphora failovers.')),
    cfg.IntOpt('status_update_threads',
               default=50,
               help=_('Number of threads performing amphora status update.')),
    cfg.StrOpt('heartbeat_key',
               help=_('key used to validate amphora sending'
                      'the message'), secret=True),
    cfg.IntOpt('heartbeat_timeout',
               default=60,
               help=_('Interval, in seconds, to wait before failing over an '
                      'amphora.')),
    cfg.IntOpt('health_check_interval',
               default=3,
               help=_('Sleep time between health checks in seconds.')),
    cfg.IntOpt('sock_rlimit', default=0,
               help=_(' sets the value of the heartbeat recv buffer')),

    # Used by the health manager on the amphora
    cfg.ListOpt('controller_ip_port_list',
                help=_('List of controller ip and port pairs for the '
                       'heartbeat receivers. Example 127.0.0.1:5555, '
                       '192.168.0.1:5555'),
                default=[]),
    cfg.IntOpt('heartbeat_interval',
               default=10,
               help=_('Sleep time between sending heartbeats.')),
    cfg.StrOpt('event_streamer_driver',
               help=_('Specifies which driver to use for the event_streamer '
                      'for syncing the octavia and neutron_lbaas dbs. If you '
                      'don\'t need to sync the database or are running '
                      'octavia in stand alone mode use the '
                      'noop_event_streamer'),
               default='noop_event_streamer')]

oslo_messaging_opts = [
    cfg.StrOpt('topic'),
    cfg.StrOpt('event_stream_topic',
               default='neutron_lbaas_event',
               help=_('topic name for communicating events through a queue')),
]

haproxy_amphora_opts = [
    cfg.StrOpt('base_path',
               default='/var/lib/octavia',
               help=_('Base directory for amphora files.')),
    cfg.StrOpt('base_cert_dir',
               default='/var/lib/octavia/certs',
               help=_('Base directory for cert storage.')),
    cfg.StrOpt('haproxy_template', help=_('Custom haproxy template.')),
    cfg.IntOpt('connection_max_retries',
               default=300,
               help=_('Retry threshold for connecting to amphorae.')),
    cfg.IntOpt('connection_retry_interval',
               default=5,
               help=_('Retry timeout between connection attempts in '
                      'seconds.')),
    cfg.StrOpt('user_group',
               default='nogroup',
               help=_('The user group for haproxy to run under inside the '
                      'amphora.')),
    cfg.StrOpt('haproxy_stick_size', default='10k',
               help=_('Size of the HAProxy stick table. Accepts k, m, g '
                      'suffixes.  Example: 10k')),

    # REST server
    cfg.IPOpt('bind_host', default='::',  # nosec
              help=_("The host IP to bind to")),
    cfg.PortOpt('bind_port', default=9443,
                help=_("The port to bind to")),
    cfg.StrOpt('lb_network_interface',
               default='o-hm0',
               help=_('Network interface through which to reach amphora, only '
                      'required if using IPv6 link local addresses.')),
    cfg.StrOpt('haproxy_cmd', default='/usr/sbin/haproxy',
               help=_("The full path to haproxy")),
    cfg.IntOpt('respawn_count', default=2,
               help=_("The respawn count for haproxy's upstart script")),
    cfg.IntOpt('respawn_interval', default=2,
               help=_("The respawn interval for haproxy's upstart script")),
    cfg.FloatOpt('rest_request_conn_timeout', default=10,
                 help=_("The time in seconds to wait for a REST API "
                        "to connect.")),
    cfg.FloatOpt('rest_request_read_timeout', default=60,
                 help=_("The time in seconds to wait for a REST API "
                        "response.")),
    # REST client
    cfg.StrOpt('client_cert', default='/etc/octavia/certs/client.pem',
               help=_("The client certificate to talk to the agent")),
    cfg.StrOpt('server_ca', default='/etc/octavia/certs/server_ca.pem',
               help=_("The ca which signed the server certificates")),
    cfg.BoolOpt('use_upstart', default=True,
                deprecated_for_removal=True,
                deprecated_reason='This is now automatically discovered '
                                  ' and configured.',
                help=_("If False, use sysvinit.")),
]

controller_worker_opts = [
    cfg.IntOpt('amp_active_retries',
               default=10,
               help=_('Retry attempts to wait for Amphora to become active')),
    cfg.IntOpt('amp_active_wait_sec',
               default=10,
               help=_('Seconds to wait between checks on whether an Amphora '
                      'has become active')),
    cfg.StrOpt('amp_flavor_id',
               default='',
               help=_('Nova instance flavor id for the Amphora')),
    cfg.StrOpt('amp_image_tag',
               default='',
               help=_('Glance image tag for the Amphora image to boot. '
                      'Use this option to be able to update the image '
                      'without reconfiguring Octavia. '
                      'Ignored if amp_image_id is defined.')),
    cfg.StrOpt('amp_image_id',
               default='',
               deprecated_for_removal=True,
               deprecated_reason='Superseded by amp_image_tag option.',
               help=_('Glance image id for the Amphora image to boot')),
    cfg.StrOpt('amp_image_owner_id',
               default='',
               help=_('Restrict glance image selection to a specific '
                      'owner ID.  This is a recommended security setting.')),
    cfg.StrOpt('amp_ssh_key_name',
               default='',
               help=_('SSH key name used to boot the Amphora')),
    cfg.BoolOpt('amp_ssh_access_allowed',
                default=True,
                help=_('Determines whether or not to allow access '
                       'to the Amphorae')),
    cfg.ListOpt('amp_boot_network_list',
                default='',
                help=_('List of networks to attach to the Amphorae. '
                       'All networks defined in the list will '
                       'be attached to each amphora.')),
    cfg.StrOpt('amp_network',
               deprecated_for_removal=True,
               deprecated_reason='Replaced by amp_boot_network_list.',
               default='',
               help=_('Network to attach to the Amphorae.')),
    cfg.ListOpt('amp_secgroup_list',
                default='',
                help=_('List of security groups to attach to the Amphora.')),
    cfg.StrOpt('client_ca',
               default='/etc/octavia/certs/ca_01.pem',
               help=_('Client CA for the amphora agent to use')),
    cfg.StrOpt('amphora_driver',
               default='amphora_noop_driver',
               help=_('Name of the amphora driver to use')),
    cfg.StrOpt('compute_driver',
               default='compute_noop_driver',
               help=_('Name of the compute driver to use')),
    cfg.StrOpt('network_driver',
               default='network_noop_driver',
               help=_('Name of the network driver to use')),
    cfg.StrOpt('loadbalancer_topology',
               default=constants.TOPOLOGY_SINGLE,
               choices=constants.SUPPORTED_LB_TOPOLOGIES,
               help=_('Load balancer topology configuration. '
                      'SINGLE - One amphora per load balancer. '
                      'ACTIVE_STANDBY - Two amphora per load balancer.')),
    cfg.BoolOpt('user_data_config_drive', default=False,
                help=_('If True, build cloud-init user-data that is passed '
                       'to the config drive on Amphora boot instead of '
                       'personality files. If False, utilize personality '
                       'files.'))
]

task_flow_opts = [
    cfg.StrOpt('engine',
               default='serial',
               help=_('TaskFlow engine to use')),
    cfg.IntOpt('max_workers',
               default=5,
               help=_('The maximum number of workers'))
]

core_cli_opts = []

certificate_opts = [
    cfg.StrOpt('cert_manager',
               default='barbican_cert_manager',
               help='Name of the cert manager to use'),
    cfg.StrOpt('cert_generator',
               default='local_cert_generator',
               help='Name of the cert generator to use'),
    cfg.StrOpt('barbican_auth',
               default='barbican_acl_auth',
               help='Name of the Barbican authentication method to use'),
    cfg.StrOpt('service_name',
               help=_('The name of the certificate service in the keystone'
                      'catalog')),
    cfg.StrOpt('endpoint', help=_('A new endpoint to override the endpoint '
                                  'in the keystone catalog.')),
    cfg.StrOpt('region_name',
               help='Region in Identity service catalog to use for '
                    'communication with the barbican service.'),
    cfg.StrOpt('endpoint_type',
               default='publicURL',
               help='The endpoint_type to be used for barbican service.'),
    cfg.StrOpt('ca_certificates_file',
               help=_('CA certificates file path')),
    cfg.BoolOpt('insecure',
                default=False,
                help=_('Disable certificate validation on SSL connections ')),
]

house_keeping_opts = [
    cfg.IntOpt('spare_check_interval',
               default=30,
               help=_('Spare check interval in seconds')),
    cfg.IntOpt('spare_amphora_pool_size',
               default=0,
               help=_('Number of spare amphorae')),
    cfg.IntOpt('cleanup_interval',
               default=30,
               help=_('DB cleanup interval in seconds')),
    cfg.IntOpt('amphora_expiry_age',
               default=604800,
               help=_('Amphora expiry age in seconds')),
    cfg.IntOpt('load_balancer_expiry_age',
               default=604800,
               help=_('Load balancer expiry age in seconds')),
    cfg.IntOpt('cert_interval',
               default=3600,
               help=_('Certificate check interval in seconds')),
    # 14 days for cert expiry buffer
    cfg.IntOpt('cert_expiry_buffer',
               default=1209600,
               help=_('Seconds until certificate expiration')),
    cfg.IntOpt('cert_rotate_threads',
               default=10,
               help=_('Number of threads performing amphora certificate'
                      ' rotation'))
]

anchor_opts = [
    cfg.StrOpt('url',
               default='http://localhost:9999/v1/sign/default',
               help=_('Anchor URL')),
    cfg.StrOpt('username',
               help=_('Anchor username')),
    cfg.StrOpt('password',
               help=_('Anchor password'),
               secret=True)
]

keepalived_vrrp_opts = [
    cfg.IntOpt('vrrp_advert_int',
               default=1,
               help=_('Amphora role and priority advertisement interval '
                      'in seconds.')),
    cfg.IntOpt('vrrp_check_interval',
               default=5,
               help=_('VRRP health check script run interval in seconds.')),
    cfg.IntOpt('vrrp_fail_count',
               default=2,
               help=_('Number of successive failures before transition to a '
                      'fail state.')),
    cfg.IntOpt('vrrp_success_count',
               default=2,
               help=_('Number of consecutive successes before transition to a '
                      'success state.')),
    cfg.IntOpt('vrrp_garp_refresh_interval',
               default=5,
               help=_('Time in seconds between gratuitous ARP announcements '
                      'from the MASTER.')),
    cfg.IntOpt('vrrp_garp_refresh_count',
               default=2,
               help=_('Number of gratuitous ARP announcements to make on '
                      'each refresh interval.'))

]

nova_opts = [
    cfg.StrOpt('service_name',
               help=_('The name of the nova service in the keystone catalog')),
    cfg.StrOpt('endpoint', help=_('A new endpoint to override the endpoint '
                                  'in the keystone catalog.')),
    cfg.StrOpt('region_name',
               help=_('Region in Identity service catalog to use for '
                      'communication with the OpenStack services.')),
    cfg.StrOpt('endpoint_type', default='publicURL',
               help=_('Endpoint interface in identity service to use')),
    cfg.StrOpt('ca_certificates_file',
               help=_('CA certificates file path')),
    cfg.BoolOpt('insecure',
                default=False,
                help=_('Disable certificate validation on SSL connections ')),
    cfg.BoolOpt('enable_anti_affinity', default=False,
                help=_('Flag to indicate if nova anti-affinity feature is '
                       'turned on.'))
]

neutron_opts = [
    cfg.StrOpt('service_name',
               help=_('The name of the neutron service in the '
                      'keystone catalog')),
    cfg.StrOpt('endpoint', help=_('A new endpoint to override the endpoint '
                                  'in the keystone catalog.')),
    cfg.StrOpt('region_name',
               help=_('Region in Identity service catalog to use for '
                      'communication with the OpenStack services.')),
    cfg.StrOpt('endpoint_type', default='publicURL',
               help=_('Endpoint interface in identity service to use')),
    cfg.StrOpt('ca_certificates_file',
               help=_('CA certificates file path')),
    cfg.BoolOpt('insecure',
                default=False,
                help=_('Disable certificate validation on SSL connections ')),
]

glance_opts = [
    cfg.StrOpt('service_name',
               help=_('The name of the glance service in the '
                      'keystone catalog')),
    cfg.StrOpt('endpoint', help=_('A new endpoint to override the endpoint '
                                  'in the keystone catalog.')),
    cfg.StrOpt('region_name',
               help=_('Region in Identity service catalog to use for '
                      'communication with the OpenStack services.')),
    cfg.StrOpt('endpoint_type', default='publicURL',
               help=_('Endpoint interface in identity service to use')),
    cfg.StrOpt('ca_certificates_file',
               help=_('CA certificates file path')),
    cfg.BoolOpt('insecure',
                default=False,
                help=_('Disable certificate validation on SSL connections ')),
]

quota_opts = [
    cfg.IntOpt('default_load_balancer_quota',
               default=constants.QUOTA_UNLIMITED,
               help=_('Default per project load balancer quota.')),
    cfg.IntOpt('default_listener_quota',
               default=constants.QUOTA_UNLIMITED,
               help=_('Default per project listener quota.')),
    cfg.IntOpt('default_member_quota',
               default=constants.QUOTA_UNLIMITED,
               help=_('Default per project member quota.')),
    cfg.IntOpt('default_pool_quota',
               default=constants.QUOTA_UNLIMITED,
               help=_('Default per project pool quota.')),
    cfg.IntOpt('default_health_monitor_quota',
               default=constants.QUOTA_UNLIMITED,
               help=_('Default per project health monitor quota.')),
]


# Register the configuration options
cfg.CONF.register_opts(core_opts)
cfg.CONF.register_opts(amphora_agent_opts, group='amphora_agent')
cfg.CONF.register_opts(networking_opts, group='networking')
cfg.CONF.register_opts(oslo_messaging_opts, group='oslo_messaging')
cfg.CONF.register_opts(haproxy_amphora_opts, group='haproxy_amphora')
cfg.CONF.register_opts(controller_worker_opts, group='controller_worker')
cfg.CONF.register_opts(keepalived_vrrp_opts, group='keepalived_vrrp')
cfg.CONF.register_opts(task_flow_opts, group='task_flow')
cfg.CONF.register_opts(oslo_messaging_opts, group='oslo_messaging')
cfg.CONF.register_opts(house_keeping_opts, group='house_keeping')
cfg.CONF.register_opts(anchor_opts, group='anchor')
cfg.CONF.register_cli_opts(core_cli_opts)
cfg.CONF.register_opts(certificate_opts, group='certificates')
cfg.CONF.register_cli_opts(healthmanager_opts, group='health_manager')
cfg.CONF.register_opts(nova_opts, group='nova')
cfg.CONF.register_opts(glance_opts, group='glance')
cfg.CONF.register_opts(neutron_opts, group='neutron')
cfg.CONF.register_opts(quota_opts, group='quotas')


# Ensure that the control exchange is set correctly
messaging.set_transport_defaults(control_exchange='octavia')
_SQL_CONNECTION_DEFAULT = 'sqlite://'
# Update the default QueuePool parameters. These can be tweaked by the
# configuration variables - max_pool_size, max_overflow and pool_timeout
db_options.set_defaults(cfg.CONF, connection=_SQL_CONNECTION_DEFAULT,
                        max_pool_size=10, max_overflow=20, pool_timeout=10)

logging.register_options(cfg.CONF)

ks_loading.register_auth_conf_options(cfg.CONF, constants.SERVICE_AUTH)
ks_loading.register_session_conf_options(cfg.CONF, constants.SERVICE_AUTH)


def init(args, **kwargs):
    cfg.CONF(args=args, project='octavia',
             version='%%prog %s' % version.version_info.release_string(),
             **kwargs)


def setup_logging(conf):
    """Sets up the logging options for a log with supplied name.

    :param conf: a cfg.ConfOpts object
    """
    product_name = "octavia"
    logging.setup(conf, product_name)
    LOG.info(_LI("Logging enabled!"))
