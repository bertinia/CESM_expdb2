#!/usr/bin/env perl
#
# processJSON - read a JSON file generated by archive_metadata and
# load it into the expdb2.0 database.
#
use strict;
use CGI;
use CGI qw(:standard);
use CGI::Carp qw(fatalsToBrowser warningsToBrowser); 
use CGI::Session qw/-ip-match/;
use CGI::Carp qw(set_die_handler);
use DBI;
use DBD::mysql;
use JSON qw( decode_json );
use Time::Piece;
use Time::Seconds;
use URI::Escape;

use lib qw(.);
use lib "/home/www/html/csegdb/lib";
use config;
use session;
use lib "/home/www/html/expdb2.0/lib";
use expdb2_0;
use CMIP6;

# set up the logger
use Log::Log4perl;
Log::Log4perl->init("/usr/local/expdb-2.0.0/conf/expdb-json-log.conf");
my $logger = Log::Log4perl->get_logger();

my $req = CGI->new;

my %item;
my $status;
my $count;
my $last_update;
my ($sql, $sth);
my ($sql1, $sth1);

# get the username, password and JSON data that has been posted to the form
my $user = uri_unescape($req->param('username'));
my $password = uri_unescape($req->param('password'));
my $data = uri_unescape($req->param('data'));
my $loginType = 'SVN';

$logger->debug("username = " . $user);
$logger->debug("password = " . $password);
$logger->debug("data = " . $data);

# Get the necessary config vars 
my %config = &getconfig;
my $version_id = $config{'version_id'};
my $dbname = $config{'dbname'};
my $dbhost = $config{'dbhost'};
my $dbuser = $config{'dbuser'};
my $dbpasswd = $config{'dbpassword'};
my $dsn = $config{'dsn'};

# check the authentication
my ($authsuccessful, $autherror) = &svn_authenticate($user, $password);
if(!$authsuccessful)
{
    # problem with the authorization so return a 401 error
    print $req->header('text/html', '401 SVN username/password incorrect!');
    die "401 - Unauthorized";
}

my $count;
my @comps = qw(atm ice lnd ocn);
my %fields;
my $fields;
my %pp_fields;
my $pp_fields;
my $key = '';
my ($pname, $pid, $pstat_id);
my @keys = qw(casename caseroot caseuser compiler compset continue_run 
              dout_s dout_s_root grid job_queue job_time machine model 
              model_cost model_throughput model_version mpilib postprocess project 
              rest_n rest_option run_dir run_refcase run_refdate run_startdate 
              run_type stop_n stop_option svn_repo_url title);

my $dbh = DBI->connect($dsn, $dbuser, $dbpasswd) or die "unable to connect to db: $DBI::errstr";
my $jsonObj = JSON->new->allow_nonref;
my $json = $jsonObj->decode($data);

