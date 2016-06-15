from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

import logging
from unittest import TestCase

from pcs.test.tools.assertions import (
    assert_raise_library_error,
    assert_report_item_list_equal,
)
from pcs.test.tools.custom_mock import MockLibraryReportProcessor
from pcs.test.tools.misc import (
    ac,
    get_test_resource as rc,
)
from pcs.test.tools.pcs_mock import mock

from pcs.common import report_codes
from pcs.lib.env import LibraryEnvironment
from pcs.lib.errors import (
    LibraryError,
    ReportItemSeverity as severity,
)
from pcs.lib.external import NodeCommunicationException
from pcs.lib.node import NodeAddresses, NodeAddressesList

from pcs.lib.commands import quorum as lib


class CmanMixin(object):
    def assert_disabled_on_cman(self, func):
        assert_raise_library_error(
            func,
            (
                severity.ERROR,
                report_codes.CMAN_UNSUPPORTED_COMMAND,
                {}
            )
        )


@mock.patch.object(LibraryEnvironment, "get_corosync_conf_data")
class GetQuorumConfigTest(TestCase, CmanMixin):
    def setUp(self):
        self.mock_logger = mock.MagicMock(logging.Logger)
        self.mock_reporter = MockLibraryReportProcessor()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_disabled_on_cman(self, mock_get_corosync):
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)
        self.assert_disabled_on_cman(lambda: lib.get_config(lib_env))
        mock_get_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_enabled_on_cman_if_not_live(self, mock_get_corosync):
        original_conf = open(rc("corosync.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(
            self.mock_logger,
            self.mock_reporter,
            corosync_conf_data=original_conf
        )

        self.assertEqual(
            {
                "options": {},
                "device": None,
            },
            lib.get_config(lib_env)
        )
        self.assertEqual([], self.mock_reporter.report_item_list)

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_no_options(self, mock_get_corosync):
        original_conf = open(rc("corosync.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        self.assertEqual(
            {
                "options": {},
                "device": None,
            },
            lib.get_config(lib_env)
        )
        self.assertEqual([], self.mock_reporter.report_item_list)

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_options(self, mock_get_corosync):
        original_conf = "quorum {\nwait_for_all: 1\n}\n"
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        self.assertEqual(
            {
                "options": {
                    "wait_for_all": "1",
                },
                "device": None,
            },
            lib.get_config(lib_env)
        )
        self.assertEqual([], self.mock_reporter.report_item_list)

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_device(self, mock_get_corosync):
        original_conf = """\
            quorum {
                provider: corosync_votequorum
                wait_for_all: 1
                device {
                    option: value
                    model: net
                    net {
                        host: 127.0.0.1
                        port: 4433
                    }
                }
            }
        """
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        self.assertEqual(
            {
                "options": {
                    "wait_for_all": "1",
                },
                "device": {
                    "model": "net",
                    "model_options": {
                        "host": "127.0.0.1",
                        "port": "4433",
                    },
                    "generic_options": {
                        "option": "value",
                    },
                },
            },
            lib.get_config(lib_env)
        )
        self.assertEqual([], self.mock_reporter.report_item_list)


@mock.patch.object(LibraryEnvironment, "push_corosync_conf")
@mock.patch.object(LibraryEnvironment, "get_corosync_conf_data")
class SetQuorumOptionsTest(TestCase, CmanMixin):
    def setUp(self):
        self.mock_logger = mock.MagicMock(logging.Logger)
        self.mock_reporter = MockLibraryReportProcessor()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_disabled_on_cman(self, mock_get_corosync, mock_push_corosync):
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)
        self.assert_disabled_on_cman(lambda: lib.set_options(lib_env, {}))
        mock_get_corosync.assert_not_called()
        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_enabled_on_cman_if_not_live(
        self, mock_get_corosync, mock_push_corosync
    ):
        original_conf = "invalid {\nconfig: stop after cman test"
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(
            self.mock_logger,
            self.mock_reporter,
            corosync_conf_data=original_conf
        )
        options = {"wait_for_all": "1"}
        assert_raise_library_error(
            lambda: lib.set_options(lib_env, options),
            (
                severity.ERROR,
                report_codes.PARSE_ERROR_COROSYNC_CONF_MISSING_CLOSING_BRACE,
                {}
            )
        )

        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_success(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        new_options = {"wait_for_all": "1"}
        lib.set_options(lib_env, new_options)

        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf.replace(
                "provider: corosync_votequorum\n",
                "provider: corosync_votequorum\n    wait_for_all: 1\n"
            )
        )
        self.assertEqual([], self.mock_reporter.report_item_list)

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_bad_options(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        new_options = {"invalid": "option"}
        assert_raise_library_error(
            lambda: lib.set_options(lib_env, new_options),
            (
                severity.ERROR,
                report_codes.INVALID_OPTION,
                {
                    "option_name": "invalid",
                    "option_type": "quorum",
                    "allowed": [
                        "auto_tie_breaker",
                        "last_man_standing",
                        "last_man_standing_window",
                        "wait_for_all",
                    ],
                }
            )
        )

        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_bad_config(self, mock_get_corosync, mock_push_corosync):
        original_conf = "invalid {\nconfig: this is"
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        new_options = {"wait_for_all": "1"}
        assert_raise_library_error(
            lambda: lib.set_options(lib_env, new_options),
            (
                severity.ERROR,
                report_codes.PARSE_ERROR_COROSYNC_CONF_MISSING_CLOSING_BRACE,
                {}
            )
        )

        mock_push_corosync.assert_not_called()


@mock.patch.object(LibraryEnvironment, "push_corosync_conf")
@mock.patch.object(LibraryEnvironment, "get_corosync_conf_data")
@mock.patch("pcs.lib.commands.quorum._add_device_model_net")
@mock.patch("pcs.lib.commands.quorum.qdevice_client.remote_client_enable")
class AddDeviceTest(TestCase, CmanMixin):
    def setUp(self):
        self.mock_logger = mock.MagicMock(logging.Logger)
        self.mock_reporter = MockLibraryReportProcessor()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_disabled_on_cman(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)
        self.assert_disabled_on_cman(
            lambda: lib.add_device(lib_env, "net", {"host": "127.0.0.1"}, {})
        )
        mock_get_corosync.assert_not_called()
        mock_push_corosync.assert_not_called()
        mock_add_net.assert_not_called()
        mock_client_enable.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_enabled_on_cman_if_not_live(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(
            self.mock_logger,
            self.mock_reporter,
            corosync_conf_data=original_conf
        )

        assert_raise_library_error(
            lambda: lib.add_device(lib_env, "bad model", {}, {}),
            (
                severity.ERROR,
                report_codes.INVALID_OPTION_VALUE,
                {
                    "option_name": "model",
                    "option_value": "bad model",
                    "allowed_values": ("net", ),
                },
                report_codes.FORCE_QDEVICE_MODEL
            )
        )

        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(0, mock_push_corosync.call_count)
        mock_add_net.assert_not_called()
        mock_client_enable.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_success(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        lib.add_device(
            lib_env,
            "net",
            {"host": "127.0.0.1", "algorithm": "ffsplit"},
            {"timeout": "12345"}
        )

        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf.replace(
                "provider: corosync_votequorum\n",
                """provider: corosync_votequorum

    device {
        timeout: 12345
        model: net

        net {
            algorithm: ffsplit
            host: 127.0.0.1
        }
    }
"""
            )
        )
        self.assertEqual([], self.mock_reporter.report_item_list)
        self.assertEqual(1, len(mock_add_net.mock_calls))
        self.assertEqual(3, len(mock_client_enable.mock_calls))

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_success_file(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(
            self.mock_logger,
            self.mock_reporter,
            corosync_conf_data=original_conf
        )

        lib.add_device(
            lib_env,
            "net",
            {"host": "127.0.0.1", "algorithm": "ffsplit"},
            {"timeout": "12345"}
        )

        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf.replace(
                "provider: corosync_votequorum\n",
                """provider: corosync_votequorum

    device {
        timeout: 12345
        model: net

        net {
            algorithm: ffsplit
            host: 127.0.0.1
        }
    }
"""
            )
        )
        self.assertEqual([], self.mock_reporter.report_item_list)
        self.assertEqual(0, len(mock_add_net.mock_calls))
        self.assertEqual(0, len(mock_client_enable.mock_calls))

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_invalid_options(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        assert_raise_library_error(
            lambda: lib.add_device(
                lib_env,
                "net",
                {"host": "127.0.0.1", "algorithm": "ffsplit"},
                {"bad_option": "bad_value", }
            ),
            (
                severity.ERROR,
                report_codes.INVALID_OPTION,
                {
                    "option_name": "bad_option",
                    "option_type": "quorum device",
                    "allowed": ["sync_timeout", "timeout"],
                },
                report_codes.FORCE_OPTIONS
            )
        )

        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(0, mock_push_corosync.call_count)
        mock_add_net.assert_not_called()
        mock_client_enable.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_invalid_options_forced(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        lib.add_device(
            lib_env,
            "net",
            {"host": "127.0.0.1", "algorithm": "ffsplit"},
            {"bad_option": "bad_value", },
            force_options=True
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.WARNING,
                    report_codes.INVALID_OPTION,
                    {
                        "option_name": "bad_option",
                        "option_type": "quorum device",
                        "allowed": ["sync_timeout", "timeout"],
                    }
                )
            ]
        )
        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf.replace(
                "provider: corosync_votequorum\n",
                """provider: corosync_votequorum

    device {
        bad_option: bad_value
        model: net

        net {
            algorithm: ffsplit
            host: 127.0.0.1
        }
    }
"""
            )
        )
        self.assertEqual(1, len(mock_add_net.mock_calls))
        self.assertEqual(3, len(mock_client_enable.mock_calls))

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_invalid_model(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        assert_raise_library_error(
            lambda: lib.add_device(lib_env, "bad model", {}, {}),
            (
                severity.ERROR,
                report_codes.INVALID_OPTION_VALUE,
                {
                    "option_name": "model",
                    "option_value": "bad model",
                    "allowed_values": ("net", ),
                },
                report_codes.FORCE_QDEVICE_MODEL
            )
        )

        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(0, mock_push_corosync.call_count)
        mock_add_net.assert_not_called()
        mock_client_enable.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_invalid_model_forced(
        self, mock_client_enable, mock_add_net, mock_get_corosync,
        mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        lib.add_device(lib_env, "bad model", {}, {}, force_model=True)

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.WARNING,
                    report_codes.INVALID_OPTION_VALUE,
                    {
                        "option_name": "model",
                        "option_value": "bad model",
                        "allowed_values": ("net", ),
                    },
                )
            ]
        )
        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf.replace(
                "provider: corosync_votequorum\n",
                """provider: corosync_votequorum

    device {
        model: bad model
    }
"""
            )
        )
        mock_add_net.assert_not_called() # invalid model - don't setup net model
        self.assertEqual(3, len(mock_client_enable.mock_calls))


