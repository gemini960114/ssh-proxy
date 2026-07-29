import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
