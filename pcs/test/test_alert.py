import shutil
import unittest

from pcs.test.tools.misc import (
    get_test_resource as rc,
    skip_unless_pacemaker_version,
    outdent,
    ParametrizedTestMetaClass,
)
from pcs.test.tools.assertions import AssertPcsMixin
from pcs.test.tools.pcs_runner import PcsRunner


old_cib = rc("cib-empty-2.0.xml")
empty_cib = rc("cib-empty-2.5.xml")
temp_cib = rc("temp-cib.xml")

skip_unless_alerts_supported = skip_unless_pacemaker_version(
    (1, 1, 15),
    "alerts"
)

class PcsAlertTest(unittest.TestCase, AssertPcsMixin):
    def setUp(self):
        shutil.copy(empty_cib, temp_cib)
        self.pcs_runner = PcsRunner(temp_cib)


@skip_unless_alerts_supported
class AlertCibUpgradeTest(unittest.TestCase, AssertPcsMixin):
    def setUp(self):
        shutil.copy(old_cib, temp_cib)
        self.pcs_runner = PcsRunner(temp_cib)

    def test_cib_upgrade(self):
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 No alerts defined
"""
        )

        self.assert_pcs_success(
            "alert create path=test",
            "CIB has been upgraded to the latest schema version.\n"
        )

        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
"""
        )


@skip_unless_alerts_supported
class CreateAlertTest(PcsAlertTest):
    def test_create_multiple_without_id(self):
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 No alerts defined
"""
        )

        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success("alert create path=test2")
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
 Alert: alert-1 (path=test)
 Alert: alert-2 (path=test2)
"""
        )

    def test_create_multiple_with_id(self):
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 No alerts defined
"""
        )
        self.assert_pcs_success("alert create id=alert1 path=test")
        self.assert_pcs_success(
            "alert create id=alert2 description=desc path=test"
        )
        self.assert_pcs_success(
            "alert create description=desc2 path=test2 id=alert3"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert1 (path=test)
 Alert: alert2 (path=test)
  Description: desc
 Alert: alert3 (path=test2)
  Description: desc2
"""
        )

    def test_create_with_options(self):
        self.assert_pcs_success(
            "alert create id=alert1 description=desc path=test "
            "options opt2=val2 opt1=val1 meta m2=v2 m1=v1"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert1 (path=test)
  Description: desc
  Options: opt1=val1 opt2=val2
  Meta options: m1=v1 m2=v2
"""
        )

    def test_already_exists(self):
        self.assert_pcs_success("alert create id=alert1 path=test")
        self.assert_pcs_fail(
            "alert create id=alert1 path=test",
            "Error: 'alert1' already exists\n"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert1 (path=test)
"""
        )

    def test_path_is_required(self):
        self.assert_pcs_fail(
            "alert create id=alert1",
            "Error: required option 'path' is missing\n"
        )


