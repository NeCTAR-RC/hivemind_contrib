from fabric.utils import error
from hivemind import decorators

try:
    from freshdesk.v2.api import API
except ImportError:
    API = None


@decorators.configurable('freshdesk')
@decorators.verbose
def get_freshdesk_config(
    api_key=None,
    email_config_id='6000071619',
    group_id='6000208874',
    domain='dhdnectar.freshdesk.com',
):
    """fetch freshdesk API details from config file"""
    msg = '\n'.join(
        [
            'No Freshdesk API key found in your Hivemind config file.',
            '',
            'To find your Freshdesk API key by following the guide here:',
            'https://support.freshdesk.com/support/solutions/'
            'articles/215517-how-to-find-your-api-key',
            '',
            'Then add the following config to your Hivemind configuration',
            'file (~/.hivemind/hivemind/config.ini):',
            '',
            '  [cfg:hivemind_contrib.freshdesk.freshdesk]',
            '  api_key = <your api key>',
        ]
    )
    if api_key is None:
        error(msg)
    config = {
        'api_key': api_key,
        'email_config_id': email_config_id,
        'group_id': group_id,
        'domain': domain,
    }
    return config


def get_freshdesk_client(domain, api_key):
    if not API:
        error(
            "To use this tool, you will need to also install the"
            "python-freshdesk package: \n"
            "  $ pip install python-freshdesk"
        )
    return API(domain, api_key)