# get all the case data into a quotable format for the SQL calls
$fields{'casename'}         = $dbh->quote($json->{'CASE'});
$fields{'caseroot'}         = $dbh->quote($json->{'CASEROOT'});
$fields{'caseuser'}         = $dbh->quote($json->{'USER'});
$fields{'compiler'}         = $dbh->quote($json->{'COMPILER'});
$fields{'compset'}          = $dbh->quote($json->{'COMPSET'});
$fields{'continue_run'}     = $dbh->quote($json->{'CONTINUE_RUN'});
$fields{'dout_s'}           = $dbh->quote($json->{'DOUT_S'});
$fields{'dout_s_root'}      = $dbh->quote($json->{'DOUT_S_ROOT'});
$fields{'expType'}          = $dbh->quote($json->{'expType'});
$fields{'grid'}             = $dbh->quote($json->{'GRID'});
$fields{'job_queue'}        = $dbh->quote($json->{'JOB_QUEUE'});
$fields{'job_time'}         = $dbh->quote($json->{'JOB_WALLCLOCK_TIME'});
$fields{'machine'}          = $dbh->quote($json->{'MACH'});
$fields{'model'}            = $dbh->quote($json->{'MODEL'});
$fields{'model_cost'}       = $dbh->quote($json->{'model_cost'});
$fields{'model_throughput'} = $dbh->quote($json->{'model_throughput'});
$fields{'model_version'}    = $dbh->quote($json->{'MODEL_VERSION'});
$fields{'mpilib'}           = $dbh->quote($json->{'MPILIB'});
$fields{'postprocess'}      = $dbh->quote($json->{'postprocess'});
$fields{'project'}          = $dbh->quote($json->{'PROJECT'});
$fields{'rest_n'}           = $dbh->quote($json->{'REST_N'});
$fields{'rest_option'}      = $dbh->quote($json->{'REST_OPTION'});
$fields{'run_dir'}          = $dbh->quote($json->{'RUNDIR'});
$fields{'run_lastdate'}     = $dbh->quote($json->{'run_lastdate'});
$fields{'run_refcase'}      = $dbh->quote($json->{'RUN_REFCASE'});
$fields{'run_refdate'}      = $dbh->quote($json->{'RUN_REFDATE'});
$fields{'run_startdate'}    = $dbh->quote($json->{'RUN_STARTDATE'});
$fields{'run_type'}         = $dbh->quote($json->{'RUN_TYPE'});
$fields{'stop_n'}           = $dbh->quote($json->{'STOP_N'});
$fields{'stop_option'}      = $dbh->quote($json->{'STOP_OPTION'});
$fields{'svn_repo_url'}     = $dbh->quote($json->{'svn_repo_url'});
$fields{'svnlogin'}         = $dbh->quote($json->{'svnlogin'});
$fields{'title'}            = $dbh->quote($json->{'title'});

$fields{'run_status'}       = $json->{'run_status'};      
$fields{'run_size'}         = $json->{'run_size'};

$fields{'sta_status'}       = $json->{'sta_status'};      
$fields{'sta_size'}         = $json->{'sta_size'};

# get all the postprocess data into a quotable format for the SQL calls
# first key is the process name

