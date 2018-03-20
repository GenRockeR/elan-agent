#!/usr/bin/env python3

import asyncio
from elan.snmp import DeviceSnmpManager

snmp_manager = DeviceSnmpManager()

# Register SNMP Application at the SNMP engine

# Run I/O dispatcher which would receive queries and send confirmations


async def receive_traps():
    proc = await asyncio.create_subprocess_exec('/usr/sbin/snmptrapd', '-On', '-Lo', '-f', 'udp:162', 'udp6:162', stdout=asyncio.subprocess.PIPE)
    in_trap = False
    trap_str = ''
    while True:
        line = await proc.stdout.readline()
        if not line:
            break  # process ended.
        line = line.decode().rstrip('\n\r')
        if in_trap:
            trap_str += line
        elif 'BEGIN VARIABLEBINDINGS' in line:
            trap_str = line
            in_trap = True
        if 'END VARIABLEBINDINGS' in trap_str:
            in_trap = False
            asyncio.ensure_future(snmp_manager.parse_trap_str(trap_str))


asyncio.get_event_loop().run_until_complete(receive_traps())
