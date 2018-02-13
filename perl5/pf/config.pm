package pf::config;

=head1 NAME

pf::config - PacketFence configuration

=cut

=head1 DESCRIPTION

pf::config 

=cut

use strict;
use warnings;
use Readonly;

use Exporter;
our ( @ISA, @EXPORT_OK );
@ISA = qw(Exporter);
# Categorized by feature, pay attention when modifying
@EXPORT_OK = qw(
        @listen_ints @dhcplistener_ints @ha_ints $monitor_int
        @internal_nets @routed_isolation_nets @routed_registration_nets @inline_nets $management_network @portal_ints @radius_ints
        @inline_enforcement_nets @vlan_enforcement_nets
        $IPTABLES_MARK_UNREG $IPTABLES_MARK_REG $IPTABLES_MARK_ISOLATION
        %mark_type_to_str %mark_type
        $MAC $PORT $SSID $ALWAYS
        %Default_Config
        %Config
        %ConfigNetworks %ConfigAuthentication %ConfigOAuth
        %ConfigFloatingDevices
        $ACCOUNTING_POLICY_TIME $ACCOUNTING_POLICY_BANDWIDTH
        $WIPS_VID $thread $fqdn $reverse_fqdn
        $IF_INTERNAL $IF_ENFORCEMENT_VLAN $IF_ENFORCEMENT_INLINE $IF_ENFORCEMENT_DNS
        $WIRELESS_802_1X $WIRELESS_MAC_AUTH $WIRED_802_1X $WIRED_MAC_AUTH $WIRED_SNMP_TRAPS $UNKNOWN $INLINE
        $NET_TYPE_INLINE $NET_TYPE_INLINE_L2 $NET_TYPE_INLINE_L3
        $WIRELESS $WIRED $EAP
        $WEB_ADMIN_NONE $WEB_ADMIN_ALL
        $VOIP $NO_VOIP $NO_PORT $NO_VLAN
        %connection_type %connection_type_to_str %connection_type_explained %connection_type_explained_to_str
        %connection_group %connection_group_to_str
        $RADIUS_API_LEVEL $ROLE_API_LEVEL $INLINE_API_LEVEL $AUTHENTICATION_API_LEVEL $BILLING_API_LEVEL
        $ROLES_API_LEVEL
        $SELFREG_MODE_EMAIL $SELFREG_MODE_SMS $SELFREG_MODE_SPONSOR $SELFREG_MODE_GOOGLE $SELFREG_MODE_FACEBOOK $SELFREG_MODE_GITHUB $SELFREG_MODE_INSTAGRAM $SELFREG_MODE_LINKEDIN $SELFREG_MODE_PRINTEREST $SELFREG_MODE_WIN_LIVE $SELFREG_MODE_TWITTER $SELFREG_MODE_NULL $SELFREG_MODE_KICKBOX $SELFREG_MODE_BLACKHOLE
        %CAPTIVE_PORTAL
        $HTTP $HTTPS
        access_duration
        $BANDWIDTH_DIRECTION_RE $BANDWIDTH_UNITS_RE
        is_vlan_enforcement_enabled is_inline_enforcement_enabled is_dns_enforcement_enabled is_type_inline
        $LOG4PERL_RELOAD_TIMER
        @Profile_Filters %Profiles_Config
        %ConfigFirewallSSO
        $OS
        $DISTRIB $DIST_VERSION
        %Doc_Config
        %ConfigRealm
        %ConfigProvisioning
        %ConfigDomain
        $default_pid
        %ConfigScan
        %ConfigWmi
        %ConfigPKI_Provider
        %ConfigDetect
        %ConfigBillingTiers
        %ConfigAdminRoles
        %ConfigPortalModules
        $local_secret
        %ConfigSwitchesGroup
        %ConfigSwitchesList
        %ConfigReport
        %ConfigSurvey
        %ConfigRoles
        %ConfigDeviceRegistration
);


# Accounting trigger policies
Readonly::Scalar our $ACCOUNTING_POLICY_TIME => 'TimeExpired';
Readonly::Scalar our $ACCOUNTING_POLICY_BANDWIDTH => 'BandwidthExpired';


Readonly our $WIPS_VID => '1100020';

# Interface types
Readonly our $IF_INTERNAL => 'internal';

# Interface enforcement techniques
# connection type constants
Readonly our $WIRELESS_802_1X   => 0b110000001;
Readonly our $WIRELESS_MAC_AUTH => 0b100000010;
Readonly our $WIRED_802_1X      => 0b011000100;
Readonly our $WIRED_MAC_AUTH    => 0b001001000;
Readonly our $WIRED_SNMP_TRAPS  => 0b001010000;
Readonly our $INLINE            => 0b000100000;
Readonly our $UNKNOWN           => 0b000000000;
# masks to be used on connection types
Readonly our $WIRELESS => 0b100000000;
Readonly our $WIRED    => 0b001000000;
Readonly our $EAP      => 0b010000000;

