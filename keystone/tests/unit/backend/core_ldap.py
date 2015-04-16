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

import ldap

from oslo_config import cfg

from keystone.common import cache
from keystone.common import ldap as common_ldap
from keystone.common.ldap import core as common_ldap_core
from keystone.common import sql
from keystone.tests import unit as tests
from keystone.tests.unit import default_fixtures
from keystone.tests.unit import fakeldap
from keystone.tests.unit.ksfixtures import database


CONF = cfg.CONF


def create_group_container(identity_api):
        # Create the groups base entry (ou=Groups,cn=example,cn=com)
        group_api = identity_api.driver.group
        conn = group_api.get_connection()
        dn = 'ou=Groups,cn=example,cn=com'
        conn.add_s(dn, [('objectclass', ['organizationalUnit']),
                        ('ou', ['Groups'])])


class BaseBackendLdapCommon(object):
    """Mixin class to set up generic LDAP backends."""

    def setUp(self):
        super(BaseBackendLdapCommon, self).setUp()

        common_ldap.register_handler('fake://', fakeldap.FakeLdap)
        self.load_backends()
        self.load_fixtures(default_fixtures)

        self.addCleanup(common_ldap_core._HANDLERS.clear)
        self.addCleanup(self.clear_database)

    def _get_domain_fixture(self):
        """Domains in LDAP are read-only, so just return the static one."""
        return self.resource_api.get_domain(CONF.identity.default_domain_id)

    def clear_database(self):
        for shelf in fakeldap.FakeShelves:
            fakeldap.FakeShelves[shelf].clear()

    def reload_backends(self, domain_id):
        # Only one backend unless we are using separate domain backends
        self.load_backends()

    def get_config(self, domain_id):
        # Only one conf structure unless we are using separate domain backends
        return CONF

    def config_overrides(self):
        super(BaseBackendLdapCommon, self).config_overrides()
        self.config_fixture.config(
            group='identity',
            driver='keystone.identity.backends.ldap.Identity')

    def config_files(self):
        config_files = super(BaseBackendLdapCommon, self).config_files()
        config_files.append(tests.dirs.tests_conf('backend_ldap.conf'))
        return config_files

    def get_user_enabled_vals(self, user):
            user_dn = (
                self.identity_api.driver.user._id_to_dn_string(user['id']))
            enabled_attr_name = CONF.ldap.user_enabled_attribute

            ldap_ = self.identity_api.driver.user.get_connection()
            res = ldap_.search_s(user_dn,
                                 ldap.SCOPE_BASE,
                                 u'(sn=%s)' % user['name'])
            if enabled_attr_name in res[0][1]:
                return res[0][1][enabled_attr_name]
            else:
                return None


class BaseBackendLdap(object):
    """Mixin class to set up an all-LDAP configuration."""
    def setUp(self):
        # NOTE(dstanek): The database must be setup prior to calling the
        # parent's setUp. The parent's setUp uses services (like
        # credentials) that require a database.
        self.useFixture(database.Database())
        super(BaseBackendLdap, self).setUp()

    def load_fixtures(self, fixtures):
        # Override super impl since need to create group container.
        create_group_container(self.identity_api)
        super(BaseBackendLdap, self).load_fixtures(fixtures)


class BaseBackendLdapIdentitySqlEverythingElse(tests.SQLDriverOverrides):
    """Mixin base for Identity LDAP, everything else SQL backend tests."""

    def config_files(self):
        config_files = super(BaseBackendLdapIdentitySqlEverythingElse,
                             self).config_files()
        config_files.append(tests.dirs.tests_conf('backend_ldap_sql.conf'))
        return config_files

    def setUp(self):
        self.useFixture(database.Database())
        super(BaseBackendLdapIdentitySqlEverythingElse, self).setUp()
        self.clear_database()
        self.load_backends()
        cache.configure_cache_region(cache.REGION)
        self.engine = sql.get_engine()
        self.addCleanup(sql.cleanup)

        sql.ModelBase.metadata.create_all(bind=self.engine)
        self.addCleanup(sql.ModelBase.metadata.drop_all, bind=self.engine)

        self.load_fixtures(default_fixtures)
        # defaulted by the data load
        self.user_foo['enabled'] = True

    def config_overrides(self):
        super(BaseBackendLdapIdentitySqlEverythingElse,
              self).config_overrides()
        self.config_fixture.config(
            group='identity',
            driver='keystone.identity.backends.ldap.Identity')
        self.config_fixture.config(
            group='resource',
            driver='keystone.resource.backends.sql.Resource')
        self.config_fixture.config(
            group='assignment',
            driver='keystone.assignment.backends.sql.Assignment')


class BaseBackendLdapIdentitySqlEverythingElseWithMapping(object):
    """Mixin base class to test mapping of default LDAP backend.

    The default configuration is not to enable mapping when using a single
    backend LDAP driver.  However, a cloud provider might want to enable
    the mapping, hence hiding the LDAP IDs from any clients of keystone.
    Setting backward_compatible_ids to False will enable this mapping.

    """
    def config_overrides(self):
        super(BaseBackendLdapIdentitySqlEverythingElseWithMapping,
              self).config_overrides()
        self.config_fixture.config(group='identity_mapping',
                                   backward_compatible_ids=False)
