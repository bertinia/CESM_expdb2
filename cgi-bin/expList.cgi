#!/usr/bin/env perl
#
use warnings;
use strict;
use CGI qw(:standard);
use Email::Simple;
use Email::Sender::Simple qw(sendmail);
use Email::Sender::Transport::Sendmail qw();
use DBI;
use DBD::mysql;
use Time::localtime;
use HTML::Entities;
use CGI::Carp qw(fatalsToBrowser warningsToBrowser); 
use CGI::Session qw/-ip-match/;
use Data::FormValidator;
use Template;
use lib qw(.);
use lib "/home/www/html/csegdb/lib";
use config;
use session;
use user;
use lib "/home/www/html/expdb2.0/lib";
use expdb2_0;

#------
# main 
#------
$ENV{PATH} = '';

my $req = CGI->new;
my %config = &getconfig;
my $dbname = $config{'dbname'};
my $dbhost = $config{'dbhost'};
my $dbuser = $config{'dbuser'};
my $dbpasswd = $config{'dbpassword'};
my $dsn = $config{'dsn'};

# initialize item hash that stores all the info
my %item = ();

# initialize validstatus hash for form feedback
my %validstatus;
$validstatus{'status'} = 1;
$validstatus{'message'} = '';

# Check the session, see if it's still valid. This will redirect to login page if needed.
my ($loggedin, $session) = &checksession($req);
my $cookie = $req->cookie(CGISESSID => $session->id);
my $sid = $req->cookie('CGISESSID');
# DEBUG
##my $loggedin = 1;

my $dbh = DBI->connect($dsn, $dbuser, $dbpasswd) or die "unable to connect to db: $DBI::errstr";

if($loggedin == 0)
{
    $dbh->disconnect;
    &sessionexpired;
}
else
{
#
# get the logged in user info and version loaded into the item hash
# note: the current version name and id is read from the config file
#
    $item{luser_id} = $session->param('user_id');
    $item{llastname} = $session->param('lastname');
    $item{lfirstname} = $session->param('firstname');
    $item{lemail} = $session->param('email');
    $item{version} = $session->param('version');
    $item{version_id} = $session->param('version_id');
#DEBUG
##    $item{llastname} = 'Bertini';
##    $item{lfirstname} = 'Alice';
##    $item{lemail} = 'aliceb@ucar.edu';
}
&doActions();

#---------
# end main
#---------
sub doActions()
{
    # get the action parameter from the URL
    my $action;
    if (defined $req->param('action'))
    {
	$action = $req->param('action');
    }
    else
    {
	$action = '';
    }

    # get the status parameter from the URL
    if (defined $req->param('status')) 
    {
	$validstatus{'status'} = $req->param('status');
    }

    # get the statusMsg parameter from the URL
    if (defined $req->param('statusMsg'))
    {
	$validstatus{'message'} = $req->param('statusMsg');
    }

    # call the function corresponding to the requested action
    if ( length($action) == 0)
    {
	&showExpList(\%validstatus);
    }
    if ($action eq "showCMIP6Exps")
    {
	&showCMIP6Exps;
    }
    if ($action eq "showCaseDetail")
    {
	&showCaseDetail($req->param('case_id'));
    }
    if ($action eq "expUpdate")
    {
    	&expUpdate();
    }
    if ($action eq "reserveCase")
    {
    	&reserveCase();
    }
}

#------------------
# showExpList - should always default to the CMIP6 experiments
#------------------

sub showExpList
{
    my $validstatus = shift;
    my @CMIP6Exps  = getCMIP6Experiments($dbh);
    my @CMIP6MIPs  = getCMIP6MIPs($dbh);
    my @CMIP6DECKs = getCMIP6DECKs($dbh);
    my @CMIP6DCPPs = getCMIP6DCPPs($dbh);
    my @cesm2exps  = getCasesByType($dbh, 2);
    my @projectA   = getCasesByType($dbh, 3);
    my @projectB   = getCasesByType($dbh, 4);
    my @allCases   = getAllCases($dbh);
    my @NCARUsers  = getNCARUsers($dbh);

    my $vars = {
	CMIP6Exps   => \@CMIP6Exps,
	CMIP6MIPs   => \@CMIP6MIPs,
	CMIP6DECKs  => \@CMIP6DECKs,
	CMIP6DCPPs  => \@CMIP6DCPPs,
	cesm2exps   => \@cesm2exps,
	projectA    => \@projectA,
	projectB    => \@projectB,
	allCases    => \@allCases,
	NCARUsers   => \@NCARUsers,
	authUser    => \%item,
	validstatus => $validstatus,
    };
	
    print $req->header(-cookie=>$cookie);
    my $tmplFile = '../templates/expList.tmpl';

    my $template = Template->new({
	ENCODING => 'utf8',
	RELATIVE => 1,
	INCLUDE_PATH => '/home/www/html/includes:/home/www/html/expdb2.0/templates',
				 });

    $template->process($tmplFile, $vars) || die ("Problem processing $tmplFile, ", $template->error());

}