if (lc($fields{'postprocess'}) eq 'true') {

    $pp_fields{'atm_averages'}{'status'}      = $json->{'atm_avg_status'};
    $pp_fields{'atm_averages'}{'size'}        = $json->{'atm_avg_size'};
    $pp_fields{'atm_averages'}{'path'}        = $dbh->quote($json->{'atm_avg_path'});
    $pp_fields{'atm_diagnostics'}{'status'}   = $json->{'atm_diag_status'};
    $pp_fields{'atm_diagnostics'}{'size'}     = $json->{'atm_diag_size'};
    $pp_fields{'atm_diagnostics'}{'path'}     = $dbh->quote($json->{'atm_diag_path'});

    $pp_fields{'lnd_averages'}{'status'}      = $json->{'lnd_avg_status'};
    $pp_fields{'lnd_averages'}{'size'}        = $json->{'lnd_avg_size'};
    $pp_fields{'lnd_averages'}{'path'}        = $dbh->quote($json->{'lnd_avg_path'});
    $pp_fields{'lnd_diagnostics'}{'status'}   = $json->{'lnd_diag_status'};
    $pp_fields{'lnd_diagnostics'}{'size'}     = $json->{'lnd_diag_size'};
    $pp_fields{'lnd_diagnostics'}{'path'}     = $dbh->quote($json->{'lnd_diag_path'});

    $pp_fields{'ice_averages'}{'status'}      = $json->{'ice_avg_status'};
    $pp_fields{'ice_averages'}{'size'}        = $json->{'ice_avg_size'};
    $pp_fields{'ice_averages'}{'path'}        = $dbh->quote($json->{'ice_avg_path'});
    $pp_fields{'ice_diagnostics'}{'status'}   = $json->{'ice_diag_status'};
    $pp_fields{'ice_diagnostics'}{'size'}     = $json->{'ice_diag_size'};
    $pp_fields{'ice_diagnostics'}{'path'}     = $dbh->quote($json->{'ice_diag_path'});

    $pp_fields{'ocn_averages'}{'status'}      = $json->{'ocn_avg_status'};
    $pp_fields{'ocn_averages'}{'size'}        = $json->{'ocn_avg_size'};
    $pp_fields{'ocn_averages'}{'path'}        = $dbh->quote($json->{'ocn_avg_path'});
    $pp_fields{'ocn_diagnostics'}{'status'}   = $json->{'ocn_diag_status'};
    $pp_fields{'ocn_diagnostics'}{'size'}     = $json->{'ocn_diag_size'};
    $pp_fields{'ocn_diagnostics'}{'path'}     = $dbh->quote($json->{'ocn_diag_path'});

    $pp_fields{'timeseries'}{'status'}        = $json->{'timeseries_status'};
    $pp_fields{'timeseries'}{'path'}          = $dbh->quote($json->{'timeseries_path'});
    $pp_fields{'timeseries'}{'size'}          = $json->{'timeseries_size'};

    $pp_fields{'atm_timeseries'}{'status'}    = $json->{'atm_timeseries_status'};
    $pp_fields{'atm_timeseries'}{'size'}      = $json->{'atm_timeseries_size'};
    $pp_fields{'atm_timeseries'}{'path'}      = $dbh->quote($json->{'atm_timeseries_path'});
    
    $pp_fields{'glc_timeseries'}{'status'}    = $json->{'glc_timeseries_status'};
    $pp_fields{'glc_timeseries'}{'size'}      = $json->{'glc_timeseries_size'};
    $pp_fields{'glc_timeseries'}{'path'}      = $dbh->quote($json->{'glc_timeseries_path'});
    
    $pp_fields{'ice_timeseries'}{'status'}    = $json->{'ice_timeseries_status'};
    $pp_fields{'ice_timeseries'}{'size'}      = $json->{'ice_timeseries_size'};
    $pp_fields{'ice_timeseries'}{'path'}      = $dbh->quote($json->{'ice_timeseries_path'});

    $pp_fields{'lnd_timeseries'}{'status'}    = $json->{'lnd_timeseries_status'};
    $pp_fields{'lnd_timeseries'}{'size'}      = $json->{'lnd_timeseries_size'};
    $pp_fields{'lnd_timeseries'}{'path'}      = $dbh->quote($json->{'lnd_timeseries_path'});

    $pp_fields{'ocn_timeseries'}{'status'}    = $json->{'ocn_timeseries_status'};
    $pp_fields{'ocn_timeseries'}{'size'}      = $json->{'ocn_timeseries_size'};
    $pp_fields{'ocn_timeseries'}{'path'}      = $dbh->quote($json->{'ocn_timeseries_path'});
    
    $pp_fields{'rof_timeseries'}{'status'}    = $json->{'rof_timeseries_status'};
    $pp_fields{'rof_timeseries'}{'size'}      = $json->{'rof_timeseries_size'};
    $pp_fields{'rof_timeseries'}{'path'}      = $dbh->quote($json->{'rof_timeseries_path'});

    $pp_fields{'iconform'}{'status'}          = $json->{'iconform_status'};
    $pp_fields{'iconform'}{'size'}            = $json->{'iconform_size'};
    $pp_fields{'iconform'}{'path'}            = $dbh->quote($json->{'iconform_path'});

    $pp_fields{'xconform'}{'status'}          = $json->{'xconform_status'};
    $pp_fields{'xconform'}{'size'}            = $json->{'xconform_size'};
    $pp_fields{'xconform'}{'path'}            = $dbh->quote($json->{'xconform_path'});
}

my $svnlogin = $dbh->quote($json->{'svnlogin'});

# get the svnuser id 
my $sql = qq(select count(user_id), user_id from t_svnusers where svnlogin = $fields{'svnlogin'});
my $sth = $dbh->prepare($sql);
$sth->execute() or die $dbh->errstr;
($count, $item{'user_id'}) = $sth->fetchrow;
$sth->finish();
if ($count == 0) {
    die "Error in $sql - no SVN user found";
}

