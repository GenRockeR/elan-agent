#! /usr/bin/env python3

from .utils import request_as_hash_of_values
from elan.event import Event, ExceptionEvent


def AuthenticationProviderFailed(req, level='danger'):
    # Treat error from auth
    try:
        request = request_as_hash_of_values(req)
        
        # Todo: set source depending on requester: radius-dot1x, captive-portal-web or captive-portal-guest-access
        event = Event('runtime-failure-authentication', source='radius', level=level)\
            .add_data('authentication_provider', request.get('ELAN-Auth-Failed'), data_type='authentication')
        
        if request.get('Module-Failure-Message'):
            event.add_data('details', request.get('Module-Failure-Message'))

        event.notify()
        
    except:
        ExceptionEvent(source='radius').notify()
        raise

def AuthenticationProviderFailedInGroup(req):
    AuthenticationProviderFailed(req, level='warning')

def AuthenticationGroupFailed(req):
    try:
        request = request_as_hash_of_values(req)
        
        # Todo: set source depending on requester: radius-dot1x, captive-portal-web or captive-portal-guest-access
        Event('runtime-failure-authentication', source='radius', level='danger')\
            .add_data('authentication_group', request.get('ELAN-Auth-Failed'), data_type='authentication')\
            .notify()
    except:
        ExceptionEvent(source='radius').notify()
        raise



