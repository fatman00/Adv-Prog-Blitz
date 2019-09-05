

# developed by Gabi Zapodeanu, TSA, GPO, Cisco Systems

import sys
sys.path.append('/bootflash/BlitzAdvanced')

import difflib
import dnac_apis
import service_now_apis
import webex_teams_apis
import netconf_restconf

import time
import requests
import os

from cli import cli

from config import SNOW_ADMIN, SNOW_DEV, SNOW_PASS, SNOW_URL
from config import DNAC_URL, DNAC_PASS, DNAC_USER
from config import DEV_IP, DEV_USER, DEV_PASS
from config import UNAUTH_USER
from config import WEBEX_TEAMS_URL, WEBEX_TEAMS_AUTH, WEBEX_TEAMS_SPACE

from requests.auth import HTTPBasicAuth  # for Basic Auth

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)  # Disable insecure https warnings


os.chdir('/bootflash/BlitzAdvanced/ios_xe_programmability')

DNAC_AUTH = HTTPBasicAuth(DNAC_USER, DNAC_PASS)


def save_config():

    # save running configuration to the file with the name {current_config}
    output = cli('show run')
    filename = 'current_config'

    f = open(filename, "w")
    f.write(output)
    f.close

    return filename


def compare_configs(cfg1, cfg2):

    # compare the two specified config files {cfg1} and {cfg2}
    d = difflib.unified_diff(cfg1, cfg2)

    diffstr = ''

    for line in d:
        if line.find('Current configuration') == -1:
            if line.find('Last configuration change') == -1:
                if (line.find('+++') == -1) and (line.find('---') == -1):
                    if (line.find('-!') == -1) and (line.find('+!') == -1):
                       if line.startswith('+'):
                            diffstr = diffstr + '\n' + line
                       elif line.startswith('-'):
                            diffstr = diffstr + '\n' + line

    return diffstr


# main application


# collect the syslog entry that triggered the script, it will include the username that made the change

syslog_input = cli('show logging | in %SYS-5-CONFIG_I')
syslog_lines = syslog_input.split('\n')
lines_no = len(syslog_lines)-2
user_info = syslog_lines[lines_no]


# check if Unauthorized user made config changes during business hours

if UNAUTH_USER in user_info:

    old_cfg_fn = '/bootflash/BlitzAdvanced/ios_xe_programmability/base-config'
    new_cfg_fn = save_config()

    f = open(old_cfg_fn)
    old_cfg = f.readlines()
    f.close

    f = open(new_cfg_fn)
    new_cfg = f.readlines()
    f.close

    diff = compare_configs(old_cfg,new_cfg)
    print diff

    f = open('/bootflash/BlitzAdvanced/ios_xe_programmability/diff', 'w')
    f.write(diff)
    f.close

    if diff != '':

        # retrieve the device hostname using RESTCONF
        device_name = netconf_restconf.get_restconf_hostname(DEV_IP, DEV_USER, DEV_PASS)


        # retrieve the serial number using Python cli
        device_info = cli("sh ver | in Processor board ID")
        device_info_list = device_info.split(' ')
        device_sn = device_info_list[-1]


        # retrieve the device location using DNA C REST APIs
        # dnac_token = dnac_apis.get_dnac_jwt_token(DNAC_AUTH)
        # location = dnac_apis.get_device_location(device_name, dnac_token)
        location = "Lake Oswego/OR/USA"


        # define the incident description and comment
        short_description = "Unauthorized Configuration Change - IOS XE Automation"
        comment = "The device with the name: " + device_name + "\n has detected an Unauthorized Configuration Change"
        comment += "\n\nThe device SN is: " + device_sn
        comment += "\nThe device location is: " + location
        comment += "\n\nThe configuration changes are\n" + diff + "\n\nConfiguration changed by user: " + UNAUTH_USER


        # create ServiceNow incident using ServiceNow APIs
        incident = service_now_apis.create_incident(short_description, comment, SNOW_DEV, 3)


        # rollback configuration after 5 seconds
        time.sleep(5)
        cli('configure replace flash:/BlitzAdvanced/ios_xe_programmability/base-config force')
        update_comment = "Configuration rollback to baseline successful - IOS XE Automation"
        service_now_apis.update_incident(incident, update_comment, SNOW_DEV)


        # find existing, or create new Webex Teams room

        webex_team_id = webex_teams_apis.get_team_id(WEBEX_TEAMS_SPACE)
        if webex_team_id is None:
            webex_teams_apis.create_space(WEBEX_TEAMS_SPACE)

        webex_teams_apis.post_space_markdown_message(WEBEX_TEAMS_SPACE, 'New Incident')
        incident_detail = service_now_apis.get_incident_detail(incident)
        webex_teams_apis.post_space_url_message(WEBEX_TEAMS_SPACE, (incident_detail["number"]), (
                "https://dev48476.service-now.com/nav_to.do?uri=incident.do?sys_id=" + incident_detail["sys_id"]))
        webex_teams_apis.post_space_message(WEBEX_TEAMS_SPACE, "Description: " + incident_detail["short_description"])
        webex_teams_apis.post_space_message(WEBEX_TEAMS_SPACE, 'Device Hostname: ' + device_name + '   Location: ' + location)



print('End Application Run - Unauthorized Configuration Change')

