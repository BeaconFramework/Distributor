# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2015 Rackspace
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

import mock
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from oslo_utils import uuidutils
import requests
import requests_mock
import six

from octavia.amphorae.driver_exceptions import exceptions as driver_except
from octavia.amphorae.drivers.haproxy import exceptions as exc
from octavia.amphorae.drivers.haproxy import rest_api_driver as driver
from octavia.db import models
from octavia.network import data_models as network_models
from octavia.tests.unit import base as base
from octavia.tests.unit.common.sample_configs import sample_certs
from octavia.tests.unit.common.sample_configs import sample_configs

FAKE_CIDR = '198.51.100.0/24'
FAKE_GATEWAY = '192.51.100.1'
FAKE_IP = '192.0.2.10'
FAKE_IPV6 = '2001:db8::cafe'
FAKE_IPV6_LLA = 'fe80::00ff:fe00:cafe'
FAKE_PEM_FILENAME = "file_name"
FAKE_UUID_1 = uuidutils.generate_uuid()
FAKE_VRRP_IP = '10.1.0.1'
FAKE_MAC_ADDRESS = '123'
FAKE_MTU = 1450


class TestHaproxyAmphoraLoadBalancerDriverTest(base.TestCase):

    def setUp(self):
        super(TestHaproxyAmphoraLoadBalancerDriverTest, self).setUp()

        DEST1 = '198.51.100.0/24'
        DEST2 = '203.0.113.0/24'
        NEXTHOP = '192.0.2.1'

        self.driver = driver.HaproxyAmphoraLoadBalancerDriver()

        self.driver.cert_manager = mock.MagicMock()
        self.driver.cert_parser = mock.MagicMock()
        self.driver.client = mock.MagicMock()
        self.driver.jinja = mock.MagicMock()

        # Build sample Listener and VIP configs
        self.sl = sample_configs.sample_listener_tuple(tls=True, sni=True)
        self.amp = self.sl.load_balancer.amphorae[0]
        self.sv = sample_configs.sample_vip_tuple()
        self.lb = self.sl.load_balancer
        self.fixed_ip = mock.MagicMock()
        self.fixed_ip.ip_address = '198.51.100.5'
        self.fixed_ip.subnet.cidr = '198.51.100.0/24'
        self.network = network_models.Network(mtu=FAKE_MTU)
        self.port = network_models.Port(mac_address=FAKE_MAC_ADDRESS,
                                        fixed_ips=[self.fixed_ip],
                                        network=self.network)

        self.host_routes = [network_models.HostRoute(destination=DEST1,
                                                     nexthop=NEXTHOP),
                            network_models.HostRoute(destination=DEST2,
                                                     nexthop=NEXTHOP)]
        host_routes_data = [{'destination': DEST1, 'nexthop': NEXTHOP},
                            {'destination': DEST2, 'nexthop': NEXTHOP}]
        self.subnet_info = {'subnet_cidr': FAKE_CIDR,
                            'gateway': FAKE_GATEWAY,
                            'mac_address': FAKE_MAC_ADDRESS,
                            'vrrp_ip': self.amp.vrrp_ip,
                            'mtu': FAKE_MTU,
                            'host_routes': host_routes_data}

    @mock.patch('octavia.common.tls_utils.cert_parser.load_certificates_data')
    @mock.patch('octavia.common.tls_utils.cert_parser.get_host_names')
    def test_update(self, mock_cert, mock_load_crt):
        mock_cert.return_value = {'cn': sample_certs.X509_CERT_CN}
        sconts = []
        for sni_container in self.sl.sni_containers:
            sconts.append(sni_container.tls_container)
        mock_load_crt.return_value = {
            'tls_cert': self.sl.default_tls_container,
            'sni_certs': sconts
        }
        self.driver.client.get_cert_md5sum.side_effect = [
            exc.NotFound, 'Fake_MD5', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']
        self.driver.jinja.build_config.side_effect = ['fake_config']
        self.driver.client.get_listener_status.side_effect = [
            dict(status='ACTIVE')]

        # Execute driver method
        self.driver.update(self.sl, self.sv)

        # verify result
        # this is called 3 times
        self.driver.client.get_cert_md5sum.assert_called_with(
            self.amp, self.sl.id, sample_certs.X509_CERT_CN_3 + '.pem')
        # this is called three times (last MD5 matches)
        fp1 = b'\n'.join([sample_certs.X509_CERT,
                          sample_certs.X509_CERT_KEY,
                          sample_certs.X509_IMDS]) + b'\n'
        fp2 = b'\n'.join([sample_certs.X509_CERT_2,
                          sample_certs.X509_CERT_KEY_2,
                          sample_certs.X509_IMDS]) + b'\n'
        fp3 = b'\n'.join([sample_certs.X509_CERT_3,
                          sample_certs.X509_CERT_KEY_3,
                          sample_certs.X509_IMDS]) + b'\n'
        ucp_calls = [
            mock.call(self.amp, self.sl.id,
                      sample_certs.X509_CERT_CN + '.pem', fp1),
            mock.call(self.amp, self.sl.id,
                      sample_certs.X509_CERT_CN_2 + '.pem', fp2),
            mock.call(self.amp, self.sl.id,
                      sample_certs.X509_CERT_CN_3 + '.pem', fp3)
        ]
        self.driver.client.upload_cert_pem.assert_has_calls(ucp_calls,
                                                            any_order=True)
        self.assertEqual(3, self.driver.client.upload_cert_pem.call_count)
        # upload only one config file
        self.driver.client.upload_config.assert_called_once_with(
            self.amp, self.sl.id, 'fake_config')
        # start should be called once
        self.driver.client.reload_listener.assert_called_once_with(
            self.amp, self.sl.id)

    def test_upload_cert_amp(self):
        self.driver.upload_cert_amp(self.amp, six.b('test'))
        self.driver.client.update_cert_for_rotation.assert_called_once_with(
            self.amp, six.b('test'))

    def test_stop(self):
        # Execute driver method
        self.driver.stop(self.sl, self.sv)
        self.driver.client.stop_listener.assert_called_once_with(
            self.amp, self.sl.id)

    def test_start(self):
        # Execute driver method
        self.driver.start(self.sl, self.sv)
        self.driver.client.start_listener.assert_called_once_with(
            self.amp, self.sl.id)

    def test_delete(self):
        # Execute driver method
        self.driver.delete(self.sl, self.sv)
        self.driver.client.delete_listener.assert_called_once_with(
            self.amp, self.sl.id)

    def test_get_info(self):
        pass

    def test_get_diagnostics(self):
        pass

    def test_finalize_amphora(self):
        pass

    def test_post_vip_plug(self):
        amphorae_network_config = mock.MagicMock()
        amphorae_network_config.get().vip_subnet.cidr = FAKE_CIDR
        amphorae_network_config.get().vip_subnet.gateway_ip = FAKE_GATEWAY
        amphorae_network_config.get().vip_subnet.host_routes = self.host_routes
        amphorae_network_config.get().vrrp_port = self.port
        self.driver.post_vip_plug(self.amp, self.lb, amphorae_network_config)
        self.driver.client.plug_vip.assert_called_once_with(
            self.amp, self.lb.vip.ip_address, self.subnet_info)

    def test_post_network_plug(self):
        # Test dhcp path
        port = network_models.Port(mac_address=FAKE_MAC_ADDRESS,
                                   fixed_ips=[],
                                   network=self.network)
        self.driver.post_network_plug(self.amp, port)
        self.driver.client.plug_network.assert_called_once_with(
            self.amp, dict(mac_address=FAKE_MAC_ADDRESS,
                           fixed_ips=[],
                           mtu=FAKE_MTU))

        self.driver.client.plug_network.reset_mock()

        # Test fixed IP path
        self.driver.post_network_plug(self.amp, self.port)
        self.driver.client.plug_network.assert_called_once_with(
            self.amp, dict(mac_address=FAKE_MAC_ADDRESS,
                           fixed_ips=[dict(ip_address='198.51.100.5',
                                           subnet_cidr='198.51.100.0/24',
                                           host_routes=[])],
                           mtu=FAKE_MTU))

    def test_post_network_plug_with_host_routes(self):
        SUBNET_ID = 'SUBNET_ID'
        FIXED_IP1 = '192.0.2.2'
        FIXED_IP2 = '192.0.2.3'
        SUBNET_CIDR = '192.0.2.0/24'
        DEST1 = '198.51.100.0/24'
        DEST2 = '203.0.113.0/24'
        NEXTHOP = '192.0.2.1'
        host_routes = [network_models.HostRoute(destination=DEST1,
                                                nexthop=NEXTHOP),
                       network_models.HostRoute(destination=DEST2,
                                                nexthop=NEXTHOP)]
        subnet = network_models.Subnet(id=SUBNET_ID, cidr=SUBNET_CIDR,
                                       ip_version=4, host_routes=host_routes)
        fixed_ips = [
            network_models.FixedIP(subnet_id=subnet.id, ip_address=FIXED_IP1,
                                   subnet=subnet),
            network_models.FixedIP(subnet_id=subnet.id, ip_address=FIXED_IP2,
                                   subnet=subnet)
        ]
        port = network_models.Port(mac_address=FAKE_MAC_ADDRESS,
                                   fixed_ips=fixed_ips,
                                   network=self.network)
        self.driver.post_network_plug(self.amp, port)
        expected_fixed_ips = [
            {'ip_address': FIXED_IP1, 'subnet_cidr': SUBNET_CIDR,
             'host_routes': [{'destination': DEST1, 'nexthop': NEXTHOP},
                             {'destination': DEST2, 'nexthop': NEXTHOP}]},
            {'ip_address': FIXED_IP2, 'subnet_cidr': SUBNET_CIDR,
             'host_routes': [{'destination': DEST1, 'nexthop': NEXTHOP},
                             {'destination': DEST2, 'nexthop': NEXTHOP}]}
        ]
        self.driver.client.plug_network.assert_called_once_with(
            self.amp, dict(mac_address=FAKE_MAC_ADDRESS,
                           fixed_ips=expected_fixed_ips,
                           mtu=FAKE_MTU))

    def test_get_vrrp_interface(self):
        self.driver.get_vrrp_interface(self.amp)
        self.driver.client.get_interface.assert_called_once_with(
            self.amp, self.amp.vrrp_ip)


class TestAmphoraAPIClientTest(base.TestCase):

    def setUp(self):
        super(TestAmphoraAPIClientTest, self).setUp()
        self.driver = driver.AmphoraAPIClient()
        self.base_url = "https://127.0.0.1:9443/0.5"
        self.amp = models.Amphora(lb_network_ip='127.0.0.1', compute_id='123')
        self.port_info = dict(mac_address=FAKE_MAC_ADDRESS)
        # Override with much lower values for testing purposes..
        conf = oslo_fixture.Config(cfg.CONF)
        conf.config(group="haproxy_amphora", connection_max_retries=2)

        self.subnet_info = {'subnet_cidr': FAKE_CIDR,
                            'gateway': FAKE_GATEWAY,
                            'mac_address': FAKE_MAC_ADDRESS,
                            'vrrp_ip': self.amp.vrrp_ip}
        patcher = mock.patch('time.sleep').start()
        self.addCleanup(patcher.stop)

    def test_base_url(self):
        url = self.driver._base_url(FAKE_IP)
        self.assertEqual('https://192.0.2.10:9443/0.5/', url)
        url = self.driver._base_url(FAKE_IPV6)
        self.assertEqual('https://[2001:db8::cafe]:9443/0.5/', url)
        url = self.driver._base_url(FAKE_IPV6_LLA)
        self.assertEqual('https://[fe80::00ff:fe00:cafe%o-hm0]:9443/0.5/', url)

    @mock.patch('requests.Session.get', side_effect=requests.ConnectionError)
    @mock.patch('octavia.amphorae.drivers.haproxy.rest_api_driver.time.sleep')
    def test_request(self, mock_sleep, mock_get):
        self.assertRaises(driver_except.TimeOutException,
                          self.driver.request,
                          'get', self.amp, 'unavailableURL')

    @requests_mock.mock()
    def test_get_info(self, m):
        info = {"hostname": "some_hostname", "version": "some_version",
                "api_version": "0.5", "uuid": FAKE_UUID_1}
        m.get("{base}/info".format(base=self.base_url),
              json=info)
        information = self.driver.get_info(self.amp)
        self.assertEqual(info, information)

    @requests_mock.mock()
    def test_get_info_unauthorized(self, m):
        m.get("{base}/info".format(base=self.base_url),
              status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.get_info, self.amp)

    @requests_mock.mock()
    def test_get_info_missing(self, m):
        m.get("{base}/info".format(base=self.base_url),
              status_code=404)
        self.assertRaises(exc.NotFound, self.driver.get_info, self.amp)

    @requests_mock.mock()
    def test_get_info_server_error(self, m):
        m.get("{base}/info".format(base=self.base_url),
              status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.get_info,
                          self.amp)

    @requests_mock.mock()
    def test_get_info_service_unavailable(self, m):
        m.get("{base}/info".format(base=self.base_url),
              status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.get_info,
                          self.amp)

    @requests_mock.mock()
    def test_get_details(self, m):
        details = {"hostname": "some_hostname", "version": "some_version",
                   "api_version": "0.5", "uuid": FAKE_UUID_1,
                   "network_tx": "some_tx", "network_rx": "some_rx",
                   "active": True, "haproxy_count": 10}
        m.get("{base}/details".format(base=self.base_url),
              json=details)
        amp_details = self.driver.get_details(self.amp)
        self.assertEqual(details, amp_details)

    @requests_mock.mock()
    def test_get_details_unauthorized(self, m):
        m.get("{base}/details".format(base=self.base_url),
              status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.get_details, self.amp)

    @requests_mock.mock()
    def test_get_details_missing(self, m):
        m.get("{base}/details".format(base=self.base_url),
              status_code=404)
        self.assertRaises(exc.NotFound, self.driver.get_details, self.amp)

    @requests_mock.mock()
    def test_get_details_server_error(self, m):
        m.get("{base}/details".format(base=self.base_url),
              status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.get_details,
                          self.amp)

    @requests_mock.mock()
    def test_get_details_service_unavailable(self, m):
        m.get("{base}/details".format(base=self.base_url),
              status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.get_details,
                          self.amp)

    @requests_mock.mock()
    def test_get_all_listeners(self, m):
        listeners = [{"status": "ONLINE", "provisioning_status": "ACTIVE",
                      "type": "PASSIVE", "uuid": FAKE_UUID_1}]
        m.get("{base}/listeners".format(base=self.base_url),
              json=listeners)
        all_listeners = self.driver.get_all_listeners(self.amp)
        self.assertEqual(listeners, all_listeners)

    @requests_mock.mock()
    def test_get_all_listeners_unauthorized(self, m):
        m.get("{base}/listeners".format(base=self.base_url),
              status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.get_all_listeners,
                          self.amp)

    @requests_mock.mock()
    def test_get_all_listeners_missing(self, m):
        m.get("{base}/listeners".format(base=self.base_url),
              status_code=404)
        self.assertRaises(exc.NotFound, self.driver.get_all_listeners,
                          self.amp)

    @requests_mock.mock()
    def test_get_all_listeners_server_error(self, m):
        m.get("{base}/listeners".format(base=self.base_url),
              status_code=500)
        self.assertRaises(exc.InternalServerError,
                          self.driver.get_all_listeners, self.amp)

    @requests_mock.mock()
    def test_get_all_listeners_service_unavailable(self, m):
        m.get("{base}/listeners".format(base=self.base_url),
              status_code=503)
        self.assertRaises(exc.ServiceUnavailable,
                          self.driver.get_all_listeners, self.amp)

    @requests_mock.mock()
    def test_get_listener_status(self, m):
        listener = {"status": "ONLINE", "provisioning_status": "ACTIVE",
                    "type": "PASSIVE", "uuid": FAKE_UUID_1}
        m.get("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            json=listener)
        status = self.driver.get_listener_status(self.amp, FAKE_UUID_1)
        self.assertEqual(listener, status)

    @requests_mock.mock()
    def test_get_listener_status_unauthorized(self, m):
        m.get("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=401)
        self.assertRaises(exc.Unauthorized,
                          self.driver.get_listener_status, self.amp,
                          FAKE_UUID_1)

    @requests_mock.mock()
    def test_get_listener_status_missing(self, m):
        m.get("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=404)
        self.assertRaises(exc.NotFound,
                          self.driver.get_listener_status, self.amp,
                          FAKE_UUID_1)

    @requests_mock.mock()
    def test_get_listener_status_server_error(self, m):
        m.get("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=500)
        self.assertRaises(exc.InternalServerError,
                          self.driver.get_listener_status, self.amp,
                          FAKE_UUID_1)

    @requests_mock.mock()
    def test_get_listener_status_service_unavailable(self, m):
        m.get("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=503)
        self.assertRaises(exc.ServiceUnavailable,
                          self.driver.get_listener_status, self.amp,
                          FAKE_UUID_1)

    @requests_mock.mock()
    def test_start_listener(self, m):
        m.put("{base}/listeners/{listener_id}/start".format(
            base=self.base_url, listener_id=FAKE_UUID_1))
        self.driver.start_listener(self.amp, FAKE_UUID_1)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_start_listener_missing(self, m):
        m.put("{base}/listeners/{listener_id}/start".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=404)
        self.assertRaises(exc.NotFound, self.driver.start_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_start_listener_unauthorized(self, m):
        m.put("{base}/listeners/{listener_id}/start".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.start_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_start_listener_server_error(self, m):
        m.put("{base}/listeners/{listener_id}/start".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.start_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_start_listener_service_unavailable(self, m):
        m.put("{base}/listeners/{listener_id}/start".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.start_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_stop_listener(self, m):
        m.put("{base}/listeners/{listener_id}/stop".format(
            base=self.base_url, listener_id=FAKE_UUID_1))
        self.driver.stop_listener(self.amp, FAKE_UUID_1)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_stop_listener_missing(self, m):
        m.put("{base}/listeners/{listener_id}/stop".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=404)
        self.assertRaises(exc.NotFound, self.driver.stop_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_stop_listener_unauthorized(self, m):
        m.put("{base}/listeners/{listener_id}/stop".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.stop_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_stop_listener_server_error(self, m):
        m.put("{base}/listeners/{listener_id}/stop".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.stop_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_stop_listener_service_unavailable(self, m):
        m.put("{base}/listeners/{listener_id}/stop".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.stop_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_delete_listener(self, m):
        m.delete("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1), json={})
        self.driver.delete_listener(self.amp, FAKE_UUID_1)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_delete_listener_missing(self, m):
        m.delete("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=404)
        self.assertRaises(exc.NotFound, self.driver.delete_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_delete_listener_unauthorized(self, m):
        m.delete("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.delete_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_delete_listener_server_error(self, m):
        m.delete("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.delete_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_delete_listener_service_unavailable(self, m):
        m.delete("{base}/listeners/{listener_id}".format(
            base=self.base_url, listener_id=FAKE_UUID_1),
            status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.delete_listener,
                          self.amp, FAKE_UUID_1)

    @requests_mock.mock()
    def test_upload_cert_pem(self, m):
        m.put("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME))
        self.driver.upload_cert_pem(self.amp, FAKE_UUID_1,
                                    FAKE_PEM_FILENAME,
                                    "some_file")
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_upload_invalid_cert_pem(self, m):
        m.put("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=400)
        self.assertRaises(exc.InvalidRequest, self.driver.upload_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME,
                          "some_file")

    @requests_mock.mock()
    def test_upload_cert_pem_unauthorized(self, m):
        m.put("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.upload_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME,
                          "some_file")

    @requests_mock.mock()
    def test_upload_cert_pem_server_error(self, m):
        m.put("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.upload_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME,
                          "some_file")

    @requests_mock.mock()
    def test_upload_cert_pem_service_unavailable(self, m):
        m.put("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.upload_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME,
                          "some_file")

    @requests_mock.mock()
    def test_update_cert_for_rotation(self, m):
        m.put("{base}/certificate".format(base=self.base_url))
        resp_body = self.driver.update_cert_for_rotation(self.amp,
                                                         "some_file")
        self.assertEqual(200, resp_body.status_code)

    @requests_mock.mock()
    def test_update_invalid_cert_for_rotation(self, m):
        m.put("{base}/certificate".format(base=self.base_url), status_code=400)
        self.assertRaises(exc.InvalidRequest,
                          self.driver.update_cert_for_rotation, self.amp,
                          "some_file")

    @requests_mock.mock()
    def test_update_cert_for_rotation_unauthorized(self, m):
        m.put("{base}/certificate".format(base=self.base_url), status_code=401)
        self.assertRaises(exc.Unauthorized,
                          self.driver.update_cert_for_rotation, self.amp,
                          "some_file")

    @requests_mock.mock()
    def test_update_cert_for_rotation_error(self, m):
        m.put("{base}/certificate".format(base=self.base_url), status_code=500)
        self.assertRaises(exc.InternalServerError,
                          self.driver.update_cert_for_rotation, self.amp,
                          "some_file")

    @requests_mock.mock()
    def test_update_cert_for_rotation_unavailable(self, m):
        m.put("{base}/certificate".format(base=self.base_url), status_code=503)
        self.assertRaises(exc.ServiceUnavailable,
                          self.driver.update_cert_for_rotation, self.amp,
                          "some_file")

    @requests_mock.mock()
    def test_get_cert_5sum(self, m):
        md5sum = {"md5sum": "some_real_sum"}
        m.get("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), json=md5sum)
        sum_test = self.driver.get_cert_md5sum(self.amp, FAKE_UUID_1,
                                               FAKE_PEM_FILENAME)
        self.assertIsNotNone(sum_test)

    @requests_mock.mock()
    def test_get_cert_5sum_missing(self, m):
        m.get("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=404)
        self.assertRaises(exc.NotFound, self.driver.get_cert_md5sum,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_get_cert_5sum_unauthorized(self, m):
        m.get("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.get_cert_md5sum,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_get_cert_5sum_server_error(self, m):
        m.get("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.get_cert_md5sum,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_get_cert_5sum_service_unavailable(self, m):
        m.get("{base}/listeners/{listener_id}/certificates/{filename}".format(
            base=self.base_url, listener_id=FAKE_UUID_1,
            filename=FAKE_PEM_FILENAME), status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.get_cert_md5sum,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_delete_cert_pem(self, m):
        m.delete(
            "{base}/listeners/{listener_id}/certificates/{filename}".format(
                base=self.base_url, listener_id=FAKE_UUID_1,
                filename=FAKE_PEM_FILENAME))
        self.driver.delete_cert_pem(self.amp, FAKE_UUID_1,
                                    FAKE_PEM_FILENAME)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_delete_cert_pem_missing(self, m):
        m.delete(
            "{base}/listeners/{listener_id}/certificates/{filename}".format(
                base=self.base_url, listener_id=FAKE_UUID_1,
                filename=FAKE_PEM_FILENAME), status_code=404)
        self.assertRaises(exc.NotFound, self.driver.delete_cert_pem, self.amp,
                          FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_delete_cert_pem_unauthorized(self, m):
        m.delete(
            "{base}/listeners/{listener_id}/certificates/{filename}".format(
                base=self.base_url, listener_id=FAKE_UUID_1,
                filename=FAKE_PEM_FILENAME), status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.delete_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_delete_cert_pem_server_error(self, m):
        m.delete(
            "{base}/listeners/{listener_id}/certificates/{filename}".format(
                base=self.base_url, listener_id=FAKE_UUID_1,
                filename=FAKE_PEM_FILENAME), status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.delete_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_delete_cert_pem_service_unavailable(self, m):
        m.delete(
            "{base}/listeners/{listener_id}/certificates/{filename}".format(
                base=self.base_url, listener_id=FAKE_UUID_1,
                filename=FAKE_PEM_FILENAME), status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.delete_cert_pem,
                          self.amp, FAKE_UUID_1, FAKE_PEM_FILENAME)

    @requests_mock.mock()
    def test_upload_config(self, m):
        config = {"name": "fake_config"}
        m.put(
            "{base}/listeners/{"
            "amphora_id}/{listener_id}/haproxy".format(
                amphora_id=self.amp.id, base=self.base_url,
                listener_id=FAKE_UUID_1),
            json=config)
        self.driver.upload_config(self.amp, FAKE_UUID_1,
                                  config)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_upload_invalid_config(self, m):
        config = '{"name": "bad_config"}'
        m.put(
            "{base}/listeners/{"
            "amphora_id}/{listener_id}/haproxy".format(
                amphora_id=self.amp.id, base=self.base_url,
                listener_id=FAKE_UUID_1),
            status_code=400)
        self.assertRaises(exc.InvalidRequest, self.driver.upload_config,
                          self.amp, FAKE_UUID_1, config)

    @requests_mock.mock()
    def test_upload_config_unauthorized(self, m):
        config = '{"name": "bad_config"}'
        m.put(
            "{base}/listeners/{"
            "amphora_id}/{listener_id}/haproxy".format(
                amphora_id=self.amp.id, base=self.base_url,
                listener_id=FAKE_UUID_1),
            status_code=401)
        self.assertRaises(exc.Unauthorized, self.driver.upload_config,
                          self.amp, FAKE_UUID_1, config)

    @requests_mock.mock()
    def test_upload_config_server_error(self, m):
        config = '{"name": "bad_config"}'
        m.put(
            "{base}/listeners/{"
            "amphora_id}/{listener_id}/haproxy".format(
                amphora_id=self.amp.id, base=self.base_url,
                listener_id=FAKE_UUID_1),
            status_code=500)
        self.assertRaises(exc.InternalServerError, self.driver.upload_config,
                          self.amp, FAKE_UUID_1, config)

    @requests_mock.mock()
    def test_upload_config_service_unavailable(self, m):
        config = '{"name": "bad_config"}'
        m.put(
            "{base}/listeners/{"
            "amphora_id}/{listener_id}/haproxy".format(
                amphora_id=self.amp.id, base=self.base_url,
                listener_id=FAKE_UUID_1),
            status_code=503)
        self.assertRaises(exc.ServiceUnavailable, self.driver.upload_config,
                          self.amp, FAKE_UUID_1, config)

    @requests_mock.mock()
    def test_plug_vip(self, m):
        m.post("{base}/plug/vip/{vip}".format(
            base=self.base_url, vip=FAKE_IP)
        )
        self.driver.plug_vip(self.amp, FAKE_IP, self.subnet_info)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_plug_network(self, m):
        m.post("{base}/plug/network".format(
            base=self.base_url)
        )
        self.driver.plug_network(self.amp, self.port_info)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_upload_vrrp_config(self, m):
        config = '{"name": "bad_config"}'
        m.put("{base}/vrrp/upload".format(
            base=self.base_url)
        )
        self.driver.upload_vrrp_config(self.amp, config)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_vrrp_action(self, m):
        action = 'start'
        m.put("{base}/vrrp/{action}".format(base=self.base_url, action=action))
        self.driver._vrrp_action(action, self.amp)
        self.assertTrue(m.called)

    @requests_mock.mock()
    def test_get_interface(self, m):
        interface = [{"interface": "eth1"}]
        ip_addr = '192.51.100.1'
        m.get("{base}/interface/{ip_addr}".format(base=self.base_url,
                                                  ip_addr=ip_addr),
              json=interface)
        self.driver.get_interface(self.amp, ip_addr)
        self.assertTrue(m.called)

        m.register_uri('GET',
                       self.base_url + '/interface/' + ip_addr,
                       status_code=500, reason='FAIL', json='FAIL')
        self.assertRaises(exc.InternalServerError,
                          self.driver.get_interface,
                          self.amp, ip_addr)
