from origin.neuron import Dendrite
import datetime

dendrite = Dendrite('session')

def format_date(date):
    if not date:
        return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        return datetime.datetime.utcfromtimestamp(date).strftime('%Y-%m-%dT%H:%M:%SZ')



def start_MAC_session(mac, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session'.format(mac=mac), {'start': format_date(start)})

def end_MAC_session(mac, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/end'.format(mac=mac), {'end': format_date(end)})



def start_VLAN_session(mac, vlan, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}'.format(mac=mac, vlan=vlan), {'start': format_date(start)})

def end_VLAN_session(mac, vlan, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/end'.format(mac=mac, vlan=vlan), {'end': format_date(end)})
    

    
def start_IP_session(mac, vlan, ip, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/ip/{ip}'.format(mac=mac, vlan=vlan, ip=ip), {'start': format_date(start)})


def end_IP_session(mac, vlan, ip, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/ip/{ip}/current/end'.format(mac=mac, vlan=vlan, ip=ip), {'end': format_date(end)})



def start_authorization_session(mac, vlan, start=None, end=None, **kwargs):
    '''
        start and end are Epoch
        kwargs can contain type, login, authentication_provider, till_disconnect 
    '''
    kwargs['start'] = format_date(start)
    if end:
        kwargs['end'] = format_date(end)
    
    dendrite.post('mac/{mac}/authorization/vlan/{vlan}'.format(mac=mac, vlan=vlan), kwargs)

def end_authorization_session(mac, vlan, end=None, **kwargs):
    ''' start is Epoch '''

    kwargs['end'] = format_date(end)

    dendrite.post('mac/{mac}/authorization/vlan/{vlan}/current/end'.format(mac=mac, vlan=vlan), kwargs)
