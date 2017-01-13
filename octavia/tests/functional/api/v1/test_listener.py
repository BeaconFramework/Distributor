#    Copyright 2014 Rackspace
#    Copyright 2016 Blue Box, an IBM Company
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

from oslo_utils import uuidutils

from octavia.common import constants
from octavia.tests.functional.api.v1 import base


class TestListener(base.BaseAPITest):

    def setUp(self):
        super(TestListener, self).setUp()
        self.lb = self.create_load_balancer({})
        self.set_lb_status(self.lb.get('id'))
        self.listeners_path = self.LISTENERS_PATH.format(
            lb_id=self.lb.get('id'))
        self.pool = self.create_pool_sans_listener(
            self.lb.get('id'), constants.PROTOCOL_HTTP,
            constants.LB_ALGORITHM_ROUND_ROBIN)
        self.set_lb_status(self.lb.get('id'))

    def test_get_all(self):
        listener1 = self.create_listener(self.lb.get('id'),
                                         constants.PROTOCOL_HTTP, 80)
        self.set_lb_status(self.lb.get('id'))
        listener2 = self.create_listener(self.lb.get('id'),
                                         constants.PROTOCOL_HTTP, 81)
        self.set_lb_status(self.lb.get('id'))
        listener3 = self.create_listener(self.lb.get('id'),
                                         constants.PROTOCOL_HTTP, 82)
        self.set_lb_status(self.lb.get('id'))
        response = self.get(self.listeners_path)
        api_listeners = response.json
        self.assertEqual(3, len(api_listeners))
        listener1['provisioning_status'] = constants.ACTIVE
        listener1['operating_status'] = constants.ONLINE
        listener2['provisioning_status'] = constants.ACTIVE
        listener2['operating_status'] = constants.ONLINE
        listener3['provisioning_status'] = constants.ACTIVE
        listener3['operating_status'] = constants.ONLINE
        for listener in api_listeners:
            del listener['updated_at']

        self.assertIsNone(listener1.pop('updated_at'))
        self.assertIsNone(listener2.pop('updated_at'))
        self.assertIsNone(listener3.pop('updated_at'))
        self.assertIn(listener1, api_listeners)
        self.assertIn(listener2, api_listeners)
        self.assertIn(listener3, api_listeners)

    def test_get_all_bad_lb_id(self):
        path = self.LISTENERS_PATH.format(lb_id='SEAN-CONNERY')
        self.get(path, status=404)

    def test_get(self):
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_HTTP, 80)
        listener_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))
        response = self.get(listener_path)
        api_lb = response.json
        expected = {'name': None, 'description': None, 'enabled': True,
                    'operating_status': constants.OFFLINE,
                    'provisioning_status': constants.PENDING_CREATE,
                    'connection_limit': None}
        listener.update(expected)
        self.assertEqual(listener, api_lb)

    def test_get_bad_listener_id(self):
        listener_path = self.LISTENER_PATH.format(lb_id=self.lb.get('id'),
                                                  listener_id='SEAN-CONNERY')
        self.get(listener_path, status=404)

    def test_create(self, **optionals):
        sni1 = uuidutils.generate_uuid()
        sni2 = uuidutils.generate_uuid()
        lb_listener = {'name': 'listener1', 'default_pool_id': None,
                       'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80, 'connection_limit': 10,
                       'tls_certificate_id': uuidutils.generate_uuid(),
                       'sni_containers': [sni1, sni2],
                       'insert_headers': {},
                       'project_id': uuidutils.generate_uuid()}
        lb_listener.update(optionals)
        response = self.post(self.listeners_path, lb_listener)
        listener_api = response.json
        extra_expects = {'provisioning_status': constants.PENDING_CREATE,
                         'operating_status': constants.OFFLINE}
        lb_listener.update(extra_expects)
        self.assertTrue(uuidutils.is_uuid_like(listener_api.get('id')))
        for key, value in optionals.items():
            self.assertEqual(value, lb_listener.get(key))
        lb_listener['id'] = listener_api.get('id')
        lb_listener.pop('sni_containers')
        sni_ex = [sni1, sni2]
        sni_resp = listener_api.pop('sni_containers')
        self.assertEqual(2, len(sni_resp))
        for sni in sni_resp:
            self.assertIn(sni, sni_ex)
        self.assertIsNotNone(listener_api.pop('created_at'))
        self.assertIsNone(listener_api.pop('updated_at'))
        self.assertEqual(lb_listener, listener_api)
        self.assert_correct_lb_status(self.lb.get('id'),
                                      constants.PENDING_UPDATE,
                                      constants.ONLINE)
        self.assert_final_lb_statuses(self.lb.get('id'))
        self.assert_final_listener_statuses(self.lb.get('id'),
                                            listener_api.get('id'))

    def test_create_with_default_pool_id(self):
        lb_listener = {'name': 'listener1',
                       'default_pool_id': self.pool.get('id'),
                       'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80,
                       'project_id': self.project_id}
        response = self.post(self.listeners_path, lb_listener)
        api_listener = response.json
        self.assertEqual(api_listener.get('default_pool_id'),
                         self.pool.get('id'))

    def test_create_with_bad_default_pool_id(self):
        lb_listener = {'name': 'listener1',
                       'default_pool_id': uuidutils.generate_uuid(),
                       'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80,
                       'project_id': self.project_id}
        self.post(self.listeners_path, lb_listener, status=404)

    def test_create_with_id(self):
        self.test_create(id=uuidutils.generate_uuid())

    def test_create_with_shared_default_pool_id(self):
        lb_listener1 = {'name': 'listener1',
                        'default_pool_id': self.pool.get('id'),
                        'description': 'desc1',
                        'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                        'protocol_port': 80,
                        'project_id': self.project_id}
        lb_listener2 = {'name': 'listener2',
                        'default_pool_id': self.pool.get('id'),
                        'description': 'desc2',
                        'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                        'protocol_port': 81,
                        'project_id': self.project_id}
        listener1 = self.post(self.listeners_path, lb_listener1).json
        self.set_lb_status(self.lb.get('id'), constants.ACTIVE)
        listener2 = self.post(self.listeners_path, lb_listener2).json
        self.assertEqual(listener1['default_pool_id'], self.pool.get('id'))
        self.assertEqual(listener1['default_pool_id'],
                         listener2['default_pool_id'])

    def test_create_with_project_id(self):
        self.test_create(project_id=uuidutils.generate_uuid())

    def test_create_with_duplicate_id(self):
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_HTTP,
                                        protocol_port=80)
        self.set_lb_status(self.lb.get('id'), constants.ACTIVE)
        path = self.LISTENERS_PATH.format(lb_id=self.lb.get('id'))
        body = {'id': listener.get('id'), 'protocol': constants.PROTOCOL_HTTP,
                'protocol_port': 81}
        self.post(path, body, status=409, expect_errors=True)

    def test_create_defaults(self):
        defaults = {'name': None, 'default_pool_id': None,
                    'description': None, 'enabled': True,
                    'connection_limit': None, 'tls_certificate_id': None,
                    'sni_containers': [], 'insert_headers': {}}
        lb_listener = {'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80,
                       'project_id': self.project_id}
        response = self.post(self.listeners_path, lb_listener)
        listener_api = response.json
        extra_expects = {'provisioning_status': constants.PENDING_CREATE,
                         'operating_status': constants.OFFLINE}
        lb_listener.update(extra_expects)
        lb_listener.update(defaults)
        self.assertTrue(uuidutils.is_uuid_like(listener_api.get('id')))
        lb_listener['id'] = listener_api.get('id')
        self.assertIsNotNone(listener_api.pop('created_at'))
        self.assertIsNone(listener_api.pop('updated_at'))
        self.assertEqual(lb_listener, listener_api)
        self.assert_correct_lb_status(self.lb.get('id'),
                                      constants.PENDING_UPDATE,
                                      constants.ONLINE)
        self.assert_final_lb_statuses(self.lb.get('id'))
        self.assert_final_listener_statuses(self.lb.get('id'),
                                            listener_api.get('id'))

    def test_create_over_quota(self):
        lb_listener = {'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80,
                       'project_id': self.project_id}
        self.check_quota_met_true_mock.start()
        self.post(self.listeners_path, lb_listener, status=403)

    def test_update(self):
        tls_uuid = uuidutils.generate_uuid()
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_TCP, 80,
                                        name='listener1', description='desc1',
                                        enabled=False, connection_limit=10,
                                        tls_certificate_id=tls_uuid,
                                        default_pool_id=None)
        self.set_lb_status(self.lb.get('id'))
        new_listener = {'name': 'listener2', 'enabled': True,
                        'default_pool_id': self.pool.get('id')}
        listener_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))
        api_listener = self.put(listener_path, new_listener).json
        update_expect = {'name': 'listener2', 'enabled': True,
                         'default_pool_id': self.pool.get('id'),
                         'provisioning_status': constants.PENDING_UPDATE,
                         'operating_status': constants.ONLINE}
        listener.update(update_expect)
        self.assertEqual(listener.pop('created_at'),
                         api_listener.pop('created_at'))
        self.assertNotEqual(listener.pop('updated_at'),
                            api_listener.pop('updated_at'))
        self.assertNotEqual(listener, api_listener)
        self.assert_correct_lb_status(self.lb.get('id'),
                                      constants.PENDING_UPDATE,
                                      constants.ONLINE)
        self.assert_final_listener_statuses(self.lb.get('id'),
                                            api_listener.get('id'))

    def test_update_bad_listener_id(self):
        listener_path = self.LISTENER_PATH.format(lb_id=self.lb.get('id'),
                                                  listener_id='SEAN-CONNERY')
        self.put(listener_path, body={}, status=404)

    def test_update_with_bad_default_pool_id(self):
        bad_pool_uuid = uuidutils.generate_uuid()
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_TCP, 80,
                                        name='listener1', description='desc1',
                                        enabled=False, connection_limit=10,
                                        default_pool_id=self.pool.get('id'))
        self.set_lb_status(self.lb.get('id'))
        new_listener = {'name': 'listener2', 'enabled': True,
                        'default_pool_id': bad_pool_uuid}
        listener_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))
        self.put(listener_path, new_listener, status=404)
        self.assert_correct_lb_status(self.lb.get('id'),
                                      constants.ACTIVE,
                                      constants.ONLINE)
        self.assert_final_listener_statuses(self.lb.get('id'),
                                            listener.get('id'))

    def test_create_listeners_same_port(self):
        listener1 = self.create_listener(self.lb.get('id'),
                                         constants.PROTOCOL_TCP, 80)
        self.set_lb_status(self.lb.get('id'))
        listener2_post = {'protocol': listener1.get('protocol'),
                          'protocol_port': listener1.get('protocol_port'),
                          'project_id': self.project_id}
        self.post(self.listeners_path, listener2_post, status=409)

    def test_update_listeners_same_port(self):
        self.skip('This test should pass with a validation layer.')
        listener1 = self.create_listener(self.lb.get('id'),
                                         constants.PROTOCOL_TCP, 80)
        self.set_lb_status(self.lb.get('id'))
        listener2 = self.create_listener(self.lb.get('id'),
                                         constants.PROTOCOL_TCP, 81)
        self.set_lb_status(self.lb.get('id'))
        listener2_put = {'protocol': listener1.get('protocol'),
                         'protocol_port': listener1.get('protocol_port')}
        listener2_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener2.get('id'))
        self.put(listener2_path, listener2_put, status=409)

    def test_delete(self):
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_HTTP, 80)
        self.set_lb_status(self.lb.get('id'))
        listener_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))
        self.delete(listener_path)
        response = self.get(listener_path)
        api_listener = response.json
        expected = {'name': None, 'default_pool_id': None,
                    'description': None, 'enabled': True,
                    'operating_status': constants.ONLINE,
                    'provisioning_status': constants.PENDING_DELETE,
                    'connection_limit': None}
        listener.update(expected)

        self.assertIsNone(listener.pop('updated_at'))
        self.assertIsNotNone(api_listener.pop('updated_at'))
        self.assertEqual(listener, api_listener)
        self.assert_correct_lb_status(self.lb.get('id'),
                                      constants.PENDING_UPDATE,
                                      constants.ONLINE)
        self.assert_final_lb_statuses(self.lb.get('id'))
        self.assert_final_listener_statuses(self.lb.get('id'),
                                            api_listener.get('id'),
                                            delete=True)

    def test_delete_bad_listener_id(self):
        listener_path = self.LISTENER_PATH.format(lb_id=self.lb.get('id'),
                                                  listener_id='SEAN-CONNERY')
        self.delete(listener_path, status=404)

    def test_create_listener_bad_protocol(self):
        lb_listener = {'protocol': 'SEAN_CONNERY',
                       'protocol_port': 80}
        self.post(self.listeners_path, lb_listener, status=400)

    def test_update_listener_bad_protocol(self):
        self.skip('This test should pass after a validation layer.')
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_TCP, 80)
        self.set_lb_status(self.lb.get('id'))
        new_listener = {'protocol': 'SEAN_CONNERY',
                        'protocol_port': 80}
        listener_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))
        self.put(listener_path, new_listener, status=400)

    def test_update_pending_create(self):
        lb = self.create_load_balancer({}, name='lb1', description='desc1',
                                       enabled=False)
        lb_listener = {'name': 'listener1', 'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80, 'connection_limit': 10,
                       'project_id': self.project_id}
        self.post(self.LISTENERS_PATH.format(lb_id=lb.get('id')),
                  lb_listener, status=409)

    def test_delete_pending_update(self):
        lb = self.create_load_balancer({}, name='lb1', description='desc1',
                                       enabled=False)
        self.set_lb_status(lb.get('id'))
        lb_listener = {'name': 'listener1', 'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80, 'connection_limit': 10,
                       'project_id': self.project_id}
        api_listener = self.post(
            self.LISTENERS_PATH.format(lb_id=lb.get('id')), lb_listener).json
        self.delete(self.LISTENER_PATH.format(
            lb_id=lb.get('id'), listener_id=api_listener.get('id')),
            status=409)

    def test_update_pending_update(self):
        lb = self.create_load_balancer({}, name='lb1', description='desc1',
                                       enabled=False)
        self.set_lb_status(lb.get('id'))
        lb_listener = {'name': 'listener1', 'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80, 'connection_limit': 10,
                       'project_id': self.project_id}
        api_listener = self.post(
            self.LISTENERS_PATH.format(lb_id=lb.get('id')), lb_listener).json
        self.set_lb_status(lb.get('id'))
        self.put(self.LB_PATH.format(lb_id=lb.get('id')), {'name': 'hi'})
        self.put(self.LISTENER_PATH.format(
            lb_id=lb.get('id'), listener_id=api_listener.get('id')),
            {}, status=409)

    def test_update_pending_delete(self):
        lb = self.create_load_balancer({}, name='lb1', description='desc1',
                                       enabled=False)
        self.set_lb_status(lb.get('id'))
        lb_listener = {'name': 'listener1', 'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80, 'connection_limit': 10,
                       'project_id': self.project_id}
        api_listener = self.post(
            self.LISTENERS_PATH.format(lb_id=lb.get('id')), lb_listener).json
        self.set_lb_status(lb.get('id'))
        self.delete(self.LB_PATH.format(lb_id=lb.get('id')))
        self.put(self.LISTENER_PATH.format(
            lb_id=lb.get('id'), listener_id=api_listener.get('id')),
            {}, status=409)

    def test_delete_pending_delete(self):
        lb = self.create_load_balancer({}, name='lb1', description='desc1',
                                       enabled=False)
        self.set_lb_status(lb.get('id'))
        lb_listener = {'name': 'listener1', 'description': 'desc1',
                       'enabled': False, 'protocol': constants.PROTOCOL_HTTP,
                       'protocol_port': 80, 'connection_limit': 10,
                       'project_id': self.project_id}
        api_listener = self.post(
            self.LISTENERS_PATH.format(lb_id=lb.get('id')), lb_listener).json
        self.set_lb_status(lb.get('id'))
        self.delete(self.LB_PATH.format(lb_id=lb.get('id')))
        self.delete(self.LISTENER_PATH.format(
            lb_id=lb.get('id'), listener_id=api_listener.get('id')),
            status=409)

    def test_create_with_tls_termination_data(self):
        tls = {'certificate': 'blah', 'intermediate_certificate': 'blah',
               'private_key': 'blah', 'passphrase': 'blah'}
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_HTTP, 80,
                                        tls_termination=tls)
        self.assertIsNone(listener.get('tls_termination'))
        get_listener = self.get(self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))).json
        self.assertIsNone(get_listener.get('tls_termination'))

    def test_update_with_tls_termination_data(self):
        tls = {'certificate': 'blah', 'intermediate_certificate': 'blah',
               'private_key': 'blah', 'passphrase': 'blah'}
        listener = self.create_listener(self.lb.get('id'),
                                        constants.PROTOCOL_HTTP, 80)
        self.set_lb_status(self.lb.get('id'))
        listener_path = self.LISTENER_PATH.format(
            lb_id=self.lb.get('id'), listener_id=listener.get('id'))
        listener = self.put(listener_path, {'tls_termination': tls}).json
        self.assertIsNone(listener.get('tls_termination'))
        get_listener = self.get(listener_path).json
        self.assertIsNone(get_listener.get('tls_termination'))

    def test_create_with_valid_insert_headers(self):
        lb_listener = {'protocol': 'HTTP',
                       'protocol_port': 80,
                       'insert_headers': {'X-Forwarded-For': 'true'},
                       'project_id': self.project_id}
        self.post(self.listeners_path, lb_listener, status=202)

    def test_create_with_bad_insert_headers(self):
        lb_listener = {'protocol': 'HTTP',
                       'protocol_port': 80,
                       # 'insert_headers': {'x': 'x'}}
                       'insert_headers': {'X-Forwarded-Four': 'true'},
                       'project_id': self.project_id}
        self.post(self.listeners_path, lb_listener, status=400)
