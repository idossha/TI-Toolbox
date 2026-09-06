import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getProject } from "../api/client";
import { activateSubjectPage, clearSubjectPages, readStoredSubject, useSubjectContext, writeStoredSubject } from "./subjectContext";

export const SUBJECT_PARAM = "subject";
export const SUBJECT_SYNC_STATE = "titSubjectSync";

/** Synchronize the active tab's subject with deep links and the project's last-used subject. */
export function useSubjectSpine(): void {
  const subjectId = useSubjectContext((state) => state.subjectId);
  const location = useLocation();
  const navigate = useNavigate();
  const project = useQuery({ queryKey: ["project"], queryFn: () => getProject() });
  const projectName = project.data?.name ?? null;
  const projectKey = project.data
    ? [project.data.name, project.data.host_path ?? "", project.data.container_path].join("\u0000")
    : null;
  const previousProject = useRef<string | null>(null);
  const adoptedLocation = useRef<string | null>(null);
  const publishedLocation = useRef<string | null>(null);
  const hydrated = useRef(false);
  const pageId = location.pathname.split("/")[1] ?? "";

  useLayoutEffect(() => {
    const switchedProject = projectKey !== null && previousProject.current !== null && projectKey !== previousProject.current;
    if (projectKey) previousProject.current = projectKey;
    if (switchedProject) {
      clearSubjectPages(projectName ? readStoredSubject(projectName) : null);
      hydrated.current = true;
      // The old route's ?subject belongs to the project we just disposed.
      activateSubjectPage(pageId);
      adoptedLocation.current = location.key;
      publishedLocation.current = null;
      return;
    }

    if (!hydrated.current && projectName) {
      hydrated.current = true;
      const stored = readStoredSubject(projectName);
      if (stored && !useSubjectContext.getState().subjectId && !new URLSearchParams(location.search).get(SUBJECT_PARAM)) {
        useSubjectContext.getState().setSubject(stored);
      }
    }

    if (adoptedLocation.current === location.key) return;
    const firstRoute = adoptedLocation.current === null;
    adoptedLocation.current = location.key;
    const signature = `${location.pathname}${location.search}`;
    if (publishedLocation.current === signature) {
      publishedLocation.current = null;
      return;
    }
    publishedLocation.current = null;
    const stateSubject = typeof location.state?.subject === "string" ? location.state.subject : null;
    const documentSubject = firstRoute && typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get(SUBJECT_PARAM)
      : null;
    activateSubjectPage(pageId, new URLSearchParams(location.search).get(SUBJECT_PARAM) ?? stateSubject ?? documentSubject);
  }, [location.key, location.pathname, location.search, location.state, pageId, projectKey, projectName]);

  useEffect(() => {
    // A layout-effect route/project change supersedes the render that queued this publication.
    const current = useSubjectContext.getState();
    if (current.subjectId !== subjectId || current.activePage !== pageId) return;
    if (projectName) writeStoredSubject(projectName, subjectId);
    const next = new URLSearchParams(location.search);
    const urlSubject = next.get(SUBJECT_PARAM);
    if (urlSubject === subjectId) return;
    if (subjectId) next.set(SUBJECT_PARAM, subjectId);
    else next.delete(SUBJECT_PARAM);
    const search = next.size ? `?${next.toString()}` : "";
    publishedLocation.current = `${location.pathname}${search}`;
    navigate({ pathname: location.pathname, search }, {
      replace: true,
      state: { ...location.state, [SUBJECT_SYNC_STATE]: true },
    });
  }, [subjectId, pageId, projectName, location.pathname, location.search, location.state, navigate]);
}
