Overview
########

ELAN Agent is platform to ease LAN management by integrating closely into the network, using existing services and equipments.

The goal is to have an easy to deploy solution that adapts the switch capabilities (802.1C, mac auth, SNMP trap notification, ...) to be able to master your LAN in terms of visibility (know exactly what is on your network) and security (access control verification/enforcement with flexible rules).

To achieve this, ELAN Agent provides the following services:

- NAC: 802.1X/Mac-Auth via RADIUS.
- SNMP polling and trap/notification monitoring.
- Access Control of devices on VLANs.
- Detection of unauthorized devices.
- Authentication using LDAP, AD or external source.
- Inventory of all devices (MAC addresses) on the network.
- Captive portal:

  - User Authentication & Guest Access.
  - Automatic captive portal when trying to access an http(s) unauthorized service.
- IDS (Suricata).
- Log of Networks events (New Device, New device on VLAN, New Device IP, disconnected Device, New connection, IDS alert for device...).
- Log of outgoing IP connections.


All configuration of these services are done via MQTT by publishing retained messages to topics. Events are also sent via MQTT.


ELAN Agent implements NAC by assigning devices a VLAN, then allowing them to access other VLANs (bridging) based on their authorizations.
Access is done on a per device (MAC address) to all devices on the allowed VLANs.
Hence you need only 1 IP address range for all your services and take advantages of local network facility like zero-conf while still separating services.


ELAN Agent fully supports IPv6.


Installation
############

ELAN Agent is designed to run on Ubuntu 18.04 (Bionic)

  .. code-block::
  
    $ sudo add-apt-repository ppa:easy-lan/stable
    $ sudo apt-get update
    $ sudo apt install elan-agent


Note: This will modify your network configuration and create a bridge with the first 2 interfaces it finds, and obtain an address by DHCP.

Documentation
#############

`ELAN Agent Documentation <https://origin-nexus.com/elan-docs/elan-agent/>`_
