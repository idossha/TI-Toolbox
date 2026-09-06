import { HelpCircle } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { PageLayout, Tabs } from "../../ui/Layout";
import { DocsTab } from "./DocsTab";
import { KeyboardTab } from "./KeyboardTab";
import { AboutTab } from "./AboutTab";
import { CiteTab } from "./CiteTab";
import { AcknowledgmentsTab } from "./AcknowledgmentsTab";
import { ContactTab } from "./ContactTab";

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

function HelpPage() {
  return (
    <PageLayout header={<PageEyebrow title="Help" />}>
      <Tabs
        items={[
          { id: "docs", label: "Docs", content: <DocsTab /> },
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