@skip_unless_alerts_supported
class UpdateAlertTest(PcsAlertTest):
    def test_update_everything(self):
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 No alerts defined
"""
        )
        self.assert_pcs_success(
            "alert create id=alert1 description=desc path=test "
            "options opt1=val1 opt3=val3 meta m1=v1 m3=v3"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert1 (path=test)
  Description: desc
  Options: opt1=val1 opt3=val3
  Meta options: m1=v1 m3=v3
"""
        )
        self.assert_pcs_success(
            "alert update alert1 description=new_desc path=/new/path "
            "options opt1= opt2=test opt3=1 meta m1= m2=v m3=3"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert1 (path=/new/path)
  Description: new_desc
  Options: opt2=test opt3=1
  Meta options: m2=v m3=3
"""
        )

    def test_not_existing_alert(self):
        self.assert_pcs_fail(
            "alert update alert1", "Error: alert 'alert1' does not exist\n"
        )


class DeleteRemoveAlertTest(PcsAlertTest):
    command = None

    def _test_usage(self):
        self.assert_pcs_fail(
            f"alert {self.command}",
            stdout_start=f"\nUsage: pcs alert <command>\n    {self.command} <"
        )

    def _test_not_existing_alert(self):
        self.assert_pcs_fail(
            f"alert {self.command} alert1",
            "Error: alert 'alert1' does not exist\n"
        )

    def _test_one(self):
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 No alerts defined
                """
            )
        )

        self.assert_pcs_success("alert create path=test id=alert1")
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert1 (path=test)
                """
            )
        )
        self.assert_pcs_success(f"alert {self.command} alert1")
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 No alerts defined
                """
            )
        )

    def _test_multiple(self):
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 No alerts defined
                """
            )
        )

        self.assert_pcs_success("alert create path=test id=alert1")
        self.assert_pcs_success("alert create path=test id=alert2")
        self.assert_pcs_success("alert create path=test id=alert3")
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert1 (path=test)
                 Alert: alert2 (path=test)
                 Alert: alert3 (path=test)
                """
            )
        )
        self.assert_pcs_success(f"alert {self.command} alert1 alert3")
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert2 (path=test)
                """
            )
        )


@skip_unless_alerts_supported
class DeleteAlertTest(
    DeleteRemoveAlertTest,
    metaclass=ParametrizedTestMetaClass
):
    command = "delete"


@skip_unless_alerts_supported
class RemoveAlertTest(
    DeleteRemoveAlertTest,
    metaclass=ParametrizedTestMetaClass
):
    command = "remove"


@skip_unless_alerts_supported
class AddRecipientTest(PcsAlertTest):
    def test_success(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
"""
        )
        self.assert_pcs_success("alert recipient add alert value=rec_value")
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=rec_value)
"""
        )
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value2 id=my-recipient "
            "description=description options o2=2 o1=1 meta m2=v2 m1=v1"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=rec_value)
   Recipient: my-recipient (value=rec_value2)
    Description: description
    Options: o1=1 o2=2
    Meta options: m1=v1 m2=v2
"""
        )

    def test_already_exists(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value id=rec"
        )
        self.assert_pcs_fail(
            "alert recipient add alert value=value id=rec",
            "Error: 'rec' already exists\n"
        )
        self.assert_pcs_fail(
            "alert recipient add alert value=value id=alert",
            "Error: 'alert' already exists\n"
        )

    def test_same_value(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value id=rec"
        )
        self.assert_pcs_fail(
            "alert recipient add alert value=rec_value",
            "Error: Recipient 'rec_value' in alert 'alert' already exists, "
            "use --force to override\n"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: rec (value=rec_value)
"""
        )
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value --force",
            "Warning: Recipient 'rec_value' in alert 'alert' already exists\n"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: rec (value=rec_value)
   Recipient: alert-recipient (value=rec_value)
"""
        )

    def test_no_value(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_fail(
            "alert recipient add alert id=rec",
            "Error: required option 'value' is missing\n"
        )



@skip_unless_alerts_supported
class UpdateRecipientAlert(PcsAlertTest):
    def test_success(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value description=description "
            "options o1=1 o3=3 meta m1=v1 m3=v3"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=rec_value)
    Description: description
    Options: o1=1 o3=3
    Meta options: m1=v1 m3=v3
"""
        )
        self.assert_pcs_success(
            "alert recipient update alert-recipient value=new description=desc "
            "options o1= o2=v2 o3=3 meta m1= m2=2 m3=3"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=new)
    Description: desc
    Options: o2=v2 o3=3
    Meta options: m2=2 m3=3
"""
        )
        self.assert_pcs_success(
            "alert recipient update alert-recipient value=new"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=new)
    Description: desc
    Options: o2=v2 o3=3
    Meta options: m2=2 m3=3
