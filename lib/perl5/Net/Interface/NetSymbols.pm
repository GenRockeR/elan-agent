#!/usr/bin/perl
#
# DO NOT ALTER THIS FILE
# IT IS WRITTEN BY Makefile.PL and inst/netsymbols.pl
# EDIT THOSE INSTEAD
#
package Net::Interface::NetSymbols;
use vars qw($VERSION @EXPORT_OK %EXPORT_TAGS);

$VERSION = 1.01;

my @afs = qw(
);
my @pfs = qw(
);
my @ifs = qw(
	IFF_POINTOPOINT
	IFHWADDRLEN
	IFNAMSIZ
	IFF_UP
	IFF_PROMISC
	IFF_NOTRAILERS
	IFF_LOOPBACK
	IFF_SLAVE
	IFF_MASTER
	IFF_DEBUG
	IFF_RUNNING
	IFF_AUTOMEDIA
	IF_NAMESIZE
	IFF_NOARP
	IFF_ALLMULTI
	IFF_BROADCAST
	IFF_PORTSEL
	IFF_MULTICAST
	IFF_DYNAMIC
);
my @iffs = qw(
	IFF_ALLMULTI
	IFF_AUTOMEDIA
	IFF_BROADCAST
	IFF_DEBUG
	IFF_DYNAMIC
	IFF_LOOPBACK
	IFF_MASTER
	IFF_MULTICAST
	IFF_NOARP
	IFF_NOTRAILERS
	IFF_POINTOPOINT
	IFF_PORTSEL
	IFF_PROMISC
	IFF_RUNNING
	IFF_SLAVE
	IFF_UP
);
my @iffIN6 = qw(
);
my %unique = (
);

my @iftype = qw(
    IPV6_ADDR_ANY
    IPV6_ADDR_UNICAST
    IPV6_ADDR_MULTICAST
    IPV6_ADDR_ANYCAST
    IPV6_ADDR_LOOPBACK
    IPV6_ADDR_LINKLOCAL
    IPV6_ADDR_SITELOCAL
    IPV6_ADDR_COMPATv4
    IPV6_ADDR_SCOPE_MASK
    IPV6_ADDR_MAPPED
    IPV6_ADDR_RESERVED
    IPV6_ADDR_ULUA
    IPV6_ADDR_6TO4
    IPV6_ADDR_6BONE
    IPV6_ADDR_AGU
    IPV6_ADDR_UNSPECIFIED
    IPV6_ADDR_SOLICITED_NODE
    IPV6_ADDR_ISATAP
    IPV6_ADDR_PRODUCTIVE
    IPV6_ADDR_6TO4_MICROSOFT
    IPV6_ADDR_TEREDO
    IPV6_ADDR_ORCHID
    IPV6_ADDR_NON_ROUTE_DOC
);

my @scope = qw(
    RFC2373_GLOBAL
    RFC2373_ORGLOCAL
    RFC2373_SITELOCAL
    RFC2373_LINKLOCAL
    RFC2373_NODELOCAL
    LINUX_COMPATv4
);

@EXPORT_OK = (@afs,@pfs,@ifs,@iftype,@scope);
%EXPORT_TAGS = (
	all	=> [@afs,@pfs,@ifs,@iftype,@scope],
	afs	=> [@afs],
	pfs	=> [@pfs],
	ifs	=> [@ifs],
	iffs	=> [@iffs],
	iffIN6	=> [@iffIN6],
	iftype	=> [@iftype],
	scope	=> [@scope],
);

sub NI_ENDVAL {return 2147483647};
sub NI_UNIQUE {return \%unique};
sub DESTROY {};

1;
__END__

=head1 NAME

Net::Interface::NetSymbols - AF_ PF_ IFxxx type symbols

=head1 SYNOPSIS

This module is built for this specific architecture during the F<make> 
process using F<inst/netsymbols.pl>. Do not edit this module, edit
F<inst/netsymbols.pl> instead.

This module contains symbols arrays only for use by Net::Interface, in all other
respects it is NOT functional. It contains documentation and data arrays 
for this specific architecture.

B<NOTE:>	WARNING !!

     usage is Net::Interface

B<NOT>  Net::Interface::NetSymbols

use Net::Interface qw(

	Net::Interface::NetSymbols::NI_ENDVAL();
	Net::Interface::NetSymbols::NI_UNIQUE();




IFF_POINTOPOINT IFHWADDRLEN IFNAMSIZ IFF_UP IFF_PROMISC IFF_NOTRAILERS IFF_LOOPBACK IFF_SLAVE IFF_MASTER IFF_DEBUG IFF_RUNNING IFF_AUTOMEDIA IF_NAMESIZE IFF_NOARP IFF_ALLMULTI IFF_BROADCAST IFF_PORTSEL IFF_MULTICAST IFF_DYNAMIC

IFF_ALLMULTI IFF_AUTOMEDIA IFF_BROADCAST IFF_DEBUG IFF_DYNAMIC IFF_LOOPBACK IFF_MASTER IFF_MULTICAST IFF_NOARP IFF_NOTRAILERS IFF_POINTOPOINT IFF_PORTSEL IFF_PROMISC IFF_RUNNING IFF_SLAVE IFF_UP

:all :afs :pfs :ifs :iffs :iftype :scope

);

=head1 DESCRIPTION

All of the AF_XXX and PF_XXX symbols available in local C<sys/socket.h> plus
usual aliases for AF_LOCAL i.e. (AF_FILE AF_UNIX PF_LOCAL PF_FILE PF_UNIX)

All of the IFxxxx and IN6_IF symbols in C<net/if.h, netinet/in.h, netinet/in_var.h> and
their includes.

Symbols may be accessed for their numeric value or their string name.

  i.e.	if ($family == AF_INET)
	    do something...

    or	print AF_INET
    will product the string "inet"

The same holds true for:

	printf("family is %s",AF_INET);
    or	sprint("family is %s",AF_INET);

To print the numeric value of the SYMBOL do:

	print (0 + SYMBOL), "\n";


=over 4

=item * :all	Import all symbols

=item * :afs	Import all AF_XXX symbols

=item * :pfs	Import all PF_XXX symbols

=item * :ifs	Import all IFxxxx symbols

=item * :iffs	Import all IFF symbols

=back

=head1 non EXPORT functions

=over 4

=item * Net::Interface::NetSymbols::NI_ENDVAL();

Reports the highest symbol value +1 of :all symbols above. Used for testing.

=item * Net::Interface::NetSymbols::NI_UNIQUE();

Returns a hash pointer to the AF_ or PF_ symbol values mapped to their
character strings as defined for this architecture.

  i.e.

=head1 AUTHOR	Michael Robinton <michael@bizsystems.com>

=head1 COPYRIGHT	2014

Michael Robinton, all rights reserved.

This library is free software. You can distribute it and/or modify it under
the same terms as Perl itself.

=cut

1;
