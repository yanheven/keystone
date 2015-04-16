# -*- coding: utf-8 -*-
# Copyright 2012 OpenStack Foundation
# Copyright 2013 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import ldappool
import mock
from oslo_config import cfg
from oslotest import mockpatch

from keystone.common.ldap import core as ldap_core
from keystone.identity.backends import ldap
from keystone.tests import unit as tests
from keystone.tests.unit import fakeldap
from keystone.tests.unit import test_backend_ldap

CONF = cfg.CONF


class LdapPoolCommonTestMixin(object):
    """LDAP pool specific common tests used here and in live tests."""

    def cleanup_pools(self):
        ldap_core.PooledLDAPHandler.connection_pools.clear()

    def test_handler_with_use_pool_enabled(self):
        # by default use_pool and use_auth_pool is enabled in test pool config
        user_ref = self.identity_api.get_user(self.user_foo['id'])
        self.user_foo.pop('password')
        self.assertDictEqual(user_ref, self.user_foo)

        handler = ldap_core._get_connection(CONF.ldap.url, use_pool=True)
        self.assertIsInstance(handler, ldap_core.PooledLDAPHandler)

    @mock.patch.object(ldap_core.KeystoneLDAPHandler, 'connect')
    @mock.patch.object(ldap_core.KeystoneLDAPHandler, 'simple_bind_s')
    def test_handler_with_use_pool_not_enabled(self, bind_method,
                                               connect_method):
        self.config_fixture.config(group='ldap', use_pool=False)
        self.config_fixture.config(group='ldap', use_auth_pool=True)
        self.cleanup_pools()

        user_api = ldap.UserApi(CONF)
        handler = user_api.get_connection(user=None, password=None,
                                          end_user_auth=True)
        # use_auth_pool flag does not matter when use_pool is False
        # still handler is non pool version
        self.assertIsInstance(handler.conn, ldap_core.PythonLDAPHandler)

    @mock.patch.object(ldap_core.KeystoneLDAPHandler, 'connect')
    @mock.patch.object(ldap_core.KeystoneLDAPHandler, 'simple_bind_s')
    def test_handler_with_end_user_auth_use_pool_not_enabled(self, bind_method,
                                                             connect_method):
        # by default use_pool is enabled in test pool config
        # now disabling use_auth_pool flag to test handler instance
        self.config_fixture.config(group='ldap', use_auth_pool=False)
        self.cleanup_pools()

        user_api = ldap.UserApi(CONF)
        handler = user_api.get_connection(user=None, password=None,
                                          end_user_auth=True)
        self.assertIsInstance(handler.conn, ldap_core.PythonLDAPHandler)

        # For end_user_auth case, flag should not be false otherwise
        # it will use, admin connections ldap pool
        handler = user_api.get_connection(user=None, password=None,
                                          end_user_auth=False)
        self.assertIsInstance(handler.conn, ldap_core.PooledLDAPHandler)

    def test_pool_size_set(self):
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.pool_size, ldappool_cm.size)

    def test_pool_retry_max_set(self):
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.pool_retry_max, ldappool_cm.retry_max)

    def test_pool_retry_delay_set(self):
        # just make one identity call to initiate ldap connection if not there
        self.identity_api.get_user(self.user_foo['id'])

        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.pool_retry_delay, ldappool_cm.retry_delay)

    def test_pool_use_tls_set(self):
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.use_tls, ldappool_cm.use_tls)

    def test_pool_timeout_set(self):
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.pool_connection_timeout,
                         ldappool_cm.timeout)

    def test_pool_use_pool_set(self):
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.use_pool, ldappool_cm.use_pool)

    def test_pool_connection_lifetime_set(self):
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        self.assertEqual(CONF.ldap.pool_connection_lifetime,
                         ldappool_cm.max_lifetime)

    def test_max_connection_error_raised(self):

        who = CONF.ldap.user
        cred = CONF.ldap.password
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        ldappool_cm.size = 2

        # 3rd connection attempt should raise Max connection error
        with ldappool_cm.connection(who, cred) as _:  # conn1
            with ldappool_cm.connection(who, cred) as _:  # conn2
                try:
                    with ldappool_cm.connection(who, cred) as _:  # conn3
                        _.unbind_s()
                        self.fail()
                except Exception as ex:
                    self.assertIsInstance(ex,
                                          ldappool.MaxConnectionReachedError)
        ldappool_cm.size = CONF.ldap.pool_size

    def test_pool_size_expands_correctly(self):

        who = CONF.ldap.user
        cred = CONF.ldap.password
        # get related connection manager instance
        ldappool_cm = self.conn_pools[CONF.ldap.url]
        ldappool_cm.size = 3

        def _get_conn():
            return ldappool_cm.connection(who, cred)

        # Open 3 connections first
        with _get_conn() as _:  # conn1
            self.assertEqual(len(ldappool_cm), 1)
            with _get_conn() as _:  # conn2
                self.assertEqual(len(ldappool_cm), 2)
                with _get_conn() as _:  # conn2
                    _.unbind_ext_s()
                    self.assertEqual(len(ldappool_cm), 3)

        # Then open 3 connections again and make sure size does not grow
        # over 3
        with _get_conn() as _:  # conn1
            self.assertEqual(len(ldappool_cm), 1)
            with _get_conn() as _:  # conn2
                self.assertEqual(len(ldappool_cm), 2)
                with _get_conn() as _:  # conn3
                    _.unbind_ext_s()
                    self.assertEqual(len(ldappool_cm), 3)

    def test_password_change_with_pool(self):
        old_password = self.user_sna['password']
        self.cleanup_pools()

        # authenticate so that connection is added to pool before password
        # change
        user_ref = self.identity_api.authenticate(
            context={},
            user_id=self.user_sna['id'],
            password=self.user_sna['password'])

        self.user_sna.pop('password')
        self.user_sna['enabled'] = True
        self.assertDictEqual(user_ref, self.user_sna)

        new_password = 'new_password'
        user_ref['password'] = new_password
        self.identity_api.update_user(user_ref['id'], user_ref)

        # now authenticate again to make sure new password works with
        # conneciton pool
        user_ref2 = self.identity_api.authenticate(
            context={},
            user_id=self.user_sna['id'],
            password=new_password)

        user_ref.pop('password')
        self.assertDictEqual(user_ref, user_ref2)

        # Authentication with old password would not work here as there
        # is only one connection in pool which get bind again with updated
        # password..so no old bind is maintained in this case.
        self.assertRaises(AssertionError,
                          self.identity_api.authenticate,
                          context={},
                          user_id=self.user_sna['id'],
                          password=old_password)


