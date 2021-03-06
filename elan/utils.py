import ctypes.util
import netaddr
import netifaces
import os
import re
import subprocess

DEFAULT_IFACE = 'elan'


def get_ether_address(if_name=DEFAULT_IFACE):
    try:
        return netifaces.ifaddresses(if_name)[netifaces.AF_PACKET][0]['addr']
    except:
        return None


def ip4_to_mac(ip):
    p = subprocess.Popen(['ip', 'neigh', 'show', ip], stdout=subprocess.PIPE)
    output = str(p.communicate()[0])
    m = re.search(r'[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]', output)
    if m:
        return str(m.group(0))


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
    return ifname.decode()


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


def manage_service(action, service, no_block=False, sudo=False):
    args = []
    if sudo:
        args.append('sudo')
    args.append('systemctl')
    if no_block:
        args.append('--no-block')
    args.append(action)
    args.append(service + '.service')

    subprocess.run(args)


def start_service(service, no_block=False, sudo=False):
    manage_service('start', service, no_block, sudo)


def stop_service(service, no_block=False, sudo=False):
    manage_service('stop', service, no_block, sudo)


def reload_service(service, no_block=False, sudo=False):
    manage_service('reload', service, no_block, sudo)


def restart_service(service, no_block=False, sudo=False):
    manage_service('restart', service, no_block, sudo)