"""
        )

    def test_value_exists(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success("alert recipient add alert value=rec_value")
        self.assert_pcs_success("alert recipient add alert value=value")
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=rec_value)
   Recipient: alert-recipient-1 (value=value)
"""
        )
        self.assert_pcs_fail(
            "alert recipient update alert-recipient value=value",
            "Error: Recipient 'value' in alert 'alert' already exists, "
            "use --force to override\n"
        )
        self.assert_pcs_success(
            "alert recipient update alert-recipient value=value --force",
            "Warning: Recipient 'value' in alert 'alert' already exists\n"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=value)
   Recipient: alert-recipient-1 (value=value)
"""
        )

    def test_value_same_as_previous(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success("alert recipient add alert value=rec_value")
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=rec_value)
"""
        )
        self.assert_pcs_success(
            "alert recipient update alert-recipient value=rec_value"
        )
        self.assert_pcs_success(
            "alert config",
            """\
Alerts:
 Alert: alert (path=test)
  Recipients:
   Recipient: alert-recipient (value=rec_value)
"""
        )

    def test_no_recipient(self):
        self.assert_pcs_fail(
            "alert recipient update rec description=desc",
            "Error: recipient 'rec' does not exist\n"
        )

    def test_empty_value(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value id=rec"
        )
        self.assert_pcs_fail(
            "alert recipient update rec value=",
            "Error: Recipient value '' is not valid.\n"
        )


class DeleteRemoveRecipientTest(PcsAlertTest):
    command = None

    def _test_usage(self):
        self.assert_pcs_fail(
            f"alert recipient {self.command}",
            stdout_start=outdent(f"""
                Usage: pcs alert <command>
                    recipient {self.command} <""")
        )

    def _test_one(self):
        self.assert_pcs_success("alert create path=test")
        self.assert_pcs_success(
            "alert recipient add alert value=rec_value id=rec"
        )
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert (path=test)
                  Recipients:
                   Recipient: rec (value=rec_value)
                """
            )
        )
        self.assert_pcs_success(f"alert recipient {self.command} rec")
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert (path=test)
                """
            )
        )

    def _test_multiple(self):
        self.assert_pcs_success("alert create path=test id=alert1")
        self.assert_pcs_success("alert create path=test id=alert2")
        self.assert_pcs_success(
            "alert recipient add alert1 value=rec_value1 id=rec1"
        )
        self.assert_pcs_success(
            "alert recipient add alert1 value=rec_value2 id=rec2"
        )
        self.assert_pcs_success(
            "alert recipient add alert2 value=rec_value3 id=rec3"
        )
        self.assert_pcs_success(
            "alert recipient add alert2 value=rec_value4 id=rec4"
        )
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert1 (path=test)
                  Recipients:
                   Recipient: rec1 (value=rec_value1)
                   Recipient: rec2 (value=rec_value2)
                 Alert: alert2 (path=test)
                  Recipients:
                   Recipient: rec3 (value=rec_value3)
                   Recipient: rec4 (value=rec_value4)
                """
            )
        )
        self.assert_pcs_success(
            f"alert recipient {self.command} rec1 rec2 rec4"
        )
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert1 (path=test)
                 Alert: alert2 (path=test)
                  Recipients:
                   Recipient: rec3 (value=rec_value3)
                """
            )
        )

    def _test_no_recipient(self):
        self.assert_pcs_success("alert create path=test id=alert1")
        self.assert_pcs_success(
            "alert recipient add alert1 value=rec_value1 id=rec1"
        )
        self.assert_pcs_fail(
            f"alert recipient {self.command} rec1 rec2 rec3", outdent("""\
                Error: recipient 'rec2' does not exist
                Error: recipient 'rec3' does not exist
                """
            )
        )
        self.assert_pcs_success(
            "alert config", outdent("""\
                Alerts:
                 Alert: alert1 (path=test)
                  Recipients:
                   Recipient: rec1 (value=rec_value1)
                """
            )
        )


class DeleteRecipientTest(
    DeleteRemoveRecipientTest,
    metaclass=ParametrizedTestMetaClass
):
    command = "delete"


class RemoveRecipientTest(
    DeleteRemoveRecipientTest,
    metaclass=ParametrizedTestMetaClass
):
    command = "remove"
