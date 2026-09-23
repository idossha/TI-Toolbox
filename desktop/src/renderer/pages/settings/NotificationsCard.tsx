import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { formatJobNotification, isNotificationSound, normalizeNotificationPrefs, SAMPLE_FINISHED_JOB, soundPlan, TI_SOUNDS, type NotificationPrefs, type NotifyResult } from "../../../shared/jobNotifications";
import { playNotificationSound } from "../../app/notificationSound";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Toggle";

const SOUND_OPTIONS = [{ value: "none", label: "None" }, { value: "system", label: "System default" }, ...TI_SOUNDS.map((s) => ({ value: s.id, label: s.label }))];

/**
 * Settings ▸ Project ▸ Notifications: the native banner main shows when a job finishes
 * (`main/jobsNotifier.ts`). Host-side preferences in the app's `settings.json`, applied at once
 * like the theme — no Save. Desktop only: a browser session has no bridge and no notifier.
 */
export function NotificationsCard() {
  const bridge = typeof window !== "undefined" ? window.tit : undefined;
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["host-notification-prefs"],
    queryFn: async () => normalizeNotificationPrefs((await bridge!.getSettings()).notifications),
    enabled: !!bridge,
  });
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<NotifyResult>();
  if (!bridge) return null;
  const prefs = query.data;

  function set(patch: Partial<NotificationPrefs>) {
    if (!prefs) return;
    const next = { ...prefs, ...patch };
    queryClient.setQueryData(["host-notification-prefs"], next);
    void bridge!.setSettings({ notifications: next });
  }

  async function sendTest() {
    if (!prefs) return;
    setTesting(true);
    const text = formatJobNotification(SAMPLE_FINISHED_JOB, prefs.detail);
    const plan = soundPlan(prefs.sound);
    try {
      const shown = bridge!.notify(text.title, text.body, plan.silent);
      playNotificationSound(plan.play);
      setTestResult(await shown);
    } catch (err) {
      setTestResult({ ok: false, reason: err instanceof Error ? err.message : String(err) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Notifications" />
      <CardBody>
        {prefs && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <Field label="Job notifications" help="A system notification when a job finishes. Click it to bring TI-Toolbox to the front.">
              <Switch checked={prefs.enabled} onCheckedChange={(enabled) => set({ enabled })} aria-label="Job notifications" />
            </Field>
            <Field label="Notify on">
              <SegmentedControl
                value={prefs.events}
                disabled={!prefs.enabled}
                onValueChange={(v) => set({ events: v as NotificationPrefs["events"] })}
                options={[
                  { value: "all", label: "All finished jobs" },
                  { value: "failures", label: "Failures only" },
                ]}
                aria-label="Notify on"
              />
            </Field>
            <Field label="Detail" help="Detailed adds the subject and the montage or target.">
              <SegmentedControl
                value={prefs.detail}
                disabled={!prefs.enabled}
                onValueChange={(v) => set({ detail: v as NotificationPrefs["detail"] })}
                options={[
                  { value: "minimal", label: "Minimal" },
                  { value: "detailed", label: "Detailed" },
                ]}
                aria-label="Notification detail"
              />
            </Field>
            <Field label="Sound" help="A TI-Toolbox sound (a failure plays it lower), the system's notification sound, or none.">
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <div style={{ width: 200, maxWidth: "100%" }}>
                  <Select value={prefs.sound} options={SOUND_OPTIONS} disabled={!prefs.enabled} onValueChange={(v) => isNotificationSound(v) && set({ sound: v })} aria-label="Notification sound" />
                </div>
                <Button size="sm" disabled={!soundPlan(prefs.sound).play} onClick={() => playNotificationSound(prefs.sound)} title="Play the selected TI-Toolbox sound">
                  Preview
                </Button>
              </div>
            </Field>
            <Field label="Test" help="Shows a sample banner with the detail and sound above.">
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "var(--space-1)" }}>
                <Button size="sm" loading={testing} onClick={() => void sendTest()}>
                  Send test notification
                </Button>
                {testResult && (
                  <div role="status" style={{ color: testResult.ok ? undefined : "var(--danger)" }}>
                    {testResult.ok ? "Shown." : `Not shown: ${testResult.reason}`}
                    {!testResult.ok && testResult.hint && <div>{testResult.hint}</div>}
                  </div>
                )}
              </div>
            </Field>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
