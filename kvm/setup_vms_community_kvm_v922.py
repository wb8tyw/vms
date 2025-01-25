#!/usr/bin/python

'''
Python script used for setting up the OpenVMS 9.2-2 Community Edition.

This script attempt to get the system up to the point that it can be
reached via DECnet.   It has not been fully tested, and is only
intended for a reference.
'''
import logging
import os
import re
import sys
from time import sleep
import libvirt     # type: ignore

# System specific data
# pylint: disable=invalid-name
host_url = 'qemu:///system'

logger = logging.getLogger(__name__)

# target specific information

# pylint: disable=invalid-name
target_name = "robin"
target_name_upper_str = target_name.upper()
target_scsnode = target_name.encode('utf-8', 'replace')
target_decnet_area_int = 1
target_decnet_number_int = 13
target_scssystemid_int = \
    target_decnet_area_int * 1024 + target_decnet_number_int
target_decnet_area = str(target_decnet_area_int).encode('utf-8', 'replace')
target_decnet_number = str(target_decnet_number_int).encode('utf-8', 'replace')
target_scssystemid = str(target_scssystemid_int).encode('utf-8', 'replace')

target_env_password = 'VMS_PASSWORD'
if target_env_password in os.environ:
    target_password_str = os.environ[target_env_password]
    target_password = target_password_str.encode('utf-8', 'replace')
else:
    logger.error('Need %s environment set!', target_env_password)
    sys.exit(1)

# Some code from:
# https://github.com/libvirt/
# libvirt-python/blob/master/examples/consolecallback.py

def error_handler(_unused, error) -> None:
    ''' Error Handler '''
    # The console stream errors on VM shutdown; we don't care
    if error[0] == libvirt.VIR_ERR_RPC and error[1] == libvirt.VIR_FROM_STREAMS:
        return
    logging.warning(error)


# pylint: disable=too-few-public-methods, too-many-instance-attributes
class Console():
    ''' Libvirt Console class '''
    def __init__(self, uri: str, name: str) -> None:
        self.uri = uri
        self.name = name
        libvirt.virEventRegisterDefaultImpl()
        self.connection = libvirt.open(uri)
        self.domain = self.connection.lookupByName(self.name)
        self.state = self.domain.state(0)
        if self.state[0] != libvirt.VIR_DOMAIN_RUNNING:
            self.domain.create()
            self.state = self.domain.state(0)
        self.connection.domainEventRegister(lifecycle_callback, self)
        self.stream = None  # Optional [libvirt.virStream]
        self.run_console = True
        self.stdin_watch = -1
        self.ring_index = 0
        self.ring_max = 10
        self.ring_buffer = ()
        self.current_string = ''
        self.prompt_index = {}
        for prompt in PROMPT_ACTIONS:
            if prompt[1] not in self.prompt_index:
                self.prompt_index[prompt[1]] = 0
        print(f'prompt_index = {self.prompt_index}')

        logging.info("%s initial state %d, reason %d",
                     self.name, self.state[0], self.state[1])


def check_console(console: Console) -> bool:
    ''' Check Console. '''
    if (console.state[0] == libvirt.VIR_DOMAIN_RUNNING or \
       console.state[0] == libvirt.VIR_DOMAIN_PAUSED):
        if console.stream is None:
            console.stream = console.connection.newStream(
                libvirt.VIR_STREAM_NONBLOCK)
            console.domain.openConsole(None, console.stream, 0)
            console.stream.eventAddCallback(libvirt.VIR_STREAM_EVENT_READABLE,
                                            stream_callback, console)
            print("Created console stream")
    else:
        if console.stream:
            print("Destroyed console stream")
            console.stream.eventRemoveCallback()
            console.stream = None

    return console.run_console


ESC_ACTIONS = [b'\x1b']


BOOTMGR_ACTIONS = [
    b'AUTO BOOT DKA0',
    b'BOOT DKA0 0 1']


SYSBOOT_ACTIONS = [
    b'SET/STARTUP OPA0:',
    b'SET WINDOW_SYSTEM 0',
    b'SET WRITESYSPARAMS 0',
    b'CONTINUE']


DOLLAR_ACTIONS = [
    b'SET DEF SYS$SYSTEM:',
    b'RUN SYS$SYSTEM:AUTHORIZE',
    b'SPAWN',
    b'@SYS$SYSTEM:STARTUP.COM',
    b'open/append mpd sys$system:modparams.dat',
    b'write mpd "SCSNODE="""' + target_scsnode + b'""',
    b'write mpd "SCSSYSTEMID="' + target_scssystemid,
    b'close mpd',
    b'set noverify',
    b'@sys$update:autogen GETDATA SETPARAMS',
    b'mcr sysman shutdown node /auto /min=0',
    b'wait 00:10',
    b'logout',
    b'@sys$manager:net$configure'
]

