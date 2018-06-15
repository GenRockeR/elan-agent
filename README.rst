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

Deployment
##########

ELAN Agent is typically deployed as an inline level 2 enforcement device.
It sits between the WAN connection and the switches and should be connected on every VLAN segment on a trunk port (all VLANs tagged) to maximize it visibility on the network.
It should also receive RADIUS authentication/accounting request from the switches and be able to connect via SNMP to the switches.

All devices on the network can share the same IP (v4/v6) subnet while being isolated by VLAN.
When a device is authorized to access another vlan, it is "bridged" on it, so that all zero-conf services are available.

DHCP/DNS services are not part of ELAN agent services but it offers connectivity to those services even if located on another VLAN.

Installation
############

ELAN Agent is designed to run on Ubuntu 18.04 (Bionic)

  .. code-block::
  
    $ sudo add-apt-repository ppa:easy-lan/stable
    $ sudo apt-get update
    $ sudo apt install elan-agent


Note: This will modify your network configuration and create a bridge with the first 2 interfaces it finds, and obtain an address by DHCP.

Configuration
#############

All configuration is done by sending JSON encoded *retained* message to MQTT topics under`conf/` on `localhost`.
No validation is made on the format nor on the parameters, they will be used as is.

IP Configuration
****************

IP v4
-----
:topic:
  `conf/ipv4`
:format:

  .. code-block:: json

    {
      "type":    <str: "none">,     // `dhcp`, `static` or `none`. Unknown value is same as `none`
      "address": <ip4>,             // IP address when `type` is `static`
      "mask":    <int>,             // mask when `type` is `static`
      "dns":     <list of ip4: []>, // List of DNS servers (in case of `dhcp`, will be added to received ones).
    }, ...

  If no configuration, defaults to `dhcp`.

IP v6
-----
:topic:
  `conf/ipv6`
:format:

  .. code-block:: json

    {
      "type":    <str: "none">,     // `autoconf`, `dhcp`, `static` or `none`. Unknown value is same as `none`
      "address": <ip6>,             // IP address when `type` is `static`
      "mask":    <int>,             // mask when `type` is `static`
      "dns":     <list of ip6: []>, // List of DNS servers. (in case of `dhcp` or `autoconf`, will be added to received ones).
    }, ...

  If no configuration, defaults to `autoconf`.

Administrator Configuration
***************************

Administrators can connect to the Agent web console to configure its network,
like IP addresses, DNS and default gateway.

:topic:
  `conf/administrator`
:format:
  *list* of administrator definitions

  .. code-block:: json
  
    [
      {
          "login":    <str: *Mandatory*>,
          "password": <pbkdf2 encrypted: *Mandatory*>
      }, ...
    ]

VLAN Configuration
******************

VLANs are identified by the network interface of the agent and the VLAN identifier.
ELAN Agent should only be connected once to every VLAN, ie do not connect the same VLAN on 2 different NICs.
However, if those vlans are completly separate, it can be connected to 2 vlans with the same identifier on different interfaces.

:topic:
  `conf/vlans`
