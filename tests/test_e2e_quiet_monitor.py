"""Quiet-monitor ancestry guards, using authored process/window fixtures.

These invented PID/start identities exercise OS lifecycle cases without opening a
window. Run: python3 -m unittest discover -s tests -p test_e2e_quiet_monitor.py.
Native macOS acquisition is separate; no product, GUI, or user process is invoked.
"""

import importlib.util
import io
from pathlib import Path
import unittest
from unittest import mock

MODULE = Path(__file__).parents[1] / "desktop/scripts/e2e_quiet_monitor.py"
spec = importlib.util.spec_from_file_location("quiet_monitor", MODULE)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def proc(pid, parent, group, start=None):
    return {"pid": pid, "ppid": parent, "pgid": group, "start": start or str(pid)}


def snapshot(processes, focus=20, windows=()):
    return {
        "processes": processes,
        "frontmost": {"pid": focus, "name": "Electron"},
        "windows": list(windows),
    }


def window(pid, layer=0):
    return {
        "pid": pid,
        "id": 555,
        "layer": layer,
        "owner": "Any app",
        "bounds": [0, 0, 400, 300],
    }


class AttributionTests(unittest.TestCase):
    def setUp(self):
        # 20 is a user's existing app, 30 its terminal, 100 the new test session.
        self.base = [proc(1, 0, 1), proc(20, 1, 20), proc(30, 1, 30)]
        self.guard = monitor.Attribution(self.base, 100)
        self.root = proc(100, 30, 100)

    def test_unrelated_electron_focus_and_new_window_are_notes(self):
        sample = snapshot(
            [*self.base, self.root, proc(40, 30, 40)], focus=40, windows=[window(40)]
        )
        self.assertEqual(self.guard.check(sample)[0], 0)

    def test_startup_descendant_window_fails_without_helper_log(self):
        sample = snapshot(
            [*self.base, self.root, proc(110, 100, 100)], windows=[window(110)]
        )
        self.assertEqual(self.guard.check(sample)[0], 1)

    def test_any_descendant_focus_fails_regardless_of_app_name(self):
        sample = snapshot([*self.base, self.root, proc(110, 100, 100)], focus=110)
        sample["frontmost"]["name"] = "Unlisted helper"
        self.assertEqual(self.guard.check(sample)[0], 1)

    def test_detached_descendant_is_found_through_ancestry(self):
        sample = snapshot(
            [*self.base, self.root, proc(110, 100, 110), proc(120, 110, 120)],
            windows=[window(120)],
        )
        self.assertEqual(self.guard.check(sample)[0], 1)

    def test_reparented_session_member_still_fails(self):
        sample = snapshot(
            [*self.base, self.root, proc(110, 1, 100)], windows=[window(110)]
        )
        self.assertEqual(self.guard.check(sample)[0], 1)

    def test_known_detached_child_remains_owned_after_reparenting(self):
        self.guard.check(snapshot([*self.base, self.root, proc(110, 100, 110)]))
        self.assertEqual(
            self.guard.check(
                snapshot(
                    [*self.base, self.root, proc(110, 1, 110)], windows=[window(110)]
                )
            )[0],
            1,
        )

    def test_new_orphan_cannot_be_declared_unrelated(self):
        self.assertEqual(
            self.guard.check(
                snapshot(
                    [*self.base, self.root, proc(110, 1, 110)], windows=[window(110)]
                )
            )[0],
            2,
        )

    def test_pid_reuse_does_not_inherit_baseline_exemption(self):
        sample = snapshot(
            [self.base[0], self.base[2], self.root, proc(20, 1, 20, "2000")],
            windows=[window(20)],
        )
        self.assertEqual(self.guard.check(sample)[0], 2)

    def test_pid_reuse_does_not_inherit_old_child_ownership(self):
        self.guard.check(snapshot([*self.base, self.root, proc(110, 100, 110)]))
        sample = snapshot(
            [*self.base, self.root, proc(110, 30, 110, "2000")], windows=[window(110)]
        )
        self.assertEqual(self.guard.check(sample)[0], 0)

    def test_reused_root_pid_is_not_a_new_test_root(self):
        self.guard.check(snapshot([*self.base, self.root]))
        sample = snapshot(
            [*self.base, proc(100, 30, 100, "2000")], focus=100, windows=[window(100)]
        )
        self.assertEqual(self.guard.check(sample)[0], 0)

    def test_missing_focus_process_is_unreadable(self):
        self.assertEqual(
            self.guard.check(snapshot([*self.base, self.root], focus=999))[0], 2
        )

    def test_missing_window_process_is_unreadable(self):
        self.assertEqual(
            self.guard.check(snapshot([*self.base, self.root], windows=[window(999)]))[
                0
            ],
            2,
        )

    def test_missing_ancestry_and_cycles_are_unreadable(self):
        for records in (
            [proc(110, 999, 110)],
            [proc(110, 120, 110), proc(120, 110, 120)],
        ):
            with self.subTest(records=records):
                self.assertEqual(
                    self.guard.check(
                        snapshot(
                            [*self.base, self.root, *records], windows=[window(110)]
                        )
                    )[0],
                    2,
                )

    def test_empty_or_malformed_snapshot_never_passes(self):
        for sample in (
            {},
            snapshot([]),
            {**snapshot(self.base), "frontmost": None},
            {**snapshot(self.base), "windows": None},
        ):
            with self.subTest(sample=sample):
                self.assertEqual(self.guard.check(sample)[0], 2)

    def test_nonzero_window_layer_is_still_a_test_window(self):
        sample = snapshot(
            [*self.base, self.root, proc(110, 100, 100)], windows=[window(110, layer=3)]
        )
        self.assertEqual(self.guard.check(sample)[0], 1)


