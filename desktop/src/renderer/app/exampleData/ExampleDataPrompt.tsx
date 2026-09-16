/**
 * "Add example data?" — asked once per project, on the first arrival in it.
 *
 * **Mounted by `Shell`, not by Overview** (the defect this fixes): the chooser used to live inside
 * `pages/overview/index.tsx`, so it could only ever appear on the Overview route — and a project
 * opened onto any other page, or one whose Overview had not mounted yet, was never asked. It also
 * treated a failed `GET /api/project/status` as "do not ask", which is precisely the brand-new
 * project (no `project_status.json` on disk yet) that most needs asking. Here it is mounted beside
 * the router outlet and reads the status once per project, so the route it lands on cannot matter.
 *
 * The answer is recorded in the project's own `project_status.json` (`example_subject_prompted`),
 * so it follows the project, not the browser. Closing it any other way counts as "Not now".
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api, unwrap } from "../../api/client";
import { Button } from "../../ui/Button";
import { Callout } from "../../ui/Feedback";
import { Dialog } from "../../ui/Overlay";
import { ExampleDataList } from "./ExampleDataList";
import { useExampleData } from "./useExampleData";
import {
  EXAMPLE_DATA_PROMPT,
  answerExampleDataPrompt,
  shouldPromptForExampleData,
  statusForPrompt,
  type ProjectStatus,
  type PromptAnswer,
  type StatusRead,
} from "./prompt";

async function getProjectStatus(): Promise<StatusRead> {
  const result = await api.GET("/api/project/status");
  // A project with no project_status.json yet: not an error, just nothing recorded.
  if (result.response.status === 404) return { state: "missing" };
  return { state: "ready", status: unwrap(result, "/api/project/status") };
}

async function patchProjectStatus(patch: ProjectStatus): Promise<ProjectStatus> {
  return unwrap(await api.PATCH("/api/project/status", { body: patch }), "/api/project/status");
}

export function ExampleDataPrompt() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["project-status"],
    queryFn: getProjectStatus,
    // A project that answers this with a network failure is asked on the next visit, not nagged now.
    retry: false,
  });
  const { start, error } = useExampleData();
  const [answered, setAnswered] = useState(false);
  const [selected, setSelected] = useState<string[]>([EXAMPLE_DATA_PROMPT.defaultSample]);
  const open =
    !answered && shouldPromptForExampleData(statusForPrompt(statusQuery.data ?? { state: "loading" }));

  function answer(choice: PromptAnswer) {
    setAnswered(true);
    void answerExampleDataPrompt(choice, selected, {
      persist: patchProjectStatus,
      startDownload: start,
    })
      .catch(() => undefined)
      .finally(() => queryClient.invalidateQueries({ queryKey: ["project-status"] }));
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) answer("later");
      }}
      title={EXAMPLE_DATA_PROMPT.title}
      description={EXAMPLE_DATA_PROMPT.body}
      footer={
        <>
          <Button variant="secondary" data-testid="example-data-later" onClick={() => answer("later")}>
            {EXAMPLE_DATA_PROMPT.later}
          </Button>
          <Button
            variant="primary"
            disabled={selected.length === 0}
            data-testid="example-data-download"
            onClick={() => answer("download")}
          >
            <Download size={14} aria-hidden /> {EXAMPLE_DATA_PROMPT.download}
          </Button>
        </>
      }
    >
      <ExampleDataList mode="choose" selected={selected} onSelectedChange={setSelected} />
      {error && <Callout kind="danger">{error}</Callout>}
    </Dialog>
  );
}
