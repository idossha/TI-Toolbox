// @vitest-environment jsdom
import React, { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { acquire, getState, release, useSystemStream } from "../../src/renderer/ws/useSystemStream";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
}

const rendered: string[] = [];
function Probe() {
  const { status } = useSystemStream();
  rendered.push(status);
  return <span>{status}</span>;
}

function mount(ui: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { root, container };
}

describe("useSystemStream", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    rendered.length = 0;
    vi.stubGlobal("WebSocket", FakeSocket);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("opens one socket per mount/unmount cycle and closes it on unmount", () => {
    expect(getState().status).toBe("idle");
    const { root, container } = mount(<Probe />);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(FakeSocket.instances[0]!.url).toMatch(/^ws:\/\/.+\/ws\/system$/);
    expect(container.textContent).toBe("connecting");

    act(() => FakeSocket.instances[0]!.onopen?.({}));
    expect(container.textContent).toBe("open");

    act(() => root.unmount());
    expect(FakeSocket.instances).toHaveLength(1);
    expect(FakeSocket.instances[0]!.closed).toBe(true);
    expect(getState().status).toBe("idle");

    const second = mount(<Probe />);
    expect(FakeSocket.instances).toHaveLength(2);
    expect(FakeSocket.instances[1]!.closed).toBe(false);
    act(() => second.root.unmount());
    expect(FakeSocket.instances[1]!.closed).toBe(true);
  });

  it("is shared between consumers and survives until the last one unmounts", () => {
    const a = mount(<Probe />);
    const b = mount(<Probe />);
    expect(FakeSocket.instances).toHaveLength(1);
    act(() => a.root.unmount());
    expect(FakeSocket.instances[0]!.closed).toBe(false);
    act(() => b.root.unmount());
    expect(FakeSocket.instances[0]!.closed).toBe(true);
  });

  it("is StrictMode-safe: the rehearsal socket is closed, exactly one stays live, none leak", () => {
    const { root } = mount(
      <StrictMode>
        <Probe />
      </StrictMode>,
    );
    const live = FakeSocket.instances.filter((s) => !s.closed);
    expect(live).toHaveLength(1);
    act(() => root.unmount());
    expect(FakeSocket.instances.every((s) => s.closed)).toBe(true);
    expect(getState().status).toBe("idle");
  });

  it("render has no side effects: acquire/release only happen in the effect", () => {
    // Direct ref-counting sanity, independent of React.
    acquire();
    acquire();
    expect(FakeSocket.instances).toHaveLength(1);
    release();
    expect(FakeSocket.instances[0]!.closed).toBe(false);
    release();
    expect(FakeSocket.instances[0]!.closed).toBe(true);
    release(); // over-release is harmless
    expect(getState().status).toBe("idle");
  });
});