@mock.patch(
    "pcs.lib.commands.quorum.qdevice_net.remote_client_import_certificate_and_key"
)
@mock.patch("pcs.lib.commands.quorum.qdevice_net.client_cert_request_to_pk12")
@mock.patch(
    "pcs.lib.commands.quorum.qdevice_net.remote_sign_certificate_request"
)
@mock.patch(
    "pcs.lib.commands.quorum.qdevice_net.client_generate_certificate_request"
)
@mock.patch("pcs.lib.commands.quorum.qdevice_net.remote_client_setup")
@mock.patch(
    "pcs.lib.commands.quorum.qdevice_net.remote_qdevice_get_ca_certificate"
)
@mock.patch.object(
    LibraryEnvironment,
    "cmd_runner",
    lambda self: "mock_runner"
)
@mock.patch.object(
    LibraryEnvironment,
    "node_communicator",
    lambda self: "mock_communicator"
)
class AddDeviceNetTest(TestCase):
    #pylint: disable=too-many-instance-attributes
    def setUp(self):
        self.mock_logger = mock.MagicMock(logging.Logger)
        self.mock_reporter = MockLibraryReportProcessor()
        self.lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)
        self.qnetd_host = "qnetd_host"
        self.cluster_name = "clusterName"
        self.nodes = NodeAddressesList([
            NodeAddresses("node1"),
            NodeAddresses("node2"),
        ])
        self.ca_cert = "CA certificate"
        self.cert_request = "client certificate request"
        self.signed_cert = "signed certificate"
        self.final_cert = "final client certificate"

    def test_success(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        skip_offline_nodes = False

        lib._add_device_model_net(
            self.lib_env,
            self.qnetd_host,
            self.cluster_name,
            self.nodes,
            skip_offline_nodes
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                )
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)
        mock_get_cert_request.assert_called_once_with(
            "mock_runner",
            self.cluster_name
        )
        mock_sign_cert_request.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host,
            self.cert_request,
            self.cluster_name
        )
        mock_cert_to_pk12.assert_called_once_with(
            "mock_runner",
            self.signed_cert
        )
        client_import_calls = [
            mock.call("mock_communicator", self.nodes[0], self.final_cert),
            mock.call("mock_communicator", self.nodes[1], self.final_cert),
        ]
        self.assertEqual(
            len(client_import_calls),
            len(mock_import_cert.mock_calls)
        )
        mock_import_cert.assert_has_calls(client_import_calls)

    def test_error_get_ca_cert(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.side_effect = NodeCommunicationException(
            "host", "command", "reason"
        )
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        skip_offline_nodes = False

        assert_raise_library_error(
            lambda: lib._add_device_model_net(
                self.lib_env,
                self.qnetd_host,
                self.cluster_name,
                self.nodes,
                skip_offline_nodes
            ),
            (
                severity.ERROR,
                report_codes.NODE_COMMUNICATION_ERROR,
                {}
            )
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                )
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        mock_client_setup.assert_not_called()
        mock_get_cert_request.assert_not_called()
        mock_sign_cert_request.assert_not_called()
        mock_cert_to_pk12.assert_not_called()
        mock_import_cert.assert_not_called()


    def test_error_client_setup(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        def raiser(communicator, node, cert):
            if node == self.nodes[1]:
                raise NodeCommunicationException("host", "command", "reason")
        mock_client_setup.side_effect = raiser
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        skip_offline_nodes = False

        assert_raise_library_error(
            lambda: lib._add_device_model_net(
                self.lib_env,
                self.qnetd_host,
                self.cluster_name,
                self.nodes,
                skip_offline_nodes
            ),
            (
                severity.ERROR,
                report_codes.NODE_COMMUNICATION_ERROR,
                {},
                report_codes.SKIP_OFFLINE_NODES
            )
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                ),
                (
                    severity.ERROR,
                    report_codes.NODE_COMMUNICATION_ERROR,
                    {},
                    report_codes.SKIP_OFFLINE_NODES
                ),
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)

    def test_error_client_setup_skip_offline(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        def raiser(communicator, node, cert):
            if node == self.nodes[1]:
                raise NodeCommunicationException("host", "command", "reason")
        mock_client_setup.side_effect = raiser
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        skip_offline_nodes = True

        lib._add_device_model_net(
            self.lib_env,
            self.qnetd_host,
            self.cluster_name,
            self.nodes,
            skip_offline_nodes
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                ),
                (
                    severity.WARNING,
                    report_codes.NODE_COMMUNICATION_ERROR,
                    {}
                ),
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)

    def test_generate_cert_request_error(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        mock_get_cert_request.side_effect = LibraryError()
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        skip_offline_nodes = False

        self.assertRaises(
            LibraryError,
            lambda: lib._add_device_model_net(
                self.lib_env,
                self.qnetd_host,
                self.cluster_name,
                self.nodes,
                skip_offline_nodes
            )
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                )
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)
        mock_get_cert_request.assert_called_once_with(
            "mock_runner",
            self.cluster_name
        )
        mock_sign_cert_request.assert_not_called()
        mock_cert_to_pk12.assert_not_called()
        mock_import_cert.assert_not_called()

    def test_sign_certificate_error(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.side_effect = NodeCommunicationException(
            "host", "command", "reason"
        )
        mock_cert_to_pk12.return_value = self.final_cert
        skip_offline_nodes = False

        assert_raise_library_error(
            lambda: lib._add_device_model_net(
                self.lib_env,
                self.qnetd_host,
                self.cluster_name,
                self.nodes,
                skip_offline_nodes
            ),
            (
                severity.ERROR,
                report_codes.NODE_COMMUNICATION_ERROR,
                {}
            )
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                )
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)
        mock_get_cert_request.assert_called_once_with(
            "mock_runner",
            self.cluster_name
        )
        mock_sign_cert_request.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host,
            self.cert_request,
            self.cluster_name
        )
        mock_cert_to_pk12.assert_not_called()
        mock_import_cert.assert_not_called()

    def test_certificate_to_pk12_error(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.side_effect = LibraryError()
        skip_offline_nodes = False

        self.assertRaises(
            LibraryError,
            lambda: lib._add_device_model_net(
                self.lib_env,
                self.qnetd_host,
                self.cluster_name,
                self.nodes,
                skip_offline_nodes
            )
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                )
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)
        mock_get_cert_request.assert_called_once_with(
            "mock_runner",
            self.cluster_name
        )
        mock_sign_cert_request.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host,
            self.cert_request,
            self.cluster_name
        )
        mock_cert_to_pk12.assert_called_once_with(
            "mock_runner",
            self.signed_cert
        )
        mock_import_cert.assert_not_called()

    def test_client_import_cert_error(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        def raiser(communicator, node, cert):
            if node == self.nodes[1]:
                raise NodeCommunicationException("host", "command", "reason")
        mock_import_cert.side_effect = raiser
        skip_offline_nodes = False

        assert_raise_library_error(
            lambda: lib._add_device_model_net(
                self.lib_env,
                self.qnetd_host,
                self.cluster_name,
                self.nodes,
                skip_offline_nodes
            ),
            (
                severity.ERROR,
                report_codes.NODE_COMMUNICATION_ERROR,
                {},
                report_codes.SKIP_OFFLINE_NODES
            )
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                ),
                (
                    severity.ERROR,
                    report_codes.NODE_COMMUNICATION_ERROR,
                    {},
                    report_codes.SKIP_OFFLINE_NODES
                ),
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)
        mock_get_cert_request.assert_called_once_with(
            "mock_runner",
            self.cluster_name
        )
        mock_sign_cert_request.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host,
            self.cert_request,
            self.cluster_name
        )
        mock_cert_to_pk12.assert_called_once_with(
            "mock_runner",
            self.signed_cert
        )
        client_import_calls = [
            mock.call("mock_communicator", self.nodes[0], self.final_cert),
            mock.call("mock_communicator", self.nodes[1], self.final_cert),
        ]
        self.assertEqual(
            len(client_import_calls),
            len(mock_import_cert.mock_calls)
        )
        mock_import_cert.assert_has_calls(client_import_calls)

    def test_client_import_cert_error_skip_offline(
        self, mock_get_ca, mock_client_setup, mock_get_cert_request,
        mock_sign_cert_request, mock_cert_to_pk12, mock_import_cert
    ):
        mock_get_ca.return_value = self.ca_cert
        mock_get_cert_request.return_value = self.cert_request
        mock_sign_cert_request.return_value = self.signed_cert
        mock_cert_to_pk12.return_value = self.final_cert
        def raiser(communicator, node, cert):
            if node == self.nodes[1]:
                raise NodeCommunicationException("host", "command", "reason")
        mock_import_cert.side_effect = raiser
        skip_offline_nodes = True

        lib._add_device_model_net(
            self.lib_env,
            self.qnetd_host,
            self.cluster_name,
            self.nodes,
            skip_offline_nodes
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.INFO,
                    report_codes.QDEVICE_CERTIFICATE_DISTRIBUTION_STARTED,
                    {}
                ),
                (
                    severity.WARNING,
                    report_codes.NODE_COMMUNICATION_ERROR,
                    {}
                ),
            ]
        )
        mock_get_ca.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host
        )
        client_setup_calls = [
            mock.call("mock_communicator", self.nodes[0], self.ca_cert),
            mock.call("mock_communicator", self.nodes[1], self.ca_cert),
        ]
        self.assertEqual(
            len(client_setup_calls),
            len(mock_client_setup.mock_calls)
        )
        mock_client_setup.assert_has_calls(client_setup_calls)
        mock_get_cert_request.assert_called_once_with(
            "mock_runner",
            self.cluster_name
        )
        mock_sign_cert_request.assert_called_once_with(
            "mock_communicator",
            self.qnetd_host,
            self.cert_request,
            self.cluster_name
        )
        mock_cert_to_pk12.assert_called_once_with(
            "mock_runner",
            self.signed_cert
        )
        client_import_calls = [
            mock.call("mock_communicator", self.nodes[0], self.final_cert),
            mock.call("mock_communicator", self.nodes[1], self.final_cert),
        ]
        self.assertEqual(
            len(client_import_calls),
            len(mock_import_cert.mock_calls)
        )
        mock_import_cert.assert_has_calls(client_import_calls)


