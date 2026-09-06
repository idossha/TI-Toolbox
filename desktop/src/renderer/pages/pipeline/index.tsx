import { Workflow } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { PipelinePage } from "./PipelinePage";

const page: PageDef = {
  id: "pipeline",
  title: "Pipeline",
  purpose: "Wire the steps you already run into one graph, run it as one job, export it as a notebook.",
  navGroup: "pipeline",
  order: 55,
  icon: Workflow,
  Component: PipelinePage,
  enabled: true,
};

export default page;