# get the status table into a hash
my %status;
$sql = qq(select id, code from t2_status);
$sth = $dbh->prepare($sql);
$sth->execute() or die $dbh->errstr;
while( my $ref = $sth->fetchrow_hashref() ) {
    $status{$ref->{'code'}} = $ref->{'id'};
}
$sth->finish();

# get the process table into a hash
my %procs;
$sql = qq(select id, name from t2_process);
$sth = $dbh->prepare($sql);
$sth->execute() or die $dbh->errstr;
while( my $ref = $sth->fetchrow_hashref() ) {
    $procs{$ref->{'name'}} = $ref->{'id'};
}
$sth->finish();

# get the case_id and expType_id based on the case name 
# NOTE - passing the json string because checkCase adds the quotes
($count, $item{'case_id'}, $item{'expType_id'}) = checkCase($dbh, $json->{'CASE'}, $json->{'expType'});

$logger->debug("count = " . $count);
$logger->debug("case_id = " . $item{'case_id'});
$logger->debug("expType_id = " . $item{'expType_id'});

if ($count == 0) {
    # load up an sql insert statement
    $sql = qq(insert into t2_cases
              (casename, caseroot, caseuser, compiler, compset, continue_run, dout_s, dout_s_root, grid,
               job_queue, job_time, machine, model, model_cost, model_throughput,  model_version, mpilib, 
               postprocess, project, expType_id, svnuser_id,
               rest_n, rest_option, run_dir, run_lastdate, run_refcase, run_refdate, run_startdate, 
               run_type, stop_n, stop_option, svn_repo_url, title, archive_date) value
              ($fields{'casename'}, $fields{'caseroot'}, $fields{'caseuser'}, $fields{'compiler'}, 
               $fields{'compset'}, $fields{'continue_run'}, $fields{'dout_s'}, $fields{'dout_s_root'}, $fields{'grid'},
               $fields{'job_queue'}, $fields{'job_time'}, $fields{'machine'}, $fields{'model'}, 
               $fields{'model_cost'}, $fields{'model_throughput'}, 
               $fields{'model_version'}, $fields{'mpilib'}, $fields{'postprocess'}, $fields{'project'},
               $item{'expType_id'}, $item{'user_id'},
               $fields{'rest_n'}, $fields{'rest_option'}, $fields{'run_dir'}, 
               $fields{'run_lastdate'}, $fields{'run_refcase'}, $fields{'run_refdate'},
               $fields{'run_startdate'}, $fields{'run_type'}, $fields{'stop_n'}, 
               $fields{'stop_option'}, $fields{'svn_repo_url'}, $fields{'title'}, NOW()));
    $sth = $dbh->prepare($sql);
    $sth->execute() or die $dbh->errstr;
    $sth->finish();
}
else {
    # check the new fields against the existing fields add to t2e_fields table if necessary
    foreach my $field (@keys) {
	$status = 'nochange';
	$count = 0;

	# handle the initial archive_date as a separate case
	$sql = qq(select count(id) from t2_cases  where 
                  archive_date is NULL and 
                  id = $item{'case_id'} and expType_id = $item{'expType_id'});
	$sth = $dbh->prepare($sql);
	$sth->execute() or die $dbh->errstr;
	my $count = $sth->fetchrow;
	$sth->finish();
	if ($count) 
	{
	    $sql = qq(update t2_cases set archive_date=NOW() where id = $item{'case_id'} and expType_id = $item{'expType_id'});
	    $sth = $dbh->prepare($sql);
	    $sth->execute() or die $dbh->errstr;
	    $sth->finish();
	}

	$count = 0;
	# check if the field is null in t2_cases
	$sql = qq(select count(id) from t2_cases  where 
                  $field is NULL and id = $item{'case_id'} and expType_id = $item{'expType_id'});
	$sth = $dbh->prepare($sql);
	$sth->execute() or die $dbh->errstr;
	my $count = $sth->fetchrow;
	$sth->finish();
	if ($count) 
	{
	    $sql = qq(update t2_cases set $field = $fields{$field} where id = $item{'case_id'} and expType_id = $item{'expType_id'});
	    $sth = $dbh->prepare($sql);
	    $sth->execute() or die $dbh->errstr;
	    $sth->finish();
	}
	else 
	{
	    # check if the field has changed from the t2_cases original
	    $sql = qq(select "change" from t2_cases  where 
                  $field != $fields{$field} and id = $item{'case_id'} and expType_id = $item{'expType_id'});
	    $sth = $dbh->prepare($sql);
	    $sth->execute() or die $dbh->errstr;
	    my $returnstatus1 = $sth->fetchrow;
	    $sth->finish();

	    # next check if the field has changed from the last update in the t2e_fields table
	    $sql = qq(select "change" from t2e_fields where 
                  field_name = '$field' and field_value != $fields{$field} and
                  case_id = $item{'case_id'} order by last_update desc);
	    $sth = $dbh->prepare($sql);
	    $sth->execute() or die $dbh->errstr;
	    my $returnstatus2 = $sth->fetchrow;
	    $sth->finish();

	    if (length($returnstatus1) > 1 || length($returnstatus2) > 1) {
		$status = "change";
	    }

	    if ($status eq "change") {
		$count = 0;
		$sql = qq(select count(*), last_update from t2e_fields where 
                          field_name = '$field' and field_value = $fields{$field} and
                          case_id = $item{'case_id'} order by last_update desc);
		$sth = $dbh->prepare($sql);
		$sth->execute() or die $dbh->errstr;
		($count, $last_update) = $sth->fetchrow;
		$sth->finish();

		if (!$count) {
		    $sql = qq(insert into t2e_fields (case_id, field_name, field_value, last_update)
                              value ($item{'case_id'}, '$field', $fields{$field}, NOW()));
		    $sth = $dbh->prepare($sql);
		    $sth->execute() or die $dbh->errstr;
		    $sth->finish();
		}
	    }
	}
    }
}

