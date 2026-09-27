import asyncio
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncssh

import ssh_proxy


class AcceptAllServer(asyncssh.SSHServer):
    def begin_auth(self, username):
        return False


class DurationTests(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(ssh_proxy.parse_duration('30s'), 30)
        self.assertEqual(ssh_proxy.parse_duration('60m'), 3600)
        self.assertEqual(ssh_proxy.parse_duration('8h'), 28800)
        self.assertEqual(ssh_proxy.parse_duration('1d'), 86400)
        self.assertEqual(ssh_proxy.parse_duration('off'), 0)

    def test_parse_duration_rejects_invalid_values(self):
        for value in ('', '30', '-1h', 'abc'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ssh_proxy.parse_duration(value)

    def test_known_host_pattern(self):
        self.assertEqual(
            ssh_proxy.known_host_pattern('nano4.nchc.org.tw', 22),
            'nano4.nchc.org.tw',
        )
        self.assertEqual(
            ssh_proxy.known_host_pattern('example.test', 2222),
            '[example.test]:2222',
        )

    def test_append_known_host_preserves_a_file_without_final_newline(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / 'known_hosts'
            path.write_text(
                'old.example ssh-ed25519 AAAA',
                encoding='ascii',
            )
            key = asyncssh.generate_private_key('ssh-ed25519')

            ssh_proxy.append_known_host(path, 'new.example', 22, key)

            lines = path.read_text(encoding='ascii').splitlines()
            self.assertEqual(lines[0], 'old.example ssh-ed25519 AAAA')
            self.assertTrue(lines[1].startswith('new.example ssh-ed25519 '))

    def test_matching_known_host_keys_accepts_a_dns_hostname(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / 'known_hosts'
            ssh_proxy.ensure_known_hosts_file(path)
            key = asyncssh.generate_private_key('ssh-ed25519')
            ssh_proxy.append_known_host(
                path,
                'nano4.nchc.org.tw',
                22,
                key,
            )

            matches = ssh_proxy.matching_known_host_keys(
                path,
                'nano4.nchc.org.tw',
                22,
            )

            self.assertEqual(
                matches[0][0].get_fingerprint(),
                key.get_fingerprint(),
            )


class HostKeyVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server_key = asyncssh.generate_private_key('ssh-ed25519')
        self.server = await asyncssh.create_server(
            AcceptAllServer,
            '127.0.0.1',
            0,
            server_host_keys=[self.server_key],
        )
        self.port = self.server.get_port()
        self.tempdir = tempfile.TemporaryDirectory()
        self.known_hosts = Path(self.tempdir.name) / 'known_hosts'

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.tempdir.cleanup()

    async def test_first_connection_prompts_then_strictly_reuses_key(self):
        with patch('builtins.input', return_value='yes') as prompt:
            connection = await ssh_proxy.connect_remote(
                '127.0.0.1',
                self.port,
                'test-user',
                self.known_hosts,
            )
        connection.close()
        await connection.wait_closed()

        prompt.assert_called_once()
        saved = self.known_hosts.read_text(encoding='utf-8')
        self.assertIn(f'[127.0.0.1]:{self.port} ssh-ed25519 ', saved)

        with patch(
            'builtins.input',
            side_effect=AssertionError('trusted key must not prompt again'),
        ):
            connection = await ssh_proxy.connect_remote(
                '127.0.0.1',
                self.port,
                'test-user',
                self.known_hosts,
            )
        connection.close()
        await connection.wait_closed()

    async def test_remote_connection_enables_ssh_keepalive(self):
        with patch(
            'ssh_proxy.asyncssh.connect',
            new_callable=AsyncMock,
        ) as connect:
            await ssh_proxy.connect_remote(
                '127.0.0.1',
                self.port,
                'test-user',
                self.known_hosts,
            )

        connect.assert_awaited_once()
        options = connect.await_args.kwargs
        self.assertEqual(options['keepalive_interval'], 30)
        self.assertEqual(options['keepalive_count_max'], 3)

    async def test_recorded_key_mismatch_is_rejected_without_prompt(self):
        ssh_proxy.ensure_known_hosts_file(self.known_hosts)
        old_key = asyncssh.generate_private_key('ssh-ed25519')
        ssh_proxy.append_known_host(
            self.known_hosts,
            '127.0.0.1',
            self.port,
            old_key,
        )

        with patch(
            'builtins.input',
            side_effect=AssertionError('changed key must not be prompted'),
        ):
            with self.assertRaisesRegex(
                ssh_proxy.HostKeyVerificationError,
                'REMOTE HOST IDENTIFICATION HAS CHANGED',
            ):
                await ssh_proxy.connect_remote(
                    '127.0.0.1',
                    self.port,
                    'test-user',
                    self.known_hosts,
                )

    async def test_rejected_first_key_sends_no_credentials_and_is_not_saved(self):
        with patch('builtins.input', return_value='no'):
            with self.assertRaisesRegex(
                ssh_proxy.HostKeyVerificationError,
                'No credentials were sent',
            ):
                await ssh_proxy.connect_remote(
                    '127.0.0.1',
                    self.port,
                    'test-user',
                    self.known_hosts,
                )

        self.assertEqual(self.known_hosts.read_text(encoding='utf-8'), '')


class PtySessionBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.remote_done = asyncio.Event()
        key = asyncssh.generate_private_key('ssh-ed25519')

        async def remote_shell(process):
            self.events.append(('size', process.term_size[:2]))
            while True:
                try:
                    data = await process.stdin.read(100)
                except asyncssh.TerminalSizeChanged as exc:
                    self.events.append(('resize', exc.term_size[:2]))
                    continue
                except asyncssh.BreakReceived:
                    self.events.append(('break',))
                    continue
                if not data:
                    self.events.append(('EOF',))
                    break
                if data == b'q':
                    break
                self.events.append(('data', data))
            process.exit(0)
            self.remote_done.set()

        self.remote_server = await asyncssh.create_server(
            AcceptAllServer, '127.0.0.1', 0,
            server_host_keys=[key],
            process_factory=remote_shell,
            encoding=None,
        )
        self.remote_conn = await asyncssh.connect(
            '127.0.0.1', self.remote_server.get_port(),
            known_hosts=None, username='test-user',
        )

        async def session_handler(process):
            await ssh_proxy.handle_session(self.remote_conn, process)

        activity = ssh_proxy.ProxyActivity()
        self.proxy_server = await asyncssh.create_server(
            lambda: ssh_proxy.NoAuthServer(self.remote_conn, activity),
            '127.0.0.1', 0,
            server_host_keys=[key],
            process_factory=session_handler,
            encoding=None,
        )

    async def asyncTearDown(self):
        self.proxy_server.close()
        await self.proxy_server.wait_closed()
        self.remote_conn.close()
        await self.remote_conn.wait_closed()
        self.remote_server.close()
        await self.remote_server.wait_closed()

    async def wait_for_event(self, event):
        for _ in range(100):
            if event in self.events:
                return
            await asyncio.sleep(0.02)
        self.fail(f'remote never saw {event!r}; saw {self.events!r}')

    async def test_resize_and_break_are_forwarded_without_closing_stdin(self):
        async with asyncssh.connect(
            '127.0.0.1', self.proxy_server.get_port(),
            known_hosts=None, username='test-user',
        ) as client:
            process = await client.create_process(
                term_type='xterm', term_size=(80, 24), encoding=None,
            )
            process.stdin.write(b'a')
            await self.wait_for_event(('data', b'a'))

            process.change_terminal_size(120, 40)
            await self.wait_for_event(('resize', (120, 40)))

            process.send_break(100)
            await self.wait_for_event(('break',))

            # stdin 在上述事件之後必須仍然暢通
            process.stdin.write(b'b')
            await self.wait_for_event(('data', b'b'))

            process.stdin.write(b'q')
            await asyncio.wait_for(self.remote_done.wait(), 5)
            await asyncio.wait_for(process.wait(), 5)

        self.assertNotIn(('EOF',), self.events)


class LocalPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_port_in_use_fails_before_remote_login(self):
        occupied = socket.socket()
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        try:
            with patch(
                'ssh_proxy.connect_remote',
                side_effect=AssertionError('must not log in when port busy'),
            ), patch('ssh_proxy.parse_ssh_config',
                     return_value=('example.test', 'me', 22)), \
                    patch('ssh_proxy.configured_proxy_port',
                          return_value=None), \
                    patch('ssh_proxy.find_free_local_port',
                          return_value=port + 1), \
                    patch.object(ssh_proxy.CONSOLE, 'print') as printed:
                exit_code = await ssh_proxy.start_proxy(
                    't3-c4', None, port, Path('unused'), 0, 0,
                )
        finally:
            occupied.close()

        self.assertEqual(exit_code, 1)
        message = printed.call_args.args[0].renderable
        self.assertIn(f'Local port {port} is already in use', message)
        self.assertIn('no password or OTP was sent', message)
        self.assertIn(f't3-c4 -l {port + 1}', message)

    def test_hint_uses_port_from_proxy_alias_in_ssh_config(self):
        output = 'hostname 127.0.0.1\nuser me\nport 2224\n'
        completed = subprocess.CompletedProcess([], 0, stdout=output)
        with patch('ssh_proxy.subprocess.run', return_value=completed) as run:
            hint = ssh_proxy.alternative_port_hint('t3-c4', 2222)
        self.assertEqual(run.call_args.args[0][-1], 't3-c4-proxy')
        self.assertIn('Port 2224', hint)
        self.assertIn('t3-c4 -l 2224', hint)

    async def test_reserved_port_blocks_others_then_serves_ssh(self):
        sock = ssh_proxy.reserve_local_port(0)
        port = sock.getsockname()[1]

        # 保留期間（OTP 登入中）：其他程式不能綁定同一 port。
        with self.assertRaises(OSError) as ctx:
            ssh_proxy.reserve_local_port(port)
        self.assertTrue(ssh_proxy.is_port_in_use_error(ctx.exception))

        server = await asyncssh.create_server(
            AcceptAllServer, sock=sock,
            server_host_keys=[asyncssh.generate_private_key('ssh-ed25519')],
        )
        try:
            async with asyncssh.connect(
                '127.0.0.1', port, known_hosts=None, username='test-user',
            ):
                pass
        finally:
            server.close()
            await server.wait_closed()

    def test_port_owner_commands_cover_each_platform(self):
        cases = [
            ('nt', 'win32', 'Get-NetTCPConnection -LocalPort 2222',
             'taskkill /PID <PID> /F'),
            ('posix', 'darwin', 'lsof -nP -iTCP:2222 -sTCP:LISTEN',
             'kill <PID>'),
            ('posix', 'linux', "ss -ltnp 'sport = :2222'", 'kill <PID>'),
        ]
        for os_name, platform, find_cmd, stop_cmd in cases:
            with self.subTest(platform=platform), \
                    patch.object(ssh_proxy.os, 'name', os_name), \
                    patch.object(ssh_proxy.sys, 'platform', platform):
                find_cmds, stop_cmds = ssh_proxy.port_owner_commands(2222)
                self.assertTrue(any(find_cmd in c for c in find_cmds))
                self.assertIn(stop_cmd, stop_cmds)


class SshConfigTests(unittest.TestCase):
    def test_openssh_resolution_is_preferred(self):
        output = (
            'user alice\n'
            'hostname real.example.org\n'
            'port 2200\n'
            'identityfile ~/.ssh/id_ed25519\n'
        )
        completed = subprocess.CompletedProcess([], 0, stdout=output)
        with patch('ssh_proxy.subprocess.run', return_value=completed) as run:
            self.assertEqual(
                ssh_proxy.parse_ssh_config('nano4'),
                ('real.example.org', 'alice', 2200),
            )
        self.assertEqual(run.call_args.args[0], ['ssh', '-G', '--', 'nano4'])

    @unittest.skipIf(os.name == 'nt', 'uses a POSIX shell script as ssh')
    def test_undecodable_ssh_output_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tempdir:
            fake_ssh = Path(tempdir) / 'ssh'
            fake_ssh.write_text(
                '#!/bin/sh\n'
                "printf 'user alice\\nhostname real.example.org\\n"
                "port 2200\\nidentityfile /home/\\377\\376/key\\n'\n",
                encoding='ascii',
            )
            fake_ssh.chmod(0o755)
            path = tempdir + os.pathsep + os.environ.get('PATH', '')
            with patch.dict(os.environ, {'PATH': path}):
                self.assertEqual(
                    ssh_proxy.resolve_with_openssh('nano4'),
                    ('real.example.org', 'alice', 2200),
                )

    def test_falls_back_to_config_file_without_ssh(self):
        config = (
            'Host nano4\n'
            '    HostName real.example.org\n'
            '    User alice\n'
            '    Port 2200\n'
            '\n'
            'Match user bob\n'
            '    HostName match.example.org\n'
            '\n'
            'Host=nano4\n'
            '    HostName second.example.org\n'
            '    User bob\n'
        )
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / 'config'
            path.write_text(config, encoding='utf-8')
            with patch('ssh_proxy.subprocess.run',
                       side_effect=FileNotFoundError('ssh')), \
                    patch('ssh_proxy.os.path.expanduser',
                          return_value=str(path)):
                self.assertEqual(
                    ssh_proxy.parse_ssh_config('nano4'),
                    ('real.example.org', 'alice', 2200),
                )

    def test_unknown_alias_uses_defaults_when_ssh_fails(self):
        failed = subprocess.CompletedProcess([], 255, stdout='')
        with patch('ssh_proxy.subprocess.run', return_value=failed), \
                patch('ssh_proxy.os.path.expanduser',
                      return_value='/nonexistent/config'), \
                patch('ssh_proxy.getpass.getuser', return_value='me'):
            self.assertEqual(
                ssh_proxy.parse_ssh_config('example.test'),
                ('example.test', 'me', 22),
            )


if __name__ == '__main__':
    unittest.main()
