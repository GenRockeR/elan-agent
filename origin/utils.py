import netifaces, subprocess, re, netaddr
import ctypes
import ctypes.util
from netaddr import IPNetwork
import os

DEFAULT_IFACE = 'br0'

def get_ip6_address(if_name=DEFAULT_IFACE):
    ''' returns first ip6 global address found , else first ipv6 found, None if not found'''
    try:
        return get_ip6_global_addresses(if_name)[0]
    except (KeyError, IndexError):
        pass
    try:
        return get_ip6_addresses(if_name)[0]
    except (KeyError, IndexError):
        return None


def get_ip6_addresses(if_name=DEFAULT_IFACE):
    ''' returns first ip6 address found, None if not found'''
    try:
        return [ 
                    { 'address': iface['addr'], 'mask': iface['netmask'], 'prefix_length': IPNetwork('::/'+iface['netmask']).prefixlen } 
                        for iface in netifaces.ifaddresses(if_name)[netifaces.AF_INET6] 
               ]
    except (KeyError, IndexError):
        return []

def get_ip6_global_addresses(if_name=DEFAULT_IFACE):
    ''' returns first ip6 address found, None if not found'''
    return [ 
                addr for addr in get_ip6_addresses(if_name) 
                     if not addr['address'].startswith('fe80') # not local link
           ]

def get_ip4_address(if_name=DEFAULT_IFACE):
    ''' returns first ip4 address found, None if not found'''
    try:
        return get_ip4_addresses(if_name)[0]
    except (KeyError, IndexError):
        return None

def get_ip4_addresses(if_name=DEFAULT_IFACE):
    ''' returns ip4 addresses found, empty list if not found'''
    try:
        return  [ 
                    { 'address': iface['addr'], 'mask': iface['netmask'], 'prefix_length': IPNetwork('0/'+iface['netmask']).prefixlen } 
                        for iface in netifaces.ifaddresses(if_name)[netifaces.AF_INET] 
                ]
    except (KeyError, IndexError):
        return []

    
def get_ether_address(if_name=DEFAULT_IFACE):
    try:
        return netifaces.ifaddresses(if_name)[netifaces.AF_PACKET][0]['addr']
    except (KeyError, IndexError):
        return None

def ip4_to_mac(ip):
    p = subprocess.Popen(['ip','neigh', 'show', ip], stdout=subprocess.PIPE)
    output = str(p.communicate()[0])
    m = re.search(r'[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]', output)
    if m:
        return str(m.group(0))

def get_ip4_default_gateway():
    try:
        gw = netifaces.gateways()['default'][netifaces.AF_INET][0]
    except (KeyError, IndexError):
        gw = None
    
    return gw

def get_ip6_default_gateway():
    try:
        gw = netifaces.gateways()['default'][netifaces.AF_INET6][0]
    except (KeyError, IndexError):
        gw = None
    
    return gw

def get_cidr6_global_networks(if_name=DEFAULT_IFACE):
    networks = set()
    for ip in get_ip6_global_addresses(if_name):
        ip_network = netaddr.IPNetwork( '{}/{}'.format(ip['address'], ip['prefix_length']) ) 
        networks.add( '{}/{}'.format(ip_network.network, ip_network.prefixlen) )
    
    return networks

def get_cidr4_networks(if_name=DEFAULT_IFACE):
    networks = set()
    for ip in get_ip4_addresses(if_name):
        ip_network = netaddr.IPNetwork( '{}/{}'.format(ip['address'], ip['prefix_length']) ) 
        networks.add( '{}/{}'.format(ip_network.network, ip_network.prefixlen) )
    
    return networks

def get_cidr_networks(if_name=DEFAULT_IFACE):
    return get_cidr6_global_networks(if_name) | get_cidr4_networks(if_name)


def get_dns_servers():
    dns_ips = []
    with open('/etc/resolv.conf', 'r') as file:
        for line in file:
            columns = line.split()
            if columns[0] == 'nameserver':
                dns_ips.extend(columns[1:])

    return dns_ips

def get_ip4_dns_servers():
    return { ip for ip in get_dns_servers() if '.' in ip }

def get_ip6_dns_servers():
    return { ip for ip in get_dns_servers() if ':' in ip }

def if_nametoindex(name):
    if not isinstance (name, str):
        raise TypeError ('name must be a string.')
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    ret = libc.if_nametoindex (name)
    if not ret:
        raise RuntimeError("Invalid Name")
    return ret
     
def if_indextoname(index):
    if not isinstance (index, int):
        raise TypeError ('index must be an int.')
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    libc.if_indextoname.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
    libc.if_indextoname.restype = ctypes.c_char_p
     
    ifname = ctypes.create_string_buffer (32)
    ifname = libc.if_indextoname (index, ifname)
    if not ifname:
        raise RuntimeError ("Inavlid Index")
    return ifname

def is_iface_up(iface):
    try:
        with open('/sys/class/net/{iface}/operstate'.format(iface=iface)) as file:
            state = file.read().replace('\n', '')
    except IOError:
        return False
    return state == 'up'

def physical_ifaces():
    ifaces = set()
    for ifname in os.listdir('/sys/class/net/'):
        try:
            if not os.readlink('/sys/class/net/' + ifname).startswith('../../devices/virtual/net/'):
                ifaces.add(ifname)
        except:
            pass
    
    return ifaces
        