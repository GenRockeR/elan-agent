package pf::log;

use strict;
use warnings;

use Exporter;
our ( @ISA, @EXPORT );
@ISA = qw(Exporter);
@EXPORT = qw(get_logger);


use Log::Log4perl qw(:easy);    
Log::Log4perl->easy_init({ level    => $DEBUG,
                           layout   => "%p %c: %m%n"
                         });

1;