# load the run status into the t2j_status join table
$pid = $procs{'case_run'};
$pstat_id = $status{ $fields{'run_status'} };
$sql = qq(insert into t2j_status (case_id, status_id, process_id, 
          last_update, disk_usage, disk_path, archive_method)
          value ($item{'case_id'}, $pstat_id, $pid, NOW(),
          $fields{'run_size'}, $fields{'run_dir'}, 'archive_metadata'));
$logger->debug('insert run status sql = ' . $sql);
$sth = $dbh->prepare($sql);
$sth->execute() or die $dbh->errstr;
$sth->finish();

# load the sta status into the t2j_status join table
if (lc($fields{'dout_s'}) eq 'true') {
    $pid = $procs{'case_st_archive'};
    $pstat_id = $status{ $fields{'sta_status'} };
    $sql = qq(insert into t2j_status (case_id, status_id, process_id, 
              last_update, disk_usage, disk_path, archive_method)
              value ($item{'case_id'}, $pstat_id, $pid, NOW(),
              $fields{'sta_size'}, $fields{'dout_s_root'}, 'archive_metadata'));
    $logger->debug('insert sta status sql = ' . $sql);
    $sth = $dbh->prepare($sql);
    $sth->execute() or die $dbh->errstr;
    $sth->finish();
}

# load the post process statuses into the t2j_status join table if postprocessing is turned on
if (lc($fields{'postprocess'}) eq 'true') {
    foreach $pname (keys %pp_fields) {
	$pid = $procs{$pname};
	$pstat_id = $status{ $pp_fields{$pname}{'status'} };
	$sql = qq(insert into t2j_status (case_id, status_id, process_id, 
                  last_update, disk_usage, disk_path, archive_method)
                  value ($item{'case_id'}, $pstat_id, $pid, NOW(),
                  $pp_fields{$pname}{'size'}, $pp_fields{$pname}{'path'}, 'archive_metadata'));
	$logger->debug('insert t2j_status sql = ' . $sql);
	$sth = $dbh->prepare($sql);
	$sth->execute() or die $dbh->errstr;
	$sth->finish();
    }
}


print $req->header;
exit 0;


