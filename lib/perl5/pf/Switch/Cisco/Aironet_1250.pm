package pf::Switch::Cisco::Aironet_1250;

=head1 NAME

pf::Switch::Cisco::Aironet_1250 - Object oriented module to access SNMP enabled Cisco Aironet 1250 APs

=head1 SYNOPSIS

The pf::Switch::Cisco::Aironet_1250 module implements an object oriented interface
to access SNMP enabled Cisco Aironet_1250 APs.

This modules extends pf::Switch::Cisco::Aironet

=cut

use strict;
use warnings;
use Log::Log4perl;
use Net::SNMP;

use base ('pf::Switch::Cisco::Aironet');

sub description { 'Cisco Aironet 1250' }

=head1 AUTHOR

Inverse inc. <info@inverse.ca>

=head1 COPYRIGHT

Copyright (C) 2005-2013 Inverse inc.

=head1 LICENSE

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
USA.

=cut

1;