class LauncherTests(unittest.TestCase):
    """CLI fixtures prove exit status and that observation precedes command release."""

    def run_monitor(self, final, command_status=0, initial=None):
        base = [proc(1, 0, 1), proc(20, 1, 20), proc(30, 1, 30)]
        first = snapshot([*base, proc(100, 30, 100)]) if initial is None else initial
        child = mock.Mock(pid=100)
        self.events = []

        def poll():
            self.events.append("poll")
            return command_status

        child.poll.side_effect = poll
        records = iter([snapshot(base), first, final, snapshot(base)])

        def acquire(_):
            self.events.append("snapshot")
            return next(records)

        child.wait.return_value = command_status
        with (
            mock.patch.object(
                monitor.sys,
                "argv",
                ["monitor", "--snapshot", "/unused", "--", "echo", "test"],
            ),
            mock.patch.object(
                monitor,
                "_snapshot",
                side_effect=acquire,
            ),
            mock.patch.object(
                monitor.subprocess, "Popen", return_value=child
            ) as launch,
            mock.patch.object(monitor.os, "write", return_value=1) as release,
            mock.patch.object(monitor.sys, "stdout", new_callable=io.StringIO),
        ):
            status = monitor.main()
        return status, launch, release

    def test_cli_violation_returns_one(self):
        sample = snapshot(
            [proc(1, 0, 1), proc(20, 1, 20), proc(100, 30, 100), proc(110, 100, 100)],
            windows=[window(110)],
        )
        status, launch, release = self.run_monitor(sample)
        self.assertEqual(status, 1)
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertEqual(len(launch.call_args.kwargs["pass_fds"]), 1)
        release.assert_called_once()

    def test_cli_unknown_returns_two(self):
        self.assertEqual(
            self.run_monitor(snapshot([proc(20, 1, 20)], windows=[window(999)]))[0], 2
        )

    def test_cli_quiet_preserves_failing_command_status(self):
        self.assertEqual(
            self.run_monitor(snapshot([proc(20, 1, 20)]), command_status=17)[0], 17
        )

    def test_cli_quiet_returns_zero(self):
        self.assertEqual(self.run_monitor(snapshot([proc(20, 1, 20)]))[0], 0)

    def test_live_descendant_after_command_exit_cannot_claim_quiet(self):
        sample = snapshot(
            [proc(1, 0, 1), proc(20, 1, 20), proc(100, 30, 100), proc(110, 100, 100)]
        )
        with mock.patch.object(monitor.time, "monotonic", side_effect=[1, 7]):
            self.assertEqual(self.run_monitor(sample)[0], 2)

    def test_live_unseen_orphan_after_exit_cannot_claim_quiet(self):
        sample = snapshot([proc(1, 0, 1), proc(20, 1, 20), proc(110, 1, 110)])
        with mock.patch.object(monitor.time, "monotonic", side_effect=[1, 7]):
            self.assertEqual(self.run_monitor(sample)[0], 2)

    def test_exit_is_observed_before_final_inventory_is_acquired(self):
        self.run_monitor(snapshot([proc(20, 1, 20)]))
        self.assertEqual(self.events[:4], ["snapshot", "snapshot", "poll", "snapshot"])

    def test_missing_startup_root_never_releases_command(self):
        status, _, release = self.run_monitor(
            snapshot([proc(20, 1, 20)]), initial=snapshot([proc(20, 1, 20)])
        )
        self.assertEqual(status, 2)
        release.assert_not_called()

    def test_unreadable_baseline_never_launches_command(self):
        with (
            mock.patch.object(
                monitor.sys, "argv", ["monitor", "--snapshot", "/unused"]
            ),
            mock.patch.object(monitor, "_snapshot", return_value={}),
            mock.patch.object(monitor.subprocess, "Popen") as launch,
            mock.patch.object(monitor.sys, "stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(monitor.main(), 2)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
