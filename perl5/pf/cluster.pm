package pf::cluster;

=head1 NAME

pf::cluster

=cut

=head1 DESCRIPTION

Interface to get information about the cluster based on the cluster.conf

=cut

use strict;
use warnings;

use Exporter;
our ( @ISA, @EXPORT );
@ISA = qw(Exporter);
@EXPORT = qw($cluster_enabled);

our $cluster_enabled = 0;


sub current_server {
}


1;
