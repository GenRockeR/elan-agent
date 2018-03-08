package pf::CHI;

=head1 NAME

pf::CHI add documentation

=cut

=head1 DESCRIPTION

pf::CHI

=cut

use strict;
use warnings;
use base qw(CHI);

our @CACHE_NAMESPACES = qw(configfilesdata configfiles httpd.admin httpd.portal pfdns switch.overlay ldap_auth omapi fingerbank firewall_sso switch metadefender accounting clustering person_lookup route_int provisioning switch_distributed);

our %DEFAULT_CONFIG = (
    'namespace' => {
        map { $_ => { 'storage' => 'raw' } } @CACHE_NAMESPACES
    },
    'memoize_cache_objects' => 1,
    'defaults'              => {'serializer' => 'Sereal'},
    'storage'               => {
        'raw' => {
            'global' => '1',
            'driver' => 'RawMemory'
        }
    }
);

__PACKAGE__->config(\%DEFAULT_CONFIG);


1;