class LdapIdentitySqlAssignment(LdapPoolCommonTestMixin,
                                test_backend_ldap.LdapIdentitySqlAssignment,
                                tests.TestCase):
    '''Executes existing base class 150+ tests with pooled LDAP handler to make
    sure it works without any error.
    '''
    def setUp(self):
        self.useFixture(mockpatch.PatchObject(
            ldap_core.PooledLDAPHandler, 'Connector', fakeldap.FakeLdapPool))
        super(LdapIdentitySqlAssignment, self).setUp()

        self.addCleanup(self.cleanup_pools)
        # storing to local variable to avoid long references
        self.conn_pools = ldap_core.PooledLDAPHandler.connection_pools
        # super class loads db fixtures which establishes ldap connection
        # so adding dummy call to highlight connection pool initialization
        # as its not that obvious though its not needed here
        self.identity_api.get_user(self.user_foo['id'])

    def config_files(self):
        config_files = super(LdapIdentitySqlAssignment, self).config_files()
        config_files.append(tests.dirs.tests_conf('backend_ldap_pool.conf'))
        return config_files

    @mock.patch.object(ldap_core, 'utf8_encode')
    def test_utf8_encoded_is_used_in_pool(self, mocked_method):
        def side_effect(arg):
            return arg
        mocked_method.side_effect = side_effect
        # invalidate the cache to get utf8_encode function called.
        self.identity_api.get_user.invalidate(self.identity_api,
                                              self.user_foo['id'])
        self.identity_api.get_user(self.user_foo['id'])
        mocked_method.assert_any_call(CONF.ldap.user)
        mocked_method.assert_any_call(CONF.ldap.password)