# Catalyst-based access level constants
Readonly::Scalar our $ADMIN_USERNAME => 'admin';
Readonly our $WEB_ADMIN_NONE => 0;
Readonly our $WEB_ADMIN_ALL => 4294967295;

# TODO we should build a connection data class with these hashes and related constants
# String to constant hash
our %connection_type = (
    'Wireless-802.11-EAP'   => $WIRELESS_802_1X,
    'Wireless-802.11-NoEAP' => $WIRELESS_MAC_AUTH,
    'Ethernet-EAP'          => $WIRED_802_1X,
    'Ethernet-NoEAP'        => $WIRED_MAC_AUTH,
    'SNMP-Traps'            => $WIRED_SNMP_TRAPS,
    'Inline'                => $INLINE,
    'WIRED_MAC_AUTH'        => $WIRED_MAC_AUTH,
);
our %connection_group = (
    'Wireless'              => $WIRELESS,
    'Ethernet'              => $WIRED,
    'EAP'                   => $EAP,
);

# Their string equivalent for database storage
our %connection_type_to_str = (
    $WIRELESS_802_1X => 'Wireless-802.11-EAP',
    $WIRELESS_MAC_AUTH => 'Wireless-802.11-NoEAP',
    $WIRED_802_1X => 'Ethernet-EAP',
    $WIRED_MAC_AUTH => 'WIRED_MAC_AUTH',
    $WIRED_SNMP_TRAPS => 'SNMP-Traps',
    $INLINE => 'Inline',
    $UNKNOWN => '',
);
our %connection_group_to_str = (
    $WIRELESS => 'Wireless',
    $WIRED => 'Ethernet',
    $EAP => 'EAP',
);

# String to constant hash
# these duplicated in html/admin/common.php for web admin display
# changes here should be reflected there
our %connection_type_explained = (
    $WIRELESS_802_1X => 'WiFi 802.1X',
    $WIRELESS_MAC_AUTH => 'WiFi MAC Auth',
    $WIRED_802_1X => 'Wired 802.1x',
    $WIRED_MAC_AUTH => 'Wired MAC Auth',
    $WIRED_SNMP_TRAPS => 'Wired SNMP',
    $INLINE => 'Inline',
    $UNKNOWN => 'Unknown',
);

our %connection_type_explained_to_str = map { $connection_type_explained{$_} => $connection_type_to_str{$_} } keys %connection_type_explained;

# VoIP constants
Readonly our $VOIP    => 'yes';
Readonly our $NO_VOIP => 'no';

# API version constants
Readonly::Scalar our $RADIUS_API_LEVEL => 1.02;
Readonly::Scalar our $ROLE_API_LEVEL => 1.04;
Readonly::Scalar our $INLINE_API_LEVEL => 1.01;
Readonly::Scalar our $AUTHENTICATION_API_LEVEL => 1.11;
Readonly::Scalar our $BILLING_API_LEVEL => 1.00;
Readonly::Scalar our $ROLES_API_LEVEL => 0.90;

# to shut up strict warnings
#$ENV{PATH} = '/sbin:/bin:/usr/bin:/usr/sbin';

# Inline related
# Ip mash marks
# Warning: make sure to verify conf/iptables.conf for hard-coded marks if you change the marks here.
Readonly::Scalar our $IPTABLES_MARK_REG => "1";
Readonly::Scalar our $IPTABLES_MARK_ISOLATION => "2";
Readonly::Scalar our $IPTABLES_MARK_UNREG => "3";

our %mark_type = (
    'Reg'   => $IPTABLES_MARK_REG,
    'Isol' => $IPTABLES_MARK_ISOLATION,
    'Unreg'          => $IPTABLES_MARK_UNREG,
);

# Their string equivalent for database storage
our %mark_type_to_str = (
    $IPTABLES_MARK_REG => 'Reg',
    $IPTABLES_MARK_ISOLATION => 'Isol',
    $IPTABLES_MARK_UNREG => 'Unreg',
);

# Use for match radius attributes

Readonly::Scalar our $MAC => "mac";
Readonly::Scalar our $PORT => "port";
Readonly::Scalar our $SSID => "ssid";
Readonly::Scalar our $ALWAYS => "always";


Readonly::Scalar our $NO_PORT => 0;
Readonly::Scalar our $NO_VLAN => 0;

# Log Reload Timer in seconds
Readonly our $LOG4PERL_RELOAD_TIMER => 5 * 60;

# simple cache for faster config lookup
my $cache_vlan_enforcement_enabled;
my $cache_inline_enforcement_enabled;
my $cache_dns_enforcement_enabled;

# Bandwdith accounting values
our $BANDWIDTH_DIRECTION_RE = qr/IN|OUT|TOT/;
our $BANDWIDTH_UNITS_RE = qr/B|KB|MB|GB|TB/;