:format:
  *list* of vlan definitions:

  .. code-block:: json

    [
      {
        "id":                        <int>               // Unique ID for the vlan so it can referenced by other vlans.
        "interface":                 <str: *Mandatory*>, // Nic Name
        "vlan_id":                   <int: 0>,           // Vlan Identifier
        "access_control":            <bool: false>,      // Enable access control on that vlan
        "log":                       <bool: false>,      // Enable connection logging
        "ids":                       <bool: false>,      // Enable IDS on that vlan
        "web_authentication":        <int: null>,        // ID of Authentication to use when authenticating users on captive portal
        "guest_access":              <int: null>,        // ID of Guest Access to use on this vlan
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
 

Authentication Configuration
****************************

Authentications can be used by captive portal and 802.1X to authenticate users against existing user databases.

:topic:
  `conf/authentication`
:format:
  *list* of authentication definitions:

  :*LDAP*:
    User will be authenticated using the following attributes for the password: `userPassword`, `ntPassword` or `sambaNTPassword`.

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

  :*Active Directory*:
    Authentication will be performed by joining the AD domain. Only one AD is supported.

  .. code-block:: json

    {
      "id":         <int: *Mandatory*>, // id that can be used in members of a group.
      "type":       "active-directory",
      "domain":     <str: *Mandatory*>, // domain to join. Should resolvable by agent DNS.
      "adminLogin": <str: null>,        // admin login used to register to domain
      "adminPwd":   <str: null>,        // password of admin.
    }

  :*External*:
    Authentication will be made by doing a request via MQTT. Unknown Authentication IDs will be considered external, so you don't really need to declare them.

  .. code-block:: json

    {
      "id":   <int: *Mandatory*>, // id that can be used in members of a group.
      "type": <str: external>,    // unknown authentication types will be considered external
    }

  :*Groups*:
    Authentication will be tried among members of the group, in the order defined.
    Nested and circular groups are supported. 
    If an authentication has been tried once, it will not be retried, even if it appears in several groups that are members of the group.

  .. code-block:: json

    {
      "id":      <int: *Mandatory*>,       // id that can be used in members of a group.
      "type":    "group",
      "members": <list of ints: []>   // list of authentication IDs. If an ID is not present in list of authentication, it will be considered as external. 
    }

RADIUS Configuration
********************
Radius will support both 802.1X and MAC-authentication. It will accept all incoming request with the correct `secret`.
All network equipments share the same RADIUS secret.


:topic:
  `conf/radius`
:format: 

  .. code-block:: json
  
    {
      "default_secret": <str: *Mandatory*>, // Secret used to authenticate RADIUS requests
      "dot1x_authentication": <int>         // authentication id to be used for user during 802.1X requests. Can be a group.
      "cert_chain":           <str>         // PEM encoded Certificate Chain to return to 802.1X client.
      "cert_key":             <str>         // PEM encoded Private key
    }

SNMP Configuration
******************
SNMP configuration is used for both SNMP polling and SNMP Trap/Informs.
Several credentials can be used, on first poll first one to succeed will be used. SNMPv3 credentials will be tried, then v2c, and finally v1.

:topic:
  `conf/snmp`
:format: 

  .. code-block:: json
  
    {
      "credentials": [
        {
          "community":  <str: *Mandatory*>, // Community for SNMP v2c and v1
                                            // or User for SNMPv3 (
                                            //    NoAuth NoPriv if `auth_key` not present,
                                            //    Auth noPriv if `auth_key` present but not `priv_key`,
                                            //    or Auth Priv if both `auth_key` and `priv_key` present)
          "auth_proto": <str>,              // MD5 or SHA
          "auth_key":   <str>,              // If present, used for SNMPv3 Auth (NoPriv or Priv if `priv_key` present)
          "priv_proto": <str>,              // DES or AES
          "priv_key":   <str>,              // If present, used for SNMPv3 Auth Priv
        },
        ...
      ],
      "engine_ids": <list of str: []> // list of Engine IDs used in SNMPv3 Informs. Hex string without leading 0x.
    }


Guest Access Configuration
**************************
Guest Access Service gives the ability to guest to fill up a form that is then submitted to the `guest-request` service that can take the necessary actions to allow the guest on the network.
The `guest-request` service is to be implement according to your needs.

:topic:
  `conf/guest-access`
:format:

  .. code-block:: json
  
    [
      {
        "id":     <int>,     // ID that can be used in vlan definitions for `guest_access`.
        "modification_time": // Sent at each Guest Request so we can invalidate authz if guest access has been updated.
        "fields": [          // list of form fields that guest can fill on captive portal to get access
          {
            "id":                  <str: *Mandatory*>,       // unique id of field.
            "type":                <str: *Mandatory*>,       // `text`, `textarea`, `email`, `date`, `date-time`, `time`.
            "display_name":        <str>,                    // Name displayed before the form field.
            "required":            <bool: true>,             // Whether that field must be filled by guest.
            "validation_patterns": <*list* of patterns: []>, // if not empty, field should match matches at least one of the patterns (for example `*@my-domain.com` for an email)
          },
          ...
        ],
        "description": <html: "">, // Description that sits above the guest request form.
        "policy":      <html: "">, // User Policy Agreement that is displayed below the guest request form/
      },
      ...
    ]
    

Active Authorizations
---------------------

This is used to tell ELAN agent what are the current active guest access authorization.
This can for example be used by your implementation of `guest-request` service.
When an authorization is revoked, republish list of active authorizations without it.
Timeouts (`till` parameter) are taken care automatically, no need to republish the list once timedout.

:topic:
  `conf/guest-access/active-authorizations`
:format:

  .. code-block:: json

    [
      {
        "id":             <int>,              // id of the authorization
        "mac":            <mac>,              // device allowed by guest access
        "till":           <UTC ISO8601 date>, // validity of authorization
        "sponsor_login":  <str>,              // Login used to authenticate sponsor.
        "sponsor_authentication_provider":    // id of authentication provider used to authenticate sponsor
      },
      ...
    ]



Services
########

These are services ELAN Agent relies on but are not implemented, so they can be defined to match closely your needs.
Services are RPC services that listen to a topic for a request and send an answer.

* They can be implemented using python:

.. code-block:: python

  from elan.neuron import Dendrite, RequestError
  
  def my_service(request, service):
    # .. process request...
    
    return {'json': 'serializable', 'object': ''}
    
    # or
    
    raise RequestError(errors={'json': 'serializable', 'error': 'object'}, error_str='an error string')
  
  dendrite = Dendrite()
  
  dendrite.provide('my-service', cb=my_service)

* or directly using MQTT requests:

  --> TODO

Registration
************

:service:
  `check-connectivity`
:purpose:
  Used to register agent to a control center for example. 

  With no request data, used to check if registration service is implemented.
:request format:
  `{'login': ..., 'password': ...}`
:returns:
  returns on success (return value ignored)

  raises RequestError on failure

Connectivity
************

:service:
  `check-connectivity`
:purpose:
  Used to check connectivity of registration service
:request format:
  None
:returns:
  returns on success  (return value ignored)

  raises RequestError on failure


External Authentications
************************

You can implement extra authentication schemes by implementing the following:

:service:
  `authentication/external/authorize`
:purpose:
  return authentication information about user to be able to authenticate him
:request format:

  .. code-block:: json

    { 
      "provider": // authentication ID to use
      "source":   // 'radius-dot1x' or 'captive-portal-web'
      "login":    
      "password" // not always available, depending on authentication scheme. 
    }
    
:returns:
  Nothing if authentication information could not be found.
  
  or
  
  .. code-block:: json

    {
      "Cleartext-Password":,
      // or
      "NT-Password":,
      // or
      "LM-Password":,
      // or
      "Password-With-Header":,
      
      "provider": # real provider that gave this auth information if different of one from request (for example an external group).
    }

  Even if password was sent in request, it is important to return it in `Cleartext-Password` to confirm it is the correct password.

Guest Request
*************

You can implement guest access authorization using:

:service:
  `guest-request`
:purpose:
  Send guest request for validation (other that field validation).
  It is then the responsibility of the implemented service to grant access to the guest
:request format:

  .. code-block:: json

    { 
      "guest_access":                   // id of the guest access
      "guest_access_modification_time": // modification time of the guest access when it was displayed to guest.
      "mac":                            // MAC address of the device requesting guest access
      "fields": [                       // fields sent by guest request form.
        {
          "display_name": // name of the field as configured in Guest Access Configuration.
          "type":         // type of the field as configured in Guest Access Configuration.
          "value":        // value of the field, validated against `type`.
          "field_id":     // id of the field as configured in Guest Access Configuration.
        },
        ...
      ],
      "vlan_id":    // VLAN Identifier of the received request.
      "interface":  // Interface the request was received on.
    }
    
:returns:
  Nothing if request accepted.
  raise RequestError to send back errors to guest requesting access.


Device Authorization
********************

:service:
  `device-authorization`
:purpose:
  Get device authorization (allowed VLANs to be one, allowed VLANs to access).
:request format:

  .. code-block:: json

    {
      "mac":             // device we want to get authorizations for.
      "auth_sessions": [ // list of authentication sessions (802.1x, captive portal or guest authorization)
        {
          "source": <str>,           // captive-portal-web, radius-dot1x, ...
          "till": <epoch>,           // till when this authorization is valid
          "till_disconnect": <bool>, // invalidate authorization on disconnect.
          "authentication_provider":,
          ...
        },
        ...
      ],
      "port": {
        "local_id":  // switch local id.
        "interface": // interface name.
        "ssid":      // ssid mac is connected to, if any
      }
    }
    
:returns:

  .. code-block:: json

    {
      "assign_vlan": <int>,      // VLAN Identifier the device should be assigned during 802.1x, mac-auth, or by SNMP.
      "allowed_on":[]            // list of interface names like eth0.100 where eth0 is interface and 100 is vlan identifier (none if untagged vlan) on which the device is allowed to be.
      "bridge_to": []            // list of interface names like eth0.100 where eth0 is interface and 100 is vlan identifier (none if untagged vlan) to which device has access.
      "till": <epoch>,           // till when this authorization is valid
      "till_disconnect": <bool>, // invalidate authorization on disconnect.
    }

Events
######

Connections
***********

:topic:
  `connection`
:format:

  .. code-block:: json
  
    {
      "src": { // source details
        "ip": <ip>,
        "mac": <mac>,  
        "port": <str>, // Layer 4 (tcp/ugp) port
        "vlan": <str>, // vlan as seen by ELAN agent in the form <device>.<vlan_id>
      },
      "dst": { // destination details
        "ip": <ip>,
        "mac": <mac>,  
        "port": <str>, // Layer 4 (tcp/ugp) port
        "vlan": <str>, // vlan as seen by ELAN agent in the form <device>.<vlan_id>
      },
      "start": <UTC ISO8601 date>,
      "transport": <str>, // transport protocol: udp, tcp, ...
      "protocol": <str>   // detected protocol
    }

Authorizations
**************

Sent when authorization is granted and when it is no longer valid.

:topic:
  `session/authorization`
:format:

  .. code-block:: json

      {
        "mac":      <mac>,
        "local_id": <int>,   // local tracking id that will be used for updates (on termination of the authorization for example)
        "till_disconnect": true, // should authorization end on disconnect
        "till": <UTC ISO8601 date>, // expiry time of authorization
        "start": "2018-06-14T08:33:15Z", // when it effectively started
        "assign_vlan": <int>, // what vlan_id may have been assigned.
        "allow_on":  <list of vlans: []>, // list of vlans, in the form <device>.<vlan_id> the device is allowed on.
        "bridge_to": <list of vlans: []>, // list of vlans, in the form <device>.<vlan_id> the device is allowed to access (assuming it is on an authorized vlan).
        "end": <UTC ISO8601 date>,  // when it effectively ended
        "termination_reason": <str>, // can be 'revoked', 'expired', 'overriden', ...
      }

Mac Session
***********

If detected at the same time as a vlan or ip event, will not be sent as all information is included in those events.

:topic:
  `session/mac`

VLAN Session
************

If detected at the same time as a ip event, will not be sent as all information is included in that events.

:topic:
  `session/vlan`

IP Session
**********

:topic:
  `session/ip`

SNMP Information
****************

:topic:
  `snmp`

Device DHCP Fingerprint
***********************
:topic:
  `mac/fingerprint`

Device Hostname
***************

:topic:
  `mac/hostname`