#------------------
# showExpDetail
#------------------

sub showCaseDetail
{
    my $case_id = shift;
    my ($case, $fields, $status, @projects) = getCaseByID($dbh, $case_id);
    my @allCases = getAllCases($dbh);

    $validstatus{'status'} = 1;
    $validstatus{'message'} = '';

    if ($case->{'case_id'} < 0)
    {
	$validstatus{'status'} = 0;
	$validstatus{'message'} = 'Error - two or more case records found in database for case ID = $case_id';
    }
    elsif ($case->{'case_id'} == 0)
    {
	$validstatus{'status'} = 0;
	$validstatus{'message'} = 'Error - no case record found in database for case ID = $case_id';
    }

    my $vars = {
	case        => $case,
	fields      => $fields,
	status      => $status,
	projects    => \@projects,
	allCases    => \@allCases,
	authUser    => \%item,
	validstatus => \%validstatus,
    };

    print $req->header(-cookie=>$cookie);
    my $tmplFile = '../templates/expDetail.tmpl';

    my $template = Template->new({
	ENCODING => 'utf8',
	RELATIVE => 1,
	INCLUDE_PATH => '/home/www/html/includes:/home/www/html/expdb2.0/templates',
				 });

    $template->process($tmplFile, $vars) || die ("Problem processing $tmplFile, ", $template->error());

}

sub expUpdate
{
    # TODO update experiment details first check the security against svnuser_id, assign_id, and science_id
    # updates experiment values and returns by displaying expDetail
    # remember this is a POST so exp_id needs to be a hidden input!!
}

