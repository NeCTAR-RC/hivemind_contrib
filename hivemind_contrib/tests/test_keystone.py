import unittest
from unittest import mock

from hivemind_contrib import keystone


class GetSessionTestCase(unittest.TestCase):
    @mock.patch.dict(
        'os.environ',
        {
            'OS_AUTH_URL': 'https://example/v3',
            'OS_AUTH_TYPE': 'token',
            'OS_TOKEN': 'abc',
            'OS_PROJECT_NAME': 'proj',
        },
        clear=True,
    )
    @mock.patch('hivemind_contrib.keystone.loading')
    @mock.patch('hivemind_contrib.keystone.session')
    def test_token_auth(self, mock_session, mock_loading):
        keystone.get_session()

        mock_loading.get_plugin_loader.assert_called_once_with('token')
        loader = mock_loading.get_plugin_loader.return_value
        opts = loader.load_from_options.call_args.kwargs
        self.assertEqual('abc', opts['token'])
        self.assertEqual('proj', opts['project_name'])
        self.assertNotIn('username', opts)
        self.assertNotIn('password', opts)

    @mock.patch.dict(
        'os.environ',
        {
            'OS_AUTH_URL': 'https://example/v3',
            'OS_USERNAME': 'u',
            'OS_PASSWORD': 'p',
            'OS_PROJECT_NAME': 'proj',
        },
        clear=True,
    )
    @mock.patch('hivemind_contrib.keystone.loading')
    @mock.patch('hivemind_contrib.keystone.session')
    def test_password_auth_is_default(self, mock_session, mock_loading):
        keystone.get_session()

        mock_loading.get_plugin_loader.assert_called_once_with('password')
        loader = mock_loading.get_plugin_loader.return_value
        opts = loader.load_from_options.call_args.kwargs
        self.assertEqual('u', opts['username'])
        self.assertEqual('p', opts['password'])
        self.assertEqual('proj', opts['project_name'])
        self.assertNotIn('token', opts)

    @mock.patch.dict(
        'os.environ',
        {
            'OS_AUTH_URL': 'https://example/v3',
            'OS_USERNAME': 'u',
            'OS_PASSWORD': 'p',
            'OS_TENANT_NAME': 'legacy-proj',
        },
        clear=True,
    )
    @mock.patch('hivemind_contrib.keystone.loading')
    @mock.patch('hivemind_contrib.keystone.session')
    def test_tenant_name_fallback(self, mock_session, mock_loading):
        keystone.get_session()

        loader = mock_loading.get_plugin_loader.return_value
        opts = loader.load_from_options.call_args.kwargs
        self.assertEqual('legacy-proj', opts['project_name'])
