import { FlaskConical } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { AnalyzerPage } from "./AnalyzerPage";

const page: PageDef = {
  id: "analyzer",
  title: "Analyzer",
  purpose:
    "Extract field statistics from an ROI in one or more simulation results.",
  navGroup: "pipeline",
  order: 50,
  icon: FlaskConical,
  shortcut: "6",
  Component: AnalyzerPage,
  enabled: true,
};

export default page;
