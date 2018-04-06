Overview
########

ELAN Agent is platform to ease LAN management by providing several services:

- NAC: 802.1X/Mac-Auth via RADIUS
- Access Control of devices to VLANs
- Detection of unauthorized devices
- Authentication using LDAP, AD or external source.
- Inventory of all devices (MAC addresses) on the network
- Captive portal: User Authentication & Guest Access
- IDS (Suricata)
- Log of Networks events (New Device, New device on VLAN, New Device IP,
  diconnected Device, New connection, IDS alert for device...)
- Log of outgoing connections

All configuration of these services are done via MQTT by publishing retained messages to topics. Events are also sent via MQTT.


ELAN Agent implements NAC by assigning devices a vlan, then allowing them to access other vlan (bridging) based on their authorisations.
Access is done on a per device (MAC address) to all devices on the allowed VLANs.
Hence you need only 1 IP address range for all your services and take advantages of local network facility like zero conf while still separating services.


ELAN Agent fully supports IPv6.


Deployment
##########

#TODO


Configuration
#############

All configuration is done by sending JSON encoded message to MQTT topics under`conf/` on `localhost`.
No validation is made on the format nor on the parameters, they will be used as is.


Administrator Configuration
***************************

Administrators can connect to the Agent web console to configure its network,
like IP addresses, DNS and default gateway.

* topic: `conf/administrator`
* format: list of administrator definitions:

.. code-block:: json

  [
     {
        "login":    <str: *Mandatory*>, "password": <pbkdf2 encrypted
        password: *Mandatory*>
     }, ...
  ]

VLAN Configuration
******************

VLANs are identified by the network interface of the agent and the VLAN identifier.
ELAN Agent should only be connected once to every VLAN, ie do not connect the same VLAN on 2 different NICs.
However, if those vlans are completly separate, it can be connected to 2 vlans with the same identifier on different interfaces.

* topic: `conf/vlans`
* format: list of vlan definitions:

  .. code-block:: json

    [
      {
        "id":                        <int: *Mandatory*>  // Unique ID for the vlan so it can referenced by other vlans.
        "interface":                 <str: *Mandatory*>, // Nic Name
        "vlan_id":                   <int: 0>,           // Vlan Identifier
        "access_control":            <bool: false>,      // Enable access control on that vlan
        "log":                       <bool: false>,      // Enable connection logging
        "ids":                       <bool: false>,      // Enable IDS on that vlan
        "web_authentication":        <int: null>,        // ID of Authentication to use when authenticating users on captive portal
        "guest_access":              <int: null>,        // ID of guest access to use on this vlan
        "dhcp_passthroughs":         <list of ints: []>, // IDs of vlans to which DHCP/IPv6autoconf requests are allowed even if device not allowed to these VLANs
        "dns_passthroughs":          <list of ints: []>, // IDs of vlans to which DNS requests are allowed even if device not allowed to these VLANs
        "ndp_passthroughs":          <list of ints: []>, // IDs of vlans to which ARP/NDP requests are allowed even if device not allowed to these VLANs
        "mdns_answers_passthroughs": <list of ints: []>, // IDs of vlans to which MDNS answers are allowed.
      },
      ...
    ]

   NDP passthroughs always include DHCP and DNS passthroughs.
   They can be useful if you want to give access to a resource via captive portal authentication as a device needs to resolve IP to MAC to access the service before getting redirected by captive portal.
   For example when WAN connectivity is not on the same Network as DHCP and DNS.
 
RADIUS Configuration
********************

#TODO
 
SNMP Configuration
******************

#TODO


Authentication Configuration
****************************

Authentications can be used by captive portal and 802.1X to authenticate users against existing user databases.

* topic: `conf/authentication`
* format: list of authentication definitions:

  - LDAP: User will be authenticated using the following attributes for the password: `userPassword`, `ntPassword` or `sambaNTPassword`.

  .. code-block:: json

      {
        "id":         <int: *Mandatory*>,        // id that can be used in members of a group.
        "type":       "LDAP",
        "host":       <ip or fqdn: *Mandatory*>, // must match Common Name of Server Certificate if certificates used.
        "port":       <int: 389 or 636>,         // port to connect to. Defaults to 636 if encryption is ssl, 389 otherwise.
        "encryption": <str: "none">,             // ssl, start_tls or none.
        "server_ca":  <str: "">,                 // PEM encoded Certificate Authority to check against when encryption is "start_tls" or "ssl". If not provided check, not performed.
        "baseDN":     <str: "">,                 // baseDN from which user will be searched.
        "bindDN":     <str: "">,                 // User DN used to bind to LDAP for search. No bind if empty.
        "bindPwd":    <str: "">,                 // Password of user used to bind to LDAP. 
        "userAttr":   <str: *Mandatory*>,        // Attribute against which search for the user authenticating.
        "userFilter": <str: "">,                 // LDAP filter used when searching for user. No filtering if empty.
      }

  - Active Directory: Authentication will be performed by joining the AD domain. Only one AD is supported.

  .. code-block:: json

    {
      "id":         <int: *Mandatory*>, // id that can be used in members of a group.
      "type":       "active-directory",
      "domain":     <str: *Mandatory*>, // domain to join. Should resolvable by agent DNS.
      "adminLogin": <str: null>,        // admin login used to register to domain
      "adminPwd":   <str: null>,        // password of admin.
    }

  - External: Authentication will be made by doing a request via MQTT. Unknown Authentication IDs will be considered external, so you don't really need to declare them.

  .. code-block:: json

    {
      "id":   <int: *Mandatory*>, // id that can be used in members of a group.
      "type": <str: external>,    // unknown authentication types will be considered external
    }

  - Groups: Authentication will be tried among members of the group, in the order defined.
    Nested and circular groups are supported. 
    If an authentication has been tried once, it will not be retried, even if it appears in several groups that are members of the group.

  .. code-block:: json

    {
      "id":      <int: *Mandatory*>,       // id that can be used in members of a group.
      "type":    "group",
      "members": <list of ints: []>   // list of authentication IDs. If an ID is not present in list of authentication, it will be considered as external. 
    }



Guest Access Configuration
**************************

#TODO

 
Events
######

#TODO


