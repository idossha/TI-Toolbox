import type { ReactNode } from "react";
import { MessageCircle, Bug, GitPullRequest } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { DefinitionList } from "../../ui/Feedback";
import { ExternalLinkButton } from "./links";

const REPO = "https://github.com/idossha/TI-Toolbox";

function GithubItem({ icon, title, description, href, label }: { icon: ReactNode; title: string; description: string; href: string; label: string }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-3)" }}>
      <div style={{ color: "var(--ink-3)", paddingTop: 2 }}>{icon}</div>
      <div style={{ flex: 1 }}>
        <p className="text-body" style={{ fontWeight: 500 }}>
          {title}
        </p>
        <p className="text-body" style={{ color: "var(--ink-2)", marginTop: 2 }}>
          {description}
        </p>
        <div style={{ marginTop: "var(--space-2)" }}>
          <ExternalLinkButton href={href}>{label}</ExternalLinkButton>
        </div>
      </div>
    </div>
  );
}

export function ContactTab() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <p className="text-body" style={{ color: "var(--ink-2)" }}>
        If you encounter issues, have questions, or would like to request new features, please feel free to reach out using one of the options below.
        Your feedback helps improve TI-Toolbox!
      </p>

      <Card>
        <CardHeader title="Main developer" />
        <CardBody>
          <DefinitionList
            entries={[
              ["Name", "Ido Haber"],
              ["Email", "ihaber@wisc.edu"],
              ["Affiliation", "University of Wisconsin — Center for Sleep and Consciousness"],
              ["GitHub", REPO],
            ]}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Contribute on GitHub" />
        <CardBody>
          <p className="text-body" style={{ color: "var(--ink-2)", marginBottom: "var(--space-3)" }}>
            GitHub is our preferred platform for bug reports, feature requests, and community discussions.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <GithubItem
              icon={<MessageCircle size={18} aria-hidden />}
              title="Join the discussion and share ideas"
              description="Have questions, ideas for improvements, or want to connect with other users? This is the best place to propose and discuss new features."
              href={`${REPO}/discussions`}
              label="Open discussions"
            />
            <GithubItem
              icon={<Bug size={18} aria-hidden />}
              title="Report a bug"
              description="Found a problem? Let us know so we can fix it."
              href={`${REPO}/issues`}
              label="Open issues"
            />
            <GithubItem
              icon={<GitPullRequest size={18} aria-hidden />}
              title="Submit a pull request"
              description="Already implemented a fix or feature? Submit a pull request to contribute your code."
              href={`${REPO}/pulls`}
              label="Open pull requests"
            />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Communication best practices" />
        <CardBody>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <div>
              <p className="text-body" style={{ fontWeight: 500 }}>
                When reporting bugs
              </p>
              <ul className="text-body" style={{ color: "var(--ink-2)", margin: "var(--space-1) 0 0", paddingLeft: 20 }}>
                <li>Be specific: a clear, concise title that summarizes the issue</li>
                <li>Provide context: what you were doing when the bug occurred</li>
                <li>Detail steps to reproduce, numbered</li>
                <li>Include system info: OS, TI-Toolbox version, relevant configuration</li>
                <li>Add screenshots when applicable</li>
              </ul>
            </div>
            <div>
              <p className="text-body" style={{ fontWeight: 500 }}>
                When requesting features
              </p>
              <ul className="text-body" style={{ color: "var(--ink-2)", margin: "var(--space-1) 0 0", paddingLeft: 20 }}>
                <li>Describe the problem you're facing first</li>
                <li>Propose a solution: how the feature might work</li>
                <li>Explain who would benefit and how</li>
                <li>Be patient: feature requests are considered alongside other priorities</li>
              </ul>
            </div>
            <div>
              <p className="text-body" style={{ fontWeight: 500 }}>
                When submitting pull requests
              </p>
              <ul className="text-body" style={{ color: "var(--ink-2)", margin: "var(--space-1) 0 0", paddingLeft: 20 }}>
                <li>Reference related issue(s)</li>
                <li>Keep changes focused: one concern per pull request</li>
                <li>Follow the existing code style and conventions</li>
                <li>Include tests for new functionality when possible</li>
                <li>Update documentation to reflect your changes</li>
              </ul>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