DECNET_DOMAIN_ACTIONS = [b'local']
DECNET_LOCAL_ACTIONS = [b'LOCAL:.' + target_scsnode]
DECNET_DEFAULT_ACTIONS = [b'']

UAF_ACTIONS = [
    b'MODIFY SYSTEM/NOPWDEXP/NOPWDLIFE/PASS="' + target_password + B'"',
    b'EXIT']

INTSET_ACTIONS = [
    b'',
    b'',
    b'']

USERNAME_ACTIONS = [
    b'SYSTEM',
    b'SYSTEM',
    b'SYSTEM',
    b'SYSTEM',
    b'SYSTEM']

PASSWORD_ACTIONS = [
    target_password,
    target_password,
    target_password,
    ]

PROMPT_ACTIONS = [
    ('Press <ESC>', 'ESC', ESC_ACTIONS),
    ('BOOTMGR> ', 'BOOTMGR', BOOTMGR_ACTIONS),
    ('SYSBOOT> ', 'SYSBOOT', SYSBOOT_ACTIONS),
    ('\r\n\x00$ ', 'DOLLAR', DOLLAR_ACTIONS),
    ('\n\r\x00$ ', 'DOLLAR', DOLLAR_ACTIONS),
    ('UAF> ', 'UAF', UAF_ACTIONS),
    ('job terminated at ', 'INTSET', INTSET_ACTIONS),
    ('\r\nUsername: ', 'USERNAME', USERNAME_ACTIONS),
    ('\n\rUsername: ', 'USERNAME', USERNAME_ACTIONS),
    ('\r\nPassword: ', 'PASSWORD', PASSWORD_ACTIONS),
    ('\n\rPassword: ', 'PASSWORD', PASSWORD_ACTIONS),
    (',Domain] : ', 'DECNET_DOMAIN', DECNET_DOMAIN_ACTIONS),
    ('LOCAL    ', 'DECNET_LOCAL', DECNET_LOCAL_ACTIONS),
    (f'[{target_name_upper_str}] : ', 'DECNET_SYNONYM', DECNET_DEFAULT_ACTIONS),
    ('[ENDNODE] : ', 'DECNET_ENDNODE', DECNET_DEFAULT_ACTIONS),
    (f' [{target_decnet_area_int}.{target_decnet_number_int}] : ',
     'DECNET_PHASE4', DECNET_DEFAULT_ACTIONS),
    ('scripts? ', 'DECNET_SCRIPTS', DECNET_DEFAULT_ACTIONS),
    ('network? ', 'DECNET_START', DECNET_DEFAULT_ACTIONS)
    ]


def prompt_handler(console: Console, prompt: tuple):
    ''' Prompt Handler. '''
    if console.stream:
        num_cmds = len(prompt[2])
        prompt_index = console.prompt_index[prompt[1]]
        if prompt_index >= num_cmds:
            logging.info("Unexpected Prompt %s %i > %i ",
                         prompt[1], prompt_index, num_cmds)
            return
        cmd = prompt[2][prompt_index] + b'\r'
        console.prompt_index[prompt[1]] += 1
        console.stream.send(cmd)
        # if prompt[1] == 'USERNAME':
        #     print("--------------------------------------------")
        #     print("Username: seen")
        #     print("--------------------------------------------")
        if prompt[1] == 'INTSET':
            print("reboot seen")
            sleep(10)
            console.stream.send(cmd)


def stream_callback(_stream: libvirt.virStream,
                    _events: int, console: Console) -> None:
    ''' Stream Callback. '''
    try:
        assert console.stream
        # Add current capture to current buffer
        new_data = console.stream.recv(1024)
        # print(f'-{new_data}-')
        new_string = new_data.decode('utf-8', 'replace')
        os.write(0, new_data)
        console.current_string += new_string

        for prompt in PROMPT_ACTIONS:
            if prompt[0] in console.current_string:
                parts = re.split(prompt[0], console.current_string, maxsplit=1)
                if len(parts) > 1:
                    console.current_string = parts[1]
                else:
                    console.current_string = ''
                prompt_handler(console, prompt)

    # pylint: disable=broad-except
    except Exception as exp:
        logging.info("stream_callback exception %s", exp, exc_info=True)
        return


def lifecycle_callback(_connection: libvirt.virConnect,
                       _domain: libvirt.virDomain,
                       _event: int, _detail: int, console: Console) -> None:
    ''' Lifecycle Callback. '''
    console.state = console.domain.state(0)
    logging.info("%s transitioned to state %d, reason %d",
                 console.uuid, console.state[0], console.state[1])



def main():
    ''' Main. '''
    logging.basicConfig(level=logging.INFO)
    # Add something to handle KeyboardInterrupt
    console = Console(host_url, target_name)
    try:
        while check_console(console):
            libvirt.virEventRunDefaultImpl()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
