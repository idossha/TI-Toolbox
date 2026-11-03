---
layout: wiki
title: Jobs
permalink: /wiki/jobs/
---

Everything in TI-Toolbox v3 is a **job**: pre-processing, a simulation, a search, an
analysis, a group statistic, a Blender export. A page never runs work in its own process,
and its process is owned by the server. The Jobs page centralizes status and cancellation; run pages also show their submitted jobs in a live Terminal pane.

<img src="{{ site.baseurl }}/assets/imgs/v3/jobs-page.png" alt="The Jobs page: 201 jobs of a real project, filterable by state, kind and subject, with elapsed time, CPU and memory per job" style="width: 100%; max-width: 1000px;">
<em>The Jobs page (⌘8). One row per job: state, kind, subjects, stage, elapsed time, CPU and memory.</em>

## Where jobs appear

- **The Jobs rail** at the bottom of every page — a one-line summary ("2 running"), expanded to a
  260 px panel with ⌘J. Its tabs are **Jobs** and **Host** — Host being the quick glance at the
  machine (CPU, memory, disk, toolbox processes) without leaving the page you are on; the
  full-height version is the **System** page, pinned at the bottom of the rail above Settings. The Jobs tab is the table beside the
  selected job's detail pane, split by a divider you can **drag**, **double-click to reset**, and
  which is remembered between sessions.
- **The Jobs page** (⌘8) — the full table with filters and a detail pane.
- **A run page's right pane** — the **Terminal** tab shows the console of the job that page just
  submitted, beside the **Scene** tab.

<img src="{{ site.baseurl }}/assets/imgs/v3/system-page.png" alt="The System page: CPU and memory history, per-core load, processes, memory, storage, Docker and host details" style="width: 100%; max-width: 1000px;">
<em>The System page: live CPU and memory, the processes in the container, disk use and the Docker engine.</em>

## How many CPUs jobs may use

All running jobs share one pool of CPUs: the **CPU limit** in **Settings ▸ Project ▸ Execution**,
a percent of the cores available to the container (default **70 %**, shown as e.g. "70 % · 7 of 10
cores"). It leaves headroom for your computer; raise it for faster searches. A job that would
exceed what is left waits ("waiting for budget") until others finish. A job that needs more memory
than the container has does not wait forever: it runs alone, once no other job is running, and may
still run out of memory. Its log says so before it starts ("needs about 16 GB of memory, more than
the 7.8 GB this container has: it will run alone, …"); give Docker more memory to avoid it. A change
applies to jobs started afterwards — running jobs keep what they were given. Scripts and notebooks
honour the same setting.

## Notifications when a job finishes

The desktop app shows a system notification when a job it watched run finishes or fails, for
example **Simulation finished** — _sub-101 · montage L_Insula_. Each subject of a multi-subject run
notifies on its own; they arrive one at a time, since a product runs one job at a time. Cancelled
jobs, and jobs that had already finished before the app opened, do not notify. Clicking a
notification brings TI-Toolbox to the front.

<img src="{{ site.baseurl }}/assets/imgs/v3/settings-project.png" alt="Settings, Project tab: project paths, theme, the CPU limit, existing-outputs policy, job notifications and telemetry" style="width: 100%; max-width: 1000px;">
<em>Settings ▸ Project holds the CPU limit (Execution) and the notification choices.</em>

**Settings ▸ Project ▸ Notifications** turns them on or off (default on) and chooses:

- **Notify on** — all finished jobs (default) or failures only;
- **Detail** — _Detailed_ (default) adds the subject and the montage or target, _Minimal_ shows
  only the title;
- **Sound** — one of TI-Toolbox's own short sounds (**Pulse**, the default, **Chime** or **Tick**;
  a failure plays the same sound lower), **System default** (the system's
  notification sound) or **None**. **Preview** beside it plays the selected TI-Toolbox sound. The
  sound plays whether or not TI-Toolbox is in front.

**Send test notification** shows a sample banner with the current detail and sound, and says
right under the button whether it was shown or why not.

On macOS the first notification asks for permission; if none appear, allow TI-Toolbox in
**System Settings ▸ Notifications**. A browser session has no notifications.

Developers running a checkout: see [Desktop Application]({{ site.baseurl }}/wiki/desktop-app/#development)
for notifications from an unsigned development Electron.

## Server restart

A server restart interrupts work and never resumes or resubmits it: queued and running jobs are
marked **failed** (a runner that had already exited keeps its real outcome) and surviving runner
processes and job containers are stopped, for up to 30 s before the server accepts requests.
Review the outputs and submit a new run if needed; reconnecting a client to a server that stayed
up changes nothing.

## Replacing existing outputs

Existing outputs require a fresh confirmation each time you run. **Replace and rerun**
is the one control for replacing outputs, and it is always available. **Skip** keeps
existing results and runs only missing work; **Cancel** submits nothing. API submissions
are checked too and still require explicit overwrite confirmation.

A pipeline's **Skip pipeline** option submits no jobs: its dependent steps cannot be
partially skipped safely. Replacement is unavailable when dependent outputs cannot yet
be previewed.