@mock.patch.object(LibraryEnvironment, "push_corosync_conf")
@mock.patch.object(LibraryEnvironment, "get_corosync_conf_data")
class RemoveDeviceTest(TestCase, CmanMixin):
    def setUp(self):
        self.mock_logger = mock.MagicMock(logging.Logger)
        self.mock_reporter = MockLibraryReportProcessor()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_disabled_on_cman(self, mock_get_corosync, mock_push_corosync):
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)
        self.assert_disabled_on_cman(lambda: lib.remove_device(lib_env))
        mock_get_corosync.assert_not_called()
        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_enabled_on_cman_if_not_live(
        self, mock_get_corosync, mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(
            self.mock_logger,
            self.mock_reporter,
            corosync_conf_data=original_conf
        )

        assert_raise_library_error(
            lambda: lib.remove_device(lib_env),
            (
                severity.ERROR,
                report_codes.QDEVICE_NOT_DEFINED,
                {}
            )
        )


    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_no_device(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        assert_raise_library_error(
            lambda: lib.remove_device(lib_env),
            (
                severity.ERROR,
                report_codes.QDEVICE_NOT_DEFINED,
                {}
            )
        )

        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_success(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes-qdevice.conf")).read()
        no_device_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        lib.remove_device(lib_env)

        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            no_device_conf
        )
        self.assertEqual([], self.mock_reporter.report_item_list)


@mock.patch.object(LibraryEnvironment, "push_corosync_conf")
@mock.patch.object(LibraryEnvironment, "get_corosync_conf_data")
class UpdateDeviceTest(TestCase, CmanMixin):
    def setUp(self):
        self.mock_logger = mock.MagicMock(logging.Logger)
        self.mock_reporter = MockLibraryReportProcessor()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_disabled_on_cman(self, mock_get_corosync, mock_push_corosync):
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)
        self.assert_disabled_on_cman(
            lambda: lib.update_device(lib_env, {"host": "127.0.0.1"}, {})
        )
        mock_get_corosync.assert_not_called()
        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: True)
    def test_enabled_on_cman_if_not_live(
        self, mock_get_corosync, mock_push_corosync
    ):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(
            self.mock_logger,
            self.mock_reporter,
            corosync_conf_data=original_conf
        )

        assert_raise_library_error(
            lambda: lib.update_device(lib_env, {"host": "127.0.0.1"}, {}),
            (
                severity.ERROR,
                report_codes.QDEVICE_NOT_DEFINED,
                {}
            )
        )

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_no_device(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        assert_raise_library_error(
            lambda: lib.update_device(lib_env, {"host": "127.0.0.1"}, {}),
            (
                severity.ERROR,
                report_codes.QDEVICE_NOT_DEFINED,
                {}
            )
        )

        mock_push_corosync.assert_not_called()

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_success(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes-qdevice.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        lib.update_device(
            lib_env,
            {"host": "127.0.0.2"},
            {"timeout": "12345"}
        )

        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf
                .replace("host: 127.0.0.1", "host: 127.0.0.2")
                .replace(
                    "model: net",
                    "model: net\n        timeout: 12345"
                )
        )
        self.assertEqual([], self.mock_reporter.report_item_list)

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_invalid_options(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes-qdevice.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        assert_raise_library_error(
            lambda: lib.update_device(
                lib_env,
                {},
                {"bad_option": "bad_value", }
            ),
            (
                severity.ERROR,
                report_codes.INVALID_OPTION,
                {
                    "option_name": "bad_option",
                    "option_type": "quorum device",
                    "allowed": ["sync_timeout", "timeout"],
                },
                report_codes.FORCE_OPTIONS
            )
        )

        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(0, mock_push_corosync.call_count)

    @mock.patch("pcs.lib.env.is_cman_cluster", lambda self: False)
    def test_invalid_options_forced(self, mock_get_corosync, mock_push_corosync):
        original_conf = open(rc("corosync-3nodes-qdevice.conf")).read()
        mock_get_corosync.return_value = original_conf
        lib_env = LibraryEnvironment(self.mock_logger, self.mock_reporter)

        lib.update_device(
            lib_env,
            {},
            {"bad_option": "bad_value", },
            force_options=True
        )

        assert_report_item_list_equal(
            self.mock_reporter.report_item_list,
            [
                (
                    severity.WARNING,
                    report_codes.INVALID_OPTION,
                    {
                        "option_name": "bad_option",
                        "option_type": "quorum device",
                        "allowed": ["sync_timeout", "timeout"],
                    }
                )
            ]
        )
        self.assertEqual(1, mock_get_corosync.call_count)
        self.assertEqual(1, len(mock_push_corosync.mock_calls))
        ac(
            mock_push_corosync.mock_calls[0][1][0].config.export(),
            original_conf.replace(
                "model: net",
                "model: net\n        bad_option: bad_value"
            )
        )
