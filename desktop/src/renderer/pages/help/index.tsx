import { useState } from "react";
import { useLocation } from "react-router-dom";
import { HelpCircle } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { PageLayout, Tabs } from "../../ui/Layout";
import { DocsTab } from "./DocsTab";
import { KeyboardTab } from "./KeyboardTab";
import { AboutTab } from "./AboutTab";
import { CiteTab } from "./CiteTab";
import { AcknowledgmentsTab } from "./AcknowledgmentsTab";
import { ContactTab } from "./ContactTab";
import { ExampleDataTab } from "./ExampleDataTab";

/**
 * Settings and Help are the two pages DESIGN.md §2.3 still allows a header — the orchestrator's
 * brief caps it at "a single 28px eyebrow" rather than the old 86px title-plus-purpose block
 * (`PageHeader`). Duplicated in `pages/settings/index.tsx` rather than shared: both pages own this
 * markup outright, and a `pages/_shared/` addition would cross into directories other lanes are
 * writing to concurrently for a dozen lines of JSX.
 */
function PageEyebrow({ title }: { title: string }) {
  return (
    <div className="page-header" style={{ height: "var(--row-h)", alignItems: "center" }}>
      <h1 className="text-eyebrow" style={{ margin: 0 }}>
        {title}
      </h1>
    </div>
  );
}

/**
 * `navigate("/help", { state: { tab: "example-data" } })` opens a named tab — how Overview's
 * toolbar button reaches the catalogue without a second copy of the list living on Overview.
 */
function HelpPage() {
  const location = useLocation();
  const requested = (location.state as { tab?: string } | null)?.tab;
  const [tab, setTab] = useState(requested ?? "docs");
  // Adjust state during render (React's own pattern) rather than in an effect: a second navigation
  // to /help naming a tab must select it, without a cascading render.
  const [lastRequested, setLastRequested] = useState(requested);
  if (requested !== lastRequested) {
    setLastRequested(requested);
    if (requested) setTab(requested);
  }
  return (
    <PageLayout header={<PageEyebrow title="Help" />}>
      <Tabs
        value={tab}
        onValueChange={setTab}
        items={[
          { id: "docs", label: "Docs", content: <DocsTab /> },
          { id: "example-data", label: "Example data", content: <ExampleDataTab /> },
          { id: "keyboard", label: "Keyboard", content: <KeyboardTab /> },
          { id: "about", label: "About", content: <AboutTab /> },
          { id: "cite", label: "Cite", content: <CiteTab /> },
          { id: "acknowledgments", label: "Acknowledgments", content: <AcknowledgmentsTab /> },
          { id: "contact", label: "Contact", content: <ContactTab /> },
        ]}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "help",
  title: "Help",
  purpose: "Documentation, citation, acknowledgments, and contact.",
  navGroup: "system",
  order: 95,
  icon: HelpCircle,
  Component: HelpPage,
  enabled: true,
};

export default page;
