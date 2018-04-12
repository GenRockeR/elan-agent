Overview
########

ELAN Agent is platform to ease LAN management by providing several services:

- NAC: 802.1X/Mac-Auth via RADIUS.
- Access Control of devices to VLANs.
- Detection of unauthorized devices.
- Authentication using LDAP, AD or external source.
- Inventory of all devices (MAC addresses) on the network.
- Captive portal: User Authentication & Guest Access.
- IDS (Suricata).
- Log of Networks events (New Device, New device on VLAN, New Device IP, diconnected Device, New connection, IDS alert for device...).
- Log of outgoing connections.

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
        "id":     <int>, // ID that can be used in vlan definitions for `guest_access`.
        "fields": [      // list of form fields that guest can fill on captive portal to get access
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

This is not really a configuration but can be used to tell ELAN agent what are the current active guest access authorization.
This can for example be used by your implementation of `guest-request` service.

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
:request format:
  `{'login': ..., 'password': ...}`
:purpose:
  Used to register agent to a control center for example.

  With no request data, used to check if registration service is implemented.
:returns:
  returns on success (return value ignored)

  raises RequestError on failure

Connectivity
************

:service:
  `check-connectivity`
:request format:
  None
:purpose:
  Used to check connectivity of registration service
:returns:
  returns on success  (return value ignored)

  raises RequestError on failure


External Authentications
************************

You can implement external authentication by implementing the following:

:service:
  `authentication/external/authorize`
:request format:

  .. code-block:: json

    { 
      "provider": // authentication ID to use
      "source":   // 'radius-dot1x' or 'captive-portal-web'
      "login":    
      "password" // not always available, depending on authentication scheme. 
    }
    
:purpose:
  return authentication information about user to be able to authenticate him
:returns:

  .. code-block:: json

    {
      "Cleartext-Password":,
      // or
      "NT-Password":,
      // or
      "LM-Password":,
      // or
      "Password-With-Header":,
      
      "provider": # real provider that gave this auth information if different of one from request.
    }

  Even if password was sent in request, it is important to return it in `Cleartext-Password` to confirm it is the correct password.



Device Authorizations
*********************

Guest Access
************

-> action url -> return other fields modified or unchanged...

Guest Access Authorizations
***************************

Check Mac Authorizations
************************


Events
######

#TODO
new mac session, new IP session for mac, new vlan session for mac, mac on port...