sub reserveCase
{
    my ($sql, $sth) = '';
    my ($sql1, $sth1) = '';
    my ($key, $value) = '';
    my (%scienceUser, %assignUser) = ();

    $validstatus{'status'} = 1;
    $validstatus{'message'} = '';

    foreach $key ( $req->param )  {
	$item{$key} = ( $req->param( $key ) );
    }
        
    # check if the casename already exists
    my ($exists, $case_id) = checkCase($dbh, $item{'case'});
    if ($exists) 
    {
	# Error - a casename already exists
	$validstatus{'status'} = 0;
	$validstatus{'message'} .= qq(Error - a case name already exists in the database for case name = $item{'case'}.\n);
    }

    # get the user assignments from the pulldown
    if ($item{'assignUser'} > 0) {
	%assignUser = getUserByID($dbh, $item{'assignUser'});
    }
    else {
	# Error - a user must be assigned
	$validstatus{'status'} = 0;
	$validstatus{'message'} .= qq(Error - A valid user must be assigned to this case.\n);
    }

    if ($item{'scienceUser'} > 0) {
	%scienceUser = getUserByID($dbh, $item{'scienceUser'});
    }
    else {
	# Error - a science lead must be assigned
	$validstatus{'status'} = 0;
	$validstatus{'message'} .= qq(Error - A valid user must be selected as the science lead for this case.\n);
    }

    # check that the expName value id is selected
    if ($item{'expName'} == 0) {
	# Error - a valid CMIP6 experiment name must be selected
	$validstatus{'status'} = 0;
	$validstatus{'message'} .= qq(Error - A valid CMIP6 experiment name must be associated with this case.\n);
    }

    # reserve this CMIP6 casename
    if ($validstatus{'status'})
    {
	# reserve the case
	my $case_name = $dbh->quote($item{'case'});
	$sql = qq(insert into t2_cases (casename, expType_id, is_ens) value ($case_name, 1, '$item{'ensemble'}'));
	$sth = $dbh->prepare($sql);
	print STDERR '>>> insert t2_cases sql = ' . $sql . '<<<<\n';
	$sth->execute();
	$sth->finish();

	# get the case id
	$sql = qq(select id from t2_cases where casename = $case_name);
	$sth = $dbh->prepare($sql);
	$sth->execute();
	my $case_id = $sth->fetchrow();
	$sth->finish();

	# insert notes
	my $note = $dbh->quote($item{'notes'});
	if (length($note) > 0)
	{
	    $sql = qq(insert into t2e_notes (case_id, note, last_update) value ($case_id, $note, NOW()));
	    $sth = $dbh->prepare($sql);
	    print STDERR '>>> insert t2e_notes sql = ' . $sql . '<<<<\n';
	    $sth->execute();
	    $sth->finish();
	}

	# update values in the t2j_cmip6 table based on the experiment association
	my $real_num = $dbh->quote($item{'ripf'});
	my $ensemble_size = 0;
	if(($item{'ensemble'} eq 'true') && defined ($item{'ensemble_size'}))
	{
	    $ensemble_size = $item{'ensemble_size'}
	}
	$sql = qq(update t2j_cmip6 set case_id = $case_id,
                  real_num = $real_num, assign_id = $item{'assignUser'},
                  science_id = $item{'scienceUser'}, ensemble_size = $ensemble_size,
                  request_date = NOW()
                  where exp_id = $item{'expName'});
	if ($item{'parentExp'} > 0)
	{
	    $sql = qq(update t2j_cmip6 set case_id = $case_id,
                      real_num = $real_num, assign_id = $item{'assignUser'},
                      science_id = $item{'scienceUser'}, ensemble_size = $ensemble_size,
                      parentExp_id = $item{'parentExp'}, request_date = NOW()
                      where exp_id = $item{'expName'});
	}
	print STDERR '>>> update t2j_cmip6 sql = ' . $sql . '<<<<\n';
	$sth = $dbh->prepare($sql);
	$sth->execute();
	$sth->finish();

	# insert pending entries in the t2j_status table for this case
	my %proc_stat;
	$sql = qq(select id, name from t2_process);
	$sth = $dbh->prepare($sql);
	$sth->execute() or die $dbh->errstr;
	while( my $ref = $sth->fetchrow_hashref() ) 
	{
	    $sql1 = qq(insert into t2j_status (case_id, status_id, process_id, last_update)
                       value ($case_id, 1, $ref->{'id'}, NOW()));
	    $sth1 = $dbh->prepare($sql1);
	    $sth1->execute() or die $dbh->errstr;
	    $sth1->finish();
	}
	$sth->finish();

	$validstatus{'message'} = qq(Success! CMIP6 $case_name is now reserved.);
	
	# send emails to svnuser login, assign_id and science_id
	my $msgbody = <<EOF;
$item{lfirstname} $item{llastname} has reserved a CMIP6 casename in the CESM Experiments 2.0 Database.
Please follow this link to review the submission.

http://csegweb.cgd.ucar.edu/expdb2.0 

1. Login using your CESM SVN developer login OR your UCAS login 
2. Select or click on the unique case name, $case_name, to review. 

This email is generated automatically by the Experiment Database. 
Replying to this email will go to $item{lfirstname} $item{llastname}.
EOF

        my $email = Email::Simple->create(
	    header => [
		From => $item{lemail},
##		To   => "$item{lemail} $assignUser{'email'} $scienceUser{'email'}",
		To   => "aliceb\@ucar.edu",
		Subject => "New CMIP6 experiment $case_name has been reserved in the CESM Experiments 2.0 Database",
	    ],
	    body => $msgbody,
	);

	sendmail($email, 
		 { from => $item{lemail},
		   transport => Email::Sender::Transport::Sendmail->new}
	    ) or die "can't send email!";

	my ($case, $fields, $status, $project) = getCaseByID($dbh, $case_id);
	
	# all is good - jump to the experiment detail screen
	my @allCases = getAllCases($dbh);
	my $vars = {
	    case        => $case,
	    fields      => $fields,
	    status      => $status,
	    project     => $project,
	    allCases    => \@allCases,
	    authUser    => \%item,
	    validstatus => \%validstatus,
	};

	print $req->header(-cookie=>$cookie);
	my $tmplFile = '../templates/expDetail.tmpl';

	my $template = Template->new({
	    ENCODING => 'utf8',
	    RELATIVE => 1,
	    INCLUDE_PATH => '/home/www/html/includes:/home/www/html/expdb2.0/templates',
				     });

	$template->process($tmplFile, $vars) || die ("Problem processing $tmplFile, ", $template->error());
    }
    else {
	# redirect back to the expList
	&showExpList(\%validstatus);
    }
}

$dbh->disconnect;
exit;
