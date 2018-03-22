from fabric.utils import error

from hivemind import decorators

from freshdesk.v2.api import API


@decorators.configurable('freshdesk')
@decorators.verbose
def get_config(api_key=None,
               email_config_id='6000071619',
               group_id='6000144734',
               domain='dhdnectar.freshdesk.com'):
    """fetch freshdesk API details from config file"""
    msg = '\n'.join([
        'No Freshdesk API key found in your Hivemind config file.',
        '',
        'To find your Freshdesk API key by following the guide here:',
        'https://support.freshdesk.com/support/solutions/'
        'articles/215517-how-to-find-your-api-key',
        '',
        'Then add the following config to your Hivemind configuration',
        'file (~/.hivemind/hivemind/config.ini):',
        '',
        '  [cfg:hivemind_contrib.security.freshdesk]',
        '  api_key = <your api key>',
    ])

    if api_key is None:
        error(msg)

    config = {'api_key': api_key,
              'email_config_id': email_config_id,
              'group_id': group_id,
              'domain': domain}

    return config


def client():
    config = get_config()
    return API(config['domain'], config['api_key'])
